-- ============================================================
-- 古代水利工程遗迹功能复原与可持续性评估系统
-- 扩展功能表 V2 (PostgreSQL + PostGIS)
-- ============================================================

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS tablefunc;

SET search_path = public, contrib;

-- ============================================================
-- 1. 古代作物产量表
-- ============================================================
CREATE TABLE IF NOT EXISTS ancient_crop_yield (
    id SERIAL PRIMARY KEY,
    region VARCHAR(64) COLLATE pg_catalog."default" NOT NULL,
    crop_type VARCHAR(32) COLLATE pg_catalog."default" NOT NULL,
    dynasty_order INTEGER NOT NULL REFERENCES dynasty_dict("order") ON DELETE CASCADE,
    yield_baseline_kg_per_mu NUMERIC(10, 4) NOT NULL,
    yield_with_irrigation_kg_per_mu NUMERIC(10, 4) NOT NULL,
    growing_season_start INTEGER NOT NULL,
    growing_season_end INTEGER NOT NULL,
    kc_initial NUMERIC(5, 3) NOT NULL,
    kc_mid NUMERIC(5, 3) NOT NULL,
    kc_late NUMERIC(5, 3) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT ck_crop_type CHECK (crop_type IN ('粟', '稻', '麦', '黍', '豆')),
    CONSTRAINT ck_growing_season_start CHECK (growing_season_start BETWEEN 1 AND 12),
    CONSTRAINT ck_growing_season_end CHECK (growing_season_end BETWEEN 1 AND 12)
);

CREATE INDEX IF NOT EXISTS idx_ancient_crop_yield_region ON ancient_crop_yield (region);
CREATE INDEX IF NOT EXISTS idx_ancient_crop_yield_region_crop_dynasty ON ancient_crop_yield (region, crop_type, dynasty_order);

-- ============================================================
-- 2. 农业影响评估表
-- ============================================================
CREATE TABLE IF NOT EXISTS agricultural_impact_assessment (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES water_heritage_sites(id) ON DELETE CASCADE,
    dominant_crop VARCHAR(32) COLLATE pg_catalog."default" NOT NULL,
    total_influenced_area_mu NUMERIC(15, 4) NOT NULL,
    yield_increase_rate NUMERIC(8, 4) NOT NULL,
    annual_yield_increase_kg NUMERIC(15, 4) NOT NULL,
    farmers_benefited_count INTEGER NOT NULL,
    water_use_efficiency_kg_per_m3 NUMERIC(10, 4) NOT NULL,
    yield_simulation_raw JSONB,
    benefit_zone_geojson JSONB,
    confidence_score NUMERIC(5, 4) NOT NULL,
    benefit_zone_geom GEOMETRY(POLYGON, 4326),
    assessed_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(site_id)
);

CREATE INDEX IF NOT EXISTS idx_agricultural_impact_assessment_site ON agricultural_impact_assessment (site_id);
CREATE INDEX IF NOT EXISTS idx_agricultural_impact_assessment_benefit_zone_geom ON agricultural_impact_assessment USING GIST (benefit_zone_geom);

-- ============================================================
-- 3. 水利网络分析表
-- ============================================================
CREATE TABLE IF NOT EXISTS hydraulic_network_analysis (
    id SERIAL PRIMARY KEY,
    region VARCHAR(64) COLLATE pg_catalog."default" NOT NULL,
    total_nodes INTEGER NOT NULL,
    total_edges INTEGER NOT NULL,
    network_connectivity NUMERIC(8, 4) NOT NULL,
    network_redundancy NUMERIC(8, 4) NOT NULL,
    avg_path_length NUMERIC(10, 4) NOT NULL,
    clustering_coefficient NUMERIC(8, 4) NOT NULL,
    synergy_score NUMERIC(8, 4) NOT NULL,
    cascade_irrigation_efficiency NUMERIC(8, 4) NOT NULL,
    flood_regulation_capacity NUMERIC(8, 4) NOT NULL,
    critical_nodes JSONB,
    network_edges_geojson JSONB,
    analyzed_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_region_analyzed_at UNIQUE (region, analyzed_at)
);

CREATE INDEX IF NOT EXISTS idx_hydraulic_network_analysis_region ON hydraulic_network_analysis (region);

-- ============================================================
-- 4. 网络成员遗迹表
-- ============================================================
CREATE TABLE IF NOT EXISTS network_member_site (
    id SERIAL PRIMARY KEY,
    network_analysis_id INTEGER NOT NULL REFERENCES hydraulic_network_analysis(id) ON DELETE CASCADE,
    site_id INTEGER NOT NULL REFERENCES water_heritage_sites(id) ON DELETE CASCADE,
    node_degree INTEGER NOT NULL,
    node_betweenness NUMERIC(10, 6) NOT NULL,
    node_closeness NUMERIC(10, 6) NOT NULL,
    node_role VARCHAR(32) COLLATE pg_catalog."default" NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT ck_node_role CHECK (node_role IN ('核心枢纽', '中转节点', '终端节点', '孤立节点'))
);

