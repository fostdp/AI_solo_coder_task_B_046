"""
测试 modules.digital_display 模块
包含工具函数、重建管线、多视角融合、深度学习增强、质量保证等测试
"""
import sys
import os
import unittest
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.digital_display import (
    hash_seed,
    create_rng,
    grade_quality,
    safe_get,
    clamp,
    PhotoPreprocessor,
    FeatureExtractor,
    SparseToDenseReconstructor,
    ThreeDModelExporter,
    DigitalReconstructionPipeline,
    MultiViewReconstructionFusionEngine,
    DeepLearningImageEnhancer,
    QualityGuaranteedReconstructor,
)


class TestUtils(unittest.TestCase):
    """测试工具函数"""

    def test_hash_seed(self):
        """测试 hash_seed 函数"""
        seed1 = hash_seed("test_identifier")
        seed2 = hash_seed("test_identifier")
        seed3 = hash_seed("different_identifier")

        self.assertIsInstance(seed1, int)
        self.assertEqual(seed1, seed2, "相同标识符应生成相同种子")
        self.assertNotEqual(seed1, seed3, "不同标识符应生成不同种子")
        print("  ✓ hash_seed 测试通过")

    def test_create_rng(self):
        """测试 create_rng 函数"""
        rng1 = create_rng("test_seed")
        rng2 = create_rng("test_seed")
        rng3 = create_rng("other_seed")

        val1 = rng1.random()
        val2 = rng2.random()
        val3 = rng3.random()

        self.assertEqual(val1, val2, "相同种子的随机数生成器应生成相同序列")
        self.assertNotEqual(val1, val3, "不同种子的随机数生成器应生成不同序列")
        print("  ✓ create_rng 测试通过")

    def test_grade_quality(self):
        """测试 grade_quality 函数"""
        self.assertEqual(grade_quality(95), "优秀")
        self.assertEqual(grade_quality(90), "优秀")
        self.assertEqual(grade_quality(85), "良好")
        self.assertEqual(grade_quality(80), "良好")
        self.assertEqual(grade_quality(75), "中等")
        self.assertEqual(grade_quality(70), "中等")
        self.assertEqual(grade_quality(65), "合格")
        self.assertEqual(grade_quality(60), "合格")
        self.assertEqual(grade_quality(50), "不合格")
        self.assertEqual(grade_quality(0), "不合格")
        print("  ✓ grade_quality 测试通过")

    def test_safe_get(self):
        """测试 safe_get 函数"""
        d = {"a": {"b": {"c": 123}}, "x": 456}

        self.assertEqual(safe_get(d, "a.b.c"), 123)
        self.assertEqual(safe_get(d, "a.b"), {"c": 123})
        self.assertEqual(safe_get(d, "x"), 456)
        self.assertEqual(safe_get(d, "nonexistent"), None)
        self.assertEqual(safe_get(d, "a.nonexistent"), None)
        self.assertEqual(safe_get(d, "a.b.c.d"), None)
        self.assertEqual(safe_get(d, "a.b.c", "default"), 123)
        self.assertEqual(safe_get(d, "nonexistent", "default"), "default")
        self.assertEqual(safe_get(None, "a.b"), None)
        self.assertEqual(safe_get({}, "a.b"), None)
        print("  ✓ safe_get 测试通过")

    def test_clamp(self):
        """测试 clamp 函数"""
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-5, 0, 10), 0)
        self.assertEqual(clamp(15, 0, 10), 10)
        self.assertEqual(clamp(0, 0, 10), 0)
        self.assertEqual(clamp(10, 0, 10), 10)
        self.assertEqual(clamp(3.5, 1.0, 5.0), 3.5)
        print("  ✓ clamp 测试通过")


