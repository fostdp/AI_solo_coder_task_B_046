"""
数字化展示与虚拟修复 - 3D重建核心引擎
负责：照片预处理、特征提取、稀疏→稠密重建、网格生成、纹理烘焙、glTF/GLB导出、VR体验生成

纯算法模块，不依赖数据库、Web框架等外部服务
"""
import os
import random
import math
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

logger = logging.getLogger("digital_display.reconstruction")

RECONSTRUCTION_STAGES = [
    "初始化",
    "照片预处理",
    "稀疏重建(SFM)",
    "稠密点云生成",
    "网格生成",
    "纹理烘焙",
    "模型导出(glTF/GLB)",
    "VR体验生成",
    "完成",
]

RECONSTRUCTION_METHODS = {
    "摄影测量": {
        "description": "基于多视角照片的摄影测量重建(SFM+MVS)",
        "params": {
            "min_photos": 5,
            "recommended_photos": 20,
            "texture_resolutions": ["1K", "2K", "4K"],
            "mesh_methods": ["poisson", "delaunay"],
        }
    },
    "激光扫描": {
        "description": "基于LiDAR点云的高精度几何重建",
        "params": {
            "min_photos": 3,
            "recommended_photos": 10,
            "texture_resolutions": ["2K", "4K"],
            "mesh_methods": ["poisson", "ball_pivoting"],
        }
    },
    "参数化建模": {
        "description": "基于CAD参数的程序化几何建模(适用于规则形制)",
        "params": {
            "min_photos": 2,
            "recommended_photos": 8,
            "texture_resolutions": ["1K", "2K"],
            "mesh_methods": ["parametric"],
        }
    },
}


class PhotoPreprocessor:
    """照片预处理：质量检测、特征提取"""

    def validate_photos(self, photo_urls: List[str]) -> Tuple[bool, List[Dict]]:
        """
        照片质量检测（模拟）：
        检查每张照片的URL、格式、估算分辨率和光照
        返回 (全部合格, 每张照片的meta信息)
        合格条件: ≥5张且每张feature_count≥200(特征点)
        """
        photo_meta_list: List[Dict] = []
        valid_formats = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp')
        valid_resolutions = [
            "1920x1080", "2560x1440", "3840x2160",
            "4096x2160", "5120x2880", "7680x4320"
        ]

        for idx, url in enumerate(photo_urls):
            meta = {
                "url": url,
                "index": idx,
                "valid": True,
                "reason": "",
                "resolution": random.choice(valid_resolutions),
                "lighting_score": round(random.uniform(0.4, 0.98), 3),
                "feature_count": random.randint(80, 1200),
                "format_detected": "",
            }

            url_lower = url.lower()
            ext = os.path.splitext(url_lower)[1] if '?' not in url_lower else ''
            if not ext:
                ext = '.jpg'

            if ext not in valid_formats:
                meta["valid"] = False
                meta["reason"] = f"不支持的图片格式: {ext}"
                meta["format_detected"] = ext
            elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("/")):
                meta["valid"] = False
                meta["reason"] = "无效的URL格式"
            else:
                meta["format_detected"] = ext
                if meta["feature_count"] < 200:
                    meta["valid"] = False
                    meta["reason"] = f"特征点不足(需≥200, 当前{meta['feature_count']})"
                if meta["lighting_score"] < 0.4:
                    if meta["valid"]:
                        meta["valid"] = False
                        meta["reason"] = f"光照条件不足(需≥0.4, 当前{meta['lighting_score']})"

            photo_meta_list.append(meta)

        total_count = len(photo_urls)
        individual_valid = all(m["valid"] for m in photo_meta_list)
        all_valid = total_count >= 5 and individual_valid

        if total_count < 5:
            for m in photo_meta_list:
                if not m["reason"]:
                    m["reason"] = f"照片总数不足(需≥5, 当前{total_count})"

        return all_valid, photo_meta_list


