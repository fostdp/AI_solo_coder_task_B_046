"""
作物模型独立Worker服务
========================

独立的作物模型模拟后台Worker，支持单站点、批量、集合三种模拟模式
使用线程池并发执行，按优先级调度任务，支持模型缓存和失败重试
纯Python实现，不依赖外部消息队列

使用方式:
    from workers.crop_model_worker import CropModelWorker

    worker = CropModelWorker(max_workers=4)
    worker.start()

    task_id = worker.submit_simulation(...)
    status = worker.get_task_status(task_id)

    worker.stop()
"""
import sys
import os
import uuid
import time
import logging
import threading
from typing import Dict, List, Optional, Any, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from modules.agricultural_impact.crop_model import AquaCropSimplifiedModel
    from modules.agricultural_impact.ensemble import EnsembleAquaCropSimulator
except ImportError:
    try:
        from services.agriculture_impact.aquacrop_model import AquaCropSimplifiedModel
        from services.agriculture_impact.ensemble_simulation import EnsembleAquaCropSimulator
    except ImportError:
        AquaCropSimplifiedModel = None
        EnsembleAquaCropSimulator = None

logger = logging.getLogger("crop_model_worker")


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """任务优先级枚举 - 数值越大优先级越高"""
    SINGLE_SIMULATION = 1
    BATCH_SIMULATION = 2
    ENSEMBLE_SIMULATION = 3


class TaskType(str, Enum):
    """任务类型枚举"""
    SINGLE = "single"
    BATCH = "batch"
    ENSEMBLE = "ensemble"


@dataclass
class SimulationTask:
    """模拟任务数据类"""
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    crop_type: str
    region: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    callback: Optional[Callable[[str, TaskStatus, Dict[str, Any]], None]] = None

    precip_data: Optional[List[float]] = None
    et0_data: Optional[List[float]] = None
    temp_data: Optional[List[float]] = None
    irrigation_enabled: bool = False
    irrigation_capability: float = 0.0
    irrigation_area: float = 100.0
    baseline_yield: Optional[float] = None
    params_override: Optional[Dict[str, Any]] = None

    sites_data: Optional[List[Dict[str, Any]]] = None
    batch_results: List[Dict[str, Any]] = field(default_factory=list)

    n_members: int = 50
    climate_data: Optional[Dict[str, List[float]]] = None
    params_dist: Optional[Dict[str, Tuple[float, float]]] = None
    ensemble_method: str = "lhs"