class TestPhotoPreprocessor(unittest.TestCase):
    """测试照片预处理器"""

    def setUp(self):
        self.preprocessor = PhotoPreprocessor()
        self.valid_urls = [
            "https://example.com/photo1.jpg",
            "https://example.com/photo2.jpg",
            "https://example.com/photo3.jpg",
            "https://example.com/photo4.jpg",
            "https://example.com/photo5.jpg",
        ]

    def test_validate_photos_valid(self):
        """测试有效照片验证"""
        random.seed(42)
        all_valid, photo_meta = self.preprocessor.validate_photos(self.valid_urls)

        self.assertIsInstance(all_valid, bool)
        self.assertIsInstance(photo_meta, list)
        self.assertEqual(len(photo_meta), len(self.valid_urls))

        for meta in photo_meta:
            self.assertIn("url", meta)
            self.assertIn("valid", meta)
            self.assertIn("resolution", meta)
            self.assertIn("lighting_score", meta)
            self.assertIn("feature_count", meta)
            self.assertIn("format_detected", meta)

        print("  ✓ PhotoPreprocessor.validate_photos 测试通过")

    def test_validate_photos_insufficient(self):
        """测试照片数量不足的情况"""
        urls = ["https://example.com/photo1.jpg"]
        all_valid, photo_meta = self.preprocessor.validate_photos(urls)

        self.assertFalse(all_valid)
        for meta in photo_meta:
            self.assertIn("不足", meta["reason"])
        print("  ✓ PhotoPreprocessor 照片数量不足测试通过")

    def test_validate_photos_invalid_format(self):
        """测试无效图片格式"""
        urls = [
            "https://example.com/photo1.gif",
            "https://example.com/photo2.jpg",
            "https://example.com/photo3.jpg",
            "https://example.com/photo4.jpg",
            "https://example.com/photo5.jpg",
        ]
        all_valid, photo_meta = self.preprocessor.validate_photos(urls)

        self.assertFalse(photo_meta[0]["valid"])
        self.assertIn("不支持的图片格式", photo_meta[0]["reason"])
        print("  ✓ PhotoPreprocessor 无效格式测试通过")


class TestFeatureExtractor(unittest.TestCase):
    """测试特征提取器"""

    def setUp(self):
        self.extractor = FeatureExtractor()
        self.photos = [
            {"feature_count": 500, "url": "https://example.com/p1.jpg"},
            {"feature_count": 600, "url": "https://example.com/p2.jpg"},
            {"feature_count": 700, "url": "https://example.com/p3.jpg"},
            {"feature_count": 800, "url": "https://example.com/p4.jpg"},
            {"feature_count": 900, "url": "https://example.com/p5.jpg"},
        ]

    def test_extract_correspondences(self):
        """测试特征对应点提取"""
        random.seed(42)
        result = self.extractor.extract_correspondences(self.photos)

        self.assertIsInstance(result, dict)
        self.assertIn("total_matches", result)
        self.assertIn("camera_positions", result)
        self.assertIn("sparse_points_count", result)
        self.assertIn("reprojection_error_avg", result)
        self.assertIn("reconstruction_feasibility", result)

        self.assertGreater(result["total_matches"], 0)
        self.assertGreater(result["sparse_points_count"], 0)
        self.assertGreaterEqual(result["reconstruction_feasibility"], 0.0)
        self.assertLessEqual(result["reconstruction_feasibility"], 1.0)
        self.assertEqual(len(result["camera_positions"]), len(self.photos))

        for cam in result["camera_positions"]:
            self.assertIn("camera_id", cam)
            self.assertIn("x", cam)
            self.assertIn("y", cam)
            self.assertIn("z", cam)
            self.assertIn("quaternion", cam)

        print("  ✓ FeatureExtractor.extract_correspondences 测试通过")

    def test_extract_features_feasibility(self):
        """测试重建可行性随照片数量增加而提高"""
        few_photos = [{"feature_count": 300} for _ in range(3)]
        many_photos = [{"feature_count": 300} for _ in range(20)]

        random.seed(1)
        result_few = self.extractor.extract_correspondences(few_photos)

        random.seed(1)
        result_many = self.extractor.extract_correspondences(many_photos)

        self.assertGreater(
            result_many["reconstruction_feasibility"],
            result_few["reconstruction_feasibility"],
            "更多照片应有更高的重建可行性"
        )
        print("  ✓ FeatureExtractor 重建可行性测试通过")


