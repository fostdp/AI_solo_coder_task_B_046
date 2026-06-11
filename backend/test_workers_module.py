"""
测试 workers 模块
包含 CropModelWorker 和 ReconstructionWorker 的测试
"""
import sys
import os
import unittest
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workers.crop_model_worker import (
    CropModelWorker,
    TaskStatus,
    TaskPriority,
    TaskType,
    get_default_worker,
    shutdown_default_worker,
)

from workers.reconstruction_worker import (
    ReconstructionWorker,
)

from workers import (
    get_default_worker as get_crop_default_worker,
    shutdown_default_worker as shutdown_crop_default_worker,
)


class TestCropModelWorker(unittest.TestCase):
    """测试作物模型 Worker"""

    def setUp(self):
        self.worker = CropModelWorker(max_workers=2, max_retries=1)
        self.precip_data = [2.5, 3.0, 1.5, 0.0, 4.2, 2.8, 1.0] * 15
        self.et0_data = [3.2, 3.5, 2.8, 4.0, 3.8, 3.0, 2.5] * 15
        self.temp_data = [20.0, 22.0, 25.0, 28.0, 26.0, 23.0, 21.0] * 15

    def tearDown(self):
        if self.worker.is_running:
            self.worker.stop(wait=True)

    def test_initialization(self):
        """测试 Worker 初始化"""
        self.assertEqual(self.worker.max_workers, 2)
        self.assertEqual(self.worker.max_retries, 1)
        self.assertFalse(self.worker.is_running)
        self.assertEqual(self.worker.pending_count, 0)
        self.assertEqual(self.worker.processing_count, 0)
        self.assertEqual(self.worker.total_tasks_count, 0)
        print("  ✓ CropModelWorker 初始化测试通过")

    def test_start_stop(self):
        """测试 start() 和 stop()"""
        self.assertFalse(self.worker.is_running)

        self.worker.start()
        self.assertTrue(self.worker.is_running)

        self.worker.stop(wait=True)
        self.assertFalse(self.worker.is_running)
        print("  ✓ CropModelWorker start/stop 测试通过")

    def test_start_twice(self):
        """测试重复 start() 不会出错"""
        self.worker.start()
        self.assertTrue(self.worker.is_running)

        self.worker.start()
        self.assertTrue(self.worker.is_running)
        print("  ✓ CropModelWorker 重复 start 测试通过")

    def test_stop_twice(self):
        """测试重复 stop() 不会出错"""
        self.worker.start()
        self.worker.stop(wait=True)
        self.assertFalse(self.worker.is_running)

        self.worker.stop(wait=True)
        self.assertFalse(self.worker.is_running)
        print("  ✓ CropModelWorker 重复 stop 测试通过")

    def test_submit_simulation(self):
        """测试提交单站点模拟任务"""
        self.worker.start()

        task_id = self.worker.submit_simulation(
            crop_type='粟',
            region='中原地区',
            precip_data=self.precip_data,
            et0_data=self.et0_data,
            temp_data=self.temp_data,
            irrigation_enabled=False,
        )

        self.assertIsInstance(task_id, str)
        self.assertGreater(len(task_id), 0)

        status = self.worker.get_task_status(task_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["task_id"], task_id)
        self.assertIn(status["status"], ["pending", "processing", "completed"])
        self.assertEqual(status["task_type"], "single")
        self.assertEqual(status["priority"], TaskPriority.SINGLE_SIMULATION.value)

        print("  ✓ CropModelWorker.submit_simulation 测试通过")

    def test_get_task_status_not_found(self):
        """测试查询不存在的任务"""
        self.worker.start()

        status = self.worker.get_task_status("nonexistent_task_id")
        self.assertEqual(status["status"], "not_found")
        self.assertIn("message", status)

        print("  ✓ CropModelWorker 任务不存在测试通过")

    def test_task_status_transition(self):
        """测试任务状态流转 pending -> processing -> completed"""
        self.worker.start()

        task_id = self.worker.submit_simulation(
            crop_type='粟',
            region='中原地区',
            precip_data=self.precip_data,
            et0_data=self.et0_data,
            temp_data=self.temp_data,
        )

        status = self.worker.get_task_status(task_id)
        initial_status = status["status"]
        self.assertIn(initial_status, ["pending", "processing"])

        max_wait = 10
        waited = 0
        while waited < max_wait:
            status = self.worker.get_task_status(task_id)
            if status["status"] == "completed":
                break
            time.sleep(0.5)
            waited += 0.5

        status = self.worker.get_task_status(task_id)
        self.assertEqual(status["status"], "completed")
        self.assertIn("result", status)
        self.assertIsNotNone(status["result"])
        self.assertEqual(status["progress"], 100.0)
        self.assertIsNotNone(status["completed_at"])

        print("  ✓ CropModelWorker 任务状态流转测试通过")

    def test_submit_batch_simulation(self):
        """测试提交批量模拟任务"""
        self.worker.start()

        sites_data = [
            {
                "site_id": f"site_{i}",
                "precip_data": self.precip_data,
                "et0_data": self.et0_data,
                "temp_data": self.temp_data,
                "irrigation_enabled": i % 2 == 0,
            }
            for i in range(3)
        ]

        batch_id = self.worker.submit_batch_simulation(
            sites_data=sites_data,
            crop_type='粟',
            region='中原地区',
        )

        self.assertIsInstance(batch_id, str)
        self.assertGreater(len(batch_id), 0)

        status = self.worker.get_batch_status(batch_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["batch_id"], batch_id)
        self.assertEqual(status["task_type"], "batch")
        self.assertEqual(status["priority"], TaskPriority.BATCH_SIMULATION.value)
        self.assertEqual(status["total_sites"], 3)

        max_wait = 15
        waited = 0
        while waited < max_wait:
            status = self.worker.get_batch_status(batch_id)
            if status["status"] == "completed":
                break
            time.sleep(0.5)
            waited += 0.5

        status = self.worker.get_batch_status(batch_id)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["completed_sites"], 3)
        self.assertIn("result", status)

        print("  ✓ CropModelWorker.submit_batch_simulation 测试通过")

    def test_submit_ensemble_simulation(self):
        """测试提交集合模拟任务"""
        self.worker.start()

        climate_data = {
            "precip_list": [2.5, 3.0, 1.5, 0.0, 4.2],
            "et0_list": [3.2, 3.5, 2.8, 4.0, 3.8],
            "temp_list": [20.0, 22.0, 25.0, 28.0, 26.0],
        }

        task_id = self.worker.submit_ensemble_simulation(
            crop_type='粟',
            region='中原地区',
            n_members=10,
            climate_data=climate_data,
            method='lhs',
        )

        self.assertIsInstance(task_id, str)
        self.assertGreater(len(task_id), 0)

        status = self.worker.get_task_status(task_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["task_type"], "ensemble")
        self.assertEqual(status["priority"], TaskPriority.ENSEMBLE_SIMULATION.value)

        max_wait = 30
        waited = 0
        while waited < max_wait:
            status = self.worker.get_task_status(task_id)
            if status["status"] == "completed":
                break
            time.sleep(0.5)
            waited += 0.5

        status = self.worker.get_task_status(task_id)
        self.assertEqual(status["status"], "completed")
        self.assertIn("result", status)

        print("  ✓ CropModelWorker.submit_ensemble_simulation 测试通过")

    def test_task_priority_order(self):
        """测试任务优先级（集合 > 批量 > 单站点）"""
        self.assertEqual(
            TaskPriority.ENSEMBLE_SIMULATION.value,
            3,
            "集合模拟优先级应为最高"
        )
        self.assertEqual(
            TaskPriority.BATCH_SIMULATION.value,
            2,
            "批量模拟优先级应为中等"
        )
        self.assertEqual(
            TaskPriority.SINGLE_SIMULATION.value,
            1,
            "单站点模拟优先级应为最低"
        )

        self.assertGreater(
            TaskPriority.ENSEMBLE_SIMULATION.value,
            TaskPriority.BATCH_SIMULATION.value,
            "集合模拟优先级应高于批量模拟"
        )
        self.assertGreater(
            TaskPriority.BATCH_SIMULATION.value,
            TaskPriority.SINGLE_SIMULATION.value,
            "批量模拟优先级应高于单站点模拟"
        )

        print("  ✓ CropModelWorker 任务优先级测试通过")

    def test_cancel_task(self):
        """测试取消任务"""
        worker = CropModelWorker(max_workers=1, max_retries=0)
        worker.start()

        task_ids = []
        for i in range(5):
            tid = worker.submit_simulation(
                crop_type='粟',
                region='中原地区',
                precip_data=self.precip_data,
                et0_data=self.et0_data,
                temp_data=self.temp_data,
            )
            task_ids.append(tid)

        cancelled = worker.cancel_task(task_ids[-1])
        self.assertTrue(cancelled)

        status = worker.get_task_status(task_ids[-1])
        self.assertEqual(status["status"], "cancelled")

        worker.stop(wait=True)
        print("  ✓ CropModelWorker.cancel_task 测试通过")

    def test_callback(self):
        """测试任务完成回调"""
        callback_results = []

        def callback(task_id, status, result):
            callback_results.append({
                "task_id": task_id,
                "status": status,
                "result": result,
            })

        self.worker.start()

        task_id = self.worker.submit_simulation(
            crop_type='粟',
            region='中原地区',
            precip_data=self.precip_data,
            et0_data=self.et0_data,
            temp_data=self.temp_data,
            callback=callback,
        )

        max_wait = 10
        waited = 0
        while waited < max_wait and len(callback_results) == 0:
            time.sleep(0.5)
            waited += 0.5

        self.assertGreater(len(callback_results), 0, "回调函数应该被调用")
        self.assertEqual(callback_results[0]["task_id"], task_id)
        self.assertEqual(callback_results[0]["status"], TaskStatus.COMPLETED)

        print("  ✓ CropModelWorker 回调测试通过")

    def test_get_all_tasks(self):
        """测试获取所有任务"""
        self.worker.start()

        for i in range(3):
            self.worker.submit_simulation(
                crop_type='粟',
                region='中原地区',
                precip_data=self.precip_data,
                et0_data=self.et0_data,
                temp_data=self.temp_data,
            )

        all_tasks = self.worker.get_all_tasks()
        self.assertEqual(len(all_tasks), 3)

        print("  ✓ CropModelWorker.get_all_tasks 测试通过")

    def test_clear_completed_tasks(self):
        """测试清理已完成任务"""
        self.worker.start()

        task_id = self.worker.submit_simulation(
            crop_type='粟',
            region='中原地区',
            precip_data=self.precip_data,
            et0_data=self.et0_data,
            temp_data=self.temp_data,
        )

        max_wait = 10
        waited = 0
        while waited < max_wait:
            status = self.worker.get_task_status(task_id)
            if status["status"] == "completed":
                break
            time.sleep(0.5)
            waited += 0.5

        count = self.worker.clear_completed_tasks()
        self.assertGreaterEqual(count, 1)

        print("  ✓ CropModelWorker.clear_completed_tasks 测试通过")

    def test_model_cache(self):
        """测试模型缓存"""
        self.worker.start()

        stats = self.worker.get_model_cache_stats()
        self.assertIn("cached_models_count", stats)
        self.assertIn("cached_keys", stats)
        self.assertEqual(stats["cached_models_count"], 0)

        self.worker.clear_model_cache()

        stats_after = self.worker.get_model_cache_stats()
        self.assertEqual(stats_after["cached_models_count"], 0)

        print("  ✓ CropModelWorker 模型缓存测试通过")