class FeatureExtractor:
    """SIFT/SFM特征提取模拟"""

    def extract_correspondences(self, photos: List[Dict]) -> Dict:
        """
        从多张照片中提取特征匹配点（模拟摄影测量SFM稀疏重建）
        """
        n = len(photos)
        if n < 5:
            feasibility = 0.2
        elif n <= 10:
            feasibility = 0.4 + (n - 5) * 0.04
        elif n <= 20:
            feasibility = 0.65 + (n - 10) * 0.02
        else:
            feasibility = 0.85 + min(0.1, (n - 20) * 0.005)

        feasibility = round(min(1.0, feasibility), 4)

        base_features = sum(p.get("feature_count", 300) for p in photos)
        total_matches = int(base_features * random.uniform(0.35, 0.65))

        camera_positions = []
        for i in range(n):
            angle = (i / n) * 2 * math.pi
            radius = random.uniform(8.0, 25.0)
            height = random.uniform(1.5, 8.0)
            camera_positions.append({
                "camera_id": f"cam_{i:03d}",
                "x": round(radius * math.cos(angle), 4),
                "y": round(height, 4),
                "z": round(radius * math.sin(angle), 4),
                "quaternion": [
                    round(random.uniform(-1, 1), 5),
                    round(random.uniform(-1, 1), 5),
                    round(random.uniform(-1, 1), 5),
                    round(random.uniform(0, 1), 5),
                ],
            })

        sparse_points_count = int(total_matches * random.uniform(0.15, 0.35))
        reprojection_error_avg = round(random.uniform(0.15, 2.8), 4)

        return {
            "total_matches": total_matches,
            "camera_positions": camera_positions,
            "sparse_points_count": sparse_points_count,
            "reprojection_error_avg": reprojection_error_avg,
            "reconstruction_feasibility": feasibility,
        }