class TestSparseToDenseReconstructor(unittest.TestCase):
    """测试稀疏到稠密重建器"""

    def setUp(self):
        self.reconstructor = SparseToDenseReconstructor()
        self.sparse_data = {
            "sparse_points_count": 10000,
            "reconstruction_feasibility": 0.8,
            "point_cloud_stats": {
                "min_x": -10, "max_x": 10,
                "min_y": 0, "max_y": 8,
                "min_z": -10, "max_z": 10,
            }
        }

    def test_run_dense_reconstruction(self):
        """测试稠密点云重建"""
        random.seed(42)
        result = self.reconstructor.run_dense_reconstruction(self.sparse_data)

        self.assertIsInstance(result, dict)
        self.assertIn("dense_points_count", result)
        self.assertIn("average_point_density_pts_per_m2", result)
        self.assertIn("point_cloud_stats", result)
        self.assertIn("noise_removed_pct", result)

        self.assertGreater(result["dense_points_count"], self.sparse_data["sparse_points_count"])
        self.assertGreater(result["noise_removed_pct"], 0.0)
        self.assertLess(result["noise_removed_pct"], 1.0)

        print("  ✓ SparseToDenseReconstructor.run_dense_reconstruction 测试通过")

    def test_generate_mesh_surface(self):
        """测试网格表面生成"""
        random.seed(42)
        dense_data = self.reconstructor.run_dense_reconstruction(self.sparse_data)
        result = self.reconstructor.generate_mesh_surface(dense_data, method='poisson')

        self.assertIsInstance(result, dict)
        self.assertIn("mesh_face_count", result)
        self.assertIn("mesh_vertex_count", result)
        self.assertIn("mesh_quality_score", result)
        self.assertIn("watertight", result)
        self.assertIn("decimated_face_count", result)
        self.assertIn("method", result)

        self.assertGreater(result["mesh_face_count"], 0)
        self.assertGreater(result["mesh_vertex_count"], 0)
        self.assertGreaterEqual(result["mesh_quality_score"], 0.0)
        self.assertLessEqual(result["mesh_quality_score"], 1.0)
        self.assertEqual(result["method"], "poisson")
        self.assertIsInstance(result["watertight"], bool)

        print("  ✓ SparseToDenseReconstructor.generate_mesh_surface 测试通过")

    def test_generate_mesh_different_methods(self):
        """测试不同网格生成方法"""
        dense_data = {"dense_points_count": 1000000, "average_point_density_pts_per_m2": 5000}

        for method in ['poisson', 'delaunay', 'ball_pivoting', 'parametric']:
            random.seed(42)
            result = self.reconstructor.generate_mesh_surface(dense_data, method=method)
            self.assertEqual(result["method"], method)
            self.assertGreater(result["mesh_face_count"], 0)

        print("  ✓ SparseToDenseReconstructor 多方法网格生成测试通过")


class TestThreeDModelExporter(unittest.TestCase):
    """测试3D模型导出器"""

    def setUp(self):
        self.exporter = ThreeDModelExporter()
        self.mesh_data = {
            "mesh_face_count": 100000,
            "mesh_vertex_count": 50000,
            "decimated_face_count": 50000,
            "mesh_quality_score": 0.85,
        }
        self.texture_data = {
            "texture_atlas_size": "2048x2048",
            "texture_resolution": "2K",
            "texture_blend_quality": 0.8,
        }
        self.site_metadata = {
            "site_id": 1,
            "reconstruction_id": 1,
            "name": "测试遗址",
        }

    def test_export_gltf_glb(self):
        """测试 glTF/GLB 导出"""
        random.seed(42)
        result = self.exporter.export_gltf_glb(
            self.mesh_data, self.texture_data, self.site_metadata
        )

        self.assertIsInstance(result, dict)
        self.assertIn("gltf_model_url", result)
        self.assertIn("glb_model_url", result)
        self.assertIn("file_size_gltf_kb", result)
        self.assertIn("file_size_glb_kb", result)
        self.assertIn("mesh_triangles", result)
        self.assertIn("materials_count", result)
        self.assertIn("vertex_count", result)
        self.assertIn("glb_binary_embedded", result)
        self.assertIn("draco_compressed", result)

        self.assertTrue(result["glb_binary_embedded"])
        self.assertIn("site_1", result["gltf_model_url"])
        self.assertIn(".gltf", result["gltf_model_url"])
        self.assertIn(".glb", result["glb_model_url"])

        print("  ✓ ThreeDModelExporter.export_gltf_glb 测试通过")

    def test_generate_vr_experience(self):
        """测试 VR 体验生成"""
        random.seed(42)
        result = self.exporter.generate_vr_experience(
            "/models/test.gltf",
            irrigation_geojson=None,
            site_metadata=self.site_metadata,
        )

        self.assertIsInstance(result, dict)
        self.assertIn("vr_experience_url", result)
        self.assertIn("hotspots", result)
        self.assertIn("walking_path_points", result)
        self.assertIn("overlay_layers", result)
        self.assertIn("supported_modes", result)
        self.assertIn("scene_setup", result)

        self.assertGreater(len(result["hotspots"]), 0)
        self.assertGreater(len(result["walking_path_points"]), 0)
        self.assertIn("desktop", result["supported_modes"])
        self.assertIn("VR", result["supported_modes"])

        for hotspot in result["hotspots"]:
            self.assertIn("id", hotspot)
            self.assertIn("position", hotspot)
            self.assertIn("title", hotspot)
            self.assertIn("type", hotspot)

        print("  ✓ ThreeDModelExporter.generate_vr_experience 测试通过")