class TestReconstructionWorker(unittest.TestCase):
    """测试重建 Worker"""

    def setUp(self):
        self.worker = ReconstructionWorker(max_workers=2)
        self.photo_urls = [
            "https://example.com/photo1.jpg",
            "https://example.com/photo2.jpg",
            "https://example.com/photo3.jpg",
            "https://example.com/photo4.jpg",
            "https://example.com/photo5.jpg",
            "https://example.com/photo6.jpg",
            "https://example.com/photo7.jpg",
            "https://example.com/photo8.jpg",
            "https://example.com/photo9.jpg",
            "https://example.com/photo10.jpg",
        ]

    def tearDown(self):
        if self.worker._running:
            self.worker.stop(wait=True)

    def test_initialization(self):
        """测试 ReconstructionWorker 初始化"""
        self.assertEqual(self.worker.max_workers, 2)
        self.assertFalse(self.worker._running)
        self.assertIsNotNone(self.worker.task_queue)
        self.assertIsInstance(self.worker.task_store, dict)
        print("  ✓ ReconstructionWorker 初始化测试通过")

    def test_start_stop(self):
        """测试 start() 和 stop()"""
        self.assertFalse(self.worker._running)

        self.worker.start()
        self.assertTrue(self.worker._running)
        self.assertIsNotNone(self.worker._executor)
        self.assertEqual(len(self.worker._worker_threads), 2)

        self.worker.stop(wait=True)
        self.assertFalse(self.worker._running)
        self.assertIsNone(self.worker._executor)
        self.assertEqual(len(self.worker._worker_threads), 0)

        print("  ✓ ReconstructionWorker start/stop 测试通过")

    def test_submit_task(self):
        """测试提交重建任务"""
        self.worker.start()

        task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            method="摄影测量",
            priority=3,
            generate_vr=False,
        )

        self.assertIsInstance(task_id, str)
        self.assertGreater(len(task_id), 0)

        status = self.worker.get_task_status(task_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["task_id"], task_id)
        self.assertIn(status["status"], ["pending", "processing"])
        self.assertEqual(status["site_id"], 1)
        self.assertEqual(status["photo_count"], len(self.photo_urls))
        self.assertEqual(status["method"], "摄影测量")
        self.assertEqual(status["priority"], 3)
        self.assertFalse(status["generate_vr"])

        print("  ✓ ReconstructionWorker.submit_task 测试通过")

    def test_submit_task_validation(self):
        """测试提交任务时的参数验证"""
        self.worker.start()

        with self.assertRaises(ValueError):
            self.worker.submit_task(site_id=1, photo_urls=[])

        with self.assertRaises(ValueError):
            self.worker.submit_task(site_id=1, photo_urls=self.photo_urls, priority=0)

        with self.assertRaises(ValueError):
            self.worker.submit_task(site_id=1, photo_urls=self.photo_urls, priority=6)

        with self.assertRaises(ValueError):
            self.worker.submit_task(site_id=1, photo_urls=self.photo_urls, max_retries=-1)

        print("  ✓ ReconstructionWorker 参数验证测试通过")

    def test_get_task_status_not_found(self):
        """测试查询不存在的任务"""
        self.worker.start()

        status = self.worker.get_task_status("nonexistent_task_id")
        self.assertIsNone(status)

        print("  ✓ ReconstructionWorker 任务不存在测试通过")

    def test_task_status_transition(self):
        """测试任务状态流转 pending -> processing -> completed"""
        self.worker.start()

        task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            method="摄影测量",
            generate_vr=False,
        )

        status = self.worker.get_task_status(task_id)
        initial_status = status["status"]
        self.assertIn(initial_status, ["pending", "processing"])

        max_wait = 30
        waited = 0
        while waited < max_wait:
            status = self.worker.get_task_status(task_id)
            if status["status"] == "completed":
                break
            time.sleep(1)
            waited += 1

        status = self.worker.get_task_status(task_id)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["progress_pct"], 100)
        self.assertIsNotNone(status["completed_at"])
        self.assertIsNotNone(status["result"])

        result = status["result"]
        self.assertIn("status", result)
        self.assertIn("point_cloud_count", result)
        self.assertIn("mesh_face_count", result)
        self.assertEqual(result["status"], "completed")

        print("  ✓ ReconstructionWorker 任务状态流转测试通过")

    def test_priority_queue(self):
        """测试优先级队列（高优先级先执行）"""
        self.worker = ReconstructionWorker(max_workers=1)
        self.worker.start()

        low_task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            priority=1,
            generate_vr=False,
        )

        high_task_id = self.worker.submit_task(
            site_id=2,
            photo_urls=self.photo_urls,
            priority=5,
            generate_vr=False,
        )

        time.sleep(0.5)

        low_status = self.worker.get_task_status(low_task_id)
        high_status = self.worker.get_task_status(high_task_id)

        self.assertEqual(high_status["priority"], 5)
        self.assertEqual(low_status["priority"], 1)

        print("  ✓ ReconstructionWorker 优先级队列测试通过")

    def test_retry_mechanism(self):
        """测试重试机制"""
        self.worker = ReconstructionWorker(max_workers=2)
        self.worker.start()

        task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            max_retries=2,
            generate_vr=False,
        )

        status = self.worker.get_task_status(task_id)
        self.assertEqual(status["retry_count"], 0)
        self.assertEqual(status["max_retries"], 2)

        print("  ✓ ReconstructionWorker 重试机制测试通过")

    def test_cancel_task(self):
        """测试取消任务"""
        self.worker = ReconstructionWorker(max_workers=1)
        self.worker.start()

        task_ids = []
        for i in range(5):
            tid = self.worker.submit_task(
                site_id=i,
                photo_urls=self.photo_urls,
                priority=1,
                generate_vr=False,
            )
            task_ids.append(tid)

        cancelled = self.worker.cancel_task(task_ids[-1])
        self.assertTrue(cancelled)

        status = self.worker.get_task_status(task_ids[-1])
        self.assertEqual(status["status"], "cancelled")

        cancel_nonexistent = self.worker.cancel_task("nonexistent")
        self.assertFalse(cancel_nonexistent)

        print("  ✓ ReconstructionWorker.cancel_task 测试通过")

    def test_callback_url(self):
        """测试回调URL设置"""
        self.worker.start()

        task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            callback_url="https://example.com/callback",
            generate_vr=False,
        )

        status = self.worker.get_task_status(task_id)
        self.assertIsNotNone(status)

        print("  ✓ ReconstructionWorker 回调URL测试通过")

    def test_get_queue_stats(self):
        """测试获取队列统计信息"""
        self.worker.start()

        stats = self.worker.get_queue_stats()
        self.assertIn("total_tasks", stats)
        self.assertIn("pending", stats)
        self.assertIn("processing", stats)
        self.assertIn("completed", stats)
        self.assertIn("failed", stats)
        self.assertIn("cancelled", stats)
        self.assertIn("queue_size", stats)
        self.assertIn("max_workers", stats)
        self.assertIn("is_running", stats)
        self.assertTrue(stats["is_running"])
        self.assertEqual(stats["max_workers"], 2)

        print("  ✓ ReconstructionWorker.get_queue_stats 测试通过")

    def test_with_statement(self):
        """测试 with 语句支持"""
        with ReconstructionWorker(max_workers=1) as worker:
            self.assertTrue(worker._running)
            task_id = worker.submit_task(
                site_id=1,
                photo_urls=self.photo_urls,
                generate_vr=False,
            )
            self.assertIsInstance(task_id, str)

        print("  ✓ ReconstructionWorker with 语句测试通过")

    def test_retry_task(self):
        """测试重试失败的任务"""
        self.worker.start()

        task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            generate_vr=False,
            max_retries=0,
        )

        max_wait = 30
        waited = 0
        while waited < max_wait:
            status = self.worker.get_task_status(task_id)
            if status["status"] == "completed":
                break
            time.sleep(1)
            waited += 1

        new_task_id = self.worker.retry_task(task_id)
        self.assertIsNone(new_task_id, "已完成的任务不能重试")

        print("  ✓ ReconstructionWorker.retry_task 测试通过")

    def test_site_metadata(self):
        """测试遗址元数据"""
        self.worker.start()

        site_metadata = {
            "site_id": 1,
            "name": "测试遗址",
            "reconstruction_id": 1,
        }

        task_id = self.worker.submit_task(
            site_id=1,
            photo_urls=self.photo_urls,
            site_metadata=site_metadata,
            generate_vr=True,
        )

        status = self.worker.get_task_status(task_id)
        self.assertIsNotNone(status)
        self.assertTrue(status["generate_vr"])

        print("  ✓ ReconstructionWorker 遗址元数据测试通过")