class SparseToDenseReconstructor:
    """稀疏→稠密重建、网格生成、纹理映射模拟"""

    def run_dense_reconstruction(self, sparse_data: Dict) -> Dict:
        """
        稠密点云生成
        """
        sparse_count = sparse_data.get("sparse_points_count", 10000)
        multiplier = random.randint(200, 800)
        dense_points_count = sparse_count * multiplier

        feasibility = sparse_data.get("reconstruction_feasibility", 0.7)
        noise_pct_base = 0.25 - feasibility * 0.15
        noise_removed_pct = round(noise_pct_base + random.uniform(-0.03, 0.05), 4)
        noise_removed_pct = max(0.02, min(0.4, noise_removed_pct))

        center = {"x": 0, "y": 0, "z": 0}
        scale = random.uniform(15.0, 80.0)
        point_cloud_stats = {
            "min_x": round(center["x"] - scale * random.uniform(0.4, 0.6), 3),
            "max_x": round(center["x"] + scale * random.uniform(0.4, 0.6), 3),
            "min_y": round(center["y"] - scale * random.uniform(0.1, 0.3), 3),
            "max_y": round(center["y"] + scale * random.uniform(0.3, 0.6), 3),
            "min_z": round(center["z"] - scale * random.uniform(0.4, 0.6), 3),
            "max_z": round(center["z"] + scale * random.uniform(0.4, 0.6), 3),
        }

        bbox_x = point_cloud_stats["max_x"] - point_cloud_stats["min_x"]
        bbox_y = point_cloud_stats["max_y"] - point_cloud_stats["min_y"]
        bbox_z = point_cloud_stats["max_z"] - point_cloud_stats["min_z"]
        volume = bbox_x * bbox_y * bbox_z
        average_point_density_pts_per_m2 = 0
        if volume > 0:
            average_point_density_pts_per_m2 = int(dense_points_count / (volume ** (2 / 3)))

        return {
            "dense_points_count": dense_points_count,
            "average_point_density_pts_per_m2": average_point_density_pts_per_m2,
            "point_cloud_stats": point_cloud_stats,
            "noise_removed_pct": noise_removed_pct,
        }

    def generate_mesh_surface(self, dense_data: Dict, method: str = 'poisson') -> Dict:
        """
        网格生成（泊松重建/Delunay三角化）
        """
        dense_count = dense_data.get("dense_points_count", 2_000_000)
        point_density = dense_data.get("average_point_density_pts_per_m2", 5000)

        if method == 'poisson':
            face_to_point_ratio = random.uniform(0.06, 0.14)
            quality_base = 0.75
        elif method == 'delaunay':
            face_to_point_ratio = random.uniform(0.12, 0.25)
            quality_base = 0.6
        elif method == 'ball_pivoting':
            face_to_point_ratio = random.uniform(0.08, 0.16)
            quality_base = 0.7
        elif method == 'parametric':
            face_to_point_ratio = random.uniform(0.02, 0.05)
            quality_base = 0.9
        else:
            face_to_point_ratio = random.uniform(0.08, 0.18)
            quality_base = 0.65

        mesh_face_count = int(dense_count * face_to_point_ratio)
        mesh_vertex_count = int(mesh_face_count * random.uniform(0.45, 0.65))

        density_factor = min(1.0, point_density / 10000.0)
        mesh_quality_score = round(quality_base + density_factor * random.uniform(0.05, 0.2), 4)
        mesh_quality_score = min(0.99, mesh_quality_score)

        watertight = mesh_quality_score > 0.75 or random.random() < 0.35
        hole_count_before_filling = random.randint(0, 35)
        if not watertight:
            hole_count_before_filling = max(hole_count_before_filling, random.randint(5, 60))

        decimation_ratio = random.uniform(0.35, 0.7)
        decimated_face_count = int(mesh_face_count * (1 - decimation_ratio))

        return {
            "mesh_face_count": mesh_face_count,
            "mesh_vertex_count": mesh_vertex_count,
            "mesh_quality_score": mesh_quality_score,
            "watertight": watertight,
            "hole_count_before_filling": hole_count_before_filling,
            "decimated_face_count": decimated_face_count,
            "method": method,
        }

    def bake_textures(self, mesh_data: Dict, photos: List[Dict],
                      resolution: str = '2K') -> Dict:
        """
        纹理映射与烘焙
        """
        resolution_map = {
            "1K": {"atlas_size": "1024x1024", "pixels": 1024 * 1024},
            "2K": {"atlas_size": "2048x2048", "pixels": 2048 * 2048},
            "4K": {"atlas_size": "4096x4096", "pixels": 4096 * 4096},
        }
        res_info = resolution_map.get(resolution, resolution_map["2K"])

        n_photos = len(photos)
        if n_photos >= 20:
            blend_base = 0.9
        elif n_photos >= 10:
            blend_base = 0.75 + (n_photos - 10) * 0.015
        else:
            blend_base = 0.55 + n_photos * 0.02

        avg_lighting = sum(p.get("lighting_score", 0.7) for p in photos) / max(1, n_photos)
        texture_blend_quality = round(
            blend_base * 0.7 + avg_lighting * 0.3 + random.uniform(-0.03, 0.03), 4
        )
        texture_blend_quality = max(0.3, min(0.99, texture_blend_quality))

        uv_unwrap_distortion_avg = round(random.uniform(0.005, 0.08), 5)

        return {
            "texture_atlas_size": res_info["atlas_size"],
            "texture_resolution": resolution,
            "uv_unwrap_distortion_avg": uv_unwrap_distortion_avg,
            "texture_blend_quality": texture_blend_quality,
            "gltf_compatible": True,
            "texture_layers": ["diffuse", "normal", "roughness", "ao"],
        }


