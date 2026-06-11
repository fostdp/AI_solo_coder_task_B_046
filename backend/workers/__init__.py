"""
后台Worker服务模块 (workers)
============================

包含两个独立的后台Worker服务：
1. CropModelWorker - 作物模型模拟后台Worker
   支持单站点、批量、集合三种模拟模式
   使用线程池并发执行，按优先级调度任务

2. ReconstructionWorker - 三维重建后台Worker
   支持优先队列、指数退避重试、任务取消、回调机制

纯Python实现，不依赖外部消息队列。

使用方式:
    from workers import CropModelWorker, ReconstructionWorker, get_default_worker

    worker = CropModelWorker(max_workers=4)
    worker.start()
    task_id = worker.submit_simulation(...)
    worker.stop()
"""

from .crop_model_worker import (
    CropModelWorker,
    TaskStatus,
    TaskPriority,
    TaskType,
    SimulationTask,
    get_default_worker,
    shutdown_default_worker,
)

from .reconstruction_worker import (
    ReconstructionWorker,
    TaskStatus as ReconTaskStatus,
    ReconstructionTask,
)

__all__ = [
    # 作物模型Worker
    'CropModelWorker',
    'TaskStatus',
    'TaskPriority',
    'TaskType',
    'SimulationTask',
    'get_default_worker',
    'shutdown_default_worker',
    # 重建Worker
    'ReconstructionWorker',
    'ReconTaskStatus',
    'ReconstructionTask',
]

__version__ = '1.0.0'
__author__ = 'Workers Module'
__description__ = '后台Worker服务：作物模型模拟 + 三维重建'
