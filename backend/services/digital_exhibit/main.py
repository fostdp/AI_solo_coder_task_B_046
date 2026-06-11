"""
数字化展示与虚拟修复 微服务
负责：3D数字化重建、VR体验生成、灌溉区叠加、热点标注、遗址图库
端口：8008
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import logging
import time
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, APIRouter, Body
from sqlalchemy.orm import Session
from sqlalchemy import func

from common.config import settings, channels
from common.database import get_db, init_db
from common.models import (
    WaterHeritageSite,
    DigitalReconstruction,
    FunctionalRestoration,
)
from common.redis_client import pubsub
from common.schemas import (
    DigitalReconstructionResponse,
    DigitalReconstructionDetail,
    DigitalReconstructionRequest,
)

from .reconstruction_engine import (
    DigitalReconstructionPipeline,
    RECONSTRUCTION_METHODS,
    RECONSTRUCTION_STAGES,
)
from .mvr_deep_enhance import (
    MultiViewReconstructionFusionEngine,
    DeepLearningImageEnhancer,
    QualityGuaranteedReconstructor,
    EnhanceStrategy,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("digital_exhibit")

DIGITAL_EXHIBIT_PORT = 8008

app = FastAPI(
    title="古代水利工程遗迹-数字化展示与虚拟修复服务",
    description="负责3D数字化重建、VR/AR体验生成、灌溉区叠加、热点标注管理、遗址数字图库",
    version="3.0.0"
)

router = APIRouter(prefix="/api/v1/digital")

_pipeline = DigitalReconstructionPipeline()
_mvr_engine = MultiViewReconstructionFusionEngine()
_enhancer = DeepLearningImageEnhancer()
_guaranteed_reconstructor = QualityGuaranteedReconstructor()


# ==============================================
# 事件订阅
# ==============================================

def _on_digital_reconstruction_requested(message: Dict[str, Any]):
    """收到重建请求事件，更新状态（冗余保护）"""
    site_id = message.get('site_id')
    if not site_id:
        return
    logger.info(f"收到数字化重建请求事件: site_id={site_id}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()
        recon = db.query(DigitalReconstruction).filter(
            DigitalReconstruction.site_id == site_id
        ).first()
        if recon and recon.reconstruction_status == "待处理":
            recon.reconstruction_status = "处理中"
            db.commit()
        db.close()
    except Exception as e:
        logger.error(f"处理重建请求事件失败 site_id={site_id}: {e}")


def _on_heritage_imported(message: Dict[str, Any]):
    """遗址导入完成后，如果附带照片URL则自动触发默认重建"""
    site_id = message.get('site_id')
    photo_urls = message.get('photo_urls') or message.get('data', {}).get('photo_urls')
    if not site_id:
        return
    if not photo_urls or not isinstance(photo_urls, list) or len(photo_urls) < 5:
        logger.info(f"遗址导入 site_id={site_id}，无足够照片，跳过自动重建")
        return

    logger.info(f"遗址导入完成，自动触发默认重建: site_id={site_id}, photos={len(photo_urls)}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()
        _pipeline.run_full_pipeline(
            db, site_id=site_id,
            photo_urls=photo_urls,
            method='摄影测量',
            generate_vr=True
        )
        db.close()
        logger.info(f"遗址导入后自动重建完成: site_id={site_id}")
    except Exception as e:
        logger.error(f"遗址导入后自动重建失败 site_id={site_id}: {e}")


@app.on_event("startup")
async def startup_event():
    logger.info("Digital Exhibit 服务启动...")
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化异常: {e}")

    pubsub.subscribe(channels.DIGITAL_RECONSTRUCTION_REQUESTED, _on_digital_reconstruction_requested)
    pubsub.subscribe(channels.HERITAGE_IMPORTED, _on_heritage_imported)
    logger.info("Redis Pub/Sub 订阅完成")


# ==============================================
# 内部辅助函数
# ==============================================

def _format_reconstruction_response(recon: DigitalReconstruction,
                                      include_site: bool = False) -> Dict:
    result = {
        "id": recon.id,
        "site_id": recon.site_id,
        "photos_uploaded_count": recon.photos_uploaded_count,
        "reconstruction_method": recon.reconstruction_method,
        "reconstruction_status": recon.reconstruction_status,
        "point_cloud_count": recon.point_cloud_count,
        "mesh_face_count": recon.mesh_face_count,
        "texture_resolution": recon.texture_resolution,
        "glb_model_url": recon.glb_model_url,
        "gltf_model_url": recon.gltf_model_url,
        "vr_experience_url": recon.vr_experience_url,
        "model_metadata": recon.model_metadata,
        "overlay_with_irrigation": recon.overlay_with_irrigation,
        "reconstruction_log": recon.reconstruction_log,
        "created_at": recon.created_at,
        "updated_at": recon.updated_at,
    }
    if include_site:
        try:
            from common.database import SessionLocal
            db_tmp = SessionLocal()
            site = db_tmp.query(WaterHeritageSite).filter(
                WaterHeritageSite.id == recon.site_id
            ).first()
            if site:
                result['site'] = {
                    "id": site.id,
                    "name": site.name,
                    "site_type": site.site_type,
                    "dynasty": site.dynasty,
                    "dynasty_order": site.dynasty_order,
                    "longitude": site.longitude,
                    "latitude": site.latitude,
                    "irrigation_area": site.irrigation_area,
                    "preservation_status": site.preservation_status,
                }
            db_tmp.close()
        except Exception:
            pass
    return result


def _get_progress_pct(recon: DigitalReconstruction) -> int:
    status = recon.reconstruction_status
    if status == "待处理":
        return 0
    if status == "已完成":
        return 100
    if status == "失败":
        log = recon.reconstruction_log or {}
        error_step = log.get("error_step", 0)
        return int((error_step / 9) * 100)

    log = recon.reconstruction_log or {}
    completed_steps = 0
    for idx in range(1, 10):
        key_prefix = f"step_{idx}_"
        matched = [k for k in log.keys() if k.startswith(key_prefix)]
        if matched:
            step_info = log[matched[0]]
            if isinstance(step_info, dict) and step_info.get("status") in ("success", "skipped"):
                completed_steps += 1
    if completed_steps == 0 and status == "处理中":
        completed_steps = 1
    return int((completed_steps / 9) * 100)


def _get_current_stage(recon: DigitalReconstruction) -> str:
    status = recon.reconstruction_status
    if status == "待处理":
        return "等待处理"
    if status == "已完成":
        return "全部完成"
    if status == "失败":
        log = recon.reconstruction_log or {}
        error_step = log.get("error_step", 0)
        return f"失败于步骤{error_step}"

    log = recon.reconstruction_log or {}
    for idx in range(1, 10):
        key_prefix = f"step_{idx}_"
        matched = [k for k in log.keys() if k.startswith(key_prefix)]
        if matched:
            step_info = log[matched[0]]
            if isinstance(step_info, dict) and step_info.get("status") not in ("success", "skipped"):
                return RECONSTRUCTION_STAGES[min(idx, len(RECONSTRUCTION_STAGES) - 1)]
        else:
            if idx <= len(RECONSTRUCTION_STAGES):
                return RECONSTRUCTION_STAGES[idx - 1]
    return "处理中"


def _do_reconstruct(db: Session, site_id: int,
                    photo_urls: List[str],
                    method: str = '摄影测量',
                    generate_vr: bool = True) -> DigitalReconstruction:
    return _pipeline.run_full_pipeline(
        db, site_id=site_id,
        photo_urls=photo_urls,
        method=method,
        generate_vr=generate_vr
    )


# ==============================================
# 健康检查
# ==============================================

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "digital_exhibit", "port": DIGITAL_EXHIBIT_PORT}


# ==============================================
# 重建方法定义
# ==============================================

@router.get("/methods")
async def get_reconstruction_methods():
    """获取支持的重建方法列表及参数说明"""
    methods_list = []
    for key, info in RECONSTRUCTION_METHODS.items():
        methods_list.append({
            'code': key,
            'name': key,
            'description': info['description'],
            'params': info['params'],
        })
    return {
        "methods": methods_list,
        "stages": RECONSTRUCTION_STAGES,
    }


# ==============================================
# 遗址数字化重建
# ==============================================

@router.post("/sites/{site_id}/reconstruct")
def reconstruct_site(
    site_id: int,
    background_tasks: BackgroundTasks,
    request: Optional[DigitalReconstructionRequest] = None,
    async_mode: bool = Query(True, description="是否异步执行"),
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    photo_urls = []
    method = "摄影测量"
    generate_vr = True

    if request:
        photo_urls = request.photo_urls or []
        if request.method:
            method = request.method
        generate_vr = request.generate_vr if request.generate_vr is not None else True

    if method not in RECONSTRUCTION_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的重建方法: {method}, 有效方法: {list(RECONSTRUCTION_METHODS.keys())}"
        )

    if not photo_urls:
        raise HTTPException(status_code=400, detail="photo_urls不能为空")

    min_photos = RECONSTRUCTION_METHODS[method]["params"]["min_photos"]
    if len(photo_urls) < min_photos:
        raise HTTPException(
            status_code=400,
            detail=f"{method}至少需要{min_photos}张照片，当前{len(photo_urls)}张"
        )

    if async_mode:
        task_id = str(uuid.uuid4())

        def _bg_task():
            try:
                from common.database import SessionLocal
                bg_db = SessionLocal()
                _pipeline.run_full_pipeline(
                    bg_db, site_id=site_id,
                    photo_urls=photo_urls,
                    method=method,
                    generate_vr=generate_vr
                )
                bg_db.close()
                logger.info(f"后台重建完成 site_id={site_id}, task={task_id}")
            except Exception as e:
                logger.error(f"后台重建失败 site_id={site_id}, task={task_id}: {e}")

        background_tasks.add_task(_bg_task)
        return {
            "status": "accepted",
            "task_id": task_id,
            "site_id": site_id,
            "method": method,
            "photo_count": len(photo_urls),
            "generate_vr": generate_vr,
            "message": "数字化重建任务已提交",
        }
    else:
        try:
            recon = _do_reconstruct(db, site_id, photo_urls=photo_urls,
                                    method=method, generate_vr=generate_vr)
            return _format_reconstruction_response(recon, include_site=True)
        except Exception as e:
            logger.error(f"同步重建失败 site_id={site_id}: {e}")
            raise HTTPException(status_code=500, detail=f"重建失败: {str(e)}")


@router.get("/sites/{site_id}/status")
def get_reconstruction_status(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon:
        raise HTTPException(status_code=404, detail="未找到重建记录，请先触发重建")

    return {
        "site_id": site_id,
        "site_name": site.name,
        "reconstruction_id": recon.id,
        "status": recon.reconstruction_status,
        "method": recon.reconstruction_method,
        "progress_pct": _get_progress_pct(recon),
        "current_stage": _get_current_stage(recon),
        "photos_count": recon.photos_uploaded_count,
        "created_at": recon.created_at,
        "updated_at": recon.updated_at,
    }


@router.get("/sites/{site_id}/model")
def get_site_model_info(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    stages = metadata.get("stages", {})

    export_info = stages.get("export", {})
    dense_info = stages.get("dense_reconstruction", {})
    mesh_info = stages.get("mesh_generation", {})
    texture_info = stages.get("texture_baking", {})

    return {
        "site_id": site_id,
        "site_name": site.name,
        "reconstruction_id": recon.id,
        "method": recon.reconstruction_method,
        "gltf_model_url": recon.gltf_model_url,
        "glb_model_url": recon.glb_model_url,
        "texture_resolution": recon.texture_resolution,
        "statistics": {
            "point_cloud_count": recon.point_cloud_count,
            "mesh_face_count": recon.mesh_face_count,
            "mesh_face_count_raw": mesh_info.get("mesh_face_count"),
            "mesh_vertex_count": mesh_info.get("mesh_vertex_count"),
            "mesh_quality_score": mesh_info.get("mesh_quality_score"),
            "watertight": mesh_info.get("watertight"),
            "point_density_pts_per_m2": dense_info.get("average_point_density_pts_per_m2"),
            "texture_blend_quality": texture_info.get("texture_blend_quality"),
            "file_size_gltf_kb": export_info.get("file_size_gltf_kb"),
            "file_size_glb_kb": export_info.get("file_size_glb_kb"),
            "materials_count": export_info.get("materials_count"),
            "bbox": dense_info.get("point_cloud_stats"),
        },
        "vr_available": recon.vr_experience_url is not None,
        "vr_experience_url": recon.vr_experience_url,
        "overlay_with_irrigation": recon.overlay_with_irrigation,
    }


@router.get("/sites/{site_id}/vr")
def get_site_vr_experience(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    stages = metadata.get("stages", {})
    vr_info = stages.get("vr_experience")

    if not vr_info:
        raise HTTPException(status_code=404, detail="VR体验未生成，请重新触发重建并启用generate_vr")

    return {
        "site_id": site_id,
        "site_name": site.name,
        "reconstruction_id": recon.id,
        "vr_experience_url": vr_info.get("vr_experience_url"),
        "gltf_model_url": vr_info.get("gltf_model_url"),
        "supported_modes": vr_info.get("supported_modes", []),
        "overlay_layers": vr_info.get("overlay_layers", []),
        "walking_path_points_count": len(vr_info.get("walking_path_points", [])),
        "hotspots_count": len(vr_info.get("hotspots", [])),
        "irrigation_overlay": vr_info.get("irrigation_overlay", False),
        "scene_setup": vr_info.get("scene_setup", {}),
    }


@router.get("/sites/{site_id}/hotspots")
def get_site_hotspots(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    stages = metadata.get("stages", {})
    vr_info = stages.get("vr_experience")

    system_hotspots = []
    custom_hotspots = []

    if vr_info:
        system_hotspots = vr_info.get("hotspots", [])

    custom_data = metadata.get("custom_hotspots", [])
    if isinstance(custom_data, list):
        custom_hotspots = custom_data

    return {
        "site_id": site_id,
        "site_name": site.name,
        "system_hotspots": system_hotspots,
        "custom_hotspots": custom_hotspots,
        "total_count": len(system_hotspots) + len(custom_hotspots),
    }


class HotspotCreateRequest(BaseModel):
    title: str = Field(..., description="热点标题")
    description: str = Field(..., description="热点描述")
    type: str = Field("custom", description="热点类型")
    position: Dict[str, float] = Field(..., description="3D位置坐标 {x, y, z}")


@router.post("/sites/{site_id}/hotspots")
def create_site_hotspot(
    site_id: int,
    request: HotspotCreateRequest,
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    if not isinstance(metadata, dict):
        metadata = {}
    if "custom_hotspots" not in metadata or not isinstance(metadata["custom_hotspots"], list):
        metadata["custom_hotspots"] = []

    hotspot_id = f"custom_hs_{site_id}_{int(time.time() * 1000)}"
    new_hotspot = {
        "id": hotspot_id,
        "position": request.position,
        "title": request.title,
        "description": request.description,
        "type": request.type,
        "is_custom": True,
        "created_at": time.time(),
    }
    metadata["custom_hotspots"].append(new_hotspot)
    recon.model_metadata = metadata
    db.commit()
    db.refresh(recon)

    return {
        "status": "created",
        "hotspot": new_hotspot,
    }


@router.delete("/sites/{site_id}/hotspots/{hotspot_id}")
def delete_site_hotspot(
    site_id: int,
    hotspot_id: str,
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon:
        raise HTTPException(status_code=404, detail="重建记录不存在")

    metadata = recon.model_metadata or {}
    custom_hotspots = metadata.get("custom_hotspots", []) if isinstance(metadata, dict) else []

    filtered = [h for h in custom_hotspots if h.get("id") != hotspot_id]
    deleted = len(custom_hotspots) - len(filtered)

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"热点不存在: {hotspot_id}")

    metadata["custom_hotspots"] = filtered
    recon.model_metadata = metadata
    db.commit()

    return {
        "status": "deleted",
        "hotspot_id": hotspot_id,
        "deleted_count": deleted,
    }


@router.get("/sites/{site_id}/reconstruction-log")
def get_site_reconstruction_log(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon:
        raise HTTPException(status_code=404, detail="未找到重建记录")

    log = recon.reconstruction_log or {}

    steps_detail = []
    for idx in range(1, 10):
        key_prefix = f"step_{idx}_"
        matched = [k for k in log.keys() if k.startswith(key_prefix)]
        if matched:
            step_info = log[matched[0]]
            if isinstance(step_info, dict):
                steps_detail.append({
                    "step_index": idx,
                    "stage_name": step_info.get("stage"),
                    "status": step_info.get("status"),
                    "duration_sec": step_info.get("duration_sec"),
                    "timestamp": step_info.get("timestamp"),
                    "data_summary": {
                        k: v for k, v in (step_info.get("data") or {}).items()
                        if isinstance(v, (str, int, float, bool))
                    } if isinstance(step_info.get("data"), dict) else {}
                })

    return {
        "site_id": site_id,
        "site_name": site.name,
        "reconstruction_id": recon.id,
        "status": recon.reconstruction_status,
        "method": recon.reconstruction_method,
        "photo_count": log.get("photo_count"),
        "generate_vr": log.get("generate_vr"),
        "pipeline_started": log.get("pipeline_started"),
        "pipeline_completed": log.get("pipeline_completed"),
        "pipeline_failed": log.get("pipeline_failed"),
        "error": log.get("error"),
        "error_step": log.get("error_step"),
        "total_duration_sec": log.get("total_duration_sec"),
        "steps": steps_detail,
        "raw_log": log,
    }


@router.delete("/sites/{site_id}/model")
def delete_site_model(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon:
        raise HTTPException(status_code=404, detail="重建记录不存在")

    db.delete(recon)
    db.commit()

    logger.info(f"删除重建模型 site_id={site_id}, recon_id={recon.id}")

    return {
        "status": "deleted",
        "site_id": site_id,
        "reconstruction_id": recon.id,
        "message": "重建模型记录已删除",
    }


@router.get("/sites/{site_id}/overlay")
def get_site_irrigation_overlay(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    stages = metadata.get("stages", {})
    overlay_data = stages.get("irrigation_overlay")

    restoration = db.query(FunctionalRestoration).filter(
        FunctionalRestoration.site_id == site_id
    ).first()
    irrigation_available = restoration is not None and restoration.water_supply_range_geom is not None

    return {
        "site_id": site_id,
        "site_name": site.name,
        "overlay_available": overlay_data is not None,
        "overlay_enabled": recon.overlay_with_irrigation,
        "irrigation_data_available": irrigation_available,
        "overlay_config": overlay_data,
        "restoration_id": restoration.id if restoration else None,
        "original_irrigation_capacity": float(restoration.original_irrigation_capacity) if restoration else None,
        "actual_irrigation_capacity": float(restoration.actual_irrigation_capacity) if restoration else None,
    }


@router.post("/sites/{site_id}/toggle-overlay")
def toggle_site_irrigation_overlay(
    site_id: int,
    enabled: Optional[bool] = Body(None, description="是否启用，不传则切换当前状态"),
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()
    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    stages = metadata.get("stages", {})
    overlay_data = stages.get("irrigation_overlay")

    if not overlay_data:
        raise HTTPException(status_code=400, detail="灌溉区叠加数据不存在，请重新触发重建")

    new_state = enabled if enabled is not None else not recon.overlay_with_irrigation
    recon.overlay_with_irrigation = new_state

    if overlay_data and isinstance(overlay_data, dict):
        overlay_data["enabled"] = new_state

    recon.model_metadata = metadata
    db.commit()
    db.refresh(recon)

    return {
        "site_id": site_id,
        "overlay_enabled": recon.overlay_with_irrigation,
        "message": f"灌溉区叠加已{'启用' if new_state else '禁用'}",
    }


# ==============================================
# 遗址图库
# ==============================================

@router.get("/gallery")
def get_digital_gallery(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(20, ge=1, le=200, description="每页数量"),
    method: Optional[str] = Query(None, description="按重建方法筛选"),
    dynasty: Optional[str] = Query(None, description="按朝代筛选"),
    site_type: Optional[str] = Query(None, description="按遗址类型筛选"),
    db: Session = Depends(get_db)
):
    query = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.reconstruction_status == "已完成"
    )

    if method:
        query = query.filter(DigitalReconstruction.reconstruction_method == method)

    subq = db.query(WaterHeritageSite.id)
    if dynasty:
        subq = subq.filter(WaterHeritageSite.dynasty == dynasty)
    if site_type:
        subq = subq.filter(WaterHeritageSite.site_type == site_type)
    site_ids = [s[0] for s in subq.all()]
    if dynasty or site_type:
        query = query.filter(DigitalReconstruction.site_id.in_(site_ids))

    total = query.count()
    recons = query.order_by(DigitalReconstruction.updated_at.desc()).offset(skip).limit(limit).all()

    items = []
    for recon in recons:
        site = db.query(WaterHeritageSite).filter(
            WaterHeritageSite.id == recon.site_id
        ).first()
        metadata = recon.model_metadata or {}
        stages = metadata.get("stages", {})
        vr_info = stages.get("vr_experience")
        dense_info = stages.get("dense_reconstruction", {})

        item = {
            "reconstruction_id": recon.id,
            "site_id": recon.site_id,
            "site_name": site.name if site else f"Site {recon.site_id}",
            "site_type": site.site_type if site else None,
            "dynasty": site.dynasty if site else None,
            "longitude": site.longitude if site else None,
            "latitude": site.latitude if site else None,
            "method": recon.reconstruction_method,
            "point_cloud_count": recon.point_cloud_count,
            "mesh_face_count": recon.mesh_face_count,
            "glb_model_url": recon.glb_model_url,
            "vr_available": recon.vr_experience_url is not None,
            "vr_experience_url": recon.vr_experience_url,
            "overlay_with_irrigation": recon.overlay_with_irrigation,
            "bbox": dense_info.get("point_cloud_stats") if dense_info else None,
            "hotspots_count": len(vr_info.get("hotspots", [])) if vr_info else 0,
            "reconstructed_at": recon.updated_at,
        }
        items.append(item)

    return {
        "total_count": total,
        "returned_count": len(items),
        "skip": skip,
        "limit": limit,
        "items": items,
    }


# ==============================================
# 全局统计
# ==============================================

@router.get("/stats")
def get_digital_stats(db: Session = Depends(get_db)):
    all_recons = db.query(DigitalReconstruction).all()
    n = len(all_recons)

    if n == 0:
        return {
            "total_reconstructions": 0,
            "total_sites_reconstructed": 0,
            "status_distribution": {},
            "method_distribution": {},
            "avg_point_cloud_count": 0,
            "avg_mesh_face_count": 0,
            "vr_support_rate": 0.0,
            "irrigation_overlay_rate": 0.0,
            "texture_resolution_distribution": {},
            "avg_reconstruction_duration_sec": 0.0,
            "by_dynasty_distribution": {},
        }

    completed = [r for r in all_recons if r.reconstruction_status == "已完成"]
    unique_sites = len(set(r.site_id for r in all_recons))

    status_dist: Dict[str, int] = {}
    method_dist: Dict[str, int] = {}
    tex_dist: Dict[str, int] = {}
    for r in all_recons:
        status_dist[r.reconstruction_status] = status_dist.get(r.reconstruction_status, 0) + 1
        method_dist[r.reconstruction_method] = method_dist.get(r.reconstruction_method, 0) + 1
        if r.texture_resolution:
            tex_dist[r.texture_resolution] = tex_dist.get(r.texture_resolution, 0) + 1

    n_completed = len(completed)
    avg_points = 0
    avg_faces = 0
    vr_count = 0
    overlay_count = 0
    total_duration = 0.0
    valid_durations = 0

    site_dynasty_map = {}
    all_sites = db.query(WaterHeritageSite).all()
    for s in all_sites:
        site_dynasty_map[s.id] = s.dynasty
    dynasty_dist: Dict[str, int] = {}

    for r in completed:
        if r.point_cloud_count:
            avg_points += r.point_cloud_count
        if r.mesh_face_count:
            avg_faces += r.mesh_face_count
        if r.vr_experience_url:
            vr_count += 1
        if r.overlay_with_irrigation:
            overlay_count += 1

        log = r.reconstruction_log or {}
        dur = log.get("total_duration_sec")
        if dur and isinstance(dur, (int, float)):
            total_duration += float(dur)
            valid_durations += 1

        dynasty = site_dynasty_map.get(r.site_id)
        if dynasty:
            dynasty_dist[dynasty] = dynasty_dist.get(dynasty, 0) + 1

    avg_points = int(avg_points / n_completed) if n_completed > 0 else 0
    avg_faces = int(avg_faces / n_completed) if n_completed > 0 else 0
    vr_rate = round(vr_count / n_completed, 4) if n_completed > 0 else 0.0
    overlay_rate = round(overlay_count / n_completed, 4) if n_completed > 0 else 0.0
    avg_duration = round(total_duration / valid_durations, 2) if valid_durations > 0 else 0.0

    return {
        "total_reconstructions": n,
        "total_sites_reconstructed": unique_sites,
        "completed_count": n_completed,
        "processing_count": status_dist.get("处理中", 0),
        "failed_count": status_dist.get("失败", 0),
        "status_distribution": status_dist,
        "method_distribution": method_dist,
        "avg_point_cloud_count": avg_points,
        "avg_mesh_face_count": avg_faces,
        "vr_support_rate": vr_rate,
        "vr_enabled_count": vr_count,
        "irrigation_overlay_rate": overlay_rate,
        "irrigation_overlay_count": overlay_count,
        "texture_resolution_distribution": tex_dist,
        "avg_reconstruction_duration_sec": avg_duration,
        "by_dynasty_distribution": dynasty_dist,
    }


# ==============================================
# 照片质量深度评估与增强 API
# ==============================================

class PhotoQualityRequest(BaseModel):
    photo_urls: List[str] = Field(..., description="照片URL列表")


class EnhancePhotosRequest(BaseModel):
    photo_urls: List[str] = Field(..., description="照片URL列表")
    enhance_strategy: str = Field("auto", description="增强策略: auto|denoise|sr|full")


class GuaranteedReconstructionRequest(BaseModel):
    photo_urls: List[str] = Field(..., description="照片URL列表")
    method: str = Field("摄影测量", description="重建方法")
    min_quality_threshold: int = Field(60, ge=0, le=100, description="最低质量阈值")
    generate_vr: bool = Field(True, description="是否生成VR体验")


@router.get("/sites/{site_id}/photo-quality")
def get_photo_quality_report(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()

    photo_urls: List[str] = []
    if recon and recon.model_metadata:
        stages = recon.model_metadata.get("stages", {})
        preprocessing = stages.get("photo_preprocessing", {})
        photo_meta = preprocessing.get("photo_meta", [])
        photo_urls = [p.get("url", "") for p in photo_meta if p.get("url")]

    if not photo_urls:
        raise HTTPException(status_code=404, detail="未找到该遗址的照片数据，请先上传照片并触发重建")

    photos = [{"url": url, "id": f"photo_{i}"} for i, url in enumerate(photo_urls)]

    per_photo_quality: List[Dict[str, Any]] = []
    issue_statistics: Dict[str, int] = {
        "噪声": 0, "模糊": 0, "光照不均": 0, "低分辨率": 0
    }
    quality_scores: List[float] = []

    recommended_strategies = _enhancer.adaptive_enhancement_strategy(photos)

    for idx, photo in enumerate(photos):
        qm = _mvr_engine.evaluate_image_quality_metrics(photo)
        quality_scores.append(qm["overall_score"])

        for issue in qm["specific_issues"]:
            if issue in issue_statistics:
                issue_statistics[issue] += 1

        photo_id = photo.get("id", photo.get("url", f"photo_{idx}"))
        per_photo_quality.append({
            "photo_index": idx,
            "photo_url": photo.get("url"),
            "photo_id": photo_id,
            "quality_metrics": qm,
            "recommended_enhance_steps": recommended_strategies.get(photo_id, ["skip"]),
        })

    avg_quality = round(sum(quality_scores) / max(1, len(quality_scores)), 2)
    min_quality = round(min(quality_scores) if quality_scores else 0.0, 2)
    max_quality = round(max(quality_scores) if quality_scores else 0.0, 2)
    low_quality_count = sum(1 for s in quality_scores if s < 60)

    overall_diagnosis: List[str] = []
    if avg_quality < 60:
        overall_diagnosis.append("整体照片质量较差，强烈建议进行深度学习增强或重新拍摄")
    elif avg_quality < 75:
        overall_diagnosis.append("整体照片质量一般，建议进行选择性增强")
    else:
        overall_diagnosis.append("整体照片质量良好")

    if low_quality_count > len(quality_scores) * 0.3:
        overall_diagnosis.append(f"低质量照片比例过高（{low_quality_count}/{len(quality_scores)}），建议重新拍摄关键视角")

    common_issues = [k for k, v in issue_statistics.items() if v > len(quality_scores) * 0.3]
    if common_issues:
        overall_diagnosis.append(f"常见问题：{', '.join(common_issues)}")

    return {
        "site_id": site_id,
        "site_name": site.name,
        "total_photos": len(photos),
        "quality_statistics": {
            "avg_overall_score": avg_quality,
            "min_score": min_quality,
            "max_score": max_quality,
            "low_quality_count": low_quality_count,
            "low_quality_ratio": round(low_quality_count / max(1, len(quality_scores)), 4),
        },
        "issue_statistics": issue_statistics,
        "per_photo_quality": per_photo_quality,
        "overall_diagnosis": overall_diagnosis,
    }


@router.post("/sites/{site_id}/enhance-photos")
def enhance_site_photos(
    site_id: int,
    request: EnhancePhotosRequest,
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    if not request.photo_urls:
        raise HTTPException(status_code=400, detail="photo_urls不能为空")

    valid_strategies = ["auto", "denoise", "sr", "full"]
    if request.enhance_strategy not in valid_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的增强策略: {request.enhance_strategy}, 有效策略: {valid_strategies}"
        )

    photos = [{"url": url, "id": f"photo_{i}"} for i, url in enumerate(request.photo_urls)]

    if request.enhance_strategy == "full":
        skip_threshold = 101.0
    elif request.enhance_strategy == "denoise":
        for p in photos:
            p["force_denoise"] = True
        skip_threshold = 101.0
    elif request.enhance_strategy == "sr":
        for p in photos:
            p["force_sr"] = True
        skip_threshold = 101.0
    else:
        skip_threshold = 70.0

    result = _enhancer.run_full_enhancement_pipeline(photos, skip_if_quality_threshold=skip_threshold)

    enhanced_photo_urls: List[Dict[str, Any]] = []
    for idx, ep in enumerate(result["enhanced_photos"]):
        enhanced_photo_urls.append({
            "original_url": ep.get("url", request.photo_urls[idx] if idx < len(request.photo_urls) else ""),
            "enhanced_url": ep.get("enhanced_url", ""),
            "enhanced": ep.get("enhanced", False),
            "quality_before": ep.get("quality_before"),
            "quality_after": ep.get("quality_before", 0) + (
                result["pipeline_log"][idx].get("quality_improvement", 0)
                if idx < len(result["pipeline_log"]) else 0
            ),
        })

    quality_improvement = result["overall_quality_improvement"]

    return {
        "site_id": site_id,
        "site_name": site.name,
        "enhance_strategy": request.enhance_strategy,
        "total_photos": len(request.photo_urls),
        "enhanced_count": quality_improvement["enhanced_count"],
        "enhanced_photo_urls": enhanced_photo_urls,
        "quality_improvement": quality_improvement,
        "pipeline_log": result["pipeline_log"],
        "message": f"照片增强完成，共增强 {quality_improvement['enhanced_count']} 张照片",
    }


@router.get("/sites/{site_id}/view-coverage")
def get_view_coverage(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()

    photo_urls: List[str] = []
    if recon and recon.model_metadata:
        stages = recon.model_metadata.get("stages", {})
        preprocessing = stages.get("photo_preprocessing", {})
        photo_meta = preprocessing.get("photo_meta", [])
        photo_urls = [p.get("url", "") for p in photo_meta if p.get("url")]

    if not photo_urls:
        raise HTTPException(status_code=404, detail="未找到该遗址的照片数据")

    photos = [{"url": url, "id": f"photo_{i}"} for i, url in enumerate(photo_urls)]

    cluster_result = _mvr_engine.cluster_photo_viewpoints(photos)

    coverage_score = cluster_result["coverage_score"]
    recommendations: List[str] = []
    missing_view_angles: List[float] = []

    if coverage_score < 60:
        recommendations.append("视角覆盖度严重不足，建议大幅补充拍摄角度")
    elif coverage_score < 75:
        recommendations.append("视角覆盖度偏低，建议补充部分缺失视角")
    elif coverage_score < 85:
        recommendations.append("视角覆盖度一般，可选择性补充视角以提升质量")
    else:
        recommendations.append("视角覆盖度良好")

    viewpoint_features = cluster_result.get("viewpoint_features", [])
    if viewpoint_features:
        azimuths = sorted([vf["azimuth_deg"] for vf in viewpoint_features])
        gaps = []
        for i in range(len(azimuths)):
            next_i = (i + 1) % len(azimuths)
            gap = (azimuths[next_i] - azimuths[i]) % 360.0
            if gap > 45.0:
                mid_angle = (azimuths[i] + gap / 2.0) % 360.0
                gaps.append({
                    "start_angle": azimuths[i],
                    "end_angle": azimuths[next_i],
                    "gap_size_deg": round(gap, 2),
                    "suggested_shoot_angle": round(mid_angle, 2),
                })
                missing_view_angles.append(round(mid_angle, 2))

        if gaps:
            recommendations.append(
                f"建议在以下方位角补拍: {', '.join([str(g['suggested_shoot_angle']) + '°' for g in gaps[:5]])}"
            )
            if len(gaps) > 5:
                recommendations.append(f"还有 {len(gaps) - 5} 处较大视角间隙建议补充")

    clusters_detail = []
    for cluster_idx, cluster in enumerate(cluster_result["clusters"]):
        cluster_photos = []
        for photo_idx in cluster:
            if photo_idx < len(photos):
                cluster_photos.append({
                    "photo_index": photo_idx,
                    "photo_url": photos[photo_idx].get("url", ""),
                })
        clusters_detail.append({
            "cluster_id": cluster_idx,
            "photo_count": len(cluster),
            "photos": cluster_photos,
        })

    return {
        "site_id": site_id,
        "site_name": site.name,
        "total_photos": len(photos),
        "coverage_score": coverage_score,
        "coverage_grade": _guaranteed_reconstructor._grade_quality(coverage_score),
        "cluster_count": cluster_result["cluster_count"],
        "clusters": clusters_detail,
        "viewpoint_features": viewpoint_features,
        "gaps": gaps if 'gaps' in locals() else [],
        "missing_view_angles": missing_view_angles,
        "recommendations": recommendations,
    }


@router.post("/sites/{site_id}/reconstruct-guaranteed")
def reconstruct_site_guaranteed(
    site_id: int,
    request: GuaranteedReconstructionRequest,
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    if not request.photo_urls:
        raise HTTPException(status_code=400, detail="photo_urls不能为空")

    if request.method not in RECONSTRUCTION_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的重建方法: {request.method}, 有效方法: {list(RECONSTRUCTION_METHODS.keys())}"
        )

    min_photos = RECONSTRUCTION_METHODS[request.method]["params"]["min_photos"]
    if len(request.photo_urls) < min_photos:
        raise HTTPException(
            status_code=400,
            detail=f"{request.method}至少需要{min_photos}张照片，当前{len(request.photo_urls)}张"
        )

    photos = [{"url": url, "id": f"photo_{i}"} for i, url in enumerate(request.photo_urls)]

    try:
        result = _guaranteed_reconstructor.run_guaranteed_reconstruction(
            site_id=site_id,
            photos=photos,
            method=request.method,
            generate_vr=request.generate_vr,
            min_quality_threshold=float(request.min_quality_threshold),
        )

        quality = result["quality_assessment"]
        status = "quality_passed" if quality["pass_fail"] else "quality_warning"

        return {
            "site_id": site_id,
            "site_name": site.name,
            "status": status,
            "method": request.method,
            "generate_vr": request.generate_vr,
            "min_quality_threshold": request.min_quality_threshold,
            "reconstruction": result["reconstruction"],
            "quality_assessment": quality,
            "warnings": result["warnings"],
            "recommendations": result["recommendations"],
            "message": "质量保证重建完成" if quality["pass_fail"] else "重建完成但质量未达阈值，建议参考改进建议",
        }
    except Exception as e:
        logger.error(f"质量保证重建失败 site_id={site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"质量保证重建失败: {str(e)}")


@router.get("/sites/{site_id}/quality-assessment")
def get_reconstruction_quality_assessment(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()

    if not recon or recon.reconstruction_status != "已完成":
        raise HTTPException(status_code=404, detail="重建未完成或不存在")

    metadata = recon.model_metadata or {}
    stages = metadata.get("stages", {})

    photo_meta: List[Dict[str, Any]] = []
    preprocessing = stages.get("photo_preprocessing", {})
    if isinstance(preprocessing, dict):
        photo_meta = preprocessing.get("photo_meta", [])
    photo_urls = [p.get("url", "") for p in photo_meta if p.get("url")]
    photos = [{"url": url, "id": f"photo_{i}"} for i, url in enumerate(photo_urls)]

    dense_info = stages.get("dense_reconstruction", {})
    mesh_info = stages.get("mesh_generation", {})
    texture_info = stages.get("texture_baking", {})

    simulated_reconstruction = {
        "site_id": site_id,
        "method": recon.reconstruction_method,
        "generate_vr": recon.vr_experience_url is not None,
        "dense_point_cloud": {
            "point_count": recon.point_cloud_count or dense_info.get("dense_points_count", 0),
            "density_pts_per_m2": dense_info.get("average_point_density_pts_per_m2", 5000),
        },
        "mesh": {
            "face_count": recon.mesh_face_count or mesh_info.get("mesh_face_count", 0),
            "vertex_count": mesh_info.get("mesh_vertex_count", 0),
            "quality_score": mesh_info.get("mesh_quality_score", 0.7),
            "watertight": mesh_info.get("watertight", False),
            "method": mesh_info.get("method", "poisson"),
        },
        "texture": {
            "resolution": recon.texture_resolution or texture_info.get("texture_resolution", "2K"),
            "blend_quality": texture_info.get("texture_blend_quality", 0.7),
        },
        "coverage_score": 75.0,
        "fusion_quality_score": 0.75,
        "input_photo_count": recon.photos_uploaded_count or len(photos),
        "selected_photo_count": len(photos),
        "synthetic_view_count": 0,
        "avg_input_quality_before": 65.0,
        "avg_input_quality_after_enhance": 75.0,
    }

    quality_assessment = _guaranteed_reconstructor.assess_reconstruction_quality(
        simulated_reconstruction, photos
    )

    return {
        "site_id": site_id,
        "site_name": site.name,
        "reconstruction_id": recon.id,
        "reconstruction_method": recon.reconstruction_method,
        "reconstruction_status": recon.reconstruction_status,
        "quality_assessment": quality_assessment,
        "detailed_metrics": {
            "point_cloud_count": recon.point_cloud_count,
            "mesh_face_count": recon.mesh_face_count,
            "texture_resolution": recon.texture_resolution,
            "mesh_quality_score": mesh_info.get("mesh_quality_score"),
            "texture_blend_quality": texture_info.get("texture_blend_quality"),
            "point_density": dense_info.get("average_point_density_pts_per_m2"),
        },
    }


@router.get("/sites/{site_id}/recommendation")
def get_site_improvement_recommendations(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    recon = db.query(DigitalReconstruction).filter(
        DigitalReconstruction.site_id == site_id
    ).first()

    photo_urls: List[str] = []
    if recon and recon.model_metadata:
        stages = recon.model_metadata.get("stages", {})
        preprocessing = stages.get("photo_preprocessing", {})
        photo_meta = preprocessing.get("photo_meta", []) if isinstance(preprocessing, dict) else []
        photo_urls = [p.get("url", "") for p in photo_meta if p.get("url")]

    if not photo_urls:
        return {
            "site_id": site_id,
            "site_name": site.name,
            "has_photos": False,
            "recommendations": [
                "请先上传至少5张不同角度的遗址照片",
                "建议使用分辨率不低于1920x1080的相机拍摄",
                "拍摄时注意保持光照均匀，避免过曝或过暗",
                "建议环绕遗址每隔15-30度拍摄一张照片",
            ],
            "photos_to_enhance": [],
            "angles_to_reshoot": [],
        }

    photos = [{"url": url, "id": f"photo_{i}"} for i, url in enumerate(photo_urls)]

    quality_list: List[Dict[str, Any]] = []
    for idx, photo in enumerate(photos):
        qm = _mvr_engine.evaluate_image_quality_metrics(photo)
        quality_list.append({
            "photo_index": idx,
            "photo_url": photo.get("url"),
            "quality_metrics": qm,
        })

    cluster_result = _mvr_engine.cluster_photo_viewpoints(photos)

    strategies = _enhancer.adaptive_enhancement_strategy(photos)

    photos_to_enhance: List[Dict[str, Any]] = []
    for q in quality_list:
        qm = q["quality_metrics"]
        if qm["enhance_needed"] or qm["overall_score"] < 75:
            photo_id = photos[q["photo_index"]].get("id", photos[q["photo_index"]].get("url"))
            photos_to_enhance.append({
                "photo_index": q["photo_index"],
                "photo_url": q["photo_url"],
                "overall_score": qm["overall_score"],
                "issues": qm["specific_issues"],
                "recommended_steps": strategies.get(photo_id, ["auto"]),
                "priority": "high" if qm["overall_score"] < 50 else "medium",
            })

    angles_to_reshoot: List[Dict[str, Any]] = []
    viewpoint_features = cluster_result.get("viewpoint_features", [])
    if viewpoint_features:
        azimuths = sorted([vf["azimuth_deg"] for vf in viewpoint_features])
        for i in range(len(azimuths)):
            next_i = (i + 1) % len(azimuths)
            gap = (azimuths[next_i] - azimuths[i]) % 360.0
            if gap > 50.0:
                mid_angle = (azimuths[i] + gap / 2.0) % 360.0
                angles_to_reshoot.append({
                    "suggested_azimuth_deg": round(mid_angle, 2),
                    "gap_size_deg": round(gap, 2),
                    "priority": "high" if gap > 80 else "medium",
                    "suggestion": f"建议在方位角 {round(mid_angle, 1)}° 方向补拍2-3张照片",
                })

    recommendations: List[str] = []

    low_quality_count = sum(1 for q in quality_list if q["quality_metrics"]["overall_score"] < 60)
    if low_quality_count > 0:
        recommendations.append(
            f"有 {low_quality_count} 张照片质量低于阈值，建议先进行增强处理或重新拍摄"
        )

    if cluster_result["coverage_score"] < 75:
        recommendations.append(
            f"当前视角覆盖度 {cluster_result['coverage_score']:.1f}/100，建议补充缺失视角"
        )

    if photos_to_enhance:
        high_priority = [p for p in photos_to_enhance if p["priority"] == "high"]
        if high_priority:
            recommendations.append(
                f"有 {len(high_priority)} 张高优先级照片需要增强"
            )

    if angles_to_reshoot:
        high_priority_angles = [a for a in angles_to_reshoot if a["priority"] == "high"]
        if high_priority_angles:
            recommendations.append(
                f"有 {len(high_priority_angles)} 处大视角间隙需要补拍"
            )

    if recon and recon.reconstruction_status == "已完成":
        metadata = recon.model_metadata or {}
        stages = metadata.get("stages", {})
        mesh_info = stages.get("mesh_generation", {})
        if isinstance(mesh_info, dict):
            if not mesh_info.get("watertight", False):
                recommendations.append("当前网格非封闭，建议补充更多视角照片以提升网格质量")
            tex_info = stages.get("texture_baking", {})
            if isinstance(tex_info, dict) and tex_info.get("texture_resolution") in ("1K",):
                recommendations.append("当前纹理分辨率较低，建议使用更高分辨率原始照片重新重建")

    if not recommendations:
        recommendations.append("当前数字化质量良好，暂无特殊改进建议")

    return {
        "site_id": site_id,
        "site_name": site.name,
        "has_photos": True,
        "total_photos": len(photos),
        "current_coverage_score": cluster_result["coverage_score"],
        "avg_photo_quality": round(
            sum(q["quality_metrics"]["overall_score"] for q in quality_list) / max(1, len(quality_list)), 2
        ),
        "recommendations": recommendations,
        "photos_to_enhance": photos_to_enhance,
        "angles_to_reshoot": angles_to_reshoot,
        "enhancement_strategies": strategies,
    }


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DIGITAL_EXHIBIT_PORT)