class ThreeDModelExporter:
    """3D模型导出(glTF/GLB) + VR场景打包"""

    def export_gltf_glb(self, mesh_data: Dict, texture_data: Dict,
                         site_metadata: Dict) -> Dict:
        """
        导出 glTF + GLB 模型文件（模拟生成虚拟URL路径）
        """
        site_id = site_metadata.get("site_id", 0)
        recon_id = site_metadata.get("reconstruction_id", 0)

        face_count = mesh_data.get("decimated_face_count", mesh_data.get("mesh_face_count", 100000))
        vertex_count = mesh_data.get("mesh_vertex_count", 50000)

        resolution_multiplier = {"1K": 1, "2K": 3, "4K": 10}
        tex_res = texture_data.get("texture_resolution", "2K")
        tex_mult = resolution_multiplier.get(tex_res, 3)

        base_kb = (face_count * 0.032 + vertex_count * 0.048)
        texture_kb = 512 * tex_mult

        gltf_size = int(base_kb + texture_kb * 1.1 + random.randint(100, 500))
        glb_size = int(base_kb * 0.92 + texture_kb + random.randint(50, 300))

        gltf_url = f"/models/digital/{site_id}/site_{recon_id}.gltf"
        glb_url = f"/models/digital/{site_id}/site_{recon_id}.glb"

        materials_count = random.randint(2, 8)

        return {
            "gltf_model_url": gltf_url,
            "glb_model_url": glb_url,
            "file_size_gltf_kb": gltf_size,
            "file_size_glb_kb": glb_size,
            "mesh_triangles": face_count,
            "materials_count": materials_count,
            "vertex_count": vertex_count,
            "glb_binary_embedded": True,
            "draco_compressed": random.random() > 0.3,
        }

    def generate_vr_experience(self, gltf_url: str,
                                irrigation_geojson: Dict = None,
                                site_metadata: Dict = None) -> Dict:
        """
        生成WebXR/VR体验页面
        """
        site_id = 0
        site_name = "未知遗址"
        if site_metadata:
            site_id = site_metadata.get("site_id", 0)
            site_name = site_metadata.get("name", site_name)

        vr_url = f"/vr/site/{site_id}/index.html"

        n_hotspots = random.randint(5, 12)
        hotspot_templates = [
            ("渠首入口", "古代水利工程的引水入口，控制水源流量", "entrance"),
            ("主堰体", "核心挡水结构，体现古代水工智慧", "structure"),
            ("分水闸", "水利分配设施，实现按需配水", "gate"),
            ("灌溉渠系", "发达的渠道网络，滋养千亩良田", "canal"),
            ("管理设施", "古代水官办公及祭祀场所", "building"),
            ("观测点", "水位观测与水文监测遗迹", "observation"),
            ("桥墩遗址", "古代桥梁遗迹，见证水陆交通", "bridge"),
            ("碑刻题记", "记载水利历史的重要文物", "inscription"),
            ("蓄水池", "调蓄水量的重要设施", "reservoir"),
            ("跌水陡坡", "利用地形落差的输水工程", "drop"),
            ("涵闸隧洞", "穿越障碍的地下输水设施", "tunnel"),
            ("生态湿地", "兼具水利与生态功能的湿地区域", "wetland"),
        ]
        selected_hotspots = random.sample(hotspot_templates, min(n_hotspots, len(hotspot_templates)))

        hotspots = []
        for i, (title, desc, htype) in enumerate(selected_hotspots):
            angle = (i / n_hotspots) * 2 * math.pi
            radius = random.uniform(3.0, 12.0)
            hotspots.append({
                "id": f"hs_{site_id}_{i:03d}",
                "position": {
                    "x": round(radius * math.cos(angle), 3),
                    "y": round(random.uniform(0.5, 4.0), 3),
                    "z": round(radius * math.sin(angle), 3),
                },
                "title": title,
                "description": f"{site_name}-{desc}",
                "type": htype,
            })

        n_path_points = random.randint(20, 50)
        walking_path_points = []
        for i in range(n_path_points):
            t = i / (n_path_points - 1)
            angle = t * 2 * math.pi * random.uniform(1.0, 2.0)
            r = 4.0 + t * 6.0
            walking_path_points.append({
                "x": round(r * math.cos(angle), 3),
                "y": round(0.3 + math.sin(t * math.pi) * 0.5, 3),
                "z": round(r * math.sin(angle), 3),
            })

        overlay_layers = ["遗址现状"]
        if irrigation_geojson is not None:
            overlay_layers.append("复原灌溉区")
        overlay_layers.append("朝代背景")

        skybox_options = ["古代晴空", "黄昏暮色", "烟雨朦胧", "四季轮回"]
        lighting_options = [
            {"type": "sun", "intensity": 1.0, "time": "12:00"},
            {"type": "sun", "intensity": 0.7, "time": "17:30"},
            {"type": "overcast", "intensity": 0.6, "time": "10:00"},
        ]
        fog_options = [
            {"enabled": False},
            {"enabled": True, "density": 0.005, "color": "#e8e4d8"},
        ]

        scene_setup = {
            "skybox": random.choice(skybox_options),
            "lighting": random.choice(lighting_options),
            "fog": random.choice(fog_options),
            "scale_factor": round(random.uniform(0.8, 1.5), 3),
            "initial_camera": {
                "position": {"x": 0, "y": 5, "z": 20},
                "target": {"x": 0, "y": 2, "z": 0},
            },
        }

        return {
            "vr_experience_url": vr_url,
            "hotspots": hotspots,
            "walking_path_points": walking_path_points,
            "overlay_layers": overlay_layers,
            "supported_modes": ["desktop", "mobile", "VR", "AR"],
            "scene_setup": scene_setup,
            "gltf_model_url": gltf_url,
            "irrigation_overlay": irrigation_geojson is not None,
        }

    def overlay_irrigation_zone(self, site_geom: Dict,
                                 irrigation_geom: Dict,
                                 model_bbox: Dict) -> Dict:
        """叠加灌溉区到3D场景"""
        min_y = model_bbox.get("min_y", -5)
        max_y = model_bbox.get("max_y", 10)
        base_height = min_y + 0.1
        extrusion_height = round(max(0.5, (max_y - min_y) * 0.15), 3)

        return {
            "layer_id": "irrigation_zone_overlay",
            "layer_name": "复原灌溉区",
            "enabled": True,
            "geometry": irrigation_geom,
            "extrusion_height_m": extrusion_height,
            "base_elevation_m": base_height,
            "opacity": 0.55,
            "color": "#4a9eff",
            "wireframe": False,
            "boundary_outline": {
                "enabled": True,
                "color": "#1565c0",
                "width": 2,
            },
            "label": {
                "text": "灌溉覆盖区",
                "position": "top",
                "enabled": True,
            },
        }


