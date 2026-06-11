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

from .aquacrop_model import AgriculturalImpactAnalyzer, AquaCropSimplifiedModel
from .ensemble_simulation import (
    ParameterSensitivityAnalyzer,
    EnsembleAquaCropSimulator,
    _safe_mean,
    _safe_std,
    _safe_percentile,
    _safe_div,
    _clamp,
)

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


# ==============================================
# 敏感性分析与集合模拟 Pydantic 模型
# ==============================================

class _EnsembleRequest(BaseModel):
    n_members: int = Field(50, ge=20, le=200, description="集合成员数")
    method: str = Field('lhs', pattern='^(lhs|mc)$', description="抽样方法: lhs=拉丁超立方, mc=蒙特卡洛")
    with_observations: bool = Field(False, description="是否使用观测数据加权")


class _BatchEnsembleRequest(BaseModel):
    region: str = Field(..., max_length=64, description="区域名称")
    n_members: int = Field(50, ge=20, le=200, description="集合成员数")
    method: str = Field('lhs', pattern='^(lhs|mc)$', description="抽样方法")


# ==============================================
# 参数敏感性分析 API
# ==============================================

@router.get("/sites/{site_id}/impact/sensitivity")
def get_site_sensitivity(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    assessment = db.query(AgriculturalImpactAssessment).filter(
        AgriculturalImpactAssessment.site_id == site_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="请先执行农业影响评估")

    try:
        region = _get_site_region(site)
        dominant_crop = assessment.dominant_crop or '粟'
        dynasty_order = site.dynasty_order or 11

        baseline_yield = get_baseline_yield(region, dominant_crop, dynasty_order)
        climate = _analyzer._generate_historical_climate_series(
            region, dynasty_order,
            AquaCropSimplifiedModel(dominant_crop, region).total_growing_days
        )

        irrigation_capability = 0.0
        irrigation_area = float(assessment.total_influenced_area_mu) if assessment else 100.0
        if assessment.yield_simulation_raw:
            irrigation_capability = float(
                assessment.yield_simulation_raw.get('irrigation_capability_m3_per_day', 0.0)
            )

        analyzer = ParameterSensitivityAnalyzer(dominant_crop, region)
        baseline_params = dict(analyzer.param_baselines)

        local_results = analyzer.analyze_local_sensitivity(
            AquaCropSimplifiedModel,
            baseline_params,
            climate['precipitation_mm'],
            climate['et0_mm'],
            climate['temperatures_c'],
            irrigation_capability=irrigation_capability,
            irrigation_area=irrigation_area,
            baseline_yield=baseline_yield,
            n_levels=5,
        )

        report = analyzer.generate_sensitivity_report(local_results)

        return {
            "site_id": site_id,
            "site_name": site.name,
            "crop_type": dominant_crop,
            "region": region,
            "sensitivity_results": local_results,
            "report": report,
        }
    except Exception as e:
        logger.error(f"敏感性分析失败 site_id={site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"敏感性分析失败: {str(e)}")


# ==============================================
# 集合模拟 API
# ==============================================

@router.post("/sites/{site_id}/impact/ensemble")
def run_site_ensemble(
    site_id: int,
    request: Optional[_EnsembleRequest] = None,
    db: Session = Depends(get_db)
):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    assessment = db.query(AgriculturalImpactAssessment).filter(
        AgriculturalImpactAssessment.site_id == site_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="请先执行农业影响评估")

    try:
        n_members = request.n_members if request else 50
        method = request.method if request else 'lhs'

        region = _get_site_region(site)
        dominant_crop = assessment.dominant_crop or '粟'
        dynasty_order = site.dynasty_order or 11

        baseline_yield = get_baseline_yield(region, dominant_crop, dynasty_order)
        climate = _analyzer._generate_historical_climate_series(
            region, dynasty_order,
            AquaCropSimplifiedModel(dominant_crop, region).total_growing_days
        )

        irrigation_capability = 0.0
        irrigation_area = float(assessment.total_influenced_area_mu) if assessment else 100.0
        if assessment.yield_simulation_raw:
            irrigation_capability = float(
                assessment.yield_simulation_raw.get('irrigation_capability_m3_per_day', 0.0)
            )

        simulator = EnsembleAquaCropSimulator(dominant_crop, region, n_members=n_members)
        raw_results = simulator.run_ensemble_simulation(
            precip_list=climate['precipitation_mm'],
            et0_list=climate['et0_mm'],
            temp_list=climate['temperatures_c'],
            irrigation_capability=irrigation_capability,
            irrigation_area=irrigation_area,
            baseline_yield=baseline_yield,
            dynasty_order=dynasty_order,
            method=method,
        )

        observations = None
        if request and request.with_observations:
            observations = [baseline_yield * (1.0 + 0.1 * i) for i in range(-2, 3)]

        post_processed = simulator.post_process_ensemble_results(
            raw_results,
            include_members=True,
            observations=observations,
        )

        return {
            "site_id": site_id,
            "site_name": site.name,
            "crop_type": dominant_crop,
            "region": region,
            "config": post_processed.get('config', {}),
            "statistics": post_processed.get('statistics', {}),
            "post_processed": post_processed.get('post_processed', {}),
            "reliability": post_processed.get('reliability', {}),
            "members": post_processed.get('members', []),
        }
    except Exception as e:
        logger.error(f"集合模拟失败 site_id={site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"集合模拟失败: {str(e)}")


@router.get("/sites/{site_id}/impact/ensemble/uncertainty")
def get_site_uncertainty(site_id: int, db: Session = Depends(get_db)):
    site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="遗迹不存在")

    assessment = db.query(AgriculturalImpactAssessment).filter(
        AgriculturalImpactAssessment.site_id == site_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="请先执行农业影响评估")

    try:
        region = _get_site_region(site)
        dominant_crop = assessment.dominant_crop or '粟'
        dynasty_order = site.dynasty_order or 11

        baseline_yield = get_baseline_yield(region, dominant_crop, dynasty_order)
        climate = _analyzer._generate_historical_climate_series(
            region, dynasty_order,
            AquaCropSimplifiedModel(dominant_crop, region).total_growing_days
        )

        irrigation_capability = 0.0
        irrigation_area = float(assessment.total_influenced_area_mu) if assessment else 100.0
        if assessment.yield_simulation_raw:
            irrigation_capability = float(
                assessment.yield_simulation_raw.get('irrigation_capability_m3_per_day', 0.0)
            )

        sensitivity_analyzer = ParameterSensitivityAnalyzer(dominant_crop, region)
        baseline_params = dict(sensitivity_analyzer.param_baselines)
        local_sensitivity = sensitivity_analyzer.analyze_local_sensitivity(
            AquaCropSimplifiedModel,
            baseline_params,
            climate['precipitation_mm'],
            climate['et0_mm'],
            climate['temperatures_c'],
            irrigation_capability=irrigation_capability,
            irrigation_area=irrigation_area,
            baseline_yield=baseline_yield,
            n_levels=3,
        )

        simulator = EnsembleAquaCropSimulator(dominant_crop, region, n_members=30)
        raw_results = simulator.run_ensemble_simulation(
            precip_list=climate['precipitation_mm'],
            et0_list=climate['et0_mm'],
            temp_list=climate['temperatures_c'],
            irrigation_capability=irrigation_capability,
            irrigation_area=irrigation_area,
            baseline_yield=baseline_yield,
            dynasty_order=dynasty_order,
            method='lhs',
        )

        stats = raw_results.get('statistics', {})
        mean_yield = stats.get('mean_yield', baseline_yield)
        ci_lower = stats.get('ci_95_lower', mean_yield)
        ci_upper = stats.get('ci_95_upper', mean_yield)
        cv = stats.get('cv', 0.0)

        ci_width_pct = _safe_div(ci_upper - ci_lower, mean_yield, 0.0) * 100.0

        if cv < 0.10:
            reliability_level = "可靠"
        elif cv < 0.20:
            reliability_level = "较可靠"
        elif cv < 0.30:
            reliability_level = "较大"
        else:
            reliability_level = "大"

        total_sensitivity = sum(
            d.get('sensitivity', 0.0) for d in local_sensitivity.values()
        )
        param_uncertainty_contribution: Dict[str, float] = {}
        sorted_sensitivity = sorted(
            local_sensitivity.items(),
            key=lambda x: x[1].get('sensitivity', 0.0),
            reverse=True,
        )
        for param, data in sorted_sensitivity:
            param_uncertainty_contribution[param] = round(
                _safe_div(data.get('sensitivity', 0.0), total_sensitivity, 0.0) * 100.0,
                2,
            )

        n_members = raw_results.get('config', {}).get('n_members', 30)
        converged = raw_results.get('reliability', {}).get('pit_uniformity', 0.0) > 0.7
        suggestions = []
        if n_members < 50:
            suggestions.append("建议增加集合成员数至 50+ 以提高稳定性")
        if not converged:
            suggestions.append("集合尚未完全收敛，建议增加成员数或检查输入数据")
        if cv > 0.20:
            suggestions.append("不确定性较大，建议补充观测数据进行约束校准")
        if len(suggestions) == 0:
            suggestions.append("模拟结果可靠，当前配置满足要求")

        return {
            "site_id": site_id,
            "site_name": site.name,
            "crop_type": dominant_crop,
            "region": region,
            "uncertainty_summary": {
                "mean_yield_kg_per_mu": round(mean_yield, 2),
                "ci_95_lower": round(ci_lower, 2),
                "ci_95_upper": round(ci_upper, 2),
                "ci_width_pct": round(ci_width_pct, 2),
                "cv": round(cv, 4),
                "reliability_level": reliability_level,
            },
            "parameter_uncertainty_contribution_pct": param_uncertainty_contribution,
            "ensemble_diagnostics": {
                "n_members": n_members,
                "converged": converged,
                "pit_uniformity": raw_results.get('reliability', {}).get('pit_uniformity', 0.0),
                "outlier_count": raw_results.get('reliability', {}).get('outlier_count', 0),
            },
            "suggestions": suggestions,
        }
    except Exception as e:
        logger.error(f"不确定性报告生成失败 site_id={site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"不确定性报告生成失败: {str(e)}")


# ==============================================
# 全局敏感度矩阵 API
# ==============================================

@router.get("/sensitivity/matrix")
def get_global_sensitivity_matrix(db: Session = Depends(get_db)):
    try:
        crops = CROP_LIST
        regions = REGIONS
        params = ParameterSensitivityAnalyzer.SENSITIVITY_PARAMS

        matrix_data: List[Dict[str, Any]] = []
        param_baseline_data: Dict[str, Dict[str, Dict[str, float]]] = {}

        for crop in crops:
            param_baseline_data[crop] = {}
            for region in regions:
                try:
                    analyzer = ParameterSensitivityAnalyzer(crop, region)
                    baseline_params = dict(analyzer.param_baselines)
                    param_baseline_data[crop][region] = {
                        p: round(v, 4) for p, v in baseline_params.items()
                    }

                    dynasty_order = 11
                    baseline_yield = get_baseline_yield(region, crop, dynasty_order)
                    climate = _analyzer._generate_historical_climate_series(
                        region, dynasty_order,
                        AquaCropSimplifiedModel(crop, region).total_growing_days
                    )

                    local_sens = analyzer.analyze_local_sensitivity(
                        AquaCropSimplifiedModel,
                        baseline_params,
                        climate['precipitation_mm'],
                        climate['et0_mm'],
                        climate['temperatures_c'],
                        irrigation_capability=50.0,
                        irrigation_area=100.0,
                        baseline_yield=baseline_yield,
                        n_levels=3,
                    )

                    for param in params:
                        sens_data = local_sens.get(param, {})
                        matrix_data.append({
                            "crop": crop,
                            "region": region,
                            "parameter": param,
                            "sensitivity": sens_data.get('sensitivity', 0.0),
                            "pct_change": sens_data.get('pct_change', 0.0),
                            "rank": sens_data.get('rank', 0),
                        })
                except Exception:
                    for param in params:
                        matrix_data.append({
                            "crop": crop,
                            "region": region,
                            "parameter": param,
                            "sensitivity": 0.0,
                            "pct_change": 0.0,
                            "rank": 0,
                        })
                    continue

        return {
            "dimensions": {
                "crops": crops,
                "regions": regions,
                "parameters": params,
            },
            "matrix": matrix_data,
            "baseline_params": param_baseline_data,
        }
    except Exception as e:
        logger.error(f"全局敏感度矩阵生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"全局敏感度矩阵生成失败: {str(e)}")


# ==============================================
# 区域批量集合模拟 API
# ==============================================

@router.post("/ensemble/batch-region")
def run_batch_region_ensemble(
    request: _BatchEnsembleRequest,
    db: Session = Depends(get_db)
):
    region = request.region
    if region not in REGIONS:
        raise HTTPException(status_code=400, detail=f"无效的区域名称，可选: {REGIONS}")

    try:
        sites = db.query(WaterHeritageSite).all()
        region_sites = [s for s in sites if _get_site_region(s) == region]

        if not region_sites:
            return {
                "status": "completed",
                "region": region,
                "total_sites": 0,
                "successful": 0,
                "failed": 0,
                "results": [],
            }

        results: List[Dict[str, Any]] = []
        successful = 0
        failed = 0

        for site in region_sites:
            try:
                site_id = site.id
                assessment = db.query(AgriculturalImpactAssessment).filter(
                    AgriculturalImpactAssessment.site_id == site_id
                ).first()

                dominant_crop = assessment.dominant_crop if assessment else '粟'
                dynasty_order = site.dynasty_order or 11

                baseline_yield = get_baseline_yield(region, dominant_crop, dynasty_order)
                climate = _analyzer._generate_historical_climate_series(
                    region, dynasty_order,
                    AquaCropSimplifiedModel(dominant_crop, region).total_growing_days
                )

                irrigation_area = float(assessment.total_influenced_area_mu) if assessment else 100.0
                irrigation_capability = 0.0
                if assessment and assessment.yield_simulation_raw:
                    irrigation_capability = float(
                        assessment.yield_simulation_raw.get('irrigation_capability_m3_per_day', 0.0)
                    )

                simulator = EnsembleAquaCropSimulator(dominant_crop, region, n_members=request.n_members)
                raw_results = simulator.run_ensemble_simulation(
                    precip_list=climate['precipitation_mm'],
                    et0_list=climate['et0_mm'],
                    temp_list=climate['temperatures_c'],
                    irrigation_capability=irrigation_capability,
                    irrigation_area=irrigation_area,
                    baseline_yield=baseline_yield,
                    dynasty_order=dynasty_order,
                    method=request.method,
                )

                post_processed = simulator.post_process_ensemble_results(
                    raw_results, include_members=False
                )

                results.append({
                    "site_id": site_id,
                    "site_name": site.name,
                    "crop_type": dominant_crop,
                    "mean_yield": post_processed.get('statistics', {}).get('mean_yield', 0.0),
                    "cv": post_processed.get('statistics', {}).get('cv', 0.0),
                    "converged": post_processed.get('post_processed', {}).get('converged', False),
                })
                successful += 1
            except Exception:
                failed += 1
                continue

        return {
            "status": "completed",
            "region": region,
            "total_sites": len(region_sites),
            "successful": successful,
            "failed": failed,
            "results": results,
        }
    except Exception as e:
        logger.error(f"区域批量集合模拟失败 region={region}: {e}")
        raise HTTPException(status_code=500, detail=f"区域批量集合模拟失败: {str(e)}")


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGRICULTURE_IMPACT_PORT)
