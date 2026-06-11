"""
Network Analyzer 微服务
负责：水利工程群网络拓扑分析、节点中心性计算、协同效应评估、网络可视化GeoJSON
端口：8006
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

from common.config import settings, channels
from common.database import get_db, init_db
from common.models import (
    WaterHeritageSite,
    HydraulicNetworkAnalysis,
    NetworkMemberSite,
    AgriculturalImpactAssessment,
)
from common.redis_client import pubsub
from common.schemas import (
    HydraulicNetworkAnalysisResponse,
    HydraulicNetworkAnalysisDetail,
    NetworkMemberSiteResponse,
    NetworkMemberSiteDetail,
    NetworkAnalysisRequest,
    BatchNetworkRequest,
)
from common.params.hydraulic_params import REGIONS

from .network_graph import (
    HydraulicNetworkGraph,
    NetworkAnalyzerService,
    get_network_service,
)
from .network_completion import (
    HydrologicalNetworkCompletor,
    UncertaintyAwareNetworkAnalyzer,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("network_analyzer")

NETWORK_ANALYZER_PORT = 8006

app = FastAPI(
    title="古代水利工程遗迹-网络分析服务",
    description="负责水利工程群网络拓扑分析、节点中心性计算、协同效应评估、网络可视化GeoJSON生成",
    version="3.0.0"
)

router = APIRouter(prefix="/api/v1/network")

_analyzer_service: NetworkAnalyzerService = get_network_service()

_audit_log_store: Dict[int, List[Dict[str, Any]]] = {}
_completor_store: Dict[str, HydrologicalNetworkCompletor] = {}


# ==============================================
# 事件订阅
# ==============================================

def _on_batch_network_requested(message: Dict[str, Any]):
    """处理批量网络分析请求事件"""
    region = message.get('region')
    if not region:
        return
    analysis_depth = message.get('analysis_depth', 'deep')
    logger.info(f"收到批量网络分析请求: region={region}, depth={analysis_depth}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()
        result = _analyzer_service.run_full_analysis(
            db, region=region, analysis_depth=analysis_depth
        )
        db.close()
        logger.info(f"批量网络分析完成: region={region}, analysis_id={result.id}")
    except ValueError as ve:
        logger.warning(f"批量网络分析跳过: {ve}")
    except Exception as e:
        logger.error(f"批量网络分析失败 region={region}: {e}")


def _on_agriculture_impact_completed(message: Dict[str, Any]):
    """农业评估完成后触发网络分析（区域内至少5个遗址有评估结果）"""
    site_id = message.get('site_id')
    if not site_id:
        return
    logger.info(f"农业评估完成，检查是否触发网络分析: site_id={site_id}")
    try:
        from common.database import SessionLocal
        db = SessionLocal()

        site = db.query(WaterHeritageSite).filter(
            WaterHeritageSite.id == site_id
        ).first()
        if not site:
            db.close()
            return

        idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
        region = REGIONS[idx]

        all_sites = db.query(WaterHeritageSite).all()
        region_site_ids = []
        for s in all_sites:
            s_idx = int(hashlib.md5(s.name.encode()).hexdigest(), 16) % len(REGIONS)
            if REGIONS[s_idx] == region:
                region_site_ids.append(s.id)

        if len(region_site_ids) < 5:
            db.close()
            logger.info(f"区域 {region} 遗址数量不足5个，跳过自动网络分析")
            return

        assessed_count = db.query(AgriculturalImpactAssessment).filter(
            AgriculturalImpactAssessment.site_id.in_(region_site_ids)
        ).count()

        if assessed_count >= 5:
            logger.info(f"区域 {region} 已有 {assessed_count} 个遗址完成农业评估，触发网络分析")
            try:
                _analyzer_service.run_full_analysis(
                    db, region=region, analysis_depth='deep'
                )
                logger.info(f"自动网络分析完成: region={region}")
            except ValueError as ve:
                logger.warning(f"自动网络分析跳过: {ve}")
        else:
            logger.info(f"区域 {region} 农业评估完成数 {assessed_count} < 5，暂不触发")

        db.close()
    except Exception as e:
        logger.error(f"农业评估后触发网络分析失败 site_id={site_id}: {e}")


@app.on_event("startup")
async def startup_event():
    logger.info("Network Analyzer 服务启动...")
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化异常: {e}")

    pubsub.subscribe(channels.BATCH_NETWORK_REQUESTED, _on_batch_network_requested)
    pubsub.subscribe(channels.AGRICULTURE_IMPACT_COMPLETED, _on_agriculture_impact_completed)
    logger.info("Redis Pub/Sub 订阅完成")


# ==============================================
# 内部辅助函数
# ==============================================

def _get_site_region(site: WaterHeritageSite) -> str:
    idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
    return REGIONS[idx]


def _format_analysis_response(analysis: HydraulicNetworkAnalysis,
                              include_members: bool = False,
                              db: Session = None) -> Dict[str, Any]:
    result = {
        "id": analysis.id,
        "region": analysis.region,
        "total_nodes": analysis.total_nodes,
        "total_edges": analysis.total_edges,
        "network_connectivity": float(analysis.network_connectivity),
        "network_redundancy": float(analysis.network_redundancy),
        "avg_path_length": float(analysis.avg_path_length),
        "clustering_coefficient": float(analysis.clustering_coefficient),
        "synergy_score": float(analysis.synergy_score),
        "cascade_irrigation_efficiency": float(analysis.cascade_irrigation_efficiency),
        "flood_regulation_capacity": float(analysis.flood_regulation_capacity),
        "critical_nodes": analysis.critical_nodes,
        "network_edges_geojson": analysis.network_edges_geojson,
        "analyzed_at": analysis.analyzed_at,
        "created_at": analysis.created_at,
    }

    if include_members and db:
        members = db.query(NetworkMemberSite).filter(
            NetworkMemberSite.network_analysis_id == analysis.id
        ).all()
        member_list = []
        for m in members:
            site = db.query(WaterHeritageSite).filter(
                WaterHeritageSite.id == m.site_id
            ).first()
            member_dict = {
                "id": m.id,
                "network_analysis_id": m.network_analysis_id,
                "site_id": m.site_id,
                "node_degree": m.node_degree,
                "node_betweenness": float(m.node_betweenness),
                "node_closeness": float(m.node_closeness),
                "node_role": m.node_role,
                "created_at": m.created_at,
            }
            if site:
                member_dict["site"] = {
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
            member_list.append(member_dict)
        result["member_sites"] = member_list

    return result


def _get_synergy_level(score: float) -> str:
    if score >= 0.80:
        return '优秀'
    elif score >= 0.65:
        return '良好'
    elif score >= 0.50:
        return '中等'
    elif score >= 0.30:
        return '一般'
    else:
        return '较弱'


# ==============================================
# 健康检查
# ==============================================

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "network_analyzer", "port": NETWORK_ANALYZER_PORT}


# ==============================================
# 区域管理
# ==============================================

@router.get("/regions")
def list_regions_with_analysis(db: Session = Depends(get_db)):
    """列出所有有分析记录的区域"""
    results = db.query(
        HydraulicNetworkAnalysis.region,
        func.count(HydraulicNetworkAnalysis.id).label('analysis_count'),
        func.max(HydraulicNetworkAnalysis.analyzed_at).label('latest_analyzed_at')
    ).group_by(HydraulicNetworkAnalysis.region).all()

    regions_list = []
    for r in results:
        regions_list.append({
            "region": r.region,
            "analysis_count": r.analysis_count,
            "latest_analyzed_at": r.latest_analyzed_at,
        })

    all_regions = []
    for region in REGIONS:
        existing = next((x for x in regions_list if x['region'] == region), None)
        if existing:
            all_regions.append(existing)
        else:
            all_regions.append({
                "region": region,
                "analysis_count": 0,
                "latest_analyzed_at": None,
            })

    return {"regions": all_regions, "total": len(all_regions)}


# ==============================================
# 区域分析
# ==============================================

@router.post("/analyze/region")
def analyze_region(
    request: NetworkAnalysisRequest,
    background_tasks: BackgroundTasks,
    async_mode: bool = Query(True, description="是否异步执行"),
    db: Session = Depends(get_db)
):
    """触发区域网络分析"""
    region = request.region
    if region not in REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"无效区域: {region}，有效区域为: {', '.join(REGIONS)}"
        )

    if async_mode:
        pubsub.publish(channels.BATCH_NETWORK_REQUESTED, {
            "event_type": "single_network_request",
            "region": region,
            "site_ids": request.site_ids,
            "analysis_depth": request.analysis_depth,
        })
        return {
            "status": "accepted",
            "region": region,
            "site_ids": request.site_ids,
            "analysis_depth": request.analysis_depth,
            "message": "网络分析已提交"
        }
    else:
        try:
            analysis = _analyzer_service.run_full_analysis(
                db,
                region=region,
                site_ids=request.site_ids,
                analysis_depth=request.analysis_depth
            )
            return _format_analysis_response(analysis, include_members=True, db=db)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"网络分析失败: {e}")
            raise HTTPException(status_code=500, detail=f"网络分析失败: {str(e)}")


@router.get("/regions/{region}/latest")
def get_latest_analysis(
    region: str,
    include_members: bool = Query(False, description="是否包含成员节点"),
    db: Session = Depends(get_db)
):
    """获取区域最新分析结果"""
    if region not in REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"无效区域: {region}，有效区域为: {', '.join(REGIONS)}"
        )

    analysis = _analyzer_service.get_latest_for_region(db, region)
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"区域 {region} 暂无分析记录，请先触发分析"
        )

    return _format_analysis_response(analysis, include_members=include_members, db=db)


@router.get("/regions/{region}/history")
def get_region_analysis_history(
    region: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取区域历史分析列表（分页）"""
    if region not in REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"无效区域: {region}，有效区域为: {', '.join(REGIONS)}"
        )

    query = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.region == region
    ).order_by(HydraulicNetworkAnalysis.analyzed_at.desc())

    total = query.count()
    records = query.offset(skip).limit(limit).all()

    history_list = []
    for r in records:
        history_list.append({
            "id": r.id,
            "region": r.region,
            "total_nodes": r.total_nodes,
            "total_edges": r.total_edges,
            "network_connectivity": float(r.network_connectivity),
            "network_redundancy": float(r.network_redundancy),
            "synergy_score": float(r.synergy_score),
            "synergy_level": _get_synergy_level(float(r.synergy_score)),
            "cascade_irrigation_efficiency": float(r.cascade_irrigation_efficiency),
            "flood_regulation_capacity": float(r.flood_regulation_capacity),
            "analyzed_at": r.analyzed_at,
        })

    return {
        "region": region,
        "total": total,
        "skip": skip,
        "limit": limit,
        "history": history_list,
    }


