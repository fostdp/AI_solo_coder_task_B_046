"""
API 网关
统一入口，聚合各微服务API
端口：8000
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import logging
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

from common.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_gateway")

app = FastAPI(
    title="古代水利工程遗迹系统 - API网关",
    description="统一API入口，聚合遗迹数据、水力复原、可持续性评估、告警推送、农业影响评估、网络分析、气候脆弱性评估、数字化展示服务",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 微服务地址
SERVICES = {
    "heritage": f"http://localhost:{settings.HERITAGE_LOADER_PORT}",
    "hydro": f"http://localhost:{settings.HYDRO_RECONSTRUCTOR_PORT}",
    "sustainability": f"http://localhost:{settings.SUSTAINABILITY_EVALUATOR_PORT}",
    "alarm": f"http://localhost:{settings.ALARM_PUBLISHER_PORT}",
    "agriculture_impact": "http://agriculture_impact:8005",
    "network_analyzer": "http://network_analyzer:8006",
    "climate_vulnerability": "http://climate_vulnerability:8007",
    "digital_exhibit": "http://digital_exhibit:8008",
}


async def forward_request(service: str, path: str, method: str = "GET",
                           params: dict = None, json_data: dict = None):
    """转发请求到后端微服务"""
    base_url = SERVICES.get(service)
    if not base_url:
        raise HTTPException(status_code=500, detail=f"未知服务: {service}")

    url = f"{base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, params=params, json=json_data)
            elif method == "PUT":
                response = await client.put(url, params=params, json=json_data)
            elif method == "DELETE":
                response = await client.delete(url, params=params)
            else:
                raise HTTPException(status_code=405, detail="不支持的方法")

            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.json())
            return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"服务不可用: {service}")
    except Exception as e:
        logger.error(f"转发请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"网关错误: {str(e)}")


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": "3.0.0",
        "architecture": "微服务架构",
        "services": {
            "heritage_loader": f"{SERVICES['heritage']}/health",
            "hydro_reconstructor": f"{SERVICES['hydro']}/health",
            "sustainability_evaluator": f"{SERVICES['sustainability']}/health",
            "alarm_publisher": f"{SERVICES['alarm']}/health",
            "agriculture_impact": f"{SERVICES['agriculture_impact']}/health",
            "network_analyzer": f"{SERVICES['network_analyzer']}/health",
            "climate_vulnerability": f"{SERVICES['climate_vulnerability']}/health",
            "digital_exhibit": f"{SERVICES['digital_exhibit']}/health",
        },
        "endpoints": {
            "sites": "/api/sites",
            "hydrology": "/api/hydrology",
            "restoration": "/api/restoration/{site_id}",
            "assessment": "/api/assessment/{site_id}",
            "supply_ranges": "/api/supply-ranges",
            "cross_section": "/api/cross-section/{site_id}",
            "alerts": "/api/alerts",
            "comprehensive": "/api/sites/{id}/comprehensive",
            "agriculture_impact": "/api/v1/agriculture/*",
            "network_analyzer": "/api/v1/network/*",
            "climate_vulnerability": "/api/v1/climate/*",
            "digital_exhibit": "/api/v1/digital/*",
        }
    }


@app.get("/health")
async def health_check():
    """网关健康检查"""
    statuses = {}
    all_ok = True
    for name, base_url in SERVICES.items():
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{base_url}/health")
                statuses[name] = "ok" if r.status_code == 200 else "error"
                if r.status_code != 200:
                    all_ok = False
        except Exception:
            statuses[name] = "unavailable"
            all_ok = False

    return {
        "status": "ok" if all_ok else "degraded",
        "gateway": "healthy",
        "services": statuses,
    }


# ==============================================
# 遗迹数据 API
# ==============================================

@app.get("/api/sites")
async def list_sites(
    skip: int = 0,
    limit: int = 100,
    site_type: Optional[str] = None,
    dynasty: Optional[str] = None,
    preservation_status: Optional[str] = None,
    min_irrigation_area: Optional[float] = None,
    max_irrigation_area: Optional[float] = None,
    min_longitude: Optional[float] = None,
    max_longitude: Optional[float] = None,
    min_latitude: Optional[float] = None,
    max_latitude: Optional[float] = None,
):
    params = {
        "skip": skip, "limit": limit,
        "site_type": site_type, "dynasty": dynasty,
        "preservation_status": preservation_status,
        "min_irrigation_area": min_irrigation_area,
        "max_irrigation_area": max_irrigation_area,
        "min_longitude": min_longitude, "max_longitude": max_longitude,
        "min_latitude": min_latitude, "max_latitude": max_latitude,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("heritage", "/sites", "GET", params=params)


@app.get("/api/sites/{site_id}")
async def get_site(site_id: int):
    return await forward_request("heritage", f"/sites/{site_id}")


@app.post("/api/sites")
async def create_site(request: Request):
    body = await request.json()
    return await forward_request("heritage", "/sites", "POST", json_data=body)


@app.put("/api/sites/{site_id}")
async def update_site(site_id: int, request: Request):
    body = await request.json()
    return await forward_request("heritage", f"/sites/{site_id}", "PUT", json_data=body)


@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: int):
    return await forward_request("heritage", f"/sites/{site_id}", "DELETE")


@app.get("/api/sites/{site_id}/comprehensive")
async def get_comprehensive(site_id: int):
    """获取综合信息（聚合七个服务的数据）"""
    results = {}

    # 并行请求
    import asyncio
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            site_task = client.get(f"{SERVICES['heritage']}/sites/{site_id}")
            resto_task = client.get(f"{SERVICES['hydro']}/restore/{site_id}")
            assess_task = client.get(f"{SERVICES['sustainability']}/assess/{site_id}")
            agri_task = client.get(f"{SERVICES['agriculture_impact']}/sites/{site_id}/impact")
            network_task = client.get(f"{SERVICES['network_analyzer']}/regions/default/latest")
            climate_task = client.get(f"{SERVICES['climate_vulnerability']}/sites/{site_id}/assessments")
            digital_task = client.get(f"{SERVICES['digital_exhibit']}/sites/{site_id}/model")

            responses = await asyncio.gather(
                site_task, resto_task, assess_task,
                agri_task, network_task, climate_task, digital_task,
                return_exceptions=True
            )

            site_resp, resto_resp, assess_resp, agri_resp, network_resp, climate_resp, digital_resp = responses

            results["site"] = site_resp.json() if not isinstance(site_resp, Exception) and site_resp.status_code == 200 else None

            results["restoration"] = resto_resp.json() if not isinstance(resto_resp, Exception) and resto_resp.status_code == 200 else None

            results["assessment"] = assess_resp.json() if not isinstance(assess_resp, Exception) and assess_resp.status_code == 200 else None

            results["agriculture_impact"] = agri_resp.json() if not isinstance(agri_resp, Exception) and agri_resp.status_code == 200 else None

            network_membership = None
            if not isinstance(network_resp, Exception) and network_resp.status_code == 200:
                try:
                    latest_data = network_resp.json()
                    analysis_id = latest_data.get("id") if isinstance(latest_data, dict) else None
                    if analysis_id:
                        nodes_resp = await client.get(f"{SERVICES['network_analyzer']}/analysis/{analysis_id}/nodes", timeout=10.0)
                        if nodes_resp.status_code == 200:
                            nodes_data = nodes_resp.json()
                            if isinstance(nodes_data, list):
                                for node in nodes_data:
                                    if isinstance(node, dict) and node.get("site_id") == site_id:
                                        network_membership = node
                                        break
                except Exception:
                    pass
            results["network_membership"] = network_membership

            results["climate_assessments"] = climate_resp.json() if not isinstance(climate_resp, Exception) and climate_resp.status_code == 200 else None

            results["digital_reconstruction"] = digital_resp.json() if not isinstance(digital_resp, Exception) and digital_resp.status_code == 200 else None

        except Exception as e:
            logger.error(f"综合信息查询失败: {e}")

    if not results.get("site"):
        raise HTTPException(status_code=404, detail="遗迹不存在")

    return results


# ==============================================
# 水文 API
# ==============================================

@app.get("/api/hydrology")
async def list_hydrology(region: Optional[str] = None,
                          start_year: Optional[int] = None,
                          end_year: Optional[int] = None,
                          skip: int = 0, limit: int = 100):
    params = {"region": region, "start_year": start_year, "end_year": end_year,
              "skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("heritage", "/hydrology", "GET", params=params)


@app.get("/api/hydrology/by-site/{site_id}")
async def get_hydrology_for_site(site_id: int, period: str = "contemporary"):
    return await forward_request("heritage", f"/hydrology/by-site/{site_id}",
                                  "GET", params={"period": period})


# ==============================================
# 功能复原 API
# ==============================================

@app.post("/api/restoration/{site_id}")
async def restore_site(site_id: int, async_mode: bool = True):
    return await forward_request("hydro", f"/restore/{site_id}", "POST",
                                  params={"async_mode": async_mode})


@app.get("/api/restoration/{site_id}")
async def get_restoration(site_id: int):
    return await forward_request("hydro", f"/restore/{site_id}")


@app.post("/api/restoration/{site_id}/monte-carlo")
async def monte_carlo(site_id: int, n_samples: int = 1000, seed: int = 42):
    return await forward_request("hydro", f"/monte-carlo/{site_id}", "POST",
                                  params={"n_samples": n_samples, "seed": seed})


@app.post("/api/parameter-estimation/{site_id}")
async def param_estimation(site_id: int):
    return await forward_request("hydro", f"/parameter-estimation/{site_id}", "POST")


@app.get("/api/supply-ranges")
async def supply_ranges(
    min_longitude: Optional[float] = None,
    max_longitude: Optional[float] = None,
    min_latitude: Optional[float] = None,
    max_latitude: Optional[float] = None,
    simplified: bool = False,
    skip: int = 0, limit: int = 100,
):
    params = {
        "min_longitude": min_longitude, "max_longitude": max_longitude,
        "min_latitude": min_latitude, "max_latitude": max_latitude,
        "simplified": simplified, "skip": skip, "limit": limit,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("hydro", "/supply-ranges", "GET", params=params)


@app.get("/api/cross-section/{site_id}")
async def cross_section(site_id: int):
    return await forward_request("hydro", f"/cross-section/{site_id}")


@app.post("/api/batch/restore")
async def batch_restore():
    return await forward_request("hydro", "/batch/restore", "POST")


# ==============================================
# 可持续性评估 API
# ==============================================

@app.post("/api/assessment/{site_id}")
async def assess_site(site_id: int, async_mode: bool = True):
    return await forward_request("sustainability", f"/assess/{site_id}", "POST",
                                  params={"async_mode": async_mode})


@app.get("/api/assessment/{site_id}")
async def get_assessment(site_id: int):
    return await forward_request("sustainability", f"/assess/{site_id}")


@app.get("/api/experts")
async def get_experts():
    return await forward_request("sustainability", "/experts")


@app.get("/api/aggregated-weights")
async def get_aggregated_weights():
    return await forward_request("sustainability", "/aggregated-weights")


@app.get("/api/criteria")
async def get_criteria():
    return await forward_request("sustainability", "/criteria")


@app.get("/api/rankings")
async def get_rankings(by: str = "total", limit: int = 20,
                        min_grade: Optional[str] = None):
    params = {"by": by, "limit": limit, "min_grade": min_grade}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("sustainability", "/rankings", "GET", params=params)


@app.post("/api/batch/assess")
async def batch_assess():
    return await forward_request("sustainability", "/batch/assess", "POST")


# ==============================================
# 告警 API
# ==============================================

@app.get("/api/alerts")
async def list_alerts(site_id: Optional[int] = None,
                       alert_level: Optional[str] = None,
                       acknowledged: Optional[bool] = None,
                       skip: int = 0, limit: int = 100):
    params = {"site_id": site_id, "alert_level": alert_level,
              "acknowledged": acknowledged, "skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("alarm", "/alerts", "GET", params=params)


@app.get("/api/alerts/{alert_id}")
async def get_alert(alert_id: int):
    return await forward_request("alarm", f"/alerts/{alert_id}")


@app.put("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    return await forward_request("alarm", f"/alerts/{alert_id}/acknowledge", "PUT")


@app.get("/api/mqtt/status")
async def mqtt_status():
    return await forward_request("alarm", "/mqtt/status")


@app.post("/api/mqtt/reconnect")
async def mqtt_reconnect():
    return await forward_request("alarm", "/mqtt/reconnect", "POST")


@app.get("/api/mqtt/dead-letter")
async def get_dead_letter(limit: int = 100):
    return await forward_request("alarm", "/mqtt/dead-letter", "GET", params={"limit": limit})


# ==============================================
# 统计 & 辅助
# ==============================================

@app.get("/api/statistics")
async def get_statistics():
    return await forward_request("heritage", "/statistics")


@app.get("/api/dynasties")
async def get_dynasties():
    return await forward_request("heritage", "/dynasties")


@app.get("/api/regions")
async def get_regions():
    return await forward_request("heritage", "/regions")


# ==============================================
# 农业影响评估 API
# ==============================================

@app.get("/api/v1/agriculture/health")
async def agri_health():
    return await forward_request("agriculture_impact", "/health")


@app.get("/api/v1/agriculture/crop-yields")
async def agri_list_crop_yields(skip: int = 0, limit: int = 100):
    params = {"skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("agriculture_impact", "/crop-yields", "GET", params=params)


@app.get("/api/v1/agriculture/crop-yields/{id}")
async def agri_get_crop_yield(id: int):
    return await forward_request("agriculture_impact", f"/crop-yields/{id}")


@app.post("/api/v1/agriculture/crop-yields")
async def agri_create_crop_yield(request: Request):
    body = await request.json()
    return await forward_request("agriculture_impact", "/crop-yields", "POST", json_data=body)


@app.put("/api/v1/agriculture/crop-yields/{id}")
async def agri_update_crop_yield(id: int, request: Request):
    body = await request.json()
    return await forward_request("agriculture_impact", f"/crop-yields/{id}", "PUT", json_data=body)


@app.delete("/api/v1/agriculture/crop-yields/{id}")
async def agri_delete_crop_yield(id: int):
    return await forward_request("agriculture_impact", f"/crop-yields/{id}", "DELETE")


@app.get("/api/v1/agriculture/sites/{site_id}/impact")
async def agri_get_site_impact(site_id: int):
    return await forward_request("agriculture_impact", f"/sites/{site_id}/impact")


@app.post("/api/v1/agriculture/sites/{site_id}/impact")
async def agri_create_site_impact(site_id: int, request: Request):
    body = await request.json()
    return await forward_request("agriculture_impact", f"/sites/{site_id}/impact", "POST", json_data=body)


@app.get("/api/v1/agriculture/sites/{site_id}/impact/benefit-zone.geojson")
async def agri_get_benefit_zone_geojson(site_id: int):
    return await forward_request("agriculture_impact", f"/sites/{site_id}/impact/benefit-zone.geojson")


@app.post("/api/v1/agriculture/batch/region")
async def agri_batch_region(request: Request):
    body = await request.json()
    return await forward_request("agriculture_impact", "/batch/region", "POST", json_data=body)


@app.get("/api/v1/agriculture/regions/{region}/impact-summary")
async def agri_get_region_impact_summary(region: str):
    return await forward_request("agriculture_impact", f"/regions/{region}/impact-summary")


@app.get("/api/v1/agriculture/stats")
async def agri_get_stats():
    return await forward_request("agriculture_impact", "/stats")


# ==============================================
# 网络分析 API
# ==============================================

@app.get("/api/v1/network/health")
async def network_health():
    return await forward_request("network_analyzer", "/health")


@app.get("/api/v1/network/regions")
async def network_list_regions():
    return await forward_request("network_analyzer", "/regions")


@app.post("/api/v1/network/analyze/region")
async def network_analyze_region(request: Request):
    body = await request.json()
    return await forward_request("network_analyzer", "/analyze/region", "POST", json_data=body)


@app.get("/api/v1/network/regions/{region}/latest")
async def network_get_region_latest(region: str):
    return await forward_request("network_analyzer", f"/regions/{region}/latest")


@app.get("/api/v1/network/regions/{region}/history")
async def network_get_region_history(region: str, skip: int = 0, limit: int = 100):
    params = {"skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("network_analyzer", f"/regions/{region}/history", "GET", params=params)


@app.get("/api/v1/network/analysis/{id}")
async def network_get_analysis(id: int):
    return await forward_request("network_analyzer", f"/analysis/{id}")


@app.delete("/api/v1/network/analysis/{id}")
async def network_delete_analysis(id: int):
    return await forward_request("network_analyzer", f"/analysis/{id}", "DELETE")


@app.get("/api/v1/network/analysis/{id}/network.geojson")
async def network_get_analysis_geojson(id: int):
    return await forward_request("network_analyzer", f"/analysis/{id}/network.geojson")


@app.get("/api/v1/network/analysis/{id}/nodes")
async def network_get_analysis_nodes(id: int):
    return await forward_request("network_analyzer", f"/analysis/{id}/nodes")


@app.get("/api/v1/network/analysis/{id}/critical-nodes")
async def network_get_analysis_critical_nodes(id: int):
    return await forward_request("network_analyzer", f"/analysis/{id}/critical-nodes")


@app.post("/api/v1/network/batch")
async def network_batch(request: Request):
    body = await request.json()
    return await forward_request("network_analyzer", "/batch", "POST", json_data=body)


@app.get("/api/v1/network/cross-region/summary")
async def network_get_cross_region_summary():
    return await forward_request("network_analyzer", "/cross-region/summary")


@app.get("/api/v1/network/stats")
async def network_get_stats():
    return await forward_request("network_analyzer", "/stats")


# ==============================================
# 气候脆弱性评估 API
# ==============================================

@app.get("/api/v1/climate/health")
async def climate_health():
    return await forward_request("climate_vulnerability", "/health")


@app.get("/api/v1/climate/scenarios")
async def climate_list_scenarios():
    return await forward_request("climate_vulnerability", "/scenarios")


@app.get("/api/v1/climate/sites/{site_id}/assessments")
async def climate_get_site_assessments(site_id: int):
    return await forward_request("climate_vulnerability", f"/sites/{site_id}/assessments")


@app.post("/api/v1/climate/sites/{site_id}/assess")
async def climate_create_site_assessment(site_id: int, request: Request):
    body = await request.json()
    return await forward_request("climate_vulnerability", f"/sites/{site_id}/assess", "POST", json_data=body)


@app.get("/api/v1/climate/sites/{site_id}/risks-summary")
async def climate_get_site_risks_summary(site_id: int):
    return await forward_request("climate_vulnerability", f"/sites/{site_id}/risks-summary")


@app.get("/api/v1/climate/sites/{site_id}/risk-zone.geojson")
async def climate_get_site_risk_zone_geojson(site_id: int):
    return await forward_request("climate_vulnerability", f"/sites/{site_id}/risk-zone.geojson")


@app.get("/api/v1/climate/sites/{site_id}/risk-matrix")
async def climate_get_site_risk_matrix(site_id: int):
    return await forward_request("climate_vulnerability", f"/sites/{site_id}/risk-matrix")


@app.post("/api/v1/climate/batch/region")
async def climate_batch_region(request: Request):
    body = await request.json()
    return await forward_request("climate_vulnerability", "/batch/region", "POST", json_data=body)


@app.get("/api/v1/climate/regions/{region}/risk-map")
async def climate_get_region_risk_map(region: str):
    return await forward_request("climate_vulnerability", f"/regions/{region}/risk-map")


@app.get("/api/v1/climate/regions/{region}/high-risk-list")
async def climate_get_region_high_risk_list(region: str, skip: int = 0, limit: int = 100):
    params = {"skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("climate_vulnerability", f"/regions/{region}/high-risk-list", "GET", params=params)


@app.get("/api/v1/climate/stats")
async def climate_get_stats():
    return await forward_request("climate_vulnerability", "/stats")


@app.get("/api/v1/climate/cross-scenario-comparison")
async def climate_get_cross_scenario_comparison():
    return await forward_request("climate_vulnerability", "/cross-scenario-comparison")


# ==============================================
# 数字化展示 API
# ==============================================

@app.get("/api/v1/digital/health")
async def digital_health():
    return await forward_request("digital_exhibit", "/health")


@app.get("/api/v1/digital/methods")
async def digital_list_methods():
    return await forward_request("digital_exhibit", "/methods")


@app.post("/api/v1/digital/sites/{site_id}/reconstruct")
async def digital_reconstruct_site(site_id: int, request: Request):
    body = await request.json()
    return await forward_request("digital_exhibit", f"/sites/{site_id}/reconstruct", "POST", json_data=body)


@app.get("/api/v1/digital/sites/{site_id}/status")
async def digital_get_site_status(site_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/status")


@app.get("/api/v1/digital/sites/{site_id}/model")
async def digital_get_site_model(site_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/model")


@app.get("/api/v1/digital/sites/{site_id}/vr")
async def digital_get_site_vr(site_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/vr")


@app.get("/api/v1/digital/sites/{site_id}/hotspots")
async def digital_list_site_hotspots(site_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/hotspots")


@app.post("/api/v1/digital/sites/{site_id}/hotspots")
async def digital_create_site_hotspot(site_id: int, request: Request):
    body = await request.json()
    return await forward_request("digital_exhibit", f"/sites/{site_id}/hotspots", "POST", json_data=body)


@app.delete("/api/v1/digital/sites/{site_id}/hotspots/{hotspot_id}")
async def digital_delete_site_hotspot(site_id: int, hotspot_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/hotspots/{hotspot_id}", "DELETE")


@app.get("/api/v1/digital/sites/{site_id}/reconstruction-log")
async def digital_get_site_reconstruction_log(site_id: int, skip: int = 0, limit: int = 100):
    params = {"skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("digital_exhibit", f"/sites/{site_id}/reconstruction-log", "GET", params=params)


@app.delete("/api/v1/digital/sites/{site_id}/model")
async def digital_delete_site_model(site_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/model", "DELETE")


@app.get("/api/v1/digital/sites/{site_id}/overlay")
async def digital_get_site_overlay(site_id: int):
    return await forward_request("digital_exhibit", f"/sites/{site_id}/overlay")


@app.post("/api/v1/digital/sites/{site_id}/toggle-overlay")
async def digital_toggle_site_overlay(site_id: int, request: Request):
    body = await request.json()
    return await forward_request("digital_exhibit", f"/sites/{site_id}/toggle-overlay", "POST", json_data=body)


@app.get("/api/v1/digital/gallery")
async def digital_get_gallery(skip: int = 0, limit: int = 100):
    params = {"skip": skip, "limit": limit}
    params = {k: v for k, v in params.items() if v is not None}
    return await forward_request("digital_exhibit", "/gallery", "GET", params=params)


@app.get("/api/v1/digital/stats")
async def digital_get_stats():
    return await forward_request("digital_exhibit", "/stats")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.GATEWAY_PORT)
