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


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DIGITAL_EXHIBIT_PORT)