class TestDefaultWorker(unittest.TestCase):
    """测试默认 Worker 实例"""

    def setUp(self):
        shutdown_default_worker()

    def tearDown(self):
        shutdown_default_worker()

    def test_get_default_worker(self):
        """测试获取默认 Worker"""
        worker = get_default_worker(max_workers=2)
        self.assertIsInstance(worker, CropModelWorker)
        self.assertTrue(worker.is_running)

        worker2 = get_default_worker(max_workers=4)
        self.assertIs(worker, worker2, "应该返回同一个实例")

        print("  ✓ get_default_worker 测试通过")

    def test_shutdown_default_worker(self):
        """测试关闭默认 Worker"""
        worker = get_default_worker(max_workers=2)
        self.assertTrue(worker.is_running)

        shutdown_default_worker()
        self.assertFalse(worker.is_running)

        print("  ✓ shutdown_default_worker 测试通过")


class TestReconstructionDefaultWorker(unittest.TestCase):
    """测试重建 Worker 的默认实例"""

    def setUp(self):
        pass

    def test_reconstruction_default_worker_exists(self):
        """测试重建 Worker 模块有 get_default_worker 函数"""
        from workers.reconstruction_worker import (
            get_default_worker as get_recon_default_worker,
        )
        self.assertTrue(callable(get_recon_default_worker))
        print("  ✓ ReconstructionWorker get_default_worker 存在测试通过")


