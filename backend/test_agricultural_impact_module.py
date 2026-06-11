"""
测试 agricultural_impact 模块
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.agricultural_impact import (
    AquaCropSimplifiedModel,
    AgriculturalImpactAnalyzer,
    ParameterSensitivityAnalyzer,
    EnsembleAquaCropSimulator,
    _safe_div,
    _clamp,
    _safe_mean,
    _safe_std,
    _safe_percentile,
)

def test_utils():
    """测试工具函数"""
    print("=== 工具函数测试 ===")
    print(f"_safe_div(10, 2) = {_safe_div(10, 2)}")
    print(f"_safe_div(10, 0) = {_safe_div(10, 0)}")
    print(f"_clamp(15, 0, 10) = {_clamp(15, 0, 10)}")
    print(f"_clamp(-5, 0, 10) = {_clamp(-5, 0, 10)}")
    print(f"_safe_mean([1,2,3,4,5]) = {_safe_mean([1,2,3,4,5])}")
    print(f"_safe_std([1,2,3,4,5]) = {_safe_std([1,2,3,4,5])}")
    print(f"_safe_percentile([1,2,3,4,5], 50) = {_safe_percentile([1,2,3,4,5], 50)}")
    print("工具函数测试通过\n")

def test_crop_model():
    """测试作物模型"""
    print("=== 作物模型测试 ===")
    model = AquaCropSimplifiedModel('粟', '中原地区')
    print(f"作物类型: {model.crop_type}")
    print(f"区域: {model.region}")
    print(f"总生育期天数: {model.total_growing_days}")
    print(f"TAW_mm: {model.TAW_mm}")
    print(f"收获指数: {model.harvest_index}")
    
    et0 = model._calculate_et0_penman_monteith(25.0, 60.0, 2.0, 15.0, 100.0)
    print(f"ET0 (25°C, 60%湿度): {round(et0, 3)} mm/day")
    
    cc = model._canopy_cover_dynamics(50)
    print(f"第50天冠层覆盖度: {round(cc, 3)}")
    
    import random
    random.seed(42)
    n_days = 120
    precip = [max(0, random.gauss(2.5, 3.0)) for _ in range(n_days)]
    et0_list = [3.0 + random.gauss(0, 0.5) for _ in range(n_days)]
    temps = [20.0 + 10 * (i/n_days) + random.gauss(0, 2) for i in range(n_days)]
    
    result = model.run_full_simulation(
        precipitation_mm_per_day=precip,
        et0_mm_per_day=et0_list,
        temperatures_c=temps,
        irrigation_capability_m3_per_day=500.0,
        irrigation_area_mu=100.0,
        historical_baseline_yield_kg_per_mu=150.0,
    )
    
    print(f"\n完整模拟结果:")
    print(f"  无灌溉亩产: {result['yield_without_irrigation_kg_per_mu']} kg/亩")
    print(f"  有灌溉亩产: {result['yield_with_irrigation_kg_per_mu']} kg/亩")
    print(f"  增产率: {round(result['yield_increase_rate'] * 100, 2)} %")
    print(f"  水分利用效率: {result['water_use_efficiency_kg_per_m3']} kg/m³")
    print(f"  总生物量(无灌溉): {result['total_biomass_no_irrigation_kg_per_ha']} kg/ha")
    print("作物模型测试通过\n")

def test_impact_analyzer():
    """测试影响分析器"""
    print("=== 影响分析器测试 ===")
    analyzer = AgriculturalImpactAnalyzer()
    
    impact_result = analyzer.analyze_site_impact(
        longitude=113.65,
        latitude=34.76,
        region='中原地区',
        dynasty_order=11,
        irrigation_area_mu=500.0,
        irrigation_capability_m3_per_day=1000.0,
    )
    
    print(f"主导作物: {impact_result['dominant_crop']}")
    print(f"总影响面积: {impact_result['total_influenced_area_mu']} 亩")
    print(f"增产率: {round(impact_result['yield_increase_rate'] * 100, 2)} %")
    print(f"年增产量: {impact_result['annual_yield_increase_kg']} kg")
    print(f"受益农户数: {impact_result['farmers_benefited_count']} 户")
    print(f"总农业人口: {impact_result['total_farmers']} 人")
    print(f"水分利用效率: {impact_result['water_use_efficiency_kg_per_m3']} kg/m³")
    print(f"置信度: {round(impact_result['confidence_score'] * 100, 1)} %")
    
    benefit_zone = analyzer.estimate_benefit_zone(
        longitude=113.65,
        latitude=34.76,
        irrigation_area_mu=500.0,
        yield_increase_rate=0.25,
        site_id=1,
        site_name='测试遗址',
    )
    print(f"\n受益区估算:")
    print(f"  受益区类型数: {len(benefit_zone['zones'])}")
    for zone_name, zone_data in benefit_zone['zones'].items():
        print(f"    {zone_name}: 半径={zone_data['radius_km']}km, 面积={zone_data['area_mu']}亩")
    
    farmer_pop = analyzer.estimate_farmer_population('中原地区', 500.0)
    print(f"\n农户人口估算:")
    print(f"  区域: {farmer_pop['region']}")
    print(f"  农户数: {farmer_pop['households']} 户")
    print(f"  总人口: {farmer_pop['total_farmers']} 人")
    print(f"  农户密度: {farmer_pop['farmer_density_per_100mu']} 人/百亩")
    
    sites = [
        {'site_id': 1, 'longitude': 113.65, 'latitude': 34.76, 'region': '中原地区', 
         'dynasty_order': 11, 'irrigation_area_mu': 200.0, 'irrigation_capability_m3_per_day': 500.0},
        {'site_id': 2, 'longitude': 108.95, 'latitude': 34.27, 'region': '关中地区',
         'dynasty_order': 11, 'irrigation_area_mu': 300.0, 'irrigation_capability_m3_per_day': 800.0},
    ]
    batch_results = analyzer.analyze_batch(sites)
    print(f"\n批量分析结果: {len(batch_results)} 个遗址")
    print("影响分析器测试通过\n")

def test_ensemble():
    """测试集合模拟"""
    print("=== 集合模拟测试 ===")
    
    import random
    random.seed(123)
    n_days = 100
    precip = [max(0, random.gauss(2.0, 2.5)) for _ in range(n_days)]
    et0_list = [3.5 + random.gauss(0, 0.6) for _ in range(n_days)]
    temps = [22.0 + 8 * (i/n_days) + random.gauss(0, 2.5) for i in range(n_days)]
    
    sensitivity = ParameterSensitivityAnalyzer('粟', '中原地区')
    print(f"敏感性参数数量: {len(sensitivity.SENSITIVITY_PARAMS)}")
    print(f"参数范围数量: {len(sensitivity.param_ranges)}")
    
    local_sens = sensitivity.analyze_local_sensitivity(
        AquaCropSimplifiedModel,
        sensitivity.param_baselines,
        precip, et0_list, temps,
        irrigation_capability=500.0,
        irrigation_area=100.0,
        baseline_yield=150.0,
        n_levels=5,
    )
    print(f"\n局部敏感性分析: {len(local_sens)} 个参数")
    if local_sens:
        sorted_params = sorted(local_sens.items(), key=lambda x: x[1].get('sensitivity', 0), reverse=True)
        print("  Top 5 敏感参数:")
        for i, (param, data) in enumerate(sorted_params[:5]):
            print(f"    {i+1}. {param}: 敏感性={data['sensitivity']}, 变化={data['pct_change']}%")
    
    report = sensitivity.generate_sensitivity_report(local_sens)
    print(f"\n敏感性报告:")
    print(f"  高敏感参数: {len(report['classifications']['high'])} 个")
    print(f"  中敏感参数: {len(report['classifications']['medium'])} 个")
    print(f"  低敏感参数: {len(report['classifications']['low'])} 个")
    print(f"  Top 3 关键参数: {report['top3_critical_params']}")
    
    ensemble = EnsembleAquaCropSimulator('粟', '中原地区', n_members=20)
    print(f"\n集合模拟引擎:")
    print(f"  集合成员数: {ensemble.n_members}")
    print(f"  参数数量: {len(ensemble.param_names)}")
    
    ens_result = ensemble.run_ensemble_simulation(
        precip, et0_list, temps,
        irrigation_capability=500.0,
        irrigation_area=100.0,
        baseline_yield=150.0,
        dynasty_order=11,
        method='lhs',
    )
    print(f"\n集合模拟结果:")
    stats = ens_result['statistics']
    print(f"  平均产量: {stats['mean_yield']} kg/亩")
    print(f"  中位数产量: {stats['median_yield']} kg/亩")
    print(f"  标准差: {stats['std']} kg/亩")
    print(f"  变异系数: {stats['cv']}")
    print(f"  95%置信区间: [{stats['ci_95_lower']}, {stats['ci_95_upper']}]")
    print(f"  变异范围: {stats['spread']} kg/亩")
    
    reliability = ens_result['reliability']
    print(f"\n可靠性:")
    print(f"  PIT均匀性: {reliability['pit_uniformity']}")
    print(f"  异常成员数: {reliability['outlier_count']}")
    print(f"  成功成员数: {reliability['successful_members']}")
    
    post_result = ensemble.post_process_ensemble_results(
        ens_result,
        include_members=False,
        observations=None,
    )
    print(f"\n后处理结果:")
    post = post_result['post_processed']
    print(f"  原始均值: {post['raw_mean_yield']} kg/亩")
    print(f"  加权均值: {post['weighted_mean_yield']} kg/亩")
    print(f"  是否收敛: {post['converged']}")
    print(f"  收敛差异: {post['convergence_diff_pct']} %")
    
    print("集合模拟测试通过\n")

def main():
    """主测试函数"""
    print("=" * 60)
    print("agricultural_impact 模块验证测试")
    print("=" * 60)
    print()
    
    try:
        test_utils()
        test_crop_model()
        test_impact_analyzer()
        test_ensemble()
        
        print("=" * 60)
        print("所有测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
