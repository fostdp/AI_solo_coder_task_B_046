"""
三维重建后台Worker
==================

独立的3D重建后台Worker进程，负责：
- 接收重建任务并加入优先队列
- 基于线程池的并发处理
- 任务状态管理与进度追踪
- 失败重试与指数退避
- 任务完成回调通知

设计特点：
- 纯Python实现，不依赖外部消息队列
- 内存级任务状态存储（可扩展到Redis）
- 支持优先级调度（1-5，5最高）
- 线程池模式，可配置并发数
- 支持任务取消、重试、进度回调
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uuid
import time
import random
import logging
import threading
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from queue import PriorityQueue, Empty
from concurrent.futures import ThreadPoolExecutor, Future

from modules.digital_display import DigitalReconstructionPipeline

logger = logging.getLogger("workers.reconstruction_worker")


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ReconstructionTask:
    """
    重建任务数据类

    Attributes:
        task_id: 任务唯一标识
        site_id: 遗址ID
        photo_urls: 照片URL列表
        method: 重建方法
        priority: 优先级（1-5，5最高）
        callback_url: 回调URL（可选）
        status: 任务状态
        progress_pct: 进度百分比（0-100）
        current_stage: 当前阶段
        retry_count: 已重试次数
        max_retries: 最大重试次数
        result: 重建结果
        error: 错误信息
        created_at: 创建时间戳
        started_at: 开始处理时间戳
        completed_at: 完成时间戳
        site_metadata: 遗址元数据
        generate_vr: 是否生成VR体验
    """
    task_id: str
    site_id: int
    photo_urls: List[str]
    method: str = "摄影测量"
    priority: int = 3
    callback_url: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    progress_pct: int = 0
    current_stage: str = "等待处理"
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    site_metadata: Optional[Dict[str, Any]] = None
    generate_vr: bool = True

    def __lt__(self, other: 'ReconstructionTask') -> bool:
        """
        优先级比较（PriorityQueue使用）
        优先级数字越大，优先级越高
        """
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.created_at < other.created_at

    def __le__(self, other: 'ReconstructionTask') -> bool:
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other: 'ReconstructionTask') -> bool:
        return not self.__le__(other)

    def __ge__(self, other: 'ReconstructionTask') -> bool:
        return not self.__lt__(other)


class ReconstructionWorker:
    """
    三维重建后台Worker

    基于优先队列和线程池的重建任务调度器，支持：
    - 多任务并发处理
    - 优先级调度
    - 失败重试（指数退避）
    - 任务状态查询
    - 进度回调
    - 优雅停止

    Attributes:
        max_workers: 最大并发数
        pipeline: 重建管线实例
        task_queue: 优先任务队列
        task_store: 任务状态存储（内存字典）
        _running: Worker运行状态标志
        _executor: 线程池执行器
        _lock: 线程锁
        _worker_threads: Worker循环线程列表
    """

    def __init__(self, max_workers: int = 2):
        """
        初始化重建Worker

        Args:
            max_workers: 最大并发处理数，默认2
        """
        self.max_workers = max_workers
        self.pipeline = DigitalReconstructionPipeline()
        self.task_queue: PriorityQueue = PriorityQueue()
        self.task_store: Dict[str, ReconstructionTask] = {}
        self._running = False
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._worker_threads: List[threading.Thread] = []
        self._futures: Dict[str, Future] = {}

        logger.info(f"ReconstructionWorker 初始化完成，最大并发数: {max_workers}")

    def start(self) -> None:
        """
        启动Worker

        创建线程池和Worker循环线程，开始处理任务队列。
        如果Worker已在运行，则不执行任何操作。
        """
        if self._running:
            logger.warning("ReconstructionWorker 已在运行中")
            return

        self._running = True
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="recon_worker"
        )

        for i in range(self.max_workers):
            t = threading.Thread(
                target=self._run_worker_loop,
                name=f"recon_dispatcher_{i}",
                daemon=True
            )
            t.start()
            self._worker_threads.append(t)

        logger.info(
            f"ReconstructionWorker 启动成功，"
            f"线程池大小: {self.max_workers}, "
            f"调度线程数: {len(self._worker_threads)}"
        )

    def stop(self, wait: bool = True) -> None:
        """
        优雅停止Worker

        停止接收新任务，等待正在处理的任务完成后退出。

        Args:
            wait: 是否等待所有任务完成，默认True
        """
        if not self._running:
            logger.warning("ReconstructionWorker 未在运行")
            return

        logger.info("ReconstructionWorker 正在停止...")
        self._running = False

        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None

        for t in self._worker_threads:
            t.join(timeout=5)
        self._worker_threads.clear()

        logger.info("ReconstructionWorker 已停止")

    def submit_task(
        self,
        site_id: int,
        photo_urls: List[str],
        method: str = "摄影测量",
        priority: int = 3,
        callback_url: Optional[str] = None,
        site_metadata: Optional[Dict[str, Any]] = None,
        generate_vr: bool = True,
        max_retries: int = 3,
    ) -> str:
        """
        提交重建任务

        Args:
            site_id: 遗址ID
            photo_urls: 照片URL列表
            method: 重建方法，默认"摄影测量"
            priority: 优先级（1-5，5最高），默认3
            callback_url: 任务完成回调URL（可选）
            site_metadata: 遗址元数据（可选）
            generate_vr: 是否生成VR体验，默认True
            max_retries: 最大重试次数，默认3

        Returns:
            task_id: 任务唯一标识

        Raises:
            ValueError: 参数无效时抛出
        """
        if not photo_urls or not isinstance(photo_urls, list):
            raise ValueError("photo_urls 不能为空且必须是列表")

        if not isinstance(priority, int) or priority < 1 or priority > 5:
            raise ValueError("priority 必须是 1-5 之间的整数")

        if max_retries < 0 or max_retries > 10:
            raise ValueError("max_retries 必须在 0-10 之间")

        task_id = str(uuid.uuid4())

        task = ReconstructionTask(
            task_id=task_id,
            site_id=site_id,
            photo_urls=photo_urls,
            method=method,
            priority=priority,
            callback_url=callback_url,
            site_metadata=site_metadata,
            generate_vr=generate_vr,
            max_retries=max_retries,
        )

        with self._lock:
            self.task_store[task_id] = task

        self.task_queue.put(task)
        logger.info(
            f"重建任务已提交: task_id={task_id}, "
            f"site_id={site_id}, "
            f"priority={priority}, "
            f"photos={len(photo_urls)}"
        )

        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        查询任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典，任务不存在时返回None
        """
        with self._lock:
            task = self.task_store.get(task_id)

        if task is None:
            return None

        return {
            "task_id": task.task_id,
            "site_id": task.site_id,
            "status": task.status.value,
            "priority": task.priority,
            "progress_pct": task.progress_pct,
            "current_stage": task.current_stage,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "method": task.method,
            "photo_count": len(task.photo_urls),
            "generate_vr": task.generate_vr,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
            "result": self._sanitize_result(task.result),
        }

    def _sanitize_result(self, result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        精简结果字典，避免返回过大数据

        Args:
            result: 原始重建结果

        Returns:
            精简后的结果字典
        """
        if result is None:
            return None

        sanitized = {}
        for key in [
            "status",
            "gltf_model_url",
            "glb_model_url",
            "vr_experience_url",
            "point_cloud_count",
            "mesh_face_count",
            "texture_resolution",
        ]:
            if key in result:
                sanitized[key] = result[key]

        if "reconstruction_log" in result:
            log = result["reconstruction_log"]
            sanitized["total_duration_sec"] = log.get("total_duration_sec")
            sanitized["pipeline_completed"] = log.get("pipeline_completed")
            sanitized["pipeline_failed"] = log.get("pipeline_failed")

        return sanitized

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        仅能取消 pending 状态的任务。正在处理的任务无法取消。

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task is None:
                return False
            if task.status != TaskStatus.PENDING:
                return False
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()

        logger.info(f"任务已取消: task_id={task_id}")
        return True

    def retry_task(self, task_id: str) -> Optional[str]:
        """
        重试失败的任务

        Args:
            task_id: 任务ID

        Returns:
            新的任务ID，任务不存在或状态不支持重试时返回None
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task is None:
                return None
            if task.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                return None

        new_task_id = self.submit_task(
            site_id=task.site_id,
            photo_urls=task.photo_urls.copy(),
            method=task.method,
            priority=task.priority,
            callback_url=task.callback_url,
            site_metadata=task.site_metadata,
            generate_vr=task.generate_vr,
            max_retries=task.max_retries,
        )

        logger.info(f"任务重试: 原task_id={task_id}, 新task_id={new_task_id}")
        return new_task_id

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        获取队列统计信息

        Returns:
            队列统计字典
        """
        with self._lock:
            total = len(self.task_store)
            pending = sum(
                1 for t in self.task_store.values()
                if t.status == TaskStatus.PENDING
            )
            processing = sum(
                1 for t in self.task_store.values()
                if t.status == TaskStatus.PROCESSING
            )
            completed = sum(
                1 for t in self.task_store.values()
                if t.status == TaskStatus.COMPLETED
            )
            failed = sum(
                1 for t in self.task_store.values()
                if t.status == TaskStatus.FAILED
            )
            cancelled = sum(
                1 for t in self.task_store.values()
                if t.status == TaskStatus.CANCELLED
            )

        return {
            "total_tasks": total,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "queue_size": self.task_queue.qsize(),
            "max_workers": self.max_workers,
            "is_running": self._running,
        }

    def _run_worker_loop(self) -> None:
        """
        Worker主循环

        持续从优先队列取任务，提交到线程池处理。
        当 _running 标志为False且队列为空时退出。
        """
        logger.debug(f"Worker循环线程启动: {threading.current_thread().name}")

        while self._running or not self.task_queue.empty():
            try:
                task = self.task_queue.get(timeout=1.0)
            except Empty:
                continue

            if not self._running:
                self.task_queue.put(task)
                break

            with self._lock:
                stored_task = self.task_store.get(task.task_id)
                if stored_task is None or stored_task.status == TaskStatus.CANCELLED:
                    self.task_queue.task_done()
                    continue

                if stored_task.status != TaskStatus.PENDING:
                    self.task_queue.task_done()
                    continue

                stored_task.status = TaskStatus.PROCESSING
                stored_task.started_at = time.time()
                stored_task.current_stage = "初始化"

            if self._executor:
                future = self._executor.submit(self._process_task, task.task_id)
                with self._lock:
                    self._futures[task.task_id] = future
                future.add_done_callback(
                    lambda f, tid=task.task_id: self._on_task_done(f, tid)
                )

            self.task_queue.task_done()

        logger.debug(f"Worker循环线程退出: {threading.current_thread().name}")

    def _process_task(self, task_id: str) -> None:
        """
        处理单个重建任务

        调用重建管线执行完整重建流程，更新任务状态，
        失败时根据重试策略决定是否重新入队。

        Args:
            task_id: 任务ID
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task is None:
                return

        logger.info(f"开始处理重建任务: task_id={task_id}, site_id={task.site_id}")

        try:
            self._update_progress(task_id, 5, "初始化")

            result = self.pipeline.run_full_pipeline(
                photo_urls=task.photo_urls,
                method=task.method,
                generate_vr=task.generate_vr,
                site_metadata=task.site_metadata,
            )

            if result.get("status") == "completed":
                self._update_progress(task_id, 100, "全部完成")
                self._complete_task(task_id, result)
                logger.info(f"重建任务完成: task_id={task_id}")
            else:
                error = result.get("error", "未知错误")
                self._fail_task(task_id, error, result)
                logger.warning(f"重建任务失败: task_id={task_id}, error={error}")

        except Exception as e:
            logger.error(f"重建任务异常: task_id={task_id}, error={e}", exc_info=True)
            self._handle_task_failure(task_id, str(e))

    def _update_progress(self, task_id: str, progress: int, stage: str) -> None:
        """
        更新任务进度

        Args:
            task_id: 任务ID
            progress: 进度百分比（0-100）
            stage: 当前阶段名称
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task:
                task.progress_pct = max(0, min(100, progress))
                task.current_stage = stage

    def _complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """
        标记任务完成

        Args:
            task_id: 任务ID
            result: 重建结果
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
                task.progress_pct = 100
                task.current_stage = "全部完成"

        self._trigger_callback(task_id, "completed", result)

    def _fail_task(self, task_id: str, error: str, result: Optional[Dict[str, Any]] = None) -> None:
        """
        标记任务失败（不自动重试）

        Args:
            task_id: 任务ID
            error: 错误信息
            result: 部分结果（可选）
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = error
                task.result = result
                task.completed_at = time.time()

        self._trigger_callback(task_id, "failed", {"error": error})

    def _handle_task_failure(self, task_id: str, error: str) -> None:
        """
        处理任务失败，根据重试策略决定是否重试

        Args:
            task_id: 任务ID
            error: 错误信息
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task is None:
                return

            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                task.error = error
                task.progress_pct = 0
                task.current_stage = "等待重试"
                task.started_at = None

                retry_delay = self._get_retry_delay(task.retry_count)
                task._next_retry_at = time.time() + retry_delay

                logger.warning(
                    f"任务失败，准备第{task.retry_count}次重试: "
                    f"task_id={task_id}, "
                    f"延迟={retry_delay:.1f}秒, "
                    f"error={error}"
                )

                retry_thread = threading.Timer(
                    retry_delay,
                    self._requeue_task,
                    args=[task_id]
                )
                retry_thread.daemon = True
                retry_thread.start()
                return

        self._fail_task(task_id, error)

    def _get_retry_delay(self, retry_count: int) -> float:
        """
        计算指数退避重试延迟

        Args:
            retry_count: 当前重试次数（第几次重试）

        Returns:
            延迟秒数
        """
        base_delay = 2.0
        max_delay = 60.0
        delay = base_delay * (2 ** (retry_count - 1))
        jitter = delay * 0.1 * (random.random() - 0.5)
        return min(delay + jitter, max_delay)

    def _requeue_task(self, task_id: str) -> None:
        """
        将任务重新加入队列

        Args:
            task_id: 任务ID
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task is None or task.status != TaskStatus.PENDING:
                return

        self.task_queue.put(task)
        logger.info(f"任务重新入队: task_id={task_id}, 重试次数={task.retry_count}")

    def _trigger_callback(self, task_id: str, event: str, data: Dict[str, Any]) -> None:
        """
        触发任务回调

        当前为模拟实现，仅记录日志。
        实际使用时可扩展为HTTP回调、消息队列通知等。

        Args:
            task_id: 任务ID
            event: 事件类型（completed/failed）
            data: 回调数据
        """
        with self._lock:
            task = self.task_store.get(task_id)
            if task is None:
                return
            callback_url = task.callback_url

        if callback_url:
            logger.info(
                f"触发回调: task_id={task_id}, "
                f"event={event}, "
                f"callback_url={callback_url}"
            )
            try:
                self._do_http_callback(callback_url, task_id, event, data)
            except Exception as e:
                logger.error(f"回调请求失败: task_id={task_id}, error={e}")
        else:
            logger.debug(f"无回调URL，跳过回调: task_id={task_id}, event={event}")

    def _do_http_callback(
        self,
        url: str,
        task_id: str,
        event: str,
        data: Dict[str, Any]
    ) -> None:
        """
        执行HTTP回调请求（模拟实现）

        实际项目中可使用 requests 或 httpx 库实现。

        Args:
            url: 回调URL
            task_id: 任务ID
            event: 事件类型
            data: 回调数据
        """
        logger.debug(
            f"[模拟HTTP回调] POST {url} "
            f"body={{'task_id': '{task_id}', 'event': '{event}'}}"
        )

    def _on_task_done(self, future: Future, task_id: str) -> None:
        """
        任务完成回调（线程池Future回调）

        Args:
            future: 线程池Future对象
            task_id: 任务ID
        """
        with self._lock:
            if task_id in self._futures:
                del self._futures[task_id]

        try:
            future.result()
        except Exception as e:
            logger.error(f"任务执行异常: task_id={task_id}, error={e}", exc_info=True)
            self._handle_task_failure(task_id, str(e))

    def __enter__(self) -> 'ReconstructionWorker':
        """支持 with 语句"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """支持 with 语句"""
        self.stop(wait=True)


_default_worker: Optional[ReconstructionWorker] = None
_default_worker_lock = threading.Lock()


def get_default_worker(max_workers: int = 2) -> ReconstructionWorker:
    """
    获取全局默认Worker实例（单例模式）

    Args:
        max_workers: 最大并发数（仅首次创建时有效）

    Returns:
        全局默认Worker实例
    """
    global _default_worker
    if _default_worker is None:
        with _default_worker_lock:
            if _default_worker is None:
                _default_worker = ReconstructionWorker(max_workers=max_workers)
                _default_worker.start()
                logger.info("全局默认ReconstructionWorker已创建并启动")
    return _default_worker