# ==============================================
# 分析结果 CRUD
# ==============================================

@router.get("/analysis/{id}")
def get_analysis_detail(
    id: int,
    include_members: bool = Query(True, description="是否包含成员节点"),
    db: Session = Depends(get_db)
):
    """获取分析详情"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    return _format_analysis_response(analysis, include_members=include_members, db=db)


@router.delete("/analysis/{id}")
def delete_analysis(id: int, db: Session = Depends(get_db)):
    """删除分析记录"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    region = analysis.region
    db.delete(analysis)
    db.commit()
    logger.info(f"删除网络分析记录: id={id}, region={region}")

    return {"status": "deleted", "id": id, "region": region}


# ==============================================
# 网络可视化与节点
# ==============================================

@router.get("/analysis/{id}/network.geojson")
def get_analysis_geojson(id: int, db: Session = Depends(get_db)):
    """获取网络分析GeoJSON"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    if analysis.network_edges_geojson:
        return analysis.network_edges_geojson

    members = db.query(NetworkMemberSite).filter(
        NetworkMemberSite.network_analysis_id == id
    ).all()
    site_ids = [m.site_id for m in members]
    sites = db.query(WaterHeritageSite).filter(
        WaterHeritageSite.id.in_(site_ids)
    ).all() if site_ids else []

    graph = HydraulicNetworkGraph(analysis.region)
    graph.build_graph_from_sites(sites)
    return graph.generate_network_geojson()


@router.get("/analysis/{id}/nodes")
def get_analysis_nodes(
    id: int,
    role: Optional[str] = Query(None, description="按角色筛选: 核心枢纽/中转节点/终端节点/孤立节点"),
    min_degree: Optional[int] = Query(None, description="最小度筛选"),
    db: Session = Depends(get_db)
):
    """获取分析的成员节点列表（含中心性）"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    query = db.query(NetworkMemberSite).filter(
        NetworkMemberSite.network_analysis_id == id
    )

    if role:
        valid_roles = ['核心枢纽', '中转节点', '终端节点', '孤立节点']
        if role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"无效角色: {role}，有效值为: {', '.join(valid_roles)}"
            )
        query = query.filter(NetworkMemberSite.node_role == role)

    if min_degree is not None:
        query = query.filter(NetworkMemberSite.node_degree >= min_degree)

    members = query.order_by(NetworkMemberSite.node_degree.desc()).all()

    nodes_list = []
    for m in members:
        site = db.query(WaterHeritageSite).filter(
            WaterHeritageSite.id == m.site_id
        ).first()

        node_dict = {
            "id": m.id,
            "network_analysis_id": m.network_analysis_id,
            "site_id": m.site_id,
            "node_degree": m.node_degree,
            "node_betweenness": float(m.node_betweenness),
            "node_closeness": float(m.node_closeness),
            "node_role": m.node_role,
            "created_at": m.created_at,
        }

        if site:
            node_dict["site"] = {
                "id": site.id,
                "name": site.name,
                "site_type": site.site_type,
                "dynasty": site.dynasty,
                "longitude": site.longitude,
                "latitude": site.latitude,
                "irrigation_area": site.irrigation_area,
            }

        nodes_list.append(node_dict)

    return {
        "analysis_id": id,
        "region": analysis.region,
        "total_nodes": len(nodes_list),
        "nodes": nodes_list,
    }


