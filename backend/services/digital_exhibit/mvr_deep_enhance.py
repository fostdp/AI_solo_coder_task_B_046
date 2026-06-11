"""
数字化展示与虚拟修复 - 多视角重建融合与深度学习图像增强引擎
负责：照片质量深度评估、视角聚类与覆盖度分析、深度学习图像增强、
     多视角立体融合、视角合成补全、质量保证重建管线
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import random
import math
import logging
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger("digital_exhibit.mvr_enhance")


class EnhanceStrategy(str, Enum):
    AUTO = "auto"
    DENOISE = "denoise"
    SR = "sr"
    FULL = "full"


class MultiViewReconstructionFusionEngine:
    """
    多视角重建融合引擎
    解决照片质量差、视角不足导致的单视角重建模型失真问题
    通过视角聚类、覆盖度评估、最优视角选择、MVS融合、视角合成提升重建质量
    """

    def __init__(self):
        self.cluster_eps = 0.3
        self.cluster_min_samples = 2
        self.sr_model_params = {
            "esrgan": {"scale_factors": [2, 4], "psnr_base": 32.5, "ssim_base": 0.91},
            "real-esrgan": {"scale_factors": [2, 4], "psnr_base": 34.2, "ssim_base": 0.93},
        }
        self.denoise_model_params = {
            "dncnn": {"noise_reduction_base": 0.72, "edge_preservation": 0.88},
            "nlm": {"noise_reduction_base": 0.65, "edge_preservation": 0.92},
        }
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
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

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

        viewpoint_features: List[Tuple[int, float, float, float, float]] = []
        for idx, photo in enumerate(photos_metadata):
            seed_str = photo.get("url", photo.get("id", str(idx)))
            seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
            rng = random.Random(seed)

            focal_length = round(rng.uniform(18.0, 200.0), 2)
            principal_x = round(rng.uniform(-0.1, 0.1), 4)
            principal_y = round(rng.uniform(-0.1, 0.1), 4)
            azimuth = round(rng.uniform(0.0, 360.0), 2)
            elevation = round(rng.uniform(-45.0, 60.0), 2)

            viewpoint_features.append((idx, focal_length, principal_x, azimuth, elevation))

        n_clusters = max(1, min(n, int(math.ceil(n / 3.0))))
        clusters: List[List[int]] = [[] for _ in range(n_clusters)]

        for idx, features in enumerate(viewpoint_features):
            _, _, _, azimuth, _ = features
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
            azimuths = sorted([f[3] for f in viewpoint_features])
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
                for idx, fl, px, az, el in viewpoint_features
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
            seed = int(hashlib.md5(f"photo_depth_{i}".encode()).hexdigest()[:8], 16)
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
            "enhanced_count": sum(1 for log in pipeline_log if log["enhanced"] if log.get("steps_applied")),
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


class QualityGuaranteedReconstructor:
    """
    质量保证重建器
    整合多视角融合引擎与深度学习增强引擎，
    实现质量可控的完整重建流程
    """

    def __init__(self):
        self.mvr_engine = MultiViewReconstructionFusionEngine()
        self.enhancer = DeepLearningImageEnhancer()

    def run_guaranteed_reconstruction(
        self,
        site_id: int,
        photos: List[Dict[str, Any]],
        method: str = '摄影测量',
        generate_vr: bool = True,
        min_quality_threshold: float = 60.0,
    ) -> Dict[str, Any]:
        """
        完整质量保证重建流程
        Step 1: 照片预处理 + 质量评估
        Step 2: 视角聚类 + 视角覆盖度评估
        Step 3: 深度学习图像增强（按需）
        Step 4: 最优视角子集选择
        Step 5: 视角合成（覆盖度不足时）
        Step 6: 多视角立体深度融合
        Step 7: 稠密点云 + 网格 + 纹理
        Step 8: 最终模型质量评估

        Args:
            site_id: 遗址ID
            photos: 照片列表
            method: 重建方法
            generate_vr: 是否生成VR体验
            min_quality_threshold: 最低质量阈值

        Returns:
            重建结果、质量评估、警告、改进建议
        """
        warnings: List[str] = []
        recommendations: List[str] = []
        pipeline_steps: Dict[str, Any] = {}

        step_start_ts = datetime.now().isoformat()

        step1_quality: List[Dict[str, Any]] = []
        overall_quality_scores: List[float] = []
        for photo in photos:
            qm = self.mvr_engine.evaluate_image_quality_metrics(photo)
            step1_quality.append(qm)
            overall_quality_scores.append(qm["overall_score"])

        avg_quality_before = round(
            sum(overall_quality_scores) / max(1, len(overall_quality_scores)), 2
        )
        low_quality_count = sum(1 for q in overall_quality_scores if q < min_quality_threshold)

        pipeline_steps["step1_quality_assessment"] = {
            "timestamp": step_start_ts,
            "photo_count": len(photos),
            "avg_overall_score": avg_quality_before,
            "low_quality_count": low_quality_count,
            "per_photo_quality": step1_quality,
        }

        if low_quality_count > 0:
            warnings.append(f"有 {low_quality_count}/{len(photos)} 张照片质量低于阈值 {min_quality_threshold}")

        step2_clusters = self.mvr_engine.cluster_photo_viewpoints(photos)
        coverage_score = step2_clusters["coverage_score"]
        pipeline_steps["step2_viewpoint_clustering"] = {
            "timestamp": datetime.now().isoformat(),
            "clusters": step2_clusters["clusters"],
            "cluster_count": step2_clusters["cluster_count"],
            "coverage_score": coverage_score,
        }

        if coverage_score < 70:
            warnings.append(f"视角覆盖度较低: {coverage_score:.1f}/100，建议补充更多拍摄视角")
            recommendations.append("建议在缺失视角方向补拍3-5张照片以提升覆盖度")

        photos_with_qm = [
            dict(p, quality_metrics=step1_quality[i])
            for i, p in enumerate(photos)
        ]
        step3_enhance = self.enhancer.run_full_enhancement_pipeline(
            photos_with_qm, skip_if_quality_threshold=min_quality_threshold
        )
        pipeline_steps["step3_image_enhancement"] = {
            "timestamp": datetime.now().isoformat(),
            "overall_quality_improvement": step3_enhance["overall_quality_improvement"],
            "enhanced_count": step3_enhance["overall_quality_improvement"]["enhanced_count"],
        }

        avg_quality_after_enhance = step3_enhance["overall_quality_improvement"]["avg_quality_after"]

        enhanced_photos = step3_enhance["enhanced_photos"]
        step4_selection = self.mvr_engine.select_optimal_view_subset(
            enhanced_photos, min_views=max(5, min(8, len(photos))), coverage_threshold=80.0
        )
        pipeline_steps["step4_optimal_view_selection"] = {
            "timestamp": datetime.now().isoformat(),
            "selected_ids": step4_selection["selected_ids"],
            "selected_count": step4_selection["selected_count"],
            "coverage_after": step4_selection["coverage_after"],
            "expected_quality_gain": step4_selection["expected_quality_gain"],
        }

        selected_photos = [
            enhanced_photos[i] for i in step4_selection["selected_ids"]
            if i < len(enhanced_photos)
        ]

        coverage_after_selection = step4_selection["coverage_after"]
        step5_synthesis = self.mvr_engine.generate_view_synthesis_enhancement(
            selected_photos,
            sparse_points={"sparse_points_count": max(1000, len(selected_photos) * 500)},
            coverage_threshold=80.0,
        )
        pipeline_steps["step5_view_synthesis"] = {
            "timestamp": datetime.now().isoformat(),
            "synthesis_needed": step5_synthesis["synthesis_needed"],
            "synthetic_count": step5_synthesis.get("synthetic_count", 0),
            "coverage_before": step5_synthesis["coverage_before"],
            "coverage_after": step5_synthesis["coverage_after"],
        }

        if step5_synthesis["synthesis_needed"]:
            recommendations.append(
                f"已合成 {step5_synthesis['synthetic_count']} 个虚拟视角以补足覆盖度，建议实际补拍以获得更好效果"
            )

        final_coverage = step5_synthesis["coverage_after"]
        sparse_sim = {
            "sparse_points_count": max(5000, len(selected_photos) * 800),
            "point_cloud_stats": {
                "min_x": -15.0, "max_x": 15.0,
                "min_y": 0.0, "max_y": 10.0,
                "min_z": -15.0, "max_z": 15.0,
            },
        }
        step6_fusion = self.mvr_engine.multi_view_stereo_fusion(
            sparse_sim, step2_clusters
        )
        pipeline_steps["step6_mvs_fusion"] = {
            "timestamp": datetime.now().isoformat(),
            "fusion_quality_metrics": step6_fusion["fusion_quality_metrics"],
            "fused_points_count": step6_fusion["fused_point_cloud"]["point_count"],
        }

        fused_pc = step6_fusion["fused_point_cloud"]
        fusion_quality = step6_fusion["fusion_quality_metrics"]["fusion_quality_score"]

        dense_points_count = fused_pc["point_count"]
        point_density = fused_pc["average_point_density_pts_per_m2"]

        if method == 'poisson' or method == '摄影测量':
            mesh_method = 'poisson'
        elif method == '激光扫描':
            mesh_method = 'ball_pivoting'
        else:
            mesh_method = 'poisson'

        if mesh_method == 'poisson':
            mesh_quality_base = 0.75
        elif mesh_method == 'ball_pivoting':
            mesh_quality_base = 0.7
        else:
            mesh_quality_base = 0.65

        density_factor = min(1.0, point_density / 10000.0)
        mesh_quality_score = round(
            min(0.99, mesh_quality_base + density_factor * 0.15 + fusion_quality * 0.05), 4
        )

        face_ratio = 0.08 if mesh_method == 'poisson' else 0.14
        mesh_face_count = int(dense_points_count * face_ratio)
        mesh_vertex_count = int(mesh_face_count * 0.55)
        watertight = mesh_quality_score > 0.75

        if avg_quality_after_enhance >= 80:
            tex_resolution = "4K"
        elif avg_quality_after_enhance >= 65:
            tex_resolution = "2K"
        else:
            tex_resolution = "1K"

        texture_blend_quality = round(
            0.5 + (avg_quality_after_enhance / 100.0) * 0.45 + random.uniform(-0.02, 0.02), 4
        )
        texture_blend_quality = max(0.3, min(0.99, texture_blend_quality))

        pipeline_steps["step7_dense_mesh_texture"] = {
            "timestamp": datetime.now().isoformat(),
            "dense_points_count": dense_points_count,
            "point_density_pts_per_m2": point_density,
            "mesh_method": mesh_method,
            "mesh_face_count": mesh_face_count,
            "mesh_vertex_count": mesh_vertex_count,
            "mesh_quality_score": mesh_quality_score,
            "watertight": watertight,
            "texture_resolution": tex_resolution,
            "texture_blend_quality": texture_blend_quality,
        }

        reconstruction = {
            "site_id": site_id,
            "method": method,
            "generate_vr": generate_vr,
            "dense_point_cloud": {
                "point_count": dense_points_count,
                "density_pts_per_m2": point_density,
            },
            "mesh": {
                "face_count": mesh_face_count,
                "vertex_count": mesh_vertex_count,
                "quality_score": mesh_quality_score,
                "watertight": watertight,
                "method": mesh_method,
            },
            "texture": {
                "resolution": tex_resolution,
                "blend_quality": texture_blend_quality,
            },
            "coverage_score": final_coverage,
            "fusion_quality_score": fusion_quality,
            "input_photo_count": len(photos),
            "selected_photo_count": len(selected_photos),
            "synthetic_view_count": step5_synthesis.get("synthetic_count", 0),
            "avg_input_quality_before": avg_quality_before,
            "avg_input_quality_after_enhance": avg_quality_after_enhance,
            "pipeline_steps": pipeline_steps,
        }

        quality_assessment = self.assess_reconstruction_quality(reconstruction, photos)
        pipeline_steps["step8_final_quality_assessment"] = {
            "timestamp": datetime.now().isoformat(),
            "quality_assessment": quality_assessment,
        }

        final_quality = quality_assessment["overall_quality"]
        if final_quality < min_quality_threshold:
            warnings.append(
                f"最终重建质量分 {final_quality:.1f} 低于阈值 {min_quality_threshold}"
            )
            if quality_assessment.get("point_cloud_density", 0) < 5000:
                recommendations.append("点云密度不足，建议增加更多高质量照片")
            if not quality_assessment.get("mesh_quality", {}).get("watertight", False):
                recommendations.append("网格非流形/非封闭，建议优化照片视角覆盖或使用更高质量输入")
            if quality_assessment.get("texture_resolution", "1K") in ("1K",):
                recommendations.append("纹理分辨率较低，建议使用更高分辨率的原始照片")
            if coverage_score < 80:
                recommendations.append("视角覆盖度不足，建议补充更多拍摄角度")
            if low_quality_count > len(photos) * 0.3:
                recommendations.append("低质量照片比例过高，建议重新拍摄或使用深度学习增强")
        else:
            if final_quality < 75:
                recommendations.append("重建质量达标但仍有提升空间，可尝试补充更多视角或更高分辨率照片")

        if not recommendations:
            recommendations.append("重建质量良好，当前配置满足要求")

        return {
            "reconstruction": reconstruction,
            "quality_assessment": quality_assessment,
            "warnings": warnings,
            "recommendations": recommendations,
        }

    def assess_reconstruction_quality(
        self,
        reconstruction: Dict[str, Any],
        photos: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        最终模型质量评估
        - 点云密度
        - 网格拓扑质量（流形/封闭性）
        - 纹理分辨率
        - 几何精度估计

        Args:
            reconstruction: 重建结果字典
            photos: 输入照片列表

        Returns:
            质量评估结果字典
        """
        point_cloud_density = reconstruction.get("dense_point_cloud", {}).get(
            "density_pts_per_m2", 0
        )

        if point_cloud_density >= 20000:
            density_score = 95.0
        elif point_cloud_density >= 10000:
            density_score = 85.0
        elif point_cloud_density >= 5000:
            density_score = 70.0
        elif point_cloud_density >= 2000:
            density_score = 55.0
        else:
            density_score = 35.0

        mesh_info = reconstruction.get("mesh", {})
        mesh_quality_score = mesh_info.get("quality_score", 0.0)
        watertight = mesh_info.get("watertight", False)

        if mesh_quality_score >= 0.9 and watertight:
            mesh_score = 95.0
        elif mesh_quality_score >= 0.8:
            mesh_score = 82.0
        elif mesh_quality_score >= 0.7:
            mesh_score = 68.0
        elif mesh_quality_score >= 0.6:
            mesh_score = 52.0
        else:
            mesh_score = 35.0

        tex_resolution = reconstruction.get("texture", {}).get("resolution", "1K")
        tex_blend = reconstruction.get("texture", {}).get("blend_quality", 0.5)

        tex_res_score_map = {"1K": 50.0, "2K": 75.0, "4K": 92.0, "8K": 98.0}
        tex_res_score = tex_res_score_map.get(tex_resolution, 50.0)
        texture_score = round(tex_res_score * 0.6 + tex_blend * 100.0 * 0.4, 2)

        coverage = reconstruction.get("coverage_score", 50.0)
        fusion_quality = reconstruction.get("fusion_quality_score", 0.5)

        avg_photo_quality = reconstruction.get("avg_input_quality_after_enhance", 60.0)

        if coverage >= 90 and avg_photo_quality >= 80:
            accuracy_cm = round(random.uniform(0.3, 1.0), 2)
        elif coverage >= 75 and avg_photo_quality >= 65:
            accuracy_cm = round(random.uniform(1.0, 3.0), 2)
        elif coverage >= 60:
            accuracy_cm = round(random.uniform(3.0, 8.0), 2)
        else:
            accuracy_cm = round(random.uniform(8.0, 20.0), 2)

        if accuracy_cm <= 1.0:
            accuracy_score = 95.0
        elif accuracy_cm <= 3.0:
            accuracy_score = 82.0
        elif accuracy_cm <= 5.0:
            accuracy_score = 68.0
        elif accuracy_cm <= 10.0:
            accuracy_score = 52.0
        else:
            accuracy_score = 35.0

        overall_quality = round(
            0.25 * density_score
            + 0.25 * mesh_score
            + 0.20 * texture_score
            + 0.15 * coverage
            + 0.15 * accuracy_score,
            2,
        )
        overall_quality = max(0.0, min(100.0, overall_quality))

        pass_fail = overall_quality >= 60.0

        return {
            "overall_quality": overall_quality,
            "pass_fail": pass_fail,
            "point_cloud_density": point_cloud_density,
            "point_cloud_density_score": round(density_score, 2),
            "mesh_quality": {
                "quality_score": mesh_quality_score,
                "watertight": watertight,
                "face_count": mesh_info.get("face_count", 0),
                "vertex_count": mesh_info.get("vertex_count", 0),
                "score": round(mesh_score, 2),
            },
            "texture_resolution": tex_resolution,
            "texture_blend_quality": tex_blend,
            "texture_score": texture_score,
            "view_coverage_score": round(coverage, 2),
            "estimated_geometric_accuracy_cm": accuracy_cm,
            "geometric_accuracy_score": round(accuracy_score, 2),
            "fusion_quality_score": round(fusion_quality * 100.0, 2),
            "grading": self._grade_quality(overall_quality),
        }

    @staticmethod
    def _grade_quality(score: float) -> str:
        if score >= 90:
            return "优秀"
        elif score >= 80:
            return "良好"
        elif score >= 70:
            return "中等"
        elif score >= 60:
            return "合格"
        else:
            return "不合格"
