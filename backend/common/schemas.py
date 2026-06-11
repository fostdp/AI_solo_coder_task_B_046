"""
Pydantic Schema 模块
所有微服务共享
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class WaterHeritageSiteBase(BaseModel):
    name: str = Field(..., max_length=200)
    dynasty: str = Field(..., max_length=100)
    dynasty_order: int
    longitude: float
    latitude: float
    site_type: str = Field(..., pattern='^(渠|堰|陂|塘|井)$')
    dam_height: Optional[float] = None
    canal_length: Optional[float] = None
    irrigation_area: float
    preservation_status: str = Field(..., pattern='^(完好|部分损毁|完全废弃)$')
    description: Optional[str] = None


class WaterHeritageSiteCreate(WaterHeritageSiteBase):
    pass


class WaterHeritageSiteUpdate(BaseModel):
    name: Optional[str] = None
    dynasty: Optional[str] = None
    dynasty_order: Optional[int] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    site_type: Optional[str] = Field(None, pattern='^(渠|堰|陂|塘|井)$')
    dam_height: Optional[float] = None
    canal_length: Optional[float] = None
    irrigation_area: Optional[float] = None
    preservation_status: Optional[str] = Field(None, pattern='^(完好|部分损毁|完全废弃)$')
    description: Optional[str] = None


class WaterHeritageSiteResponse(WaterHeritageSiteBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaleoHydrologyDataBase(BaseModel):
    year: int
    region: str
    rainfall: float
    runoff: float
    temperature: Optional[float] = None


class PaleoHydrologyDataResponse(PaleoHydrologyDataBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FunctionalRestorationBase(BaseModel):
    site_id: int
    original_irrigation_capacity: float
    actual_irrigation_capacity: float
    water_supply_range_geom: Optional[dict] = None
    supply_population: Optional[int] = None
    restoration_notes: Optional[str] = None
    parameter_estimation: Optional[dict] = None
    uncertainty_analysis: Optional[dict] = None


class FunctionalRestorationResponse(FunctionalRestorationBase):
    id: int
    calculated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SustainabilityAssessmentBase(BaseModel):
    site_id: int
    structural_score: float
    hydrological_score: float
    economic_score: float
    cultural_score: float
    environmental_score: float
    total_score: float
    grade: str
    restoration_potential: bool
    assessment_details: Optional[dict] = None
    group_decision_info: Optional[dict] = None


class SustainabilityAssessmentResponse(SustainabilityAssessmentBase):
    id: int
    assessed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AlertRecordBase(BaseModel):
    site_id: int
    alert_type: str
    alert_level: str = Field(..., pattern='^(低|中|高|紧急)$')
    message: str
    mqtt_topic: Optional[str] = None


class AlertRecordResponse(AlertRecordBase):
    id: int
    acknowledged: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AHPCriteriaWeights(BaseModel):
    structural: float = 0.30
    hydrological: float = 0.25
    economic: float = 0.15
    cultural: float = 0.15
    environmental: float = 0.15


class SiteComprehensiveInfo(BaseModel):
    site: WaterHeritageSiteResponse
    restoration: Optional[FunctionalRestorationResponse] = None
    assessment: Optional[SustainabilityAssessmentResponse] = None


class StatisticsResponse(BaseModel):
    total_sites: int
    by_type: dict
    by_dynasty: dict
    by_status: dict
    avg_irrigation_area: float
    alerts_count: int
    high_potential_count: int


class EventMessage(BaseModel):
    """Redis Pub/Sub 事件消息格式"""
    event_type: str
    site_id: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: float
    source: str
    message_id: str


class AncientCropYieldBase(BaseModel):
    region: str = Field(..., max_length=64)
    crop_type: str = Field(..., pattern='^(粟|稻|麦|黍|豆)$')
    dynasty_order: int
    yield_baseline_kg_per_mu: float
    yield_with_irrigation_kg_per_mu: float
    growing_season_start: int = Field(..., ge=1, le=12)
    growing_season_end: int = Field(..., ge=1, le=12)
    kc_initial: float
    kc_mid: float
    kc_late: float


class AncientCropYieldCreate(AncientCropYieldBase):
    pass


class AncientCropYieldResponse(AncientCropYieldBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AncientCropYieldDetail(AncientCropYieldResponse):
    pass


class AgriculturalImpactAssessmentBase(BaseModel):
    site_id: int
    dominant_crop: str = Field(..., max_length=32)
    total_influenced_area_mu: float
    yield_increase_rate: float
    annual_yield_increase_kg: float
    farmers_benefited_count: int
    water_use_efficiency_kg_per_m3: float
    yield_simulation_raw: Optional[Dict[str, Any]] = None
    benefit_zone_geojson: Optional[Dict[str, Any]] = None
    confidence_score: float


class AgriculturalImpactAssessmentCreate(AgriculturalImpactAssessmentBase):
    pass


class AgriculturalImpactAssessmentResponse(AgriculturalImpactAssessmentBase):
    id: int
    assessed_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AgriculturalImpactAssessmentDetail(AgriculturalImpactAssessmentResponse):
    site: Optional[WaterHeritageSiteResponse] = None


class HydraulicNetworkAnalysisBase(BaseModel):
    region: str = Field(..., max_length=64)
    total_nodes: int
    total_edges: int
    network_connectivity: float
    network_redundancy: float
    avg_path_length: float
    clustering_coefficient: float
    synergy_score: float
    cascade_irrigation_efficiency: float
    flood_regulation_capacity: float
    critical_nodes: Optional[Dict[str, Any]] = None
    network_edges_geojson: Optional[Dict[str, Any]] = None


class HydraulicNetworkAnalysisCreate(HydraulicNetworkAnalysisBase):
    pass


class HydraulicNetworkAnalysisResponse(HydraulicNetworkAnalysisBase):
    id: int
    analyzed_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HydraulicNetworkAnalysisDetail(HydraulicNetworkAnalysisResponse):
    member_sites: Optional[List['NetworkMemberSiteResponse']] = None


class NetworkMemberSiteBase(BaseModel):
    network_analysis_id: int
    site_id: int
    node_degree: int
    node_betweenness: float
    node_closeness: float
    node_role: str = Field(..., pattern='^(核心枢纽|中转节点|终端节点|孤立节点)$')


class NetworkMemberSiteCreate(NetworkMemberSiteBase):
    pass


class NetworkMemberSiteResponse(NetworkMemberSiteBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class NetworkMemberSiteDetail(NetworkMemberSiteResponse):
    site: Optional[WaterHeritageSiteResponse] = None
    network_analysis: Optional[HydraulicNetworkAnalysisResponse] = None


class ClimateVulnerabilityAssessmentBase(BaseModel):
    site_id: int
    scenario: str = Field(..., pattern='^(RCP2.6|RCP4.5|RCP8.5)$')
    assessment_year: int = Field(..., ge=2030, le=2100)
    flood_risk_level: str = Field(..., pattern='^(无|低|中|高|极高)$')
    flood_inundation_depth_m: float
    flood_exposure_probability: float
    drought_risk_level: str = Field(..., pattern='^(无|低|中|高|极高)$')
    drought_severity_spei: float
    drought_month_count: int
    overall_vulnerability_score: float
    vulnerability_category: str = Field(..., pattern='^(低|较低|中|较高|高)$')
    risk_zone_geom: Optional[Dict[str, Any]] = None
    risk_factors: Optional[Dict[str, Any]] = None
    adaptation_suggestions: Optional[Dict[str, Any]] = None


class ClimateVulnerabilityAssessmentCreate(ClimateVulnerabilityAssessmentBase):
    pass


class ClimateVulnerabilityAssessmentResponse(ClimateVulnerabilityAssessmentBase):
    id: int
    assessed_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ClimateVulnerabilityAssessmentDetail(ClimateVulnerabilityAssessmentResponse):
    site: Optional[WaterHeritageSiteResponse] = None


class DigitalReconstructionBase(BaseModel):
    site_id: int
    photos_uploaded_count: int
    reconstruction_method: str = Field(..., pattern='^(摄影测量|激光扫描|参数化建模)$')
    reconstruction_status: str = Field(..., pattern='^(待处理|处理中|已完成|失败)$')
    point_cloud_count: Optional[int] = None
    mesh_face_count: Optional[int] = None
    texture_resolution: Optional[str] = Field(None, pattern='^(1K|2K|4K)$')
    glb_model_url: Optional[str] = Field(None, max_length=512)
    gltf_model_url: Optional[str] = Field(None, max_length=512)
    vr_experience_url: Optional[str] = Field(None, max_length=512)
    model_metadata: Optional[Dict[str, Any]] = None
    overlay_with_irrigation: bool = False
    reconstruction_log: Optional[Dict[str, Any]] = None


class DigitalReconstructionCreate(DigitalReconstructionBase):
    pass


class DigitalReconstructionResponse(DigitalReconstructionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DigitalReconstructionDetail(DigitalReconstructionResponse):
    site: Optional[WaterHeritageSiteResponse] = None


class AgricultureImpactRequest(BaseModel):
    site_id: int
    crop_types: Optional[List[str]] = None
    scenario: Optional[str] = None


class NetworkAnalysisRequest(BaseModel):
    region: str
    site_ids: Optional[List[int]] = None
    analysis_depth: str = Field(..., pattern='^(basic|deep|full)$')


class ClimateVulnerabilityRequest(BaseModel):
    site_id: int
    scenarios: List[str]
    years: List[int]


class DigitalReconstructionRequest(BaseModel):
    site_id: int
    photo_urls: List[str]
    method: str
    generate_vr: bool = False


class BatchAgricultureRequest(BaseModel):
    region: str
    trigger_network: bool = False


class BatchClimateRequest(BaseModel):
    region: str
    scenarios: List[str]
    years: List[int]


class BatchNetworkRequest(BaseModel):
    region: str
    analysis_depth: str = Field(..., pattern='^(basic|deep|full)$')


class AgricultureImpactTaskResponse(BaseModel):
    task_id: str
    site_id: int
    status: str


class NetworkAnalysisTaskResponse(BaseModel):
    task_id: str
    region: str
    status: str


class ClimateVulnerabilityTaskResponse(BaseModel):
    task_id: str
    site_id: int
    scenarios: List[str]
    years: List[int]
    status: str


class DigitalReconstructionTaskResponse(BaseModel):
    task_id: str
    site_id: int
    status: str
    generate_vr: bool


class BatchAgricultureTaskResponse(BaseModel):
    batch_id: str
    region: str
    total_sites: int
    status: str


class BatchClimateTaskResponse(BaseModel):
    batch_id: str
    region: str
    total_sites: int
    scenarios: List[str]
    years: List[int]
    status: str


class BatchNetworkTaskResponse(BaseModel):
    batch_id: str
    region: str
    total_sites: int
    analysis_depth: str
    status: str


HydraulicNetworkAnalysisDetail.model_rebuild()