@router.get("/analysis/{id}/critical-nodes")
def get_analysis_critical_nodes(id: int, db: Session = Depends(get_db)):
    """获取关键节点（关节点 + 度最高Top10）"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    critical_data = analysis.critical_nodes or {}
    articulation_ids = critical_data.get('articulation_points', [])
    top_degree_ids = critical_data.get('top_degree_nodes', [])
    all_critical_ids = critical_data.get('all_critical', [])

    members = db.query(NetworkMemberSite).filter(
        NetworkMemberSite.network_analysis_id == id
    ).all()
    member_map = {m.site_id: m for m in members}

    articulation_nodes = []
    for sid in articulation_ids:
        m = member_map.get(sid)
        if m:
            site = db.query(WaterHeritageSite).filter(
                WaterHeritageSite.id == sid
            ).first()
            articulation_nodes.append({
                "site_id": sid,
                "name": site.name if site else "",
                "node_degree": m.node_degree,
                "node_betweenness": float(m.node_betweenness),
                "node_role": m.node_role,
                "longitude": site.longitude if site else None,
                "latitude": site.latitude if site else None,
            })

    top_degree_nodes = []
    for sid in top_degree_ids:
        m = member_map.get(sid)
        if m:
            site = db.query(WaterHeritageSite).filter(
                WaterHeritageSite.id == sid
            ).first()
            top_degree_nodes.append({
                "site_id": sid,
                "name": site.name if site else "",
                "node_degree": m.node_degree,
                "node_betweenness": float(m.node_betweenness),
                "node_role": m.node_role,
                "longitude": site.longitude if site else None,
                "latitude": site.latitude if site else None,
            })

    return {
        "analysis_id": id,
        "region": analysis.region,
        "articulation_points": articulation_nodes,
        "articulation_count": len(articulation_nodes),
        "top_degree_nodes": top_degree_nodes,
        "top_degree_count": len(top_degree_nodes),
        "total_critical": len(all_critical_ids),
    }


# ==============================================
# 批量操作
# ==============================================

@router.post("/batch")
def batch_analyze_regions(
    request: BatchNetworkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """批量分析多个区域"""
    region = request.region
    if region not in REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"无效区域: {region}，有效区域为: {', '.join(REGIONS)}"
        )

    pubsub.publish(channels.BATCH_NETWORK_REQUESTED, {
        "event_type": "batch_network_request",
        "region": region,
        "analysis_depth": request.analysis_depth,
    })

    query = db.query(WaterHeritageSite)
    total_sites = 0
    all_sites = query.all()
    for site in all_sites:
        idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
        if REGIONS[idx] == region:
            total_sites += 1

    return {
        "status": "accepted",
        "region": region,
        "total_sites": total_sites,
        "analysis_depth": request.analysis_depth,
        "message": "批量网络分析已提交"
    }


# ==============================================
# 跨区域对比
# ==============================================

@router.get("/cross-region/summary")
def get_cross_region_summary(db: Session = Depends(get_db)):
    """跨区域网络对比（12区域协同得分排名）"""
    region_latest = {}

    for region in REGIONS:
        latest = db.query(HydraulicNetworkAnalysis).filter(
            HydraulicNetworkAnalysis.region == region
        ).order_by(HydraulicNetworkAnalysis.analyzed_at.desc()).first()

        if latest:
            region_latest[region] = {
                "region": region,
                "analysis_id": latest.id,
                "total_nodes": latest.total_nodes,
                "total_edges": latest.total_edges,
                "network_connectivity": float(latest.network_connectivity),
                "network_redundancy": float(latest.network_redundancy),
                "avg_path_length": float(latest.avg_path_length),
                "clustering_coefficient": float(latest.clustering_coefficient),
                "synergy_score": float(latest.synergy_score),
                "synergy_level": _get_synergy_level(float(latest.synergy_score)),
                "cascade_irrigation_efficiency": float(latest.cascade_irrigation_efficiency),
                "flood_regulation_capacity": float(latest.flood_regulation_capacity),
                "analyzed_at": latest.analyzed_at,
            }
        else:
            region_latest[region] = {
                "region": region,
                "analysis_id": None,
                "total_nodes": 0,
                "total_edges": 0,
                "network_connectivity": 0.0,
                "network_redundancy": 0.0,
                "avg_path_length": 0.0,
                "clustering_coefficient": 0.0,
                "synergy_score": 0.0,
                "synergy_level": "暂无数据",
                "cascade_irrigation_efficiency": 0.0,
                "flood_regulation_capacity": 0.0,
                "analyzed_at": None,
            }

    ranked_by_synergy = sorted(
        region_latest.values(),
        key=lambda x: x['synergy_score'],
        reverse=True
    )

    for i, item in enumerate(ranked_by_synergy, 1):
        item['rank'] = i

    ranked_by_connectivity = sorted(
        [r for r in region_latest.values() if r['total_nodes'] > 0],
        key=lambda x: x['network_connectivity'],
        reverse=True
    )

    return {
        "total_regions": len(REGIONS),
        "analyzed_regions": sum(1 for r in region_latest.values() if r['analysis_id'] is not None),
        "ranked_by_synergy": ranked_by_synergy,
        "ranked_by_connectivity": ranked_by_connectivity,
        "avg_synergy_score": round(
            sum(r['synergy_score'] for r in region_latest.values() if r['analysis_id']) /
            max(1, sum(1 for r in region_latest.values() if r['analysis_id'])),
            4
        ),
        "avg_connectivity": round(
            sum(r['network_connectivity'] for r in region_latest.values() if r['analysis_id']) /
            max(1, sum(1 for r in region_latest.values() if r['analysis_id'])),
            4
        ),
    }


# ==============================================
# 全局统计
# ==============================================

@router.get("/stats")
def get_global_stats(db: Session = Depends(get_db)):
    """全局统计（平均连通度、平均协同得分、关键节点总数等）"""
    all_analyses = db.query(HydraulicNetworkAnalysis).all()
    total_analyses = len(all_analyses)

    if total_analyses == 0:
        return {
            "total_analyses": 0,
            "unique_regions": 0,
            "total_nodes_all": 0,
            "total_edges_all": 0,
            "avg_network_connectivity": 0.0,
            "avg_network_redundancy": 0.0,
            "avg_synergy_score": 0.0,
            "avg_cascade_efficiency": 0.0,
            "avg_flood_regulation": 0.0,
            "total_critical_nodes": 0,
            "total_articulation_points": 0,
            "synergy_level_distribution": {},
            "by_region": {},
        }

    unique_regions = len(set(a.region for a in all_analyses))
    total_nodes_all = sum(a.total_nodes for a in all_analyses)
    total_edges_all = sum(a.total_edges for a in all_analyses)

    avg_connectivity = sum(float(a.network_connectivity) for a in all_analyses) / total_analyses
    avg_redundancy = sum(float(a.network_redundancy) for a in all_analyses) / total_analyses
    avg_synergy = sum(float(a.synergy_score) for a in all_analyses) / total_analyses
    avg_cascade = sum(float(a.cascade_irrigation_efficiency) for a in all_analyses) / total_analyses
    avg_flood = sum(float(a.flood_regulation_capacity) for a in all_analyses) / total_analyses

    total_critical = 0
    total_articulation = 0
    synergy_level_dist: Dict[str, int] = {
        '优秀': 0, '良好': 0, '中等': 0, '一般': 0, '较弱': 0
    }

    by_region_stats: Dict[str, Dict] = {}

    for a in all_analyses:
        level = _get_synergy_level(float(a.synergy_score))
        synergy_level_dist[level] = synergy_level_dist.get(level, 0) + 1

        if a.critical_nodes:
            total_critical += len(a.critical_nodes.get('all_critical', []))
            total_articulation += len(a.critical_nodes.get('articulation_points', []))

        if a.region not in by_region_stats:
            by_region_stats[a.region] = {
                "analysis_count": 0,
                "latest_synergy": 0.0,
                "total_nodes": 0,
            }
        by_region_stats[a.region]['analysis_count'] += 1
        by_region_stats[a.region]['latest_synergy'] = max(
            by_region_stats[a.region]['latest_synergy'],
            float(a.synergy_score)
        )
        by_region_stats[a.region]['total_nodes'] = max(
            by_region_stats[a.region]['total_nodes'],
            a.total_nodes
        )

    return {
        "total_analyses": total_analyses,
        "unique_regions": unique_regions,
        "total_nodes_all": total_nodes_all,
        "total_edges_all": total_edges_all,
        "avg_network_connectivity": round(avg_connectivity, 4),
        "avg_network_redundancy": round(avg_redundancy, 4),
        "avg_synergy_score": round(avg_synergy, 4),
        "avg_cascade_efficiency": round(avg_cascade, 4),
        "avg_flood_regulation": round(avg_flood, 4),
        "total_critical_nodes": total_critical,
        "total_articulation_points": total_articulation,
        "synergy_level_distribution": synergy_level_dist,
        "by_region": by_region_stats,
    }


# ==============================================
# 水系补全与不确定性分析 API
# ==============================================

@router.get("/regions/{region}/completion")
def get_region_completion_suggestions(
    region: str,
    max_distance_km: float = Query(50, ge=1, le=200, description="最大搜索距离(km)"),
    db: Session = Depends(get_db)
):
    """获取区域水系补全建议（候选边列表、置信度、证据分）"""
    if region not in REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"无效区域: {region}，有效区域为: {', '.join(REGIONS)}"
        )

    try:
        sites = _analyzer_service._load_sites_in_region(db, region)
        if not sites or len(sites) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"区域 {region} 内遗址数量不足（至少需要2个）"
            )

        completor = HydrologicalNetworkCompletor(region)
        _completor_store[region] = completor

        hydrology_extract = completor.extract_known_hydrology(sites)
        known_edges = hydrology_extract['known_edges']
        inferred_edges = completor.infer_missing_connections(sites, known_edges, max_distance_km=max_distance_km)

        return {
            "region": region,
            "total_sites": len(sites),
            "known_edges": len(known_edges),
            "inferred_edge_count": len(inferred_edges),
            "inferred_river_nodes": hydrology_extract['inferred_river_nodes'],
            "candidate_edges": inferred_edges,
            "completion_threshold": completor.completion_threshold,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取水系补全建议失败 region={region}: {e}")
        raise HTTPException(status_code=500, detail=f"获取水系补全建议失败: {str(e)}")


@router.post("/{analysis_id}/apply-corrections")
def apply_expert_corrections(
    analysis_id: int,
    request_body: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """执行专家修正（添加边/删除边/改角色），返回修正后分析+审计日志"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == analysis_id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    corrections = request_body.get("corrections", [])
    expert_id = request_body.get("expert_id", "unknown")

    if not isinstance(corrections, list):
        raise HTTPException(status_code=400, detail="corrections 必须是列表")

    try:
        members = db.query(NetworkMemberSite).filter(
            NetworkMemberSite.network_analysis_id == analysis_id
        ).all()
        site_ids = [m.site_id for m in members]
        sites = db.query(WaterHeritageSite).filter(
            WaterHeritageSite.id.in_(site_ids)
        ).all() if site_ids else []

        graph = HydraulicNetworkGraph(analysis.region)
        graph.build_graph_from_sites(sites)

        node_dict = {}
        for idx, node_info in graph.nodes.items():
            member = next((m for m in members if m.site_id == node_info.get('id')), None)
            node_dict[idx] = {
                **node_info,
                'role': member.node_role if member else '终端节点',
            }

        graph_data = {
            'edges': [dict(e) for e in graph.edges],
            'nodes': node_dict,
        }

        for corr in corrections:
            corr['expert_id'] = expert_id

        completor = _completor_store.get(analysis.region)
        if not completor:
            completor = HydrologicalNetworkCompletor(analysis.region)
            _completor_store[analysis.region] = completor

        result = completor.apply_expert_correction(graph_data, corrections)

        if analysis_id not in _audit_log_store:
            _audit_log_store[analysis_id] = []
        _audit_log_store[analysis_id].extend(result['audit_log'])

        return {
            "analysis_id": analysis_id,
            "correction_count": len(corrections),
            "audit_log": result['audit_log'],
            "corrected_graph_summary": {
                "total_edges": len(result['graph']['edges']),
                "total_nodes": len(result['graph']['nodes']),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"应用专家修正失败 analysis_id={analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"应用专家修正失败: {str(e)}")


@router.get("/{analysis_id}/uncertainty")
def get_network_uncertainty(
    analysis_id: int,
    db: Session = Depends(get_db)
):
    """不确定性分析：各指标P5/P50/P95区间、节点角色概率分布、置信度报告"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == analysis_id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    try:
        members = db.query(NetworkMemberSite).filter(
            NetworkMemberSite.network_analysis_id == analysis_id
        ).all()
        site_ids = [m.site_id for m in members]
        sites = db.query(WaterHeritageSite).filter(
            WaterHeritageSite.id.in_(site_ids)
        ).all() if site_ids else []

        graph = HydraulicNetworkGraph(analysis.region)
        graph.build_graph_from_sites(sites)

        analyzer = UncertaintyAwareNetworkAnalyzer(graph)
        mc_result = analyzer.monte_carlo_network_sampling(n_samples=200, seed=42)
        robustness = analyzer.calculate_robustness_metrics(mc_result)
        node_role_probs = analyzer.propagate_edge_uncertainty_to_node_roles()
        confidence_report = analyzer.generate_completion_confidence_report()

        def _extract_interval(metric_data: Dict) -> Dict:
            return {
                "p5": metric_data.get("p5"),
                "p50": metric_data.get("p50"),
                "p95": metric_data.get("p95"),
                "mean": metric_data.get("mean"),
                "std": metric_data.get("std"),
            }

        return {
            "analysis_id": analysis_id,
            "metric_intervals": {
                "connectivity": _extract_interval(mc_result.get("connectivity", {})),
                "redundancy": _extract_interval(mc_result.get("redundancy", {})),
                "cascade_efficiency": _extract_interval(mc_result.get("cascade_efficiency", {})),
                "synergy_score": _extract_interval(mc_result.get("synergy_score", {})),
            },
            "node_role_probabilities": node_role_probs,
            "robustness_metrics": robustness,
            "confidence_report": {
                "edge_source_distribution": confidence_report.get("edge_source_distribution", {}),
                "low_confidence_edge_count": confidence_report.get("low_confidence_edge_count", 0),
                "questionable_node_count": confidence_report.get("questionable_node_count", 0),
                "metric_reliability": confidence_report.get("metric_reliability", {}),
                "recommendations": confidence_report.get("recommendations", []),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取不确定性分析失败 analysis_id={analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"获取不确定性分析失败: {str(e)}")


@router.post("/{analysis_id}/monte-carlo")
def run_monte_carlo_sampling(
    analysis_id: int,
    request_body: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """运行指定数量的蒙特卡洛采样，返回详细分布数据"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == analysis_id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    n_samples = int(request_body.get("n_samples", 200))
    seed = int(request_body.get("seed", 42))

    if n_samples < 10:
        raise HTTPException(status_code=400, detail="n_samples 至少为 10")
    if n_samples > 2000:
        raise HTTPException(status_code=400, detail="n_samples 最多为 2000")

    try:
        members = db.query(NetworkMemberSite).filter(
            NetworkMemberSite.network_analysis_id == analysis_id
        ).all()
        site_ids = [m.site_id for m in members]
        sites = db.query(WaterHeritageSite).filter(
            WaterHeritageSite.id.in_(site_ids)
        ).all() if site_ids else []

        graph = HydraulicNetworkGraph(analysis.region)
        graph.build_graph_from_sites(sites)

        analyzer = UncertaintyAwareNetworkAnalyzer(graph)
        mc_result = analyzer.monte_carlo_network_sampling(n_samples=n_samples, seed=seed)
        robustness = analyzer.calculate_robustness_metrics(mc_result)

        samples_detail = {}
        for metric in ['connectivity', 'redundancy', 'cascade_efficiency', 'synergy_score']:
            data = mc_result.get(metric, {})
            samples_detail[metric] = {
                "mean": data.get("mean"),
                "std": data.get("std"),
                "p5": data.get("p5"),
                "p50": data.get("p50"),
                "p95": data.get("p95"),
                "samples": data.get("samples", [])[:100],
                "sample_count": len(data.get("samples", [])),
            }

        return {
            "analysis_id": analysis_id,
            "n_samples": n_samples,
            "seed": seed,
            "samples_detail": samples_detail,
            "robustness_metrics": robustness,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"蒙特卡洛采样失败 analysis_id={analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"蒙特卡洛采样失败: {str(e)}")


@router.get("/{analysis_id}/audit-log")
def get_analysis_audit_log(
    analysis_id: int,
    db: Session = Depends(get_db)
):
    """返回专家修正的完整审计轨迹（含专家ID、时间、理由、置信度）"""
    analysis = db.query(HydraulicNetworkAnalysis).filter(
        HydraulicNetworkAnalysis.id == analysis_id
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    audit_log = _audit_log_store.get(analysis_id, [])

    return {
        "analysis_id": analysis_id,
        "region": analysis.region,
        "total_corrections": len(audit_log),
        "audit_log": audit_log,
    }


@router.get("/regions/{region}/completion-quality")
def get_completion_quality(
    region: str,
    db: Session = Depends(get_db)
):
    """返回补全质量评估结果（密度变化率、补后边占比等）"""
    if region not in REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"无效区域: {region}，有效区域为: {', '.join(REGIONS)}"
        )

    try:
        sites = _analyzer_service._load_sites_in_region(db, region)
        if not sites or len(sites) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"区域 {region} 内遗址数量不足（至少需要2个）"
            )

        original_graph = HydraulicNetworkGraph(region)
        original_graph.build_graph_from_sites(sites)
        original_data = {
            'edges': [dict(e) for e in original_graph.edges],
            'nodes': dict(original_graph.nodes),
        }

        completor = _completor_store.get(region)
        if not completor:
            completor = HydrologicalNetworkCompletor(region)
            _completor_store[region] = completor

        prior_network = completor.build_hydrological_prior_network(region, sites)
        completed_data = {
            'edges': prior_network['edges'],
            'nodes': prior_network['node_metadata'],
        }

        quality = completor.evaluate_completion_quality(original_data, completed_data)

        return {
            "region": region,
            "total_sites": len(sites),
            "quality_metrics": quality,
            "node_metadata_summary": {
                "inferred_river_node_count": sum(
                    1 for m in prior_network['node_metadata'].values()
                    if m.get('inferred_river')
                ),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取补全质量评估失败 region={region}: {e}")
        raise HTTPException(status_code=500, detail=f"获取补全质量评估失败: {str(e)}")


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=NETWORK_ANALYZER_PORT)