CREATE INDEX IF NOT EXISTS idx_network_member_site_network_analysis_id ON network_member_site (network_analysis_id);
CREATE INDEX IF NOT EXISTS idx_network_member_site_site_id ON network_member_site (site_id);

-- ============================================================
-- 5. 气候脆弱性评估表
-- ============================================================
CREATE TABLE IF NOT EXISTS climate_vulnerability_assessment (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES water_heritage_sites(id) ON DELETE CASCADE,
    scenario VARCHAR(16) COLLATE pg_catalog."default" NOT NULL,
    assessment_year INTEGER NOT NULL,
    flood_risk_level VARCHAR(16) COLLATE pg_catalog."default" NOT NULL,
    flood_inundation_depth_m NUMERIC(8, 4) NOT NULL,
    flood_exposure_probability NUMERIC(8, 4) NOT NULL,
    drought_risk_level VARCHAR(16) COLLATE pg_catalog."default" NOT NULL,
    drought_severity_spei NUMERIC(8, 4) NOT NULL,
    drought_month_count INTEGER NOT NULL,
    overall_vulnerability_score NUMERIC(8, 4) NOT NULL,
    vulnerability_category VARCHAR(16) COLLATE pg_catalog."default" NOT NULL,
    risk_zone_geom GEOMETRY(POLYGON, 4326),
    risk_factors JSONB,
    adaptation_suggestions JSONB,
    assessed_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT ck_climate_scenario CHECK (scenario IN ('RCP2.6', 'RCP4.5', 'RCP8.5')),
    CONSTRAINT ck_assessment_year CHECK (assessment_year IN (2030, 2050, 2070, 2100)),
    CONSTRAINT ck_flood_risk_level CHECK (flood_risk_level IN ('无', '低', '中', '高', '极高')),
    CONSTRAINT ck_drought_risk_level CHECK (drought_risk_level IN ('无', '低', '中', '高', '极高')),
    CONSTRAINT ck_vulnerability_category CHECK (vulnerability_category IN ('低', '较低', '中', '较高', '高')),
    CONSTRAINT uq_site_scenario_year UNIQUE (site_id, scenario, assessment_year)
);

CREATE INDEX IF NOT EXISTS idx_climate_vulnerability_assessment_site ON climate_vulnerability_assessment (site_id);
CREATE INDEX IF NOT EXISTS idx_climate_vulnerability_assessment_risk_zone_geom ON climate_vulnerability_assessment USING GIST (risk_zone_geom);
CREATE UNIQUE INDEX IF NOT EXISTS idx_climate_vulnerability_uq_site_scenario_year ON climate_vulnerability_assessment (site_id, scenario, assessment_year);

-- ============================================================
-- 6. 数字化重建表
-- ============================================================
CREATE TABLE IF NOT EXISTS digital_reconstruction (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES water_heritage_sites(id) ON DELETE CASCADE,
    photos_uploaded_count INTEGER NOT NULL,
    reconstruction_method VARCHAR(32) COLLATE pg_catalog."default" NOT NULL,
    reconstruction_status VARCHAR(16) COLLATE pg_catalog."default" NOT NULL,
    point_cloud_count INTEGER,
    mesh_face_count INTEGER,
    texture_resolution VARCHAR(16) COLLATE pg_catalog."default",
    glb_model_url VARCHAR(512) COLLATE pg_catalog."default",
    gltf_model_url VARCHAR(512) COLLATE pg_catalog."default",
    vr_experience_url VARCHAR(512) COLLATE pg_catalog."default",
    model_metadata JSONB,
    overlay_with_irrigation BOOLEAN DEFAULT FALSE,
    reconstruction_log JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(site_id),
    CONSTRAINT ck_reconstruction_method CHECK (reconstruction_method IN ('摄影测量', '激光扫描', '参数化建模')),
    CONSTRAINT ck_reconstruction_status CHECK (reconstruction_status IN ('待处理', '处理中', '已完成', '失败')),
    CONSTRAINT ck_texture_resolution CHECK (texture_resolution IN ('1K', '2K', '4K') OR texture_resolution IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_digital_reconstruction_site ON digital_reconstruction (site_id);

-- ============================================================
-- 7. PostGIS 几何字段 SRID 校验与设置
-- ============================================================

-- climate_vulnerability_assessment.risk_zone_geom
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'climate_vulnerability_assessment' 
        AND column_name = 'risk_zone_geom'
    ) THEN
        PERFORM UpdateGeometrySRID('climate_vulnerability_assessment', 'risk_zone_geom', 4326);
    END IF;
END $$;

-- agricultural_impact_assessment.benefit_zone_geom
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'agricultural_impact_assessment' 
        AND column_name = 'benefit_zone_geom'
    ) THEN
        PERFORM UpdateGeometrySRID('agricultural_impact_assessment', 'benefit_zone_geom', 4326);
    END IF;
END $$;