class TestDigitalReconstructionPipeline(unittest.TestCase):
    """测试完整重建管线"""

    def setUp(self):
        self.pipeline = DigitalReconstructionPipeline()
        self.photo_urls = [
            f"https://example.com/photo{i}.jpg"
            for i in range(10)
        ]
        self.many_photo_urls = [
            f"https://example.com/photo{i}.jpg"
            for i in range(30)
        ]

    def test_run_full_pipeline_failed_insufficient_photos(self):
        """测试照片数量不足时管线失败"""
        result = self.pipeline.run_full_pipeline(
            photo_urls=["https://example.com/photo1.jpg"],
            method='摄影测量',
            generate_vr=False,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "failed")
        self.assertIn("reconstruction_log", result)
        self.assertIn("model_metadata", result)
        self.assertIn("pipeline_failed", result["reconstruction_log"])
        self.assertIn("error", result["reconstruction_log"])
        self.assertIn("照片", result["reconstruction_log"]["error"])

        print("  ✓ DigitalReconstructionPipeline 照片不足失败测试通过")

    def test_run_full_pipeline_result_structure(self):
        """测试管线返回结果的结构（成功或失败都应有正确结构）"""
        random.seed(123)
        result = self.pipeline.run_full_pipeline(
            photo_urls=self.many_photo_urls,
            method='摄影测量',
            generate_vr=True,
            site_metadata={"site_id": 1, "name": "测试遗址", "reconstruction_id": 1},
        )

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        self.assertIn("reconstruction_log", result)
        self.assertIn("model_metadata", result)
        self.assertIn(result["status"], ["completed", "failed"])

        if result["status"] == "completed":
            self.assertIn("gltf_model_url", result)
            self.assertIn("glb_model_url", result)
            self.assertIn("point_cloud_count", result)
            self.assertIn("mesh_face_count", result)
            self.assertIn("texture_resolution", result)
            self.assertGreater(result["point_cloud_count"], 0)
            self.assertGreater(result["mesh_face_count"], 0)
            self.assertIsNotNone(result["vr_experience_url"])
            print("  ✓ DigitalReconstructionPipeline.run_full_pipeline 成功路径测试通过")
        else:
            self.assertIn("error", result["reconstruction_log"])
            print("  ✓ DigitalReconstructionPipeline.run_full_pipeline 失败路径测试通过")

    def test_run_full_pipeline_no_vr(self):
        """测试不生成 VR 的重建流程"""
        random.seed(123)
        result = self.pipeline.run_full_pipeline(
            photo_urls=self.many_photo_urls,
            method='摄影测量',
            generate_vr=False,
        )

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)

        if result["status"] == "completed":
            self.assertIsNone(result["vr_experience_url"])
            self.assertIn("point_cloud_count", result)
            self.assertIn("mesh_face_count", result)
            print("  ✓ DigitalReconstructionPipeline 无VR测试通过")
        else:
            print("  ✓ DigitalReconstructionPipeline 无VR测试（失败路径）通过")

    def test_run_full_pipeline_different_methods(self):
        """测试不同重建方法"""
        methods = ['摄影测量', '激光扫描', '参数化建模']
        for method in methods:
            random.seed(123)
            result = self.pipeline.run_full_pipeline(
                photo_urls=self.many_photo_urls,
                method=method,
                generate_vr=False,
            )
            self.assertIsInstance(result, dict)
            self.assertIn("status", result)
            if result["status"] == "completed":
                self.assertIn("point_cloud_count", result)

        print("  ✓ DigitalReconstructionPipeline 多方法测试通过")