class DigitalReconstructionPipeline:
    """完整重建管线编排器（纯算法版本）"""

    def __init__(self):
        self.preprocessor = PhotoPreprocessor()
        self.extractor = FeatureExtractor()
        self.reconstructor = SparseToDenseReconstructor()
        self.exporter = ThreeDModelExporter()

    def _record_step(self, log: Dict, step_idx: int, step_name: str,
                     status: str, start_ts: float, data: Dict = None) -> None:
        elapsed = round(time.time() - start_ts, 3)
        log[f"step_{step_idx}_{step_name}"] = {
            "stage": step_name,
            "status": status,
            "duration_sec": elapsed,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }

    def run_full_pipeline(self, photo_urls: List[str],
                          method: str = '摄影测量',
                          generate_vr: bool = True,
                          site_metadata: Dict = None) -> Dict[str, Any]:
        """
        完整9步重建流程（纯算法版本）

        Args:
            photo_urls: 照片URL列表
            method: 重建方法
            generate_vr: 是否生成VR体验
            site_metadata: 遗址元数据

        Returns:
            重建结果字典
        """
        reconstruction_log: Dict[str, Any] = {
            "pipeline_started": datetime.now().isoformat(),
            "method": method,
            "photo_count": len(photo_urls),
            "generate_vr": generate_vr,
        }
        current_step = 0

        site_id = 0
        recon_id = 0
        site_name = "未知遗址"
        if site_metadata:
            site_id = site_metadata.get("site_id", 0)
            site_name = site_metadata.get("name", site_name)
            recon_id = site_metadata.get("reconstruction_id", 0)

        model_metadata: Dict[str, Any] = {
            "site_info": {
                "site_id": site_id,
                "name": site_name,
            },
            "stages": {},
        }

        try:
            current_step = 1
            step_start = time.time()
            self._record_step(reconstruction_log, 1, "初始化", "success", step_start, {
                "reconstruction_id": recon_id,
                "site_id": site_id,
            })

            current_step = 2
            step_start = time.time()
            all_valid, photo_meta = self.preprocessor.validate_photos(photo_urls)
            if not all_valid:
                failed_reasons = [
                    f"照片{i+1}: {m['reason']}"
                    for i, m in enumerate(photo_meta) if not m["valid"]
                ]
                self._record_step(reconstruction_log, 2, "照片预处理", "failed", step_start, {
                    "photos_checked": len(photo_meta),
                    "valid_count": sum(1 for m in photo_meta if m["valid"]),
                    "errors": failed_reasons,
                })
                reconstruction_log["pipeline_failed"] = datetime.now().isoformat()
                reconstruction_log["error"] = f"照片预处理失败: {'; '.join(failed_reasons)}"
                return {
                    "status": "failed",
                    "reconstruction_log": reconstruction_log,
                    "model_metadata": model_metadata,
                }

            self._record_step(reconstruction_log, 2, "照片预处理", "success", step_start, {
                "photos_checked": len(photo_meta),
                "valid_count": sum(1 for m in photo_meta if m["valid"]),
                "avg_lighting": round(
                    sum(m["lighting_score"] for m in photo_meta) / len(photo_meta), 3
                ),
                "avg_features": int(
                    sum(m["feature_count"] for m in photo_meta) / len(photo_meta)
                ),
            })
            model_metadata["stages"]["photo_preprocessing"] = {
                "photo_meta": photo_meta,
            }

            current_step = 3
            step_start = time.time()
            sparse_data = self.extractor.extract_correspondences(photo_meta)
            self._record_step(reconstruction_log, 3, "稀疏重建(SFM)", "success", step_start, {
                "total_matches": sparse_data["total_matches"],
                "sparse_points_count": sparse_data["sparse_points_count"],
                "cameras_count": len(sparse_data["camera_positions"]),
                "reprojection_error_avg": sparse_data["reprojection_error_avg"],
                "reconstruction_feasibility": sparse_data["reconstruction_feasibility"],
            })
            model_metadata["stages"]["sparse_reconstruction"] = sparse_data

            current_step = 4
            step_start = time.time()
            dense_data = self.reconstructor.run_dense_reconstruction(sparse_data)
            self._record_step(reconstruction_log, 4, "稠密点云生成", "success", step_start, {
                "dense_points_count": dense_data["dense_points_count"],
                "average_point_density_pts_per_m2": dense_data["average_point_density_pts_per_m2"],
                "noise_removed_pct": dense_data["noise_removed_pct"],
                "bbox": dense_data["point_cloud_stats"],
            })
            model_metadata["stages"]["dense_reconstruction"] = dense_data

            mesh_method = "poisson"
            if method == "激光扫描":
                mesh_method = random.choice(["poisson", "ball_pivoting"])
            elif method == "参数化建模":
                mesh_method = "parametric"

            current_step = 5
            step_start = time.time()
            mesh_data = self.reconstructor.generate_mesh_surface(dense_data, method=mesh_method)
            self._record_step(reconstruction_log, 5, "网格生成", "success", step_start, {
                "mesh_face_count": mesh_data["mesh_face_count"],
                "mesh_vertex_count": mesh_data["mesh_vertex_count"],
                "mesh_quality_score": mesh_data["mesh_quality_score"],
                "watertight": mesh_data["watertight"],
                "decimated_face_count": mesh_data["decimated_face_count"],
                "method": mesh_data["method"],
            })
            model_metadata["stages"]["mesh_generation"] = mesh_data

            current_step = 6
            step_start = time.time()
            tex_res = "2K"
            texture_data = self.reconstructor.bake_textures(
                mesh_data, photo_meta, resolution=tex_res
            )
            self._record_step(reconstruction_log, 6, "纹理烘焙", "success", step_start, {
                "texture_atlas_size": texture_data["texture_atlas_size"],
                "texture_resolution": texture_data["texture_resolution"],
                "uv_unwrap_distortion_avg": texture_data["uv_unwrap_distortion_avg"],
                "texture_blend_quality": texture_data["texture_blend_quality"],
            })
            model_metadata["stages"]["texture_baking"] = texture_data

            current_step = 7
            step_start = time.time()
            export_result = self.exporter.export_gltf_glb(
                mesh_data, texture_data,
                site_metadata={"site_id": site_id, "reconstruction_id": recon_id}
            )
            self._record_step(reconstruction_log, 7, "模型导出", "success", step_start, {
                "gltf_model_url": export_result["gltf_model_url"],
                "glb_model_url": export_result["glb_model_url"],
                "file_size_gltf_kb": export_result["file_size_gltf_kb"],
                "file_size_glb_kb": export_result["file_size_glb_kb"],
                "mesh_triangles": export_result["mesh_triangles"],
                "materials_count": export_result["materials_count"],
            })
            model_metadata["stages"]["export"] = export_result

            current_step = 8
            irrigation_overlay = None
            vr_result = None
            if generate_vr:
                step_start = time.time()

                vr_result = self.exporter.generate_vr_experience(
                    export_result["gltf_model_url"],
                    irrigation_geojson=None,
                    site_metadata={"site_id": site_id, "name": site_name}
                )
                self._record_step(reconstruction_log, 8, "VR体验生成", "success", step_start, {
                    "vr_experience_url": vr_result["vr_experience_url"],
                    "hotspots_count": len(vr_result["hotspots"]),
                    "walking_path_points_count": len(vr_result["walking_path_points"]),
                    "overlay_layers": vr_result["overlay_layers"],
                    "supported_modes": vr_result["supported_modes"],
                })
                model_metadata["stages"]["vr_experience"] = vr_result
            else:
                reconstruction_log["step_8_VR体验生成"] = {
                    "stage": "VR体验生成",
                    "status": "skipped",
                    "reason": "generate_vr=False",
                    "timestamp": datetime.now().isoformat(),
                }

            current_step = 9
            step_start = time.time()
            reconstruction_log["pipeline_completed"] = datetime.now().isoformat()
            reconstruction_log["total_duration_sec"] = round(
                time.time() - reconstruction_log.get("_start_time", time.time()), 3
            )
            self._record_step(reconstruction_log, 9, "完成", "success", step_start, {
                "total_stages_completed": 9 if generate_vr else 8,
                "final_status": "已完成",
            })

            return {
                "status": "completed",
                "reconstruction_log": reconstruction_log,
                "model_metadata": model_metadata,
                "gltf_model_url": export_result["gltf_model_url"],
                "glb_model_url": export_result["glb_model_url"],
                "vr_experience_url": vr_result["vr_experience_url"] if vr_result else None,
                "point_cloud_count": dense_data["dense_points_count"],
                "mesh_face_count": mesh_data["decimated_face_count"],
                "texture_resolution": texture_data["texture_resolution"],
            }

        except Exception as e:
            logger.error(f"重建管线失败 step={current_step}: {e}")
            step_name = RECONSTRUCTION_STAGES[min(current_step, len(RECONSTRUCTION_STAGES) - 1)]
            reconstruction_log["pipeline_failed"] = datetime.now().isoformat()
            reconstruction_log["error"] = f"步骤{current_step}({step_name})失败: {str(e)}"
            reconstruction_log["error_step"] = current_step

            if current_step < 9:
                self._record_step(
                    reconstruction_log, current_step, step_name, "failed",
                    reconstruction_log.get("_start_time", time.time()),
                    {"error": str(e)}
                )

            return {
                "status": "failed",
                "reconstruction_log": reconstruction_log,
                "model_metadata": model_metadata,
                "error": str(e),
            }