-- ============================================================
-- 8. 触发器函数：气候风险告警
-- ============================================================
CREATE OR REPLACE FUNCTION climate_risk_alert_trigger_func()
RETURNS TRIGGER AS $$
DECLARE
    site_name_var VARCHAR(200);
BEGIN
    IF NEW.vulnerability_category = '高' OR NEW.flood_risk_level IN ('高', '极高') THEN
        SELECT name INTO site_name_var FROM water_heritage_sites WHERE id = NEW.site_id;
        
        INSERT INTO alert_records (site_id, alert_type, alert_level, message, mqtt_topic)
        VALUES (
            NEW.site_id,
            '气候风险',
            CASE 
                WHEN NEW.flood_risk_level = '极高' OR NEW.vulnerability_category = '高' THEN '紧急'
                ELSE '高'
            END,
            '水利遗迹【' || COALESCE(site_name_var, 'ID:' || NEW.site_id) || '】检测到气候风险：脆弱性等级=' || NEW.vulnerability_category || 
            '，洪水风险等级=' || NEW.flood_risk_level || 
            '，情景=' || NEW.scenario || '/' || NEW.assessment_year || '，请及时关注！',
            'heritage/climate_alert/' || NEW.site_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS climate_risk_alert_trigger ON climate_vulnerability_assessment;
CREATE TRIGGER climate_risk_alert_trigger
AFTER INSERT OR UPDATE ON climate_vulnerability_assessment
FOR EACH ROW EXECUTE FUNCTION climate_risk_alert_trigger_func();

-- ============================================================
-- 9. 触发器函数：重大网络协同发现告警
-- ============================================================
CREATE OR REPLACE FUNCTION network_synergy_trigger_func()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.synergy_score >= 0.80 THEN
        INSERT INTO alert_records (site_id, alert_type, alert_level, message, mqtt_topic)
        VALUES (
            (SELECT s.id FROM water_heritage_sites s
             INNER JOIN network_member_site nms ON s.id = nms.site_id
             WHERE nms.network_analysis_id = NEW.id
             ORDER BY nms.node_betweenness DESC
             LIMIT 1),
            '重大协同发现',
            '中',
            '水利网络【' || NEW.region || '】检测到重大协同效应：协同得分=' || 
            ROUND(NEW.synergy_score::numeric, 4) || 
            '，节点数=' || NEW.total_nodes || 
            '，边数=' || NEW.total_edges || 
            '，级联灌溉效率=' || ROUND(NEW.cascade_irrigation_efficiency::numeric, 4) || 
            '，建议进一步研究该区域的历史水利协同机制！',
            'heritage/network_synergy/' || NEW.id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS network_synergy_trigger ON hydraulic_network_analysis;
CREATE TRIGGER network_synergy_trigger
AFTER INSERT OR UPDATE ON hydraulic_network_analysis
FOR EACH ROW EXECUTE FUNCTION network_synergy_trigger_func();

-- ============================================================
-- 10. 扩展视图：遗迹综合信息视图 V2
-- ============================================================
CREATE OR REPLACE VIEW v_site_comprehensive AS
SELECT 
    s.*,
    ST_X(s.geom) AS lng,
    ST_Y(s.geom) AS lat,
    r.original_irrigation_capacity,
    r.actual_irrigation_capacity,
    r.water_supply_range_geom,
    a.total_score,
    a.grade,
    a.restoration_potential,
    d.name as dynasty_name,
    d.start_year as dynasty_start,
    d.end_year as dynasty_end,
    ag.yield_increase_rate,
    ag.annual_yield_increase_kg,
    hna.synergy_score,
    cva.overall_vulnerability_score,
    cva.vulnerability_category,
    dr.reconstruction_status,
    dr.vr_experience_url
FROM water_heritage_sites s
LEFT JOIN functional_restoration r ON s.id = r.site_id
LEFT JOIN sustainability_assessment a ON s.id = a.site_id
LEFT JOIN dynasty_dict d ON s.dynasty_order = d."order"
LEFT JOIN agricultural_impact_assessment ag ON s.id = ag.site_id
LEFT JOIN network_member_site nms ON s.id = nms.site_id
LEFT JOIN hydraulic_network_analysis hna ON nms.network_analysis_id = hna.id
    AND hna.analyzed_at = (
        SELECT MAX(hna2.analyzed_at)
        FROM hydraulic_network_analysis hna2
        INNER JOIN network_member_site nms2 ON hna2.id = nms2.network_analysis_id
        WHERE nms2.site_id = s.id
    )
LEFT JOIN climate_vulnerability_assessment cva ON s.id = cva.site_id
    AND cva.scenario = 'RCP4.5'
    AND cva.assessment_year = 2050
LEFT JOIN digital_reconstruction dr ON s.id = dr.site_id;

-- ============================================================
-- 11. 统计信息收集
-- ============================================================
ANALYZE ancient_crop_yield;
ANALYZE agricultural_impact_assessment;
ANALYZE hydraulic_network_analysis;
ANALYZE network_member_site;
ANALYZE climate_vulnerability_assessment;
ANALYZE digital_reconstruction;