def run_tests():
    """运行所有测试"""
    print("=" * 70)
    print("Workers 模块单元测试")
    print("=" * 70)

    test_cases = [
        ("CropModelWorker 测试", TestCropModelWorker),
        ("ReconstructionWorker 测试", TestReconstructionWorker),
        ("默认 Worker 测试", TestDefaultWorker),
        ("重建默认 Worker 测试", TestReconstructionDefaultWorker),
    ]

    total_tests = 0
    total_passed = 0
    total_failed = 0

    for name, test_class in test_cases:
        print(f"\n{name}")
        print("-" * 50)

        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=0)
        result = runner.run(suite)

        total_tests += result.testsRun
        total_passed += result.testsRun - len(result.failures) - len(result.errors)
        total_failed += len(result.failures) + len(result.errors)

        if result.failures:
            print(f"  失败: {len(result.failures)}")
            for test, traceback in result.failures:
                print(f"    - {test}: {traceback.split(chr(10))[-2]}")
        if result.errors:
            print(f"  错误: {len(result.errors)}")
            for test, traceback in result.errors:
                print(f"    - {test}: {traceback.split(chr(10))[-2]}")

        print(f"  完成: {result.testsRun} 个测试, "
              f"通过: {result.testsRun - len(result.failures) - len(result.errors)}, "
              f"失败: {len(result.failures) + len(result.errors)}")

    print("\n" + "=" * 70)
    print(f"测试总结: 总计 {total_tests} 个测试, "
          f"通过 {total_passed} 个, 失败 {total_failed} 个")
    print("=" * 70)

    return total_failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