class TestMultiViewReconstructionFusionEngine(unittest.TestCase):
    """测试多视角重建融合引擎"""

    def setUp(self):
        self.engine = MultiViewReconstructionFusionEngine()
        self.photos = [
            {"id": f"photo_{i}", "url": f"https://example.com/photo{i}.jpg", "quality_score": 70 + i}
            for i in range(10)
        ]

    def test_evaluate_image_quality_metrics(self):
        """测试图像质量评估"""
        photo = {"id": "test_photo", "url": "https://example.com/test.jpg"}
        result = self.engine.evaluate_image_quality_metrics(photo)

        self.assertIsInstance(result, dict)
        self.assertIn("overall_score", result)
        self.assertIn("sharpness", result)
        self.assertIn("lighting_uniformity", result)
        self.assertIn("resolution_grade", result)
        self.assertIn("contrast", result)
        self.assertIn("noise_level", result)
        self.assertIn("resolution_category", result)
        self.assertIn("enhance_needed", result)
        self.assertIn("specific_issues", result)

        self.assertGreaterEqual(result["overall_score"], 0.0)
        self.assertLessEqual(result["overall_score"], 100.0)
        self.assertIsInstance(result["enhance_needed"], bool)
        self.assertIsInstance(result["specific_issues"], list)

        print("  ✓ MultiViewReconstructionFusionEngine.evaluate_image_quality_metrics 测试通过")

    def test_cluster_photo_viewpoints(self):
        """测试照片视角聚类"""
        result = self.engine.cluster_photo_viewpoints(self.photos)

        self.assertIsInstance(result, dict)
        self.assertIn("clusters", result)
        self.assertIn("viewpoint_count", result)
        self.assertIn("cluster_count", result)
        self.assertIn("coverage_score", result)
        self.assertIn("viewpoint_features", result)

        self.assertEqual(result["viewpoint_count"], len(self.photos))
        self.assertGreaterEqual(result["cluster_count"], 1)
        self.assertGreaterEqual(result["coverage_score"], 0.0)
        self.assertLessEqual(result["coverage_score"], 100.0)
        self.assertEqual(len(result["viewpoint_features"]), len(self.photos))

        for vf in result["viewpoint_features"]:
            self.assertIn("photo_index", vf)
            self.assertIn("focal_length_mm", vf)
            self.assertIn("azimuth_deg", vf)
            self.assertIn("elevation_deg", vf)

        print("  ✓ MultiViewReconstructionFusionEngine.cluster_photo_viewpoints 测试通过")

    def test_cluster_empty_photos(self):
        """测试空照片列表聚类"""
        result = self.engine.cluster_photo_viewpoints([])

        self.assertEqual(result["viewpoint_count"], 0)
        self.assertEqual(result["clusters"], [])
        self.assertEqual(result["coverage_score"], 0.0)

        print("  ✓ MultiViewReconstructionFusionEngine 空照片测试通过")

    def test_multi_view_stereo_fusion(self):
        """测试多视角立体融合"""
        sparse_reconstruction = {
            "sparse_points_count": 50000,
            "point_cloud_stats": {
                "min_x": -15, "max_x": 15,
                "min_y": 0, "max_y": 10,
                "min_z": -15, "max_z": 15,
            }
        }
        photo_clusters = {
            "clusters": [[0, 1, 2], [3, 4, 5], [6, 7, 8, 9]],
            "viewpoint_count": 10,
            "cluster_count": 3,
        }

        random.seed(42)
        result = self.engine.multi_view_stereo_fusion(sparse_reconstruction, photo_clusters)

        self.assertIsInstance(result, dict)
        self.assertIn("fused_point_cloud", result)
        self.assertIn("fusion_quality_metrics", result)

        fused_pc = result["fused_point_cloud"]
        self.assertIn("point_count", fused_pc)
        self.assertIn("average_point_density_pts_per_m2", fused_pc)
        self.assertIn("has_normals", fused_pc)
        self.assertIn("has_colors", fused_pc)

        fusion_metrics = result["fusion_quality_metrics"]
        self.assertIn("fusion_quality_score", fusion_metrics)
        self.assertIn("cluster_count", fusion_metrics)

        self.assertGreater(fused_pc["point_count"], 0)
        self.assertTrue(fused_pc["has_normals"])
        self.assertTrue(fused_pc["has_colors"])

        print("  ✓ MultiViewReconstructionFusionEngine.multi_view_stereo_fusion 测试通过")


