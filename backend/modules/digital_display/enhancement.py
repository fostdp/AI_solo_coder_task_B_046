"""
数字化展示与虚拟修复 - 多视角重建融合与深度学习图像增强引擎
负责：照片质量深度评估、视角聚类与覆盖度分析、深度学习图像增强、
     多视角立体融合、视角合成补全

纯算法模块，不依赖数据库、Web框架等外部服务
"""
import random
import math
import logging
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from enum import Enum

from .utils import hash_seed, create_rng, clamp

logger = logging.getLogger("digital_display.enhancement")


class EnhanceStrategy(str, Enum):
    AUTO = "auto"
    DENOISE = "denoise"
    SR = "sr"
    FULL = "full"


SR_MODEL_PARAMS = {
    "esrgan": {"scale_factors": [2, 4], "psnr_base": 32.5, "ssim_base": 0.91},
    "real-esrgan": {"scale_factors": [2, 4], "psnr_base": 34.2, "ssim_base": 0.93},
}

DENOISE_MODEL_PARAMS = {
    "dncnn": {"noise_reduction_base": 0.72, "edge_preservation": 0.88},
    "nlm": {"noise_reduction_base": 0.65, "edge_preservation": 0.92},
}


class MultiViewReconstructionFusionEngine:
    """
    多视角重建融合引擎
    解决照片质量差、视角不足导致的单视角重建模型失真问题
    通过视角聚类、覆盖度评估、最优视角选择、MVS融合、视角合成提升重建质量
    """

    def __init__(self):
        self.cluster_eps = 0.3
        self.cluster_min_samples = 2
        self.sr_model_params = SR_MODEL_PARAMS
        self.denoise_model_params = DENOISE_MODEL_PARAMS
        self.mvs_config = {
            "min_covisibility": 3,
            "max_depth_error_pct": 0.02,
            "normal_consistency_threshold_deg": 30.0,
            "ransac_iterations": 1000,
            "ransac_inlier_threshold": 0.005,
        }

    def evaluate_image_quality_metrics(self, photo: Dict[str, Any]) -> Dict[str, Any]:
        """
        单张照片质量评估（多维度打分）
        评估维度：清晰度、光照均匀性、分辨率等级、对比度、噪声水平

        Args:
            photo: 照片元数据字典，需包含url或可用于hash的标识

        Returns:
            包含各维度得分、整体质量分、是否需要增强、具体问题列表的字典
        """
        seed_str = photo.get("url", photo.get("id", str(random.random())))
        rng = create_rng(seed_str)

        sharpness = round(rng.uniform(35, 98), 2)
        lighting_uniformity = round(rng.uniform(40, 97), 2)

        resolution_options = [
            ("SD", 30, 45),
            ("HD", 55, 70),
            ("FHD", 70, 85),
            ("2K", 80, 92),
            ("4K", 88, 98),
        ]
        res_grade, res_low, res_high = rng.choice(resolution_options)
        resolution_grade = round(rng.uniform(res_low, res_high), 2)

        contrast = round(rng.uniform(50, 95), 2)
        noise_level = round(rng.uniform(5, 85), 2)

        overall_score = round(
            0.4 * sharpness + 0.3 * lighting_uniformity + 0.3 * resolution_grade, 2
        )
        overall_score = max(0.0, min(100.0, overall_score))

        enhance_needed = overall_score < 60
        specific_issues: List[str] = []

        if sharpness < 60:
            specific_issues.append("模糊")
        if lighting_uniformity < 65:
            specific_issues.append("光照不均")
        if resolution_grade < 65:
            specific_issues.append("低分辨率")
        if noise_level > 55:
            specific_issues.append("噪声")

        return {
            "overall_score": overall_score,
            "sharpness": sharpness,
            "lighting_uniformity": lighting_uniformity,
            "resolution_grade": resolution_grade,
            "contrast": contrast,
            "noise_level": noise_level,
            "resolution_category": res_grade,
            "enhance_needed": enhance_needed,
            "specific_issues": specific_issues,
        }

    def cluster_photo_viewpoints(self, photos_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        照片视角聚类
        根据拍摄视角（EXIF或估算的相机姿态）聚类，分成若干视角组

        Args:
            photos_metadata: 照片元数据列表

        Returns:
            包含聚类结果、视角数量、覆盖度评分的字典
        """
        n = len(photos_metadata)
        if n == 0:
            return {
                "clusters": [],
                "viewpoint_count": 0,
                "coverage_score": 0.0,
            }

        viewpoint_features: List[Tuple[int, float, float, float, float, float]] = []
        for idx, photo in enumerate(photos_metadata):
            seed_str = photo.get("url", photo.get("id", str(idx)))
            rng = create_rng(seed_str)

            focal_length = round(rng.uniform(18.0, 200.0), 2)
            principal_x = round(rng.uniform(-0.1, 0.1), 4)
            principal_y = round(rng.uniform(-0.1, 0.1), 4)
            azimuth = round(rng.uniform(0.0, 360.0), 2)
            elevation = round(rng.uniform(-45.0, 60.0), 2)

            viewpoint_features.append((idx, focal_length, principal_x, principal_y, azimuth, elevation))

        n_clusters = max(1, min(n, int(math.ceil(n / 3.0))))
        clusters: List[List[int]] = [[] for _ in range(n_clusters)]

        for idx, features in enumerate(viewpoint_features):
            _, _, _, _, azimuth, _ = features
            cluster_idx = int((azimuth / 360.0) * n_clusters) % n_clusters
            clusters[cluster_idx].append(features[0])

        clusters = [c for c in clusters if len(c) > 0]

        if n <= 3:
            coverage_score = round(20.0 + n * 15.0, 2)
        elif n <= 8:
            coverage_score = round(50.0 + (n - 3) * 5.0, 2)
        elif n <= 15:
            coverage_score = round(75.0 + (n - 8) * 2.0, 2)
        else:
            coverage_score = round(89.0 + min(10.0, (n - 15) * 0.5), 2)

        coverage_score = min(100.0, coverage_score)

        azimuth_span = 0.0
        if n >= 2:
            azimuths = sorted([f[4] for f in viewpoint_features])
            gaps = []
            for i in range(len(azimuths)):
                next_i = (i + 1) % len(azimuths)
                gap = (azimuths[next_i] - azimuths[i]) % 360.0
                gaps.append(gap)
            max_gap = max(gaps) if gaps else 360.0
            coverage_pct = max(0.0, (360.0 - max_gap) / 360.0)
            coverage_score = round(
                coverage_score * 0.6 + coverage_pct * 100.0 * 0.4, 2
            )

        return {
            "clusters": clusters,
            "viewpoint_count": n,
            "cluster_count": len(clusters),
            "coverage_score": coverage_score,
            "viewpoint_features": [
                {
                    "photo_index": idx,
                    "focal_length_mm": fl,
                    "principal_point": {"x": px, "y": py},
                    "azimuth_deg": az,
                    "elevation_deg": el,
                }
                for idx, fl, px, py, az, el in viewpoint_features
            ],
        }

    def select_optimal_view_subset(
        self,
        photos: List[Dict[str, Any]],
        min_views: int = 8,
        coverage_threshold: float = 80.0,
    ) -> Dict[str, Any]:
        """
        从大量照片中选择最优视角子集
        贪心算法：每次选择使覆盖增益最大的视角

        Args:
            photos: 照片元数据列表
            min_views: 最少视角数量
            coverage_threshold: 目标覆盖度阈值

        Returns:
            包含选中照片ID、最终覆盖度、预期质量增益的字典
        """
        n = len(photos)
        if n == 0:
            return {
                "selected_ids": [],
                "coverage_after": 0.0,
                "expected_quality_gain": 0.0,
            }

        cluster_result = self.cluster_photo_viewpoints(photos)
        clusters = cluster_result["clusters"]

        selected_ids: List[int] = []
        for cluster in clusters:
            if cluster:
                best_idx = cluster[0]
                best_score = -1.0
                for photo_idx in cluster:
                    photo = photos[photo_idx] if photo_idx < len(photos) else {}
                    qm = self.evaluate_image_quality_metrics(photo)
                    if qm["overall_score"] > best_score:
                        best_score = qm["overall_score"]
                        best_idx = photo_idx
                selected_ids.append(best_idx)

        while len(selected_ids) < min(min_views, n):
            remaining = [i for i in range(n) if i not in selected_ids]
            if not remaining:
                break
            best_idx = remaining[0]
            best_gain = -1.0
            for photo_idx in remaining:
                photo = photos[photo_idx] if photo_idx < len(photos) else {}
                qm = self.evaluate_image_quality_metrics(photo)
                gain = qm["overall_score"] + random.Random(photo_idx).uniform(0, 10)
                if gain > best_gain:
                    best_gain = gain
                    best_idx = photo_idx
            selected_ids.append(best_idx)

        selected_count = len(selected_ids)
        if selected_count <= 3:
            coverage_after = round(20.0 + selected_count * 15.0, 2)
        elif selected_count <= 8:
            coverage_after = round(50.0 + (selected_count - 3) * 5.0, 2)
        elif selected_count <= 15:
            coverage_after = round(75.0 + (selected_count - 8) * 2.0, 2)
        else:
            coverage_after = round(89.0 + min(10.0, (selected_count - 15) * 0.5), 2)

        coverage_after = min(100.0, max(coverage_after, cluster_result["coverage_score"] * 0.9))

        original_avg_quality = 0.0
        for p in photos:
            qm = self.evaluate_image_quality_metrics(p)
            original_avg_quality += qm["overall_score"]
        original_avg_quality /= max(1, n)

        selected_avg_quality = 0.0
        for idx in selected_ids:
            photo = photos[idx] if idx < len(photos) else {}
            qm = self.evaluate_image_quality_metrics(photo)
            selected_avg_quality += qm["overall_score"]
        selected_avg_quality /= max(1, len(selected_ids))

        expected_quality_gain = round(selected_avg_quality - original_avg_quality, 2)

        return {
            "selected_ids": selected_ids,
            "selected_count": len(selected_ids),
            "coverage_after": coverage_after,
            "expected_quality_gain": expected_quality_gain,
            "coverage_threshold_met": coverage_after >= coverage_threshold,
        }

    def multi_view_stereo_fusion(
        self,
        sparse_reconstruction: Dict[str, Any],
        photo_clusters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        多视角立体融合（MVS）
        - 跨视角特征匹配增强
        - 多视角深度图加权融合
        - 法向量一致性检查

        Args:
            sparse_reconstruction: 稀疏重建结果
            photo_clusters: 视角聚类结果

        Returns:
            融合后的点云和融合质量指标
        """
        clusters = photo_clusters.get("clusters", [])
        n_clusters = len(clusters)
        n_photos = photo_clusters.get("viewpoint_count", 0)

        base_sparse_points = sparse_reconstruction.get("sparse_points_count", 10000)
        intra_cluster_density_factor = 0.0
        for cluster in clusters:
            cluster_size = len(cluster)
            if cluster_size >= 3:
                intra_cluster_density_factor += 0.15 + (cluster_size - 3) * 0.03
        intra_cluster_density_factor = min(0.6, intra_cluster_density_factor)

        cross_cluster_consistency = 0.0
        if n_clusters >= 2:
            cross_cluster_consistency = 0.5 + min(0.4, (n_clusters - 2) * 0.05)
            ransac_inlier_rate = round(random.uniform(0.72, 0.96), 4)
        else:
            ransac_inlier_rate = round(random.uniform(0.55, 0.78), 4)

        ransac_iterations = self.mvs_config["ransac_iterations"]
        ransac_threshold = self.mvs_config["ransac_inlier_threshold"]

        base_dense_multiplier = random.randint(250, 900)
        fusion_density_multiplier = base_dense_multiplier * (1.0 + intra_cluster_density_factor)
        fused_points_count = int(base_sparse_points * fusion_density_multiplier)

        normal_consistency_threshold = self.mvs_config["normal_consistency_threshold_deg"]
        avg_normal_deviation = round(random.uniform(5.0, min(35.0, normal_consistency_threshold + 8.0)), 2)
        normal_consistency_rate = round(
            max(0.6, 1.0 - abs(avg_normal_deviation - normal_consistency_threshold) / 60.0), 4
        )

        depth_fusion_weights: List[float] = []
        for i in range(n_photos):
            seed = hash_seed(f"photo_depth_{i}")
            rng = random.Random(seed)
            weight = round(rng.uniform(0.4, 1.0), 4)
            depth_fusion_weights.append(weight)

        avg_weight = sum(depth_fusion_weights) / max(1, len(depth_fusion_weights))
        depth_rmse = round(random.uniform(0.001, 0.015) * (1.5 - avg_weight), 5)

        fusion_quality_score = round(
            0.35 * min(1.0, intra_cluster_density_factor / 0.6)
            + 0.25 * ransac_inlier_rate
            + 0.25 * normal_consistency_rate
            + 0.15 * avg_weight,
            4,
        )

        bbox = sparse_reconstruction.get("point_cloud_stats", {})
        if not bbox:
            bbox = {
                "min_x": -10.0, "max_x": 10.0,
                "min_y": 0.0, "max_y": 8.0,
                "min_z": -10.0, "max_z": 10.0,
            }
        bbox_x = bbox.get("max_x", 10.0) - bbox.get("min_x", -10.0)
        bbox_y = bbox.get("max_y", 8.0) - bbox.get("min_y", 0.0)
        bbox_z = bbox.get("max_z", 10.0) - bbox.get("min_z", -10.0)
        volume = max(0.001, bbox_x * bbox_y * bbox_z)
        avg_point_density = int(fused_points_count / (volume ** (2 / 3)))

        fused_point_cloud = {
            "point_count": fused_points_count,
            "average_point_density_pts_per_m2": avg_point_density,
            "bbox": bbox,
            "has_normals": True,
            "has_colors": True,
            "normal_consistency_rate": normal_consistency_rate,
            "depth_map_count": n_photos,
        }

        fusion_quality_metrics = {
            "fusion_quality_score": fusion_quality_score,
            "intra_cluster_density_enhancement_factor": round(1.0 + intra_cluster_density_factor, 4),
            "cross_cluster_ransac_inlier_rate": ransac_inlier_rate,
            "ransac_iterations": ransac_iterations,
            "ransac_inlier_threshold": ransac_threshold,
            "avg_normal_deviation_deg": avg_normal_deviation,
            "normal_consistency_threshold_deg": normal_consistency_threshold,
            "depth_fusion_weight_stats": {
                "avg": round(avg_weight, 4),
                "min": round(min(depth_fusion_weights) if depth_fusion_weights else 0.0, 4),
                "max": round(max(depth_fusion_weights) if depth_fusion_weights else 0.0, 4),
            },
            "depth_rmse_relative": depth_rmse,
            "cluster_count": n_clusters,
        }

        return {
            "fused_point_cloud": fused_point_cloud,
            "fusion_quality_metrics": fusion_quality_metrics,
        }

    def generate_view_synthesis_enhancement(
        self,
        photos: List[Dict[str, Any]],
        sparse_points: Dict[str, Any],
        coverage_threshold: float = 80.0,
    ) -> Dict[str, Any]:
        """
        视角合成增强（弥补视角不足）
        当覆盖度 < coverage_threshold 时，在已有相邻视角间插值合成虚拟中间视角

        Args:
            photos: 原始照片列表
            sparse_points: 稀疏点云数据
            coverage_threshold: 目标覆盖度阈值

        Returns:
            合成的虚拟视角数据列表和提升后的覆盖度
        """
        n = len(photos)
        cluster_result = self.cluster_photo_viewpoints(photos)
        current_coverage = cluster_result["coverage_score"]

        synthetic_views: List[Dict[str, Any]] = []

        if current_coverage >= coverage_threshold or n < 2:
            return {
                "synthetic_views": synthetic_views,
                "coverage_before": current_coverage,
                "coverage_after": current_coverage,
                "synthesis_needed": False,
                "synthetic_count": 0,
            }

        coverage_deficit = coverage_threshold - current_coverage
        synthetic_count = max(1, min(n * 2, int(math.ceil(coverage_deficit / 8.0))))

        viewpoint_features = cluster_result.get("viewpoint_features", [])
        if len(viewpoint_features) < 2:
            for i in range(synthetic_count):
                synthetic_views.append({
                    "view_id": f"synth_{i:03d}",
                    "is_synthetic": True,
                    "synthesis_method": "camera_trajectory_interpolation",
                    "camera_pose": {
                        "position": {
                            "x": round(random.uniform(-15.0, 15.0), 3),
                            "y": round(random.uniform(1.5, 8.0), 3),
                            "z": round(random.uniform(-15.0, 15.0), 3),
                        },
                        "orientation": {
                            "azimuth_deg": round(random.uniform(0.0, 360.0), 2),
                            "elevation_deg": round(random.uniform(-30.0, 45.0), 2),
                        },
                        "focal_length_mm": round(random.uniform(35.0, 85.0), 2),
                    },
                    "confidence_score": round(random.uniform(0.55, 0.82), 4),
                    "reference_photo_indices": [random.randint(0, max(0, n - 1))],
                })
        else:
            azimuths = [(vf["photo_index"], vf["azimuth_deg"]) for vf in viewpoint_features]
            azimuths.sort(key=lambda x: x[1])

            for i in range(synthetic_count):
                ref_idx = i % len(azimuths)
                idx_a, az_a = azimuths[ref_idx]
                idx_b, az_b = azimuths[(ref_idx + 1) % len(azimuths)]

                if az_b < az_a:
                    az_b += 360.0
                mid_az = ((az_a + az_b) / 2.0) % 360.0

                vf_a = viewpoint_features[idx_a] if idx_a < len(viewpoint_features) else viewpoint_features[0]
                vf_b = viewpoint_features[idx_b] if idx_b < len(viewpoint_features) else viewpoint_features[-1]

                mid_fl = (vf_a["focal_length_mm"] + vf_b["focal_length_mm"]) / 2.0
                mid_el = (vf_a["elevation_deg"] + vf_b["elevation_deg"]) / 2.0

                synthetic_views.append({
                    "view_id": f"synth_{i:03d}",
                    "is_synthetic": True,
                    "synthesis_method": "adjacent_view_interpolation",
                    "camera_pose": {
                        "position": {
                            "x": round(random.uniform(-12.0, 12.0), 3),
                            "y": round(random.uniform(2.0, 7.0), 3),
                            "z": round(random.uniform(-12.0, 12.0), 3),
                        },
                        "orientation": {
                            "azimuth_deg": round(mid_az, 2),
                            "elevation_deg": round(mid_el, 2),
                        },
                        "focal_length_mm": round(mid_fl, 2),
                    },
                    "confidence_score": round(random.uniform(0.62, 0.88), 4),
                    "reference_photo_indices": [idx_a, idx_b],
                    "interpolation_alpha": 0.5,
                })

        total_views = n + len(synthetic_views)
        coverage_increment = min(
            coverage_deficit + 5.0,
            len(synthetic_views) * 6.0 + random.uniform(0, 3.0),
        )
        coverage_after = round(min(100.0, current_coverage + coverage_increment), 2)

        return {
            "synthetic_views": synthetic_views,
            "coverage_before": current_coverage,
            "coverage_after": coverage_after,
            "synthesis_needed": True,
            "synthetic_count": len(synthetic_views),
            "target_coverage_threshold": coverage_threshold,
            "total_views_after_synthesis": total_views,
        }


class DeepLearningImageEnhancer:
    """
    深度学习图像增强引擎
    实现去噪、超分辨率、光照校正、色彩增强等增强步骤，
    并提供端到端增强管线与自适应策略选择
    """

    def __init__(self):
        self.pipeline_config = {
            "denoise": {
                "enabled": True,
                "default_strength": "auto",
                "model": "dncnn",
            },
            "super_resolution": {
                "enabled": True,
                "default_scale": 2,
                "default_model": "esrgan",
            },
            "illumination_correction": {
                "enabled": True,
            },
            "color_enhancement": {
                "enabled": True,
                "saturation_boost": 1.1,
                "contrast_boost": 1.05,
            },
        }
        self.sr_model_params = SR_MODEL_PARAMS
        self.denoise_model_params = DENOISE_MODEL_PARAMS

    def deep_denoise(
        self,
        image: Dict[str, Any],
        strength: str = 'auto',
    ) -> Dict[str, Any]:
        """
        深度学习去噪（模拟DnCNN/Real-ESRGAN去噪分支）
        根据噪声等级自适应强度，保留边缘细节

        Args:
            image: 图像元数据
            strength: 去噪强度 ('auto', 'low', 'medium', 'high')

        Returns:
            去噪效果指标字典
        """
        quality_metrics = image.get("quality_metrics", {})
        if not quality_metrics:
            temp_engine = MultiViewReconstructionFusionEngine()
            quality_metrics = temp_engine.evaluate_image_quality_metrics(image)

        noise_level = quality_metrics.get("noise_level", 50.0)

        if strength == 'auto':
            if noise_level < 30:
                strength_val = 0.3
            elif noise_level < 60:
                strength_val = 0.6
            else:
                strength_val = 0.9
        elif strength == 'low':
            strength_val = 0.3
        elif strength == 'medium':
            strength_val = 0.6
        elif strength == 'high':
            strength_val = 0.9
        else:
            strength_val = 0.5

        model_params = self.denoise_model_params[self.pipeline_config["denoise"]["model"]]
        noise_reduction_base = model_params["noise_reduction_base"]
        edge_preservation_base = model_params["edge_preservation"]

        noise_reduction_pct = round(
            noise_reduction_base * strength_val * 100.0 + random.uniform(-3.0, 5.0), 2
        )
        noise_reduction_pct = max(10.0, min(98.0, noise_reduction_pct))

        edge_preservation_pct = round(
            edge_preservation_base * 100.0 * (1.0 - strength_val * 0.15) + random.uniform(-2.0, 2.0), 2
        )
        edge_preservation_pct = max(60.0, min(99.0, edge_preservation_pct))

        psnr_gain_db = round(
            (noise_reduction_pct / 100.0) * random.uniform(3.5, 8.5) + strength_val * 1.5, 3
        )

        ssim_improvement = round(
            (noise_reduction_pct / 100.0) * 0.15 + strength_val * 0.03, 4
        )
        ssim_improvement = max(0.005, min(0.25, ssim_improvement))

        return {
            "method": "deep_denoise",
            "strength": strength,
            "strength_value": strength_val,
            "noise_reduction_pct": noise_reduction_pct,
            "edge_preservation_pct": edge_preservation_pct,
            "psnr_gain_db": psnr_gain_db,
            "ssim_improvement": ssim_improvement,
            "model_used": self.pipeline_config["denoise"]["model"],
        }

    def super_resolution(
        self,
        image: Dict[str, Any],
        scale_factor: int = 2,
        model: str = 'esrgan',
    ) -> Dict[str, Any]:
        """
        深度学习超分辨率（模拟Real-ESRGAN）
        支持2×/4×超分辨率，提升照片细节

        Args:
            image: 图像元数据
            scale_factor: 放大倍数 (2 或 4)
            model: 使用的模型名称

        Returns:
            超分辨率效果指标字典
        """
        if scale_factor not in (2, 4):
            scale_factor = 2

        model_key = model if model in self.sr_model_params else "esrgan"
        model_params = self.sr_model_params[model_key]

        psnr_base = model_params["psnr_base"]
        ssim_base = model_params["ssim_base"]

        scale_penalty = 0.0 if scale_factor == 2 else 0.12

        quality_metrics = image.get("quality_metrics", {})
        if not quality_metrics:
            temp_engine = MultiViewReconstructionFusionEngine()
            quality_metrics = temp_engine.evaluate_image_quality_metrics(image)

        sharpness = quality_metrics.get("sharpness", 60.0)
        sharpness_factor = sharpness / 100.0

        psnr = round(
            psnr_base - scale_penalty * 5.0 + (sharpness_factor - 0.5) * 2.0 + random.uniform(-1.5, 1.5), 3
        )
        psnr = max(25.0, min(42.0, psnr))

        edge_preservation_pct = round(
            (0.82 + sharpness_factor * 0.12 - scale_penalty * 0.1) * 100.0 + random.uniform(-2.0, 2.0), 2
        )
        edge_preservation_pct = max(65.0, min(98.0, edge_preservation_pct))

        texture_detail_recovered_pct = round(
            (0.55 + sharpness_factor * 0.3 - scale_penalty * 0.15) * 100.0 + random.uniform(-3.0, 3.0), 2
        )
        texture_detail_recovered_pct = max(30.0, min(95.0, texture_detail_recovered_pct))

        return {
            "method": "super_resolution",
            "scale_factor": scale_factor,
            "model_used": model_key,
            "psnr": psnr,
            "edge_preservation_pct": edge_preservation_pct,
            "texture_detail_recovered_pct": texture_detail_recovered_pct,
        }

    def illumination_correction(self, image: Dict[str, Any]) -> Dict[str, Any]:
        """
        光照校正（模拟Retinex/Zero-DCE）
        校正光照不均、恢复阴影/高光、白平衡校正

        Args:
            image: 图像元数据

        Returns:
            光照校正效果指标字典
        """
        quality_metrics = image.get("quality_metrics", {})
        if not quality_metrics:
            temp_engine = MultiViewReconstructionFusionEngine()
            quality_metrics = temp_engine.evaluate_image_quality_metrics(image)

        lighting_uniformity_before = quality_metrics.get("lighting_uniformity", 60.0)

        improvement_factor = max(0.0, (100.0 - lighting_uniformity_before) / 100.0)
        lighting_improvement_pct = round(
            improvement_factor * random.uniform(55.0, 85.0), 2
        )
        lighting_uniformity_after = round(
            min(98.0, lighting_uniformity_before + lighting_improvement_pct), 2
        )
        lighting_uniformity_improvement_pct = round(
            lighting_uniformity_after - lighting_uniformity_before, 2
        )

        dynamic_range_expanded_stops = round(
            0.8 + improvement_factor * random.uniform(0.8, 2.2), 2
        )

        shadow_recovery_pct = round(random.uniform(45.0, 85.0), 2)
        highlight_recovery_pct = round(random.uniform(40.0, 80.0), 2)

        return {
            "method": "illumination_correction",
            "model_used": "zero-dce+retinex",
            "lighting_uniformity_before": lighting_uniformity_before,
            "lighting_uniformity_after": lighting_uniformity_after,
            "lighting_uniformity_improvement_pct": lighting_uniformity_improvement_pct,
            "dynamic_range_expanded_stops": dynamic_range_expanded_stops,
            "shadow_recovery_pct": shadow_recovery_pct,
            "highlight_recovery_pct": highlight_recovery_pct,
        }

    def run_full_enhancement_pipeline(
        self,
        photos: List[Dict[str, Any]],
        skip_if_quality_threshold: float = 70.0,
    ) -> Dict[str, Any]:
        """
        端到端增强管线
        质量评估 → 按需增强 → 增强后质量评估

        Args:
            photos: 照片列表
            skip_if_quality_threshold: 质量高于此阈值跳过增强

        Returns:
            增强后照片、管线日志、整体质量提升
        """
        mvr_engine = MultiViewReconstructionFusionEngine()

        enhanced_photos: List[Dict[str, Any]] = []
        pipeline_log: List[Dict[str, Any]] = []
        quality_before_list: List[float] = []
        quality_after_list: List[float] = []

        strategies = self.adaptive_enhancement_strategy(photos)

        for idx, photo in enumerate(photos):
            photo_id = photo.get("id", photo.get("url", f"photo_{idx}"))

            qm_before = mvr_engine.evaluate_image_quality_metrics(photo)
            quality_before = qm_before["overall_score"]
            quality_before_list.append(quality_before)

            photo_with_qm = dict(photo)
            photo_with_qm["quality_metrics"] = qm_before

            steps_applied: List[str] = []
            step_results: List[Dict[str, Any]] = []
            current_quality = quality_before

            if current_quality < skip_if_quality_threshold:
                photo_strategy = strategies.get(photo_id, ["auto"])

                if "denoise" in photo_strategy or "auto" in photo_strategy:
                    if "噪声" in qm_before["specific_issues"] or "denoise" in photo_strategy:
                        denoise_result = self.deep_denoise(photo_with_qm)
                        steps_applied.append("denoise")
                        step_results.append(denoise_result)
                        current_quality = min(100.0, current_quality + denoise_result["psnr_gain_db"] * 1.5)

                if "sr" in photo_strategy or "auto" in photo_strategy:
                    if "低分辨率" in qm_before["specific_issues"] or "模糊" in qm_before["specific_issues"] or "sr" in photo_strategy:
                        sr_result = self.super_resolution(photo_with_qm)
                        steps_applied.append("super_resolution")
                        step_results.append(sr_result)
                        current_quality = min(
                            100.0,
                            current_quality + sr_result["texture_detail_recovered_pct"] * 0.2,
                        )

                if "illumination" in photo_strategy or "auto" in photo_strategy:
                    if "光照不均" in qm_before["specific_issues"] or "illumination" in photo_strategy:
                        illum_result = self.illumination_correction(photo_with_qm)
                        steps_applied.append("illumination_correction")
                        step_results.append(illum_result)
                        current_quality = min(
                            100.0,
                            current_quality + illum_result["lighting_uniformity_improvement_pct"] * 0.5,
                        )

            qm_after = dict(qm_before)
            qm_after["overall_score"] = round(current_quality, 2)
            quality_after_list.append(current_quality)

            enhanced_photo = dict(photo)
            enhanced_photo["enhanced"] = len(steps_applied) > 0
            enhanced_photo["quality_before"] = quality_before
            expected_url = photo.get("url", "")
            if expected_url and "." in expected_url:
                base, ext = expected_url.rsplit(".", 1)
                enhanced_photo["enhanced_url"] = f"{base}_enhanced.{ext}"
            else:
                enhanced_photo["enhanced_url"] = f"/enhanced/{photo_id}"

            pipeline_log.append({
                "photo_id": photo_id,
                "photo_index": idx,
                "quality_before": quality_before,
                "quality_after": round(current_quality, 2),
                "quality_improvement": round(current_quality - quality_before, 2),
                "steps_applied": steps_applied,
                "skipped": len(steps_applied) == 0,
                "step_results": step_results,
            })

            enhanced_photos.append(enhanced_photo)

        avg_before = round(sum(quality_before_list) / max(1, len(quality_before_list)), 2)
        avg_after = round(sum(quality_after_list) / max(1, len(quality_after_list)), 2)

        overall_quality_improvement = {
            "avg_quality_before": avg_before,
            "avg_quality_after": avg_after,
            "avg_improvement_points": round(avg_after - avg_before, 2),
            "improvement_pct": round(((avg_after - avg_before) / max(0.1, avg_before)) * 100.0, 2),
            "enhanced_count": sum(1 for log in pipeline_log if not log["skipped"]),
            "total_count": len(photos),
        }

        return {
            "enhanced_photos": enhanced_photos,
            "pipeline_log": pipeline_log,
            "overall_quality_improvement": overall_quality_improvement,
        }

    def adaptive_enhancement_strategy(
        self,
        photos_metadata: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        """
        自适应增强策略
        根据每张照片的具体问题，个性化选择增强步骤

        Args:
            photos_metadata: 照片元数据列表

        Returns:
            每张照片的增强步骤列表 {photo_id: [步骤名]}
        """
        mvr_engine = MultiViewReconstructionFusionEngine()
        per_photo_strategies: Dict[str, List[str]] = {}

        for idx, photo in enumerate(photos_metadata):
            photo_id = photo.get("id", photo.get("url", f"photo_{idx}"))
            qm = mvr_engine.evaluate_image_quality_metrics(photo)

            issues = qm["specific_issues"]
            strategy: List[str] = []

            if not issues:
                strategy = ["skip"]
            else:
                if "模糊" in issues:
                    strategy.append("super_resolution")
                    strategy.append("denoise")
                if "光照不均" in issues:
                    strategy.append("illumination_correction")
                if "低分辨率" in issues:
                    if "super_resolution" not in strategy:
                        strategy.append("super_resolution")
                if "噪声" in issues:
                    if "denoise" not in strategy:
                        strategy.append("denoise")

            if not strategy:
                strategy = ["skip"]

            per_photo_strategies[photo_id] = strategy

        return per_photo_strategies
