"""重构验证脚本 - 验证modules和workers层导入和基础功能"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print('=' * 70)
print('重构验证 - modules层 + workers层')
print('=' * 70)
print()

passed = 0
failed = 0

def check(name, func):
    global passed, failed
    try:
        result = func()
        print(f'✅ {name}')
        if result:
            print(f'   → {result}')
        passed += 1
        return True
    except Exception as e:
        print(f'❌ {name}: {e}')
        import traceback
        traceback.print_exc()
        failed += 1
        return False

# ==============================================
# modules.agricultural_impact
# ==============================================
print('【模块 1: agricultural_impact')

def test_agri_import():
    from modules.agricultural_impact import (
        AquaCropSimplifiedModel,
        AgriculturalImpactAnalyzer,
        ParameterSensitivityAnalyzer,
        EnsembleAquaCropSimulator,
        _safe_div, _clamp,
    )
    return f'4个核心类 + 工具函数'
check('导入测试', test_agri_import)

def test_agri_model():
    from modules = __import__('modules.agricultural_impact', fromlist=['AquaCropSimplifiedModel'])
    model = modules.AquaCropSimplifiedModel(crop_type='麦', region='中原地区')
    return f'总生育期={model.total_growing_days}天, 收获指数={model.harvest_index:.3f}'
check('AquaCrop模型初始化', test_agri_model)

def test_agri_simulation():
    from modules.agricultural_impact import AquaCropSimplifiedModel
    model = AquaCropSimplifiedModel(crop_type='粟', region='关中地区')
    n = model.total_growing_days
    precip = [3.0] * n
    et0 = [4.0] * n
    temps = [20.0] * n
    result = model.run_full_simulation(precip, et0, temps, irrigation_enabled=True)
    yield_irr = result.get('yield_with_irrigation', 0)
    yield_rain = result.get('yield_rainfed', 0)
    gain = (yield_irr - yield_rain) / max(yield_rain, 1) * 100
    return f'灌溉产量={yield_irr:.1f}kg/亩, 雨养={yield_rain:.1f}kg/亩, 增产+{gain:.0f}%'
check('作物模型模拟运行', test_agri_simulation)

def test_agri_ensemble():
    from modules.agricultural_impact import EnsembleAquaCropSimulator
    sim = EnsembleAquaCropSimulator(crop_type='粟', region='中原地区', n_members=20)
    n = 120
    result = sim.run_ensemble_simulation(
        precip_list=[3.0]*n, et0_list=[4.0]*n, temp_list=[20.0]*n,
        irrigation_enabled=True,
    )
    mean_yield = result.get('mean_yield', 0)
    cv = result.get('coefficient_of_variation', 0)
    return f'集合均值={mean_yield:.1f}kg/亩, CV={cv:.3f}'
check('集合模拟', test_agri_ensemble)

print()

# ==============================================
# modules.network_effect
# ==============================================
print('【模块 2: network_effect')

def test_net_import():
    from modules.network_effect import (
        HydraulicNetworkGraph,
        NetworkAnalyzerService,
        HydrologicalNetworkCompletor,
        UncertaintyAwareNetworkAnalyzer,
        haversine_distance_km,
    )
    return '4个核心类 + 工具函数'
check('导入测试', test_net_import)

def test_net_graph():
    from modules.net = __import__('modules.network_effect', fromlist=['HydraulicNetworkGraph'])
    graph = modules.net.HydraulicNetworkGraph()
    sites = [
        {'site_id': i, 'longitude': 113.0 + i*0.05, 'latitude': 34.0, 'site_type': '灌溉渠道', 'dynasty_order': 3}
        for i in range(1, 11)
    ]
    graph.build_graph_from_sites(sites)
    metrics = graph.calculate_graph_metrics()
    nc = metrics.get('node_count', 0)
    ec = metrics.get('edge_count', 0)
    conn = metrics.get('connectivity', 0)
    return f'节点={nc}, 边={ec}, 连通度={conn:.3f}'
check('网络图构建与度量', test_net_graph)

def test_net_centrality():
    from modules.network_effect import HydraulicNetworkGraph
    graph = HydraulicNetworkGraph()
    sites = [
        {'site_id': i, 'longitude': 113.0 + i*0.05, 'latitude': 34.0, 'site_type': '灌溉渠道'}
        for i in range(1, 11)
    ]
    graph.build_graph_from_sites(sites)
    cents = graph.calculate_node_centralities()
    return f'计算了{len(cents)}个节点的中心性'
check('节点中心性计算', test_net_centrality)

def test_net_completion():
    from modules.network_effect import HydrologicalNetworkCompletor
    completor = HydrologicalNetworkCompletor()
    sites = [
        {'site_id': i, 'longitude': 113.0 + i*0.03, 'latitude': 34.0,
         'site_type': '灌溉渠道', 'region': '中原地区', 'dynasty_order': 3}
        for i in range(1, 11)
    ]
    result = completor.infer_missing_connections(sites, known_edges=[], max_distance_km=50)
    inferred = result.get('inferred_edges', [])
    return f'推断边数={len(inferred)}'
check('水系补全算法', test_net_completion)

print()

# ==============================================
# modules.climate_vulnerability
# ==============================================
print('【模块 3: climate_vulnerability')

def test_clim_import():
    from modules.climate_vulnerability import (
        ClimateScenarioSimulator,
        FloodRiskAssessor,
        DroughtRiskAssessor,
        ClimateVulnerabilityIntegrator,
        ClimateStatisticalDownscaler,
        BiasCorrectedRiskAssessor,
        hargreaves_pet,
        calculate_spei,
    )
    return '6个核心类 + 2个工具函数'
check('导入测试', test_clim_import)

def test_clim_scenario():
    from modules.climate_vulnerability import ClimateScenarioSimulator
    sim = ClimateScenarioSimulator('中原地区')
    result = sim.simulate_future_climate_series('RCP4.5', 2050)
    t = result.get('annual_avg_temp', 0)
    p = result.get('annual_total_precip', 0)
    return f'年均温={t:.2f}℃, 年降水={p:.1f}mm'
check('气候情景模拟', test_clim_scenario)

def test_clim_flood():
    from modules.climate_vulnerability import FloodRiskAssessor
    assessor = FloodRiskAssessor()
    site = {'site_type': '蓄水陂塘', 'irrigation_area': 500, 'longitude': 113.0, 'latitude': 34.0}
    rest = {'design_storage_million_m3=150000, 'current_storage_efficiency': 0.7}
    future_climate = {'annual_avg_temp': 22.0, 'extreme_precip_days': 8}
    result = assessor.assess_flood_risk(site, rest, future_climate, 'RCP8.5', 2070)
    level = result.get('flood_risk_level', '?')
    depth = result.get('inundation_depth_m', 0)
    return f'风险等级={level}, 淹没深度={depth:.2f}m'
check('洪水风险评估', test_clim_flood)

def test_clim_downscale():
    from modules.climate_vulnerability import ClimateStatisticalDownscaler
    ds = ClimateStatisticalDownscaler('中原地区', site_lat=34.0, site_lon=113.0)
    result = ds.delta_method_downscale(
        gcm_temp=21.5, gcm_precip=700,
        baseline_climate={'avg_temp': 20.0, 'total_precip': 650},
    )
    t = result.get('downscaled_temp', 0)
    return f'降尺度后温度={t:.2f}℃'
check('统计降尺度', test_clim_downscale)

print()

# ==============================================
# modules.digital_display
# ==============================================
print('【模块 4: digital_display')

def test_dig_import():
    from modules.digital_display import (
        DigitalReconstructionPipeline,
        MultiViewReconstructionFusionEngine,
        DeepLearningImageEnhancer,
        QualityGuaranteedReconstructor,
        RECONSTRUCTION_STAGES,
        RECONSTRUCTION_METHODS,
    )
    return '4个核心类 + 常量'
check('导入测试', test_dig_import)

def test_dig_pipeline():
    from modules.digital_display import DigitalReconstructionPipeline
    pipeline = DigitalReconstructionPipeline()
    photos = [f'https://example.com/p{i}.jpg' for i in range(1, 9)]
    result = pipeline.run_full_pipeline(
        photo_urls=photos,
        method='摄影测量',
        generate_vr=True,
        site_metadata={'site_id': 1, 'name': '测试遗址'},
    )
    status = result.get('status', '?')
    pts = result.get('point_cloud_count', 0)
    faces = result.get('mesh_face_count', 0)
    return f'状态={status}, 点云={pts}, 网格面={faces}'
check('重建管线运行', test_dig_pipeline)

def test_dig_enhance():
    from modules.digital_display import DeepLearningImageEnhancer
    enhancer = DeepLearningImageEnhancer()
    result = enhancer.deep_denoise({'quality_score': 45}, strength='medium')
    gain = result.get('psnr_gain_db', 0)
    return f'去噪PSNR增益={gain:.1f}dB'
check('深度学习去噪', test_dig_enhance)

def test_dig_mvr():
    from modules.digital_display import MultiViewReconstructionFusionEngine
    engine = MultiViewReconstructionFusionEngine()
    photos = [{'id': i, 'quality_score': 50 + i*5} for i in range(8)]
    clusters = engine.cluster_photo_viewpoints(photos)
    return f'视角聚类数={len(clusters.get(clusters', []))}'
check('多视角融合引擎', test_dig_mvr)

def test_dig_quality():
    from modules.digital_display import QualityGuaranteedReconstructor
    recon = QualityGuaranteedReconstructor()
    photos = [f'https://example.com/p{i}.jpg' for i in range(1, 9)]
    result = recon.run_guaranteed_reconstruction(
        site_id=1, photos=photos, method='摄影测量',
        generate_vr=True, min_quality_threshold=60,
    )
    quality = result.get('quality_assessment', {}).get('overall_quality', 0)
    return f'质量分={quality:.1f}'
check('质量保证重建', test_dig_quality)

print()

# ==============================================
# workers层
# ==============================================
print('【Worker 1: reconstruction_worker')

def test_worker_recon_import():
    from workers import ReconstructionWorker, TaskStatus, get_default_worker
    return 'Reconstruction Worker'
check('导入测试', test_worker_recon_import)

def test_worker_recon_create():
    from workers import ReconstructionWorker
    worker = ReconstructionWorker(max_workers=2)
    worker.start()
    task_id = worker.submit_task(
        site_id=1,
        photo_urls=[f'https://example.com/p{i}.jpg' for i in range(1, 6)],
        method='摄影测量',
        priority=3,
    )
    status = worker.get_task_status(task_id)
    worker.stop(wait=False)
    return f'task_id={task_id[:8]}..., 状态={status.get(status", "?")}'
check('重建Worker基本功能', test_worker_recon_create)

print()

print('【Worker 2: crop_model_worker')

def test_worker_crop_import():
    from workers import CropModelWorker, TaskType
    return 'CropModel Worker'
check('导入测试', test_worker_crop_import)

def test_worker_crop_create():
    from workers import CropModelWorker
    worker = CropModelWorker(max_workers=2)
    worker.start()
    task_id = worker.submit_simulation(
        crop_type='粟',
        region='中原地区',
        precip_data=[3.0]*120,
        et0_data=[4.0]*120,
        temp_data=[20.0]*120,
        irrigation_enabled=True,
    )
    status = worker.get_task_status(task_id)
    worker.stop(wait=False)
    return f'task_id={task_id[:8]}..., 状态={status.get("status", "?")}'
check('作物模型Worker基本功能', test_worker_crop_create)

print()

# ==============================================
# 总结
# ==============================================
print('=' * 70)
print(f'验证结果: 通过 {passed} 项, 失败 {failed} 项')
if failed == 0:
    print('🎉 全部重构模块验证通过！')
else:
    print('⚠️  部分模块验证失败，请检查上方错误信息')
print('=' * 70)