class TestDeepLearningImageEnhancer(unittest.TestCase):
    """测试深度学习图像增强器"""

    def setUp(self):
        self.enhancer = DeepLearningImageEnhancer()
        self.photo_info = {
            "id": "test_photo",
            "url": "https://example.com/test.jpg",
            "quality_metrics": {
                "overall_score": 55.0,
                "sharpness": 50.0,
                "lighting_uniformity": 55.0,
                "resolution_grade": 60.0,
                "noise_level": 70.0,
                "specific_issues": ["模糊", "噪声", "低分辨率"],
            }
        }

    def test_deep_denoise(self):
        """测试深度学习去噪"""
        result = self.enhancer.deep_denoise(self.photo_info, strength='auto')

        self.assertIsInstance(result, dict)
        self.assertEqual(result["method"], "deep_denoise")
        self.assertIn("strength", result)
        self.assertIn("strength_value", result)
        self.assertIn("noise_reduction_pct", result)
        self.assertIn("edge_preservation_pct", result)
        self.assertIn("psnr_gain_db", result)
        self.assertIn("ssim_improvement", result)
        self.assertIn("model_used", result)

        self.assertGreater(result["noise_reduction_pct"], 0.0)
        self.assertGreater(result["edge_preservation_pct"], 0.0)
        self.assertGreater(result["psnr_gain_db"], 0.0)
        self.assertGreater(result["ssim_improvement"], 0.0)

        print("  ✓ DeepLearningImageEnhancer.deep_denoise 测试通过")

    def test_deep_denoise_different_strengths(self):
        """测试不同去噪强度"""
        for strength in ['low', 'medium', 'high', 'auto']:
            result = self.enhancer.deep_denoise(self.photo_info, strength=strength)
            self.assertEqual(result["strength"], strength)
            self.assertGreater(result["noise_reduction_pct"], 0.0)

        print("  ✓ DeepLearningImageEnhancer 多强度去噪测试通过")

    def test_super_resolution(self):
        """测试超分辨率"""
        for scale in [2, 4]:
            result = self.enhancer.super_resolution(self.photo_info, scale_factor=scale)

            self.assertIsInstance(result, dict)
            self.assertEqual(result["method"], "super_resolution")
            self.assertEqual(result["scale_factor"], scale)
            self.assertIn("model_used", result)
            self.assertIn("psnr", result)
            self.assertIn("edge_preservation_pct", result)
            self.assertIn("texture_detail_recovered_pct", result)

            self.assertGreater(result["psnr"], 0.0)
            self.assertGreater(result["edge_preservation_pct"], 0.0)
            self.assertGreater(result["texture_detail_recovered_pct"], 0.0)

        print("  ✓ DeepLearningImageEnhancer.super_resolution 测试通过")

    def test_illumination_correction(self):
        """测试光照校正（低光增强）"""
        result = self.enhancer.illumination_correction(self.photo_info)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["method"], "illumination_correction")
        self.assertIn("model_used", result)
        self.assertIn("lighting_uniformity_before", result)
        self.assertIn("lighting_uniformity_after", result)
        self.assertIn("lighting_uniformity_improvement_pct", result)
        self.assertIn("dynamic_range_expanded_stops", result)
        self.assertIn("shadow_recovery_pct", result)
        self.assertIn("highlight_recovery_pct", result)

        self.assertGreaterEqual(result["lighting_uniformity_after"], result["lighting_uniformity_before"])
        self.assertGreater(result["lighting_uniformity_improvement_pct"], 0.0)

        print("  ✓ DeepLearningImageEnhancer.illumination_correction 测试通过")

    def test_low_light_enhance(self):
        """测试低光增强（使用 illumination_correction 实现）"""
        result = self.enhancer.illumination_correction(self.photo_info)
        self.assertIsInstance(result, dict)
        self.assertGreater(result["lighting_uniformity_improvement_pct"], 0)
        print("  ✓ DeepLearningImageEnhancer 低光增强测试通过")


