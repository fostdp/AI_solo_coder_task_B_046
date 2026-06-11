"""
数字化展示与虚拟修复 - 质量评估与保证
负责：质量保证重建、重建质量评估、质量分级

纯算法模块，不依赖数据库、Web框架等外部服务
"""
import random
import logging
from typing import List, Dict, Any
from datetime import datetime

from .enhancement import (
    MultiViewReconstructionFusionEngine,
    DeepLearningImageEnhancer,
)
from .utils import grade_quality, clamp

logger = logging.getLogger("digital_display.quality")


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
        return grade_quality(score)


def assess_point_cloud_quality(point_cloud: Dict[str, Any]) -> Dict[str, Any]:
    """
    点云质量评估

    Args:
        point_cloud: 点云数据字典

    Returns:
        点云质量评估结果
    """
    density = point_cloud.get("average_point_density_pts_per_m2", 0)
    point_count = point_cloud.get("point_count", 0)
    has_normals = point_cloud.get("has_normals", False)
    has_colors = point_cloud.get("has_colors", False)

    if density >= 20000:
        density_grade = "优秀"
        density_score = 95
    elif density >= 10000:
        density_grade = "良好"
        density_score = 85
    elif density >= 5000:
        density_grade = "中等"
        density_score = 70
    elif density >= 2000:
        density_grade = "合格"
        density_score = 55
    else:
        density_grade = "不合格"
        density_score = 35

    bonus = 0
    if has_normals:
        bonus += 5
    if has_colors:
        bonus += 5

    overall_score = min(100, density_score + bonus)

    return {
        "density_pts_per_m2": density,
        "point_count": point_count,
        "has_normals": has_normals,
        "has_colors": has_colors,
        "density_grade": density_grade,
        "density_score": density_score,
        "overall_score": overall_score,
        "grading": grade_quality(overall_score),
    }


def assess_mesh_quality(mesh: Dict[str, Any]) -> Dict[str, Any]:
    """
    网格质量评估

    Args:
        mesh: 网格数据字典

    Returns:
        网格质量评估结果
    """
    quality_score = mesh.get("quality_score", 0.0)
    watertight = mesh.get("watertight", False)
    face_count = mesh.get("face_count", 0)
    vertex_count = mesh.get("vertex_count", 0)

    quality_score_pct = quality_score * 100

    if quality_score_pct >= 90 and watertight:
        grade = "优秀"
        score = 95
    elif quality_score_pct >= 80:
        grade = "良好"
        score = 82
    elif quality_score_pct >= 70:
        grade = "中等"
        score = 68
    elif quality_score_pct >= 60:
        grade = "合格"
        score = 52
    else:
        grade = "不合格"
        score = 35

    watertight_bonus = 5 if watertight else 0
    overall_score = min(100, score + watertight_bonus)

    return {
        "quality_score": quality_score,
        "watertight": watertight,
        "face_count": face_count,
        "vertex_count": vertex_count,
        "grade": grade,
        "score": overall_score,
        "grading": grade_quality(overall_score),
    }