class CropModelWorker:
    """作物模型独立Worker服务

    支持单站点模拟、批量模拟、集合模拟三种任务类型
    使用优先级队列调度，线程池并发执行，模型实例缓存复用
    """

    def __init__(self, max_workers: int = 4, max_retries: int = 2):
        """初始化作物模型Worker

        Args:
            max_workers: 最大并发工作线程数，默认4
            max_retries: 失败最大重试次数，默认2次
        """
        self.max_workers = max_workers
        self.max_retries = max_retries

        self._task_queue: List[SimulationTask] = []
        self._task_queue_lock = threading.Lock()
        self._tasks: Dict[str, SimulationTask] = {}
        self._tasks_lock = threading.Lock()

        self._model_cache: Dict[str, AquaCropSimplifiedModel] = {}
        self._model_cache_lock = threading.Lock()

        self._executor: Optional[ThreadPoolExecutor] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._stop_event = threading.Event()

        self._active_futures: Dict[str, Future] = {}
        self._futures_lock = threading.Lock()

        logger.info(f"CropModelWorker 初始化完成，max_workers={max_workers}, max_retries={max_retries}")

    def start(self) -> None:
        """启动Worker服务

        初始化线程池并启动主循环线程
        """
        if self._running:
            logger.warning("Worker已在运行中")
            return

        self._running = True
        self._stop_event.clear()
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)

        self._worker_thread = threading.Thread(target=self._run_worker_loop, daemon=True)
        self._worker_thread.start()

        logger.info("CropModelWorker 启动成功")

    def stop(self, wait: bool = True) -> None:
        """优雅停止Worker服务

        Args:
            wait: 是否等待当前任务完成后再停止
        """
        if not self._running:
            logger.warning("Worker未在运行")
            return

        logger.info("CropModelWorker 正在停止...")
        self._stop_event.set()
        self._running = False

        if self._executor:
            if wait:
                self._executor.shutdown(wait=True)
            else:
                self._executor.shutdown(wait=False)

        if self._worker_thread and wait:
            self._worker_thread.join(timeout=30.0)

        logger.info("CropModelWorker 已停止")

    def submit_simulation(
        self,
        crop_type: str,
        region: str,
        precip_data: List[float],
        et0_data: List[float],
        temp_data: List[float],
        irrigation_enabled: bool = False,
        irrigation_capability: float = 0.0,
        irrigation_area: float = 100.0,
        baseline_yield: Optional[float] = None,
        params_override: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[str, TaskStatus, Dict[str, Any]], None]] = None,
    ) -> str:
        """提交单站点模拟任务

        Args:
            crop_type: 作物类型（粟、稻、麦、黍、豆）
            region: 区域名称
            precip_data: 逐日降雨量序列 (mm)
            et0_data: 逐日参考蒸散量序列 (mm)
            temp_data: 逐日气温序列 (°C)
            irrigation_enabled: 是否启用灌溉
            irrigation_capability: 日灌溉能力 (m³/天)
            irrigation_area: 灌溉面积 (亩)
            baseline_yield: 历史基准亩产 (kg/亩)
            params_override: 参数覆盖字典
            callback: 任务完成回调函数 (task_id, status, result)

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())

        task = SimulationTask(
            task_id=task_id,
            task_type=TaskType.SINGLE,
            priority=TaskPriority.SINGLE_SIMULATION,
            crop_type=crop_type,
            region=region,
            precip_data=precip_data,
            et0_data=et0_data,
            temp_data=temp_data,
            irrigation_enabled=irrigation_enabled,
            irrigation_capability=irrigation_capability,
            irrigation_area=irrigation_area,
            baseline_yield=baseline_yield,
            params_override=params_override,
            callback=callback,
            max_retries=self.max_retries,
        )

        self._enqueue_task(task)
        logger.info(f"单站点模拟任务已提交: task_id={task_id}, crop={crop_type}, region={region}")
        return task_id

    def submit_batch_simulation(
        self,
        sites_data: List[Dict[str, Any]],
        crop_type: str,
        region: str,
        callback: Optional[Callable[[str, TaskStatus, Dict[str, Any]], None]] = None,
    ) -> str:
        """提交批量模拟任务（优先级更高）

        Args:
            sites_data: 站点数据列表，每个站点包含precip_data、et0_data、temp_data等
            crop_type: 作物类型
            region: 区域名称
            callback: 任务完成回调函数

        Returns:
            批量任务ID
        """
        batch_id = str(uuid.uuid4())

        task = SimulationTask(
            task_id=batch_id,
            task_type=TaskType.BATCH,
            priority=TaskPriority.BATCH_SIMULATION,
            crop_type=crop_type,
            region=region,
            sites_data=sites_data,
            callback=callback,
            max_retries=self.max_retries,
        )

        self._enqueue_task(task)
        logger.info(f"批量模拟任务已提交: batch_id={batch_id}, sites={len(sites_data)}, crop={crop_type}")
        return batch_id

    def submit_ensemble_simulation(
        self,
        crop_type: str,
        region: str,
        n_members: int,
        climate_data: Dict[str, List[float]],
        params_dist: Optional[Dict[str, Tuple[float, float]]] = None,
        irrigation_capability: float = 0.0,
        irrigation_area: float = 100.0,
        baseline_yield: Optional[float] = None,
        method: str = "lhs",
        callback: Optional[Callable[[str, TaskStatus, Dict[str, Any]], None]] = None,
    ) -> str:
        """提交集合模拟任务（优先级最高）

        Args:
            crop_type: 作物类型
            region: 区域名称
            n_members: 集合成员数
            climate_data: 气候数据字典，包含precip_list、et0_list、temp_list
            params_dist: 参数分布字典 {param_name: (low, high)}
            irrigation_capability: 日灌溉能力 (m³/天)
            irrigation_area: 灌溉面积 (亩)
            baseline_yield: 基准产量 (kg/亩)
            method: 抽样方法 'lhs' (拉丁超立方) 或 'mc' (蒙特卡洛)
            callback: 任务完成回调函数

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())

        task = SimulationTask(
            task_id=task_id,
            task_type=TaskType.ENSEMBLE,
            priority=TaskPriority.ENSEMBLE_SIMULATION,
            crop_type=crop_type,
            region=region,
            n_members=n_members,
            climate_data=climate_data,
            params_dist=params_dist,
            irrigation_capability=irrigation_capability,
            irrigation_area=irrigation_area,
            baseline_yield=baseline_yield,
            ensemble_method=method,
            callback=callback,
            max_retries=self.max_retries,
        )

        self._enqueue_task(task)
        logger.info(f"集合模拟任务已提交: task_id={task_id}, n_members={n_members}, crop={crop_type}")
        return task_id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询单站点/集合模拟任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典，包含status、progress、result等信息
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)

        if not task:
            return {
                "task_id": task_id,
                "status": "not_found",
                "message": "任务不存在",
            }

        return self._build_task_status_dict(task)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务

        仅能取消 pending 状态的任务。正在处理的任务无法取消。

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status != TaskStatus.PENDING:
                return False
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()

        logger.info(f"任务已取消: task_id={task_id}")
        return True

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """查询批量模拟任务状态

        Args:
            batch_id: 批量任务ID

        Returns:
            批量任务状态字典
        """
        with self._tasks_lock:
            task = self._tasks.get(batch_id)

        if not task:
            return {
                "batch_id": batch_id,
                "status": "not_found",
                "message": "批量任务不存在",
            }

        status_dict = self._build_task_status_dict(task)
        status_dict["batch_id"] = batch_id

        if task.sites_data:
            status_dict["total_sites"] = len(task.sites_data)
            status_dict["completed_sites"] = len(task.batch_results)

        return status_dict

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务列表

        Returns:
            任务状态列表
        """
        with self._tasks_lock:
            tasks = list(self._tasks.values())

        return [self._build_task_status_dict(task) for task in tasks]

    def clear_completed_tasks(self) -> int:
        """清理已完成和失败的任务

        Returns:
            清理的任务数量
        """
        count = 0
        with self._tasks_lock:
            task_ids_to_remove = [
                task_id for task_id, task in self._tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            ]
            for task_id in task_ids_to_remove:
                del self._tasks[task_id]
                count += 1

        logger.info(f"清理了 {count} 个已完成/失败的任务")
        return count

    def get_model_cache_stats(self) -> Dict[str, Any]:
        """获取模型缓存统计信息

        Returns:
            缓存统计字典
        """
        with self._model_cache_lock:
            cached_keys = list(self._model_cache.keys())

        return {
            "cached_models_count": len(cached_keys),
            "cached_keys": cached_keys,
        }

    def clear_model_cache(self) -> None:
        """清空模型缓存"""
        with self._model_cache_lock:
            self._model_cache.clear()
        logger.info("模型缓存已清空")

    def _enqueue_task(self, task: SimulationTask) -> None:
        """将任务加入队列

        Args:
            task: 模拟任务对象
        """
        with self._task_queue_lock:
            self._task_queue.append(task)
            self._task_queue.sort(key=lambda t: t.priority.value, reverse=True)

        with self._tasks_lock:
            self._tasks[task.task_id] = task

    def _dequeue_task(self) -> Optional[SimulationTask]:
        """从队列中取出最高优先级的任务

        Returns:
            优先级最高的任务，队列为空则返回None
        """
        with self._task_queue_lock:
            if not self._task_queue:
                return None
            task = self._task_queue.pop(0)
            return task

    def _get_or_create_model(self, crop_type: str, region: str) -> Optional[AquaCropSimplifiedModel]:
        """获取或创建作物模型实例（带缓存）

        Args:
            crop_type: 作物类型
            region: 区域名称

        Returns:
            作物模型实例
        """
        cache_key = f"{crop_type}:{region}"

        with self._model_cache_lock:
            if cache_key in self._model_cache:
                return self._model_cache[cache_key]

        if AquaCropSimplifiedModel is None:
            logger.error("AquaCropSimplifiedModel 不可用")
            return None

        try:
            model = AquaCropSimplifiedModel(crop_type, region)
            with self._model_cache_lock:
                self._model_cache[cache_key] = model
            logger.debug(f"模型实例已创建并缓存: {cache_key}")
            return model
        except Exception as e:
            logger.error(f"创建模型实例失败: crop={crop_type}, region={region}, error={e}")
            return None

    def _build_task_status_dict(self, task: SimulationTask) -> Dict[str, Any]:
        """构建任务状态字典

        Args:
            task: 模拟任务对象

        Returns:
            任务状态字典
        """
        status_dict = {
            "task_id": task.task_id,
            "task_type": task.task_type.value,
            "status": task.status.value,
            "priority": task.priority.value,
            "crop_type": task.crop_type,
            "region": task.region,
            "progress": round(task.progress, 2),
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
        }

        if task.status == TaskStatus.COMPLETED and task.result:
            status_dict["result"] = task.result

        if task.status == TaskStatus.FAILED and task.error:
            status_dict["error"] = task.error

        return status_dict

    def _run_worker_loop(self) -> None:
        """Worker主循环

        持续从队列中取出任务并提交到线程池执行
        """
        logger.info("Worker主循环已启动")

        while not self._stop_event.is_set():
            try:
                task = self._dequeue_task()

                if task is None:
                    time.sleep(0.1)
                    continue

                if task.status != TaskStatus.PENDING:
                    continue

                with self._futures_lock:
                    active_count = sum(
                        1 for f in self._active_futures.values()
                        if not f.done()
                    )

                if active_count >= self.max_workers:
                    with self._task_queue_lock:
                        self._task_queue.insert(0, task)
                    time.sleep(0.1)
                    continue

                task.status = TaskStatus.PROCESSING
                task.started_at = time.time()
                task.progress = 0.0

                with self._tasks_lock:
                    self._tasks[task.task_id] = task

                future = self._executor.submit(self._execute_task, task)
                with self._futures_lock:
                    self._active_futures[task.task_id] = future

                future.add_done_callback(
                    lambda f, tid=task.task_id: self._on_task_complete(tid, f)
                )

            except Exception as e:
                logger.error(f"Worker主循环异常: {e}")
                time.sleep(0.5)

        logger.info("Worker主循环已退出")

    def _execute_task(self, task: SimulationTask) -> Dict[str, Any]:
        """执行任务（在线程池中运行）

        Args:
            task: 模拟任务对象

        Returns:
            执行结果字典
        """
        logger.debug(f"开始执行任务: {task.task_id}, type={task.task_type.value}")

        try:
            if task.task_type == TaskType.SINGLE:
                result = self._process_simulation_task(task)
            elif task.task_type == TaskType.BATCH:
                result = self._process_batch_task(task)
            elif task.task_type == TaskType.ENSEMBLE:
                result = self._process_ensemble_task(task)
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"任务执行失败: {task.task_id}, error={e}")
            return {"success": False, "error": str(e)}

    def _process_simulation_task(self, task: SimulationTask) -> Dict[str, Any]:
        """处理单站点模拟任务

        Args:
            task: 模拟任务对象

        Returns:
            模拟结果字典
        """
        logger.debug(f"处理单站点模拟: {task.task_id}")

        model = self._get_or_create_model(task.crop_type, task.region)
        if model is None:
            raise RuntimeError("无法获取作物模型实例")

        task.progress = 10.0

        if task.precip_data is None or task.et0_data is None or task.temp_data is None:
            raise ValueError("缺少必要的气候数据")

        result = model.run_full_simulation(
            precipitation_mm_per_day=task.precip_data,
            et0_mm_per_day=task.et0_data,
            temperatures_c=task.temp_data,
            irrigation_capability_m3_per_day=task.irrigation_capability if task.irrigation_enabled else 0.0,
            irrigation_area_mu=task.irrigation_area,
            historical_baseline_yield_kg_per_mu=task.baseline_yield,
        )

        task.progress = 100.0
        logger.debug(f"单站点模拟完成: {task.task_id}")
        return result

    def _process_batch_task(self, task: SimulationTask) -> Dict[str, Any]:
        """处理批量模拟任务

        Args:
            task: 批量模拟任务对象

        Returns:
            批量结果字典
        """
        logger.debug(f"处理批量模拟: {task.task_id}, sites={len(task.sites_data) if task.sites_data else 0}")

        if not task.sites_data:
            raise ValueError("缺少站点数据")

        model = self._get_or_create_model(task.crop_type, task.region)
        if model is None:
            raise RuntimeError("无法获取作物模型实例")

        total_sites = len(task.sites_data)
        results = []
        success_count = 0
        failed_count = 0

        for idx, site in enumerate(task.sites_data):
            try:
                precip_data = site.get("precip_data", [])
                et0_data = site.get("et0_data", [])
                temp_data = site.get("temp_data", [])
                irrigation_enabled = site.get("irrigation_enabled", False)
                irrigation_capability = site.get("irrigation_capability", 0.0)
                irrigation_area = site.get("irrigation_area", 100.0)
                baseline_yield = site.get("baseline_yield")

                site_result = model.run_full_simulation(
                    precipitation_mm_per_day=precip_data,
                    et0_mm_per_day=et0_data,
                    temperatures_c=temp_data,
                    irrigation_capability_m3_per_day=irrigation_capability if irrigation_enabled else 0.0,
                    irrigation_area_mu=irrigation_area,
                    historical_baseline_yield_kg_per_mu=baseline_yield,
                )

                results.append({
                    "site_index": idx,
                    "site_id": site.get("site_id"),
                    "success": True,
                    "result": site_result,
                })
                success_count += 1

            except Exception as e:
                results.append({
                    "site_index": idx,
                    "site_id": site.get("site_id"),
                    "success": False,
                    "error": str(e),
                })
                failed_count += 1

            task.progress = ((idx + 1) / total_sites) * 100.0
            task.batch_results = results.copy()

        task.progress = 100.0

        logger.debug(f"批量模拟完成: {task.task_id}, success={success_count}, failed={failed_count}")
        return {
            "total_sites": total_sites,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    def _process_ensemble_task(self, task: SimulationTask) -> Dict[str, Any]:
        """处理集合模拟任务

        Args:
            task: 集合模拟任务对象

        Returns:
            集合模拟结果字典
        """
        logger.debug(f"处理集合模拟: {task.task_id}, n_members={task.n_members}")

        if EnsembleAquaCropSimulator is None:
            raise RuntimeError("EnsembleAquaCropSimulator 不可用")

        if task.climate_data is None:
            raise ValueError("缺少气候数据")

        task.progress = 5.0

        simulator = EnsembleAquaCropSimulator(
            crop_type=task.crop_type,
            region=task.region,
            n_members=task.n_members,
        )

        task.progress = 10.0

        if task.params_dist:
            for param, (lo, hi) in task.params_dist.items():
                if param in simulator.param_ranges:
                    simulator.param_ranges[param] = (lo, hi)

        task.progress = 15.0

        precip_list = task.climate_data.get("precip_list", [])
        et0_list = task.climate_data.get("et0_list", [])
        temp_list = task.climate_data.get("temp_list", [])

        raw_results = simulator.run_ensemble_simulation(
            precip_list=precip_list,
            et0_list=et0_list,
            temp_list=temp_list,
            irrigation_capability=task.irrigation_capability,
            irrigation_area=task.irrigation_area,
            baseline_yield=task.baseline_yield,
            method=task.ensemble_method,
        )

        task.progress = 90.0

        post_processed = simulator.post_process_ensemble_results(
            raw_results,
            include_members=True,
        )

        task.progress = 100.0
        logger.debug(f"集合模拟完成: {task.task_id}")
        return post_processed

    def _on_task_complete(self, task_id: str, future: Future) -> None:
        """任务完成回调

        Args:
            task_id: 任务ID
            future: 线程池Future对象
        """
        try:
            result_dict = future.result()

            with self._tasks_lock:
                task = self._tasks.get(task_id)

            if not task:
                return

            if result_dict.get("success"):
                task.status = TaskStatus.COMPLETED
                task.result = result_dict.get("result")
                task.progress = 100.0
                task.completed_at = time.time()
                logger.info(f"任务完成: {task_id}, type={task.task_type.value}")
            else:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    task.error = result_dict.get("error")
                    logger.warning(f"任务失败，准备重试 ({task.retry_count}/{task.max_retries}): {task_id}")
                    self._requeue_task(task)
                    return
                else:
                    task.status = TaskStatus.FAILED
                    task.error = result_dict.get("error")
                    task.completed_at = time.time()
                    logger.error(f"任务最终失败: {task_id}, error={task.error}")

            with self._tasks_lock:
                self._tasks[task_id] = task

            if task.callback:
                try:
                    task.callback(task_id, task.status, task.result or {})
                except Exception as cb_err:
                    logger.error(f"任务回调执行失败: {task_id}, error={cb_err}")

        except Exception as e:
            logger.error(f"处理任务完成回调时出错: {task_id}, error={e}")

        finally:
            with self._futures_lock:
                self._active_futures.pop(task_id, None)

    def _requeue_task(self, task: SimulationTask) -> None:
        """将任务重新加入队列（用于重试）

        Args:
            task: 需要重试的任务
        """
        task.progress = 0.0
        task.started_at = None

        with self._task_queue_lock:
            self._task_queue.append(task)
            self._task_queue.sort(key=lambda t: t.priority.value, reverse=True)

        with self._tasks_lock:
            self._tasks[task.task_id] = task

    @property
    def is_running(self) -> bool:
        """检查Worker是否在运行

        Returns:
            True表示正在运行
        """
        return self._running

    @property
    def pending_count(self) -> int:
        """获取待处理任务数量

        Returns:
            待处理任务数
        """
        with self._task_queue_lock:
            return len(self._task_queue)

    @property
    def processing_count(self) -> int:
        """获取正在处理的任务数量

        Returns:
            处理中任务数
        """
        count = 0
        with self._tasks_lock:
            for task in self._tasks.values():
                if task.status == TaskStatus.PROCESSING:
                    count += 1
        return count

    @property
    def total_tasks_count(self) -> int:
        """获取总任务数量

        Returns:
            总任务数
        """
        with self._tasks_lock:
            return len(self._tasks)


_default_worker: Optional[CropModelWorker] = None


def get_default_worker(max_workers: int = 4) -> CropModelWorker:
    """获取默认的全局Worker实例

    Args:
        max_workers: 最大并发数（仅在首次创建时生效）

    Returns:
        全局Worker实例
    """
    global _default_worker
    if _default_worker is None:
        _default_worker = CropModelWorker(max_workers=max_workers)
        _default_worker.start()
    return _default_worker


def shutdown_default_worker() -> None:
    """关闭默认的全局Worker实例"""
    global _default_worker
    if _default_worker is not None:
        _default_worker.stop()
        _default_worker = None