class TestQualityGuaranteedReconstructor(unittest.TestCase):
    """测试质量保证重建器"""

    def setUp(self):
        self.reconstructor = QualityGuaranteedReconstructor()
        self.photos = [
            {"id": f"photo_{i}", "url": f"https://example.com/photo{i}.jpg"}
            for i in range(10)
        ]

    def test_run_guaranteed_reconstruction(self):
        """测试质量保证重建流程"""
        random.seed(42)
        result = self.reconstructor.run_guaranteed_reconstruction(
            site_id=1,
            photos=self.photos,
            method='摄影测量',
            generate_vr=False,
            min_quality_threshold=60.0,
        )

        self.assertIsInstance(result, dict)
        self.assertIn("reconstruction", result)
        self.assertIn("quality_assessment", result)
        self.assertIn("warnings", result)
        self.assertIn("recommendations", result)

        reconstruction = result["reconstruction"]
        self.assertEqual(reconstruction["site_id"], 1)
        self.assertIn("dense_point_cloud", reconstruction)
        self.assertIn("mesh", reconstruction)
        self.assertIn("texture", reconstruction)
        self.assertIn("coverage_score", reconstruction)
        self.assertIn("fusion_quality_score", reconstruction)
        self.assertIn("pipeline_steps", reconstruction)

        quality = result["quality_assessment"]
        self.assertIn("overall_quality", quality)
        self.assertIn("pass_fail", quality)
        self.assertIn("point_cloud_density", quality)
        self.assertIn("mesh_quality", quality)
        self.assertIn("texture_resolution", quality)
        self.assertIn("grading", quality)

        self.assertGreaterEqual(quality["overall_quality"], 0.0)
        self.assertLessEqual(quality["overall_quality"], 100.0)
        self.assertIsInstance(result["warnings"], list)
        self.assertIsInstance(result["recommendations"], list)
        self.assertGreater(len(result["recommendations"]), 0)

        print("  ✓ QualityGuaranteedReconstructor.run_guaranteed_reconstruction 测试通过")

    def test_assess_reconstruction_quality(self):
        """测试重建质量评估"""
        reconstruction = {
            "dense_point_cloud": {
                "density_pts_per_m2": 8000,
            },
            "mesh": {
                "quality_score": 0.85,
                "watertight": True,
                "face_count": 100000,
                "vertex_count": 50000,
            },
            "texture": {
                "resolution": "2K",
                "blend_quality": 0.8,
            },
            "coverage_score": 85.0,
            "fusion_quality_score": 0.75,
            "avg_input_quality_after_enhance": 75.0,
        }

        result = self.reconstructor.assess_reconstruction_quality(reconstruction, self.photos)

        self.assertIsInstance(result, dict)
        self.assertIn("overall_quality", result)
        self.assertIn("pass_fail", result)
        self.assertIn("grading", result)
        self.assertIn("point_cloud_density_score", result)
        self.assertIn("mesh_quality", result)
        self.assertIn("texture_score", result)
        self.assertIn("view_coverage_score", result)
        self.assertIn("geometric_accuracy_score", result)

        self.assertGreaterEqual(result["overall_quality"], 0.0)
        self.assertLessEqual(result["overall_quality"], 100.0)
        self.assertIsInstance(result["pass_fail"], bool)
        self.assertIn(result["grading"], ["优秀", "良好", "中等", "合格", "不合格"])

        print("  ✓ QualityGuaranteedReconstructor.assess_reconstruction_quality 测试通过")


def run_tests():
    """运行所有测试"""
    print("=" * 70)
    print("数字化展示模块单元测试")
    print("=" * 70)

    test_cases = [
        ("工具函数测试", TestUtils),
        ("照片预处理器测试", TestPhotoPreprocessor),
        ("特征提取器测试", TestFeatureExtractor),
        ("稀疏到稠密重建器测试", TestSparseToDenseReconstructor),
        ("3D模型导出器测试", TestThreeDModelExporter),
        ("完整重建管线测试", TestDigitalReconstructionPipeline),
        ("多视角重建融合引擎测试", TestMultiViewReconstructionFusionEngine),
        ("深度学习图像增强器测试", TestDeepLearningImageEnhancer),
        ("质量保证重建器测试", TestQualityGuaranteedReconstructor),
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
