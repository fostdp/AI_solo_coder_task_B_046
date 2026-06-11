"""
Agriculture Impact 微服务
负责：AquaCrop作物模拟、农业影响评估、受益区生成、产量数据CRUD
端口：8005
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import logging
import hashlib
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, APIRouter
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from geoalchemy2.shape import to_shape, from_shape
from shapely.geometry import mapping

from common.config import settings, channels
from common.database import get_db, init_db
from common.models import (
    WaterHeritageSite,
    AncientCropYield,
    AgriculturalImpactAssessment,
    DynastyDict,
)
from common.redis_client import pubsub
from pydantic import BaseModel, Field
from common.schemas import (
    AncientCropYieldCreate,
    AncientCropYieldResponse,
    AncientCropYieldDetail,
    AgriculturalImpactAssessmentResponse,
    AgriculturalImpactAssessmentDetail,
    AgricultureImpactRequest,
    BatchAgricultureRequest,
)


class _AncientCropYieldUpdate(BaseModel):
    region: Optional[str] = Field(None, max_length=64)
    crop_type: Optional[str] = Field(None, pattern='^(粟|稻|麦|黍|豆)$')
    dynasty_order: Optional[int] = None
    yield_baseline_kg_per_mu: Optional[float] = None
    yield_with_irrigation_kg_per_mu: Optional[float] = None
    growing_season_start: Optional[int] = Field(None, ge=1, le=12)
    growing_season_end: Optional[int] = Field(None, ge=1, le=12)
    kc_initial: Optional[float] = None
    kc_mid: Optional[float] = None
    kc_late: Optional[float] = None
from common.params.crop_params import (
    CROP_KC,
    CROP_LIST,
    BASELINE_YIELDS,
    get_baseline_yield,
)
from common.params.hydraulic_params import REGIONS

from .aquacrop_model import AgriculturalImpactAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agriculture_impact")

AGRICULTURE_IMPACT_PORT = 8005

app = FastAPI(
    title="古代水利工程遗迹-农业影响评估服务",
    description="负责AquaCrop作物模拟、农业影响评估、受益区生成、产量数据管理",
    version="3.0.0"
)

router = APIRouter(prefix="/api/v1/agriculture")

_analyzer = AgriculturalImpactAnalyzer()


# ==============================================
# 兼容：REGIONAL_CLIMATE 和 get_regional_climate
# ==============================================

_REGIONAL_CLIMATE_FALLBACK: Dict[str, Dict[str, float]] = {
    '中原地区': {'avg_temp_c': 14.0, 'seasonal_temp_amp': 12.5, 'annual_precipitation_mm': 650.0, 'avg_et0_mm_per_day': 3.2},
    '关中地区': {'avg_temp_c': 13.5, 'seasonal_temp_amp': 13.0, 'annual_precipitation_mm': 580.0, 'avg_et0_mm_per_day': 3.3},
    '江南地区': {'avg_temp_c': 17.0, 'seasonal_temp_amp': 10.5, 'annual_precipitation_mm': 1200.0, 'avg_et0_mm_per_day': 3.8},
    '巴蜀地区': {'avg_temp_c': 16.5, 'seasonal_temp_amp': 10.0, 'annual_precipitation_mm': 1100.0, 'avg_et0_mm_per_day': 3.6},
    '岭南地区': {'avg_temp_c': 20.5, 'seasonal_temp_amp': 8.5, 'annual_precipitation_mm': 1600.0, 'avg_et0_mm_per_day': 4.0},
    '江淮地区': {'avg_temp_c': 15.5, 'seasonal_temp_amp': 11.5, 'annual_precipitation_mm': 1000.0, 'avg_et0_mm_per_day': 3.5},
    '山东地区': {'avg_temp_c': 13.0, 'seasonal_temp_amp': 13.0, 'annual_precipitation_mm': 680.0, 'avg_et0_mm_per_day': 3.3},
    '河北地区': {'avg_temp_c': 12.0, 'seasonal_temp_amp': 13.5, 'annual_precipitation_mm': 550.0, 'avg_et0_mm_per_day': 3.2},
    '河东地区': {'avg_temp_c': 11.5, 'seasonal_temp_amp': 13.5, 'annual_precipitation_mm': 500.0, 'avg_et0_mm_per_day': 3.1},
    '河西地区': {'avg_temp_c': 8.5, 'seasonal_temp_amp': 14.0, 'annual_precipitation_mm': 150.0, 'avg_et0_mm_per_day': 3.8},
    '辽东地区': {'avg_temp_c': 8.0, 'seasonal_temp_amp': 14.0, 'annual_precipitation_mm': 700.0, 'avg_et0_mm_per_day': 3.0},
    '滇黔地区': {'avg_temp_c': 15.5, 'seasonal_temp_amp': 9.5, 'annual_precipitation_mm': 1100.0, 'avg_et0_mm_per_day': 3.5},
}


def _safe_get_regional_climate(region: str) -> Dict[str, float]:
    try:
        from common.params.climate_params import REGIONAL_CLIMATE, get_regional_climate
        result = get_regional_climate(region)
        if result and len(result) > 0:
            return result
    except Exception:
        pass
    return _REGIONAL_CLIMATE_FALLBACK.get(region, _REGIONAL_CLIMATE_FALLBACK['中原地区'])


# ==============================================
# 事件订阅
# ==============================================

def _on_heritage_imported(message: Dict[str, Any]):
    site_id = message.get('site_id')
    if not site_id:
        return
    logger.info(f"新遗迹导入，自动评估农业影响: site_id={site_id}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()
        _do_analyze(db, site_id)
        db.close()
    except Exception as e:
        logger.error(f"自动农业影响评估失败 site_id={site_id}: {e}")


def _on_restoration_completed(message: Dict[str, Any]):
    site_id = message.get('site_id')
    if not site_id:
        return
    logger.info(f"复原完成，触发农业影响评估: site_id={site_id}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()
        _do_analyze(db, site_id)
        db.close()
    except Exception as e:
        logger.error(f"复原后农业影响评估失败 site_id={site_id}: {e}")


def _on_batch_agriculture_requested(message: Dict[str, Any]):
    region = message.get('region')
    site_ids = message.get('site_ids')
    logger.info(f"收到批量农业评估请求: region={region}, site_ids={site_ids}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()
        success_ids = _analyzer.analyze_batch(db, region=region, site_ids=site_ids)
        db.close()
        logger.info(f"批量农业评估完成: {len(success_ids)} 个遗址成功")
    except Exception as e:
        logger.error(f"批量农业评估失败: {e}")


@app.on_event("startup")
async def startup_event():
    logger.info("Agriculture Impact 服务启动...")
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化异常: {e}")

    pubsub.subscribe(channels.HERITAGE_IMPORTED, _on_heritage_imported)
    pubsub.subscribe(channels.RESTORATION_COMPLETED, _on_restoration_completed)
    pubsub.subscribe(channels.BATCH_AGRICULTURE_REQUESTED, _on_batch_agriculture_requested)
    logger.info("Redis Pub/Sub 订阅完成")


# ==============================================
# 内部辅助函数
# ==============================================

def _get_site_region(site: WaterHeritageSite) -> str:
    idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
    return REGIONS[idx]


def _do_analyze(db: Session, site_id: int,
                crop_types: List[str] = None,
                scenario: str = 'typical') -> Optional[AgriculturalImpactAssessment]:
    assessment = _analyzer.analyze_site_impact(db, site_id, crop_types=crop_types, scenario=scenario)
    if assessment:
        pubsub.publish(channels.AGRICULTURE_IMPACT_COMPLETED, {
            "event_type": "agriculture_impact_completed",
            "site_id": site_id,
            "data": {
                "yield_increase_rate": float(assessment.yield_increase_rate),
                "annual_yield_increase_kg": float(assessment.annual_yield_increase_kg),
                "farmers_benefited_count": assessment.farmers_benefited_count,
                "dominant_crop": assessment.dominant_crop,
                "confidence_score": float(assessment.confidence_score),
            }
        })
    return assessment


def _format_crop_yield_response(yield_record: AncientCropYield) -> Dict:
    return {
        "id": yield_record.id,
        "region": yield_record.region,
        "crop_type": yield_record.crop_type,
        "dynasty_order": yield_record.dynasty_order,
        "yield_baseline_kg_per_mu": float(yield_record.yield_baseline_kg_per_mu),
        "yield_with_irrigation_kg_per_mu": float(yield_record.yield_with_irrigation_kg_per_mu),
        "growing_season_start": yield_record.growing_season_start,
        "growing_season_end": yield_record.growing_season_end,
        "kc_initial": float(yield_record.kc_initial),
        "kc_mid": float(yield_record.kc_mid),
        "kc_late": float(yield_record.kc_late),
        "created_at": yield_record.created_at,
    }


def _format_impact_response(assessment: AgriculturalImpactAssessment,
                            include_site: bool = False) -> Dict:
    result = {
        "id": assessment.id,
        "site_id": assessment.site_id,
        "dominant_crop": assessment.dominant_crop,
        "total_influenced_area_mu": float(assessment.total_influenced_area_mu),
        "yield_increase_rate": float(assessment.yield_increase_rate),
        "annual_yield_increase_kg": float(assessment.annual_yield_increase_kg),
        "farmers_benefited_count": assessment.farmers_benefited_count,
        "water_use_efficiency_kg_per_m3": float(assessment.water_use_efficiency_kg_per_m3),
        "yield_simulation_raw": assessment.yield_simulation_raw,
        "benefit_zone_geojson": assessment.benefit_zone_geojson,
        "confidence_score": float(assessment.confidence_score),
        "assessed_at": assessment.assessed_at,
        "created_at": assessment.created_at,
    }
    if include_site:
        from common.models import WaterHeritageSite
        from common.database import SessionLocal
        try:
            db_tmp = SessionLocal()
            site = db_tmp.query(WaterHeritageSite).filter(WaterHeritageSite.id == assessment.site_id).first()
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


# ==============================================
# 健康检查
# ==============================================

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "agriculture_impact", "port": AGRICULTURE_IMPACT_PORT}


# ==============================================
# AncientCropYield CRUD
# ==============================================

@router.get("/crop-yields", response_model=List[AncientCropYieldResponse])
def list_crop_yields(
    region: Optional[str] = Query(None, description="区域筛选"),
    crop_type: Optional[str] = Query(None, description="作物类型筛选"),
    dynasty_order: Optional[int] = Query(None, description="朝代顺序筛选"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(AncientCropYield)
    if region:
        query = query.filter(AncientCropYield.region == region)
    if crop_type:
        query = query.filter(AncientCropYield.crop_type == crop_type)
    if dynasty_order is not None:
        query = query.filter(AncientCropYield.dynasty_order == dynasty_order)
    records = query.order_by(AncientCropYield.region, AncientCropYield.crop_type, AncientCropYield.dynasty_order).offset(skip).limit(limit).all()
    return records


@router.get("/crop-yields/{yield_id}", response_model=AncientCropYieldDetail)
def get_crop_yield(yield_id: int, db: Session = Depends(get_db)):
    record = db.query(AncientCropYield).filter(AncientCropYield.id == yield_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="作物产量记录不存在")
    return record


@router.post("/crop-yields", response_model=AncientCropYieldResponse)
def create_crop_yield(data: AncientCropYieldCreate, db: Session = Depends(get_db)):
    record = AncientCropYield(**data.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"创建作物产量记录: region={data.region}, crop={data.crop_type}, dynasty={data.dynasty_order}")
    return record


@router.put("/crop-yields/{yield_id}", response_model=AncientCropYieldResponse)
def update_crop_yield(yield_id: int, data: _AncientCropYieldUpdate, db: Session = Depends(get_db)):
    record = db.query(AncientCropYield).filter(AncientCropYield.id == yield_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="作物产量记录不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    logger.info(f"更新作物产量记录: id={yield_id}")
    return record


@router.delete("/crop-yields/{yield_id}")
def delete_crop_yield(yield_id: int, db: Session = Depends(get_db)):
    record = db.query(AncientCropYield).filter(AncientCropYield.id == yield_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="作物产量记录不存在")
    db.delete(record)
    db.commit()
    logger.info(f"删除作物产量记录: id={yield_id}")
    return {"status": "deleted", "id": yield_id}


# ==============================================
# 农业影响评估
# ==============================================

@router.get("/sites/{site_id}/impact", response_model=AgriculturalImpactAssessmentDetail)
def get_site_impact(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")
    assessment = db.query(AgriculturalImpactAssessment).filter(
        AgriculturalImpactAssessment.site_id == site_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="未找到农业影响评估结果，请先触发评估")
    result = _format_impact_response(assessment, include_site=True)
    return result


@router.post("/sites/{site_id}/impact")
def analyze_site_impact_endpoint(
    site_id: int,
    background_tasks: BackgroundTasks,
    request: Optional[AgricultureImpactRequest] = None,
    async_mode: bool = Query(True, description="是否异步执行"),
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    crop_types = None
    scenario = 'typical'
    if request:
        crop_types = request.crop_types
        scenario = request.scenario or 'typical'

    if async_mode:
        pubsub.publish(channels.BATCH_AGRICULTURE_REQUESTED, {
            "event_type": "single_agriculture_request",
            "site_ids": [site_id],
            "crop_types": crop_types,
            "scenario": scenario,
        })
        return {"status": "accepted", "site_id": site_id, "message": "农业影响评估已提交"}
    else:
        assessment = _do_analyze(db, site_id, crop_types=crop_types, scenario=scenario)
        if not assessment:
            raise HTTPException(status_code=500, detail="农业影响评估失败")
        return _format_impact_response(assessment, include_site=True)


@router.get("/sites/{site_id}/impact/benefit-zone.geojson")
def get_benefit_zone_geojson(site_id: int, db: Session = Depends(get_db)):
    assessment = db.query(AgriculturalImpactAssessment).filter(
        AgriculturalImpactAssessment.site_id == site_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="未找到评估结果")
    if not assessment.benefit_zone_geojson:
        site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="遗迹不存在")
        from .aquacrop_model import AgriculturalImpactAnalyzer
        analyzer_tmp = AgriculturalImpactAnalyzer()
        region = _get_site_region(site)
        yield_rate = float(assessment.yield_increase_rate) if assessment else 0.25
        area = float(assessment.total_influenced_area_mu) if assessment else float(site.irrigation_area)
        geojson, _ = analyzer_tmp._generate_benefit_zones(site, area, yield_rate)
        return geojson
    return assessment.benefit_zone_geojson


# ==============================================
# 批量操作
# ==============================================

@router.post("/batch/region")
def batch_analyze_region(
    request: BatchAgricultureRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    region = request.region
    pubsub.publish(channels.BATCH_AGRICULTURE_REQUESTED, {
        "event_type": "batch_agriculture_request",
        "region": region,
        "trigger_network": request.trigger_network,
    })
    query = db.query(WaterHeritageSite)
    total = query.count()
    return {"status": "accepted", "region": region, "total_sites": total, "message": "批量农业评估已提交"}


# ==============================================
# 区域汇总
# ==============================================

@router.get("/regions/{region}/impact-summary")
def get_region_impact_summary(region: str, db: Session = Depends(get_db)):
    assessments = db.query(AgriculturalImpactAssessment).join(
        WaterHeritageSite,
        AgriculturalImpactAssessment.site_id == WaterHeritageSite.id
    ).all()

    region_assessments = []
    for a in assessments:
        site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == a.site_id).first()
        if site and _get_site_region(site) == region:
            region_assessments.append(a)

    if not region_assessments:
        return {
            "region": region,
            "total_sites_assessed": 0,
            "avg_yield_increase_rate": 0.0,
            "total_influenced_area_mu": 0.0,
            "total_annual_yield_increase_kg": 0.0,
            "total_farmers_benefited": 0,
            "dominant_crops": [],
            "avg_water_use_efficiency_kg_per_m3": 0.0,
            "avg_confidence_score": 0.0,
        }

    n = len(region_assessments)
    avg_yield_rate = sum(float(a.yield_increase_rate) for a in region_assessments) / n
    total_area = sum(float(a.total_influenced_area_mu) for a in region_assessments)
    total_yield_increase = sum(float(a.annual_yield_increase_kg) for a in region_assessments)
    total_farmers = sum(a.farmers_benefited_count for a in region_assessments)
    avg_wue = sum(float(a.water_use_efficiency_kg_per_m3) for a in region_assessments) / n
    avg_conf = sum(float(a.confidence_score) for a in region_assessments) / n

    crop_counts: Dict[str, int] = {}
    for a in region_assessments:
        crop = a.dominant_crop
        crop_counts[crop] = crop_counts.get(crop, 0) + 1
    dominant_crops = sorted(crop_counts.keys(), key=lambda c: crop_counts[c], reverse=True)[:3]

    return {
        "region": region,
        "total_sites_assessed": n,
        "avg_yield_increase_rate": round(avg_yield_rate, 4),
        "total_influenced_area_mu": round(total_area, 1),
        "total_annual_yield_increase_kg": round(total_yield_increase, 1),
        "total_farmers_benefited": total_farmers,
        "dominant_crops": dominant_crops,
        "avg_water_use_efficiency_kg_per_m3": round(avg_wue, 4),
        "avg_confidence_score": round(avg_conf, 4),
    }


# ==============================================
# 全系统统计
# ==============================================

@router.get("/stats")
def get_system_stats(db: Session = Depends(get_db)):
    assessments = db.query(AgriculturalImpactAssessment).all()
    n = len(assessments)

    if n == 0:
        return {
            "total_sites_assessed": 0,
            "avg_yield_increase_rate": 0.0,
            "total_influenced_area_mu": 0.0,
            "total_annual_yield_increase_kg": 0.0,
            "total_farmers_benefited": 0,
            "avg_water_use_efficiency_kg_per_m3": 0.0,
            "avg_confidence_score": 0.0,
            "by_dominant_crop": {},
            "high_confidence_count": 0,
            "assessments_with_benefit_zone": 0,
        }

    avg_yield_rate = sum(float(a.yield_increase_rate) for a in assessments) / n
    total_area = sum(float(a.total_influenced_area_mu) for a in assessments)
    total_yield = sum(float(a.annual_yield_increase_kg) for a in assessments)
    total_farmers = sum(a.farmers_benefited_count for a in assessments)
    avg_wue = sum(float(a.water_use_efficiency_kg_per_m3) for a in assessments) / n
    avg_conf = sum(float(a.confidence_score) for a in assessments) / n

    crop_counts: Dict[str, int] = {}
    for a in assessments:
        crop_counts[a.dominant_crop] = crop_counts.get(a.dominant_crop, 0) + 1

    high_conf_count = sum(1 for a in assessments if float(a.confidence_score) >= 0.8)
    zone_count = sum(1 for a in assessments if a.benefit_zone_geojson is not None)

    return {
        "total_sites_assessed": n,
        "avg_yield_increase_rate": round(avg_yield_rate, 4),
        "total_influenced_area_mu": round(total_area, 1),
        "total_annual_yield_increase_kg": round(total_yield, 1),
        "total_farmers_benefited": total_farmers,
        "avg_water_use_efficiency_kg_per_m3": round(avg_wue, 4),
        "avg_confidence_score": round(avg_conf, 4),
        "by_dominant_crop": crop_counts,
        "high_confidence_count": high_conf_count,
        "assessments_with_benefit_zone": zone_count,
    }


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGRICULTURE_IMPACT_PORT)
