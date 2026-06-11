"""
数据模型模块
所有微服务共享的SQLAlchemy模型
"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, CheckConstraint, JSON,
    Numeric, UniqueConstraint
)
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from common.database import Base


class DynastyDict(Base):
    __tablename__ = "dynasty_dict"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    start_year = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)
    order = Column(Integer, nullable=False, unique=True)


class WaterHeritageSite(Base):
    __tablename__ = "water_heritage_sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    dynasty = Column(String(100), nullable=False)
    dynasty_order = Column(Integer, nullable=False, index=True)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type='POINT', srid=4326), index=True)
    site_type = Column(String(20), nullable=False, index=True)
    dam_height = Column(Float)
    canal_length = Column(Float)
    irrigation_area = Column(Float, nullable=False)
    preservation_status = Column(String(20), nullable=False, index=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("site_type IN ('渠', '堰', '陂', '塘', '井')", name='ck_site_type'),
        CheckConstraint("preservation_status IN ('完好', '部分损毁', '完全废弃')", name='ck_preservation_status'),
    )


class PaleoHydrologyData(Base):
    __tablename__ = "paleo_hydrology_data"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    region = Column(String(100), nullable=False, index=True)
    rainfall = Column(Float, nullable=False)
    runoff = Column(Float, nullable=False)
    temperature = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FunctionalRestoration(Base):
    __tablename__ = "functional_restoration"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False, unique=True)
    original_irrigation_capacity = Column(Float, nullable=False)
    actual_irrigation_capacity = Column(Float, nullable=False)
    water_supply_range_geom = Column(Geometry(geometry_type='POLYGON', srid=4326), index=True)
    supply_population = Column(Integer)
    restoration_notes = Column(Text)
    parameter_estimation = Column(JSON)
    uncertainty_analysis = Column(JSON)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())


class SustainabilityAssessment(Base):
    __tablename__ = "sustainability_assessment"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False, unique=True)
    structural_score = Column(Float, nullable=False)
    hydrological_score = Column(Float, nullable=False)
    economic_score = Column(Float, nullable=False)
    cultural_score = Column(Float, nullable=False)
    environmental_score = Column(Float, nullable=False)
    total_score = Column(Float, nullable=False, index=True)
    grade = Column(String(2), nullable=False)
    restoration_potential = Column(Boolean, nullable=False)
    assessment_details = Column(JSON)
    group_decision_info = Column(JSON)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now())


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    alert_level = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)
    mqtt_topic = Column(String(200))
    mqtt_message_id = Column(String(100))
    mqtt_status = Column(String(20))
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint("alert_level IN ('低', '中', '高', '紧急')", name='ck_alert_level'),
    )


class AncientCropYield(Base):
    __tablename__ = "ancient_crop_yield"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String(64), nullable=False, index=True)
    crop_type = Column(String(32), nullable=False)
    dynasty_order = Column(Integer, ForeignKey("dynasty_dict.order", ondelete="CASCADE"), nullable=False)
    yield_baseline_kg_per_mu = Column(Numeric(10, 4), nullable=False)
    yield_with_irrigation_kg_per_mu = Column(Numeric(10, 4), nullable=False)
    growing_season_start = Column(Integer, nullable=False)
    growing_season_end = Column(Integer, nullable=False)
    kc_initial = Column(Numeric(5, 3), nullable=False)
    kc_mid = Column(Numeric(5, 3), nullable=False)
    kc_late = Column(Numeric(5, 3), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("crop_type IN ('粟', '稻', '麦', '黍', '豆')", name='ck_crop_type'),
        CheckConstraint("growing_season_start BETWEEN 1 AND 12", name='ck_growing_season_start'),
        CheckConstraint("growing_season_end BETWEEN 1 AND 12", name='ck_growing_season_end'),
    )


class AgriculturalImpactAssessment(Base):
    __tablename__ = "agricultural_impact_assessment"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False, unique=True)
    dominant_crop = Column(String(32), nullable=False)
    total_influenced_area_mu = Column(Numeric(15, 4), nullable=False)
    yield_increase_rate = Column(Numeric(8, 4), nullable=False)
    annual_yield_increase_kg = Column(Numeric(15, 4), nullable=False)
    farmers_benefited_count = Column(Integer, nullable=False)
    water_use_efficiency_kg_per_m3 = Column(Numeric(10, 4), nullable=False)
    yield_simulation_raw = Column(JSON)
    benefit_zone_geojson = Column(JSON)
    confidence_score = Column(Numeric(5, 4), nullable=False)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HydraulicNetworkAnalysis(Base):
    __tablename__ = "hydraulic_network_analysis"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String(64), nullable=False, index=True)
    total_nodes = Column(Integer, nullable=False)
    total_edges = Column(Integer, nullable=False)
    network_connectivity = Column(Numeric(8, 4), nullable=False)
    network_redundancy = Column(Numeric(8, 4), nullable=False)
    avg_path_length = Column(Numeric(10, 4), nullable=False)
    clustering_coefficient = Column(Numeric(8, 4), nullable=False)
    synergy_score = Column(Numeric(8, 4), nullable=False)
    cascade_irrigation_efficiency = Column(Numeric(8, 4), nullable=False)
    flood_regulation_capacity = Column(Numeric(8, 4), nullable=False)
    critical_nodes = Column(JSON)
    network_edges_geojson = Column(JSON)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('region', 'analyzed_at', name='uq_region_analyzed_at'),
    )


class NetworkMemberSite(Base):
    __tablename__ = "network_member_site"

    id = Column(Integer, primary_key=True, index=True)
    network_analysis_id = Column(Integer, ForeignKey("hydraulic_network_analysis.id", ondelete="CASCADE"), nullable=False)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False)
    node_degree = Column(Integer, nullable=False)
    node_betweenness = Column(Numeric(10, 6), nullable=False)
    node_closeness = Column(Numeric(10, 6), nullable=False)
    node_role = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("node_role IN ('核心枢纽', '中转节点', '终端节点', '孤立节点')", name='ck_node_role'),
    )


class ClimateVulnerabilityAssessment(Base):
    __tablename__ = "climate_vulnerability_assessment"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False)
    scenario = Column(String(16), nullable=False)
    assessment_year = Column(Integer, nullable=False)
    flood_risk_level = Column(String(16), nullable=False)
    flood_inundation_depth_m = Column(Numeric(8, 4), nullable=False)
    flood_exposure_probability = Column(Numeric(8, 4), nullable=False)
    drought_risk_level = Column(String(16), nullable=False)
    drought_severity_spei = Column(Numeric(8, 4), nullable=False)
    drought_month_count = Column(Integer, nullable=False)
    overall_vulnerability_score = Column(Numeric(8, 4), nullable=False)
    vulnerability_category = Column(String(16), nullable=False)
    risk_zone_geom = Column(Geometry(geometry_type='POLYGON', srid=4326), index=True)
    risk_factors = Column(JSON)
    adaptation_suggestions = Column(JSON)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("scenario IN ('RCP2.6', 'RCP4.5', 'RCP8.5')", name='ck_climate_scenario'),
        CheckConstraint("assessment_year IN (2030, 2050, 2070, 2100)", name='ck_assessment_year'),
        CheckConstraint("flood_risk_level IN ('无', '低', '中', '高', '极高')", name='ck_flood_risk_level'),
        CheckConstraint("drought_risk_level IN ('无', '低', '中', '高', '极高')", name='ck_drought_risk_level'),
        CheckConstraint("vulnerability_category IN ('低', '较低', '中', '较高', '高')", name='ck_vulnerability_category'),
        UniqueConstraint('site_id', 'scenario', 'assessment_year', name='uq_site_scenario_year'),
    )


class DigitalReconstruction(Base):
    __tablename__ = "digital_reconstruction"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("water_heritage_sites.id", ondelete="CASCADE"), nullable=False, unique=True)
    photos_uploaded_count = Column(Integer, nullable=False)
    reconstruction_method = Column(String(32), nullable=False)
    reconstruction_status = Column(String(16), nullable=False)
    point_cloud_count = Column(Integer)
    mesh_face_count = Column(Integer)
    texture_resolution = Column(String(16))
    glb_model_url = Column(String(512))
    gltf_model_url = Column(String(512))
    vr_experience_url = Column(String(512))
    model_metadata = Column(JSON)
    overlay_with_irrigation = Column(Boolean, default=False)
    reconstruction_log = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("reconstruction_method IN ('摄影测量', '激光扫描', '参数化建模')", name='ck_reconstruction_method'),
        CheckConstraint("reconstruction_status IN ('待处理', '处理中', '已完成', '失败')", name='ck_reconstruction_status'),
        CheckConstraint("texture_resolution IN ('1K', '2K', '4K')", name='ck_texture_resolution'),
    )
