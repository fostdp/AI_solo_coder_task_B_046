"""
AquaCrop简化版作物参数 - 外置配置
作物生长参数、产量基准、水分胁迫等农业科学参数
"""
from typing import Dict, List, Any


# ========== 作物列表 ==========
CROP_LIST: List[str] = ['粟', '稻', '麦', '黍', '豆']


# ========== 作物Kc参数及生长周期 ==========
# 基于FAO-56及中国农业气象试验站实测数据估算
CROP_KC: Dict[str, Dict[str, float]] = {
    '粟': {
        'initial': 0.35,
        'mid': 1.05,
        'late': 0.55,
        'length_init_days': 25,
        'length_dev_days': 30,
        'length_mid_days': 55,
        'length_late_days': 35,
        'rooting_depth_m': 1.2,
        'max_leaf_area_index': 4.5,
        'harvest_index': 0.38,
    },
    '稻': {
        'initial': 0.40,
        'mid': 1.20,
        'late': 0.65,
        'length_init_days': 30,
        'length_dev_days': 35,
        'length_mid_days': 60,
        'length_late_days': 40,
        'rooting_depth_m': 0.9,
        'max_leaf_area_index': 6.5,
        'harvest_index': 0.48,
    },
    '麦': {
        'initial': 0.30,
        'mid': 1.10,
        'late': 0.50,
        'length_init_days': 35,
        'length_dev_days': 40,
        'length_mid_days': 65,
        'length_late_days': 40,
        'rooting_depth_m': 1.5,
        'max_leaf_area_index': 5.5,
        'harvest_index': 0.42,
    },
    '黍': {
        'initial': 0.32,
        'mid': 1.00,
        'late': 0.50,
        'length_init_days': 20,
        'length_dev_days': 25,
        'length_mid_days': 45,
        'length_late_days': 30,
        'rooting_depth_m': 1.3,
        'max_leaf_area_index': 4.0,
        'harvest_index': 0.35,
    },
    '豆': {
        'initial': 0.38,
        'mid': 1.08,
        'late': 0.58,
        'length_init_days': 25,
        'length_dev_days': 30,
        'length_mid_days': 50,
        'length_late_days': 35,
        'rooting_depth_m': 1.0,
        'max_leaf_area_index': 5.0,
        'harvest_index': 0.40,
    },
}


# ========== 作物水分胁迫参数 ==========
# 基于AquaCrop模型手册典型值调整
CROP_WATER_STRESS: Dict[str, Dict[str, float]] = {
    '粟': {
        'Ks_upper_pct': 0.65,
        'Ks_lower_pct': 0.30,
        'yield_response_factor_Ky': 0.90,
        'stomatal_conductance_p50': 0.45,
    },
    '稻': {
        'Ks_upper_pct': 0.80,
        'Ks_lower_pct': 0.45,
        'yield_response_factor_Ky': 1.15,
        'stomatal_conductance_p50': 0.55,
    },
    '麦': {
        'Ks_upper_pct': 0.60,
        'Ks_lower_pct': 0.28,
        'yield_response_factor_Ky': 1.05,
        'stomatal_conductance_p50': 0.42,
    },
    '黍': {
        'Ks_upper_pct': 0.55,
        'Ks_lower_pct': 0.22,
        'yield_response_factor_Ky': 0.80,
        'stomatal_conductance_p50': 0.38,
    },
    '豆': {
        'Ks_upper_pct': 0.62,
        'Ks_lower_pct': 0.32,
        'yield_response_factor_Ky': 0.95,
        'stomatal_conductance_p50': 0.44,
    },
}


# ========== 12区域×5作物×17朝代基准产量矩阵 ==========
# 单位: kg/亩，基于中国农业史文献综合估算
# 规律：南方(江南、巴蜀、岭南、江淮、滇黔)稻产量高，北方麦产量高
#       唐(11)、北宋(13)、明清(16,17)产量高于远古，朝代越晚总体越高
# 朝代产量系数：以清代(17)为基准1.0
_DYNASTY_YIELD_COEFF: Dict[int, float] = {
    1: 0.40,   # 春秋
    2: 0.48,   # 战国
    3: 0.52,   # 秦
    4: 0.60,   # 西汉
    5: 0.65,   # 东汉
    6: 0.60,   # 三国
    7: 0.58,   # 西晋
    8: 0.60,   # 东晋
    9: 0.65,   # 南北朝
    10: 0.75,  # 隋
    11: 0.85,  # 唐
    12: 0.78,  # 五代
    13: 0.92,  # 北宋
    14: 0.90,  # 南宋
    15: 0.88,  # 元
    16: 0.98,  # 明
    17: 1.00,  # 清
}

# 各区域各作物清代(17)基准产量 kg/亩
_REGION_CROP_BASELINE_QING: Dict[str, Dict[str, float]] = {
    '中原地区': {'粟': 175, '稻': 145, '麦': 210, '黍': 125, '豆': 105},
    '关中地区': {'粟': 165, '稻': 120, '麦': 195, '黍': 115, '豆': 100},
    '江南地区': {'粟': 110, '稻': 280, '麦': 125, '黍': 80, '豆': 105},
    '巴蜀地区': {'粟': 130, '稻': 250, '麦': 140, '黍': 95, '豆': 110},
    '岭南地区': {'粟': 100, '稻': 260, '麦': 90, '黍': 85, '豆': 115},
    '江淮地区': {'粟': 135, '稻': 265, '麦': 145, '黍': 90, '豆': 100},
    '山东地区': {'粟': 180, '稻': 110, '麦': 220, '黍': 135, '豆': 110},
    '河北地区': {'粟': 170, '稻': 95, '麦': 205, '黍': 130, '豆': 95},
    '河东地区': {'粟': 160, '稻': 85, '麦': 190, '黍': 120, '豆': 90},
    '河西地区': {'粟': 140, '稻': 65, '麦': 170, '黍': 110, '豆': 80},
    '辽东地区': {'粟': 130, '稻': 70, '麦': 160, '黍': 105, '豆': 75},
    '滇黔地区': {'粟': 120, '稻': 220, '麦': 115, '黍': 90, '豆': 95},
}

# 12区域×5作物×17朝代 基准产量矩阵
BASELINE_YIELDS: Dict[str, Dict[str, Dict[int, float]]] = {}
for _region, _crop_yields in _REGION_CROP_BASELINE_QING.items():
    BASELINE_YIELDS[_region] = {}
    for _crop, _qing_yield in _crop_yields.items():
        BASELINE_YIELDS[_region][_crop] = {}
        for _dyn, _coeff in _DYNASTY_YIELD_COEFF.items():
            BASELINE_YIELDS[_region][_crop][_dyn] = round(_qing_yield * _coeff, 1)


# ========== 灌溉增产率因子 ==========
# 基于灌溉试验数据：灌溉对产量提升幅度，因作物和朝代技术而异
IRRIGATION_YIELD_GAIN_FACTOR: Dict[str, Any] = {
    '粟': {'minimum': 0.10, 'maximum': 0.40, 'typical': 0.25},
    '稻': {'minimum': 0.15, 'maximum': 0.55, 'typical': 0.35},
    '麦': {'minimum': 0.12, 'maximum': 0.45, 'typical': 0.30},
    '黍': {'minimum': 0.08, 'maximum': 0.35, 'typical': 0.22},
    '豆': {'minimum': 0.10, 'maximum': 0.38, 'typical': 0.24},
}

# 分朝代灌溉增产率修正系数（技术越成熟，灌溉效益越稳定）
_DYNASTY_IRRIG_COEFF: Dict[int, float] = {
    1: 0.65, 2: 0.70, 3: 0.73, 4: 0.78, 5: 0.80,
    6: 0.78, 7: 0.76, 8: 0.77, 9: 0.80, 10: 0.85,
    11: 0.92, 12: 0.86, 13: 0.96, 14: 0.95, 15: 0.93,
    16: 0.98, 17: 1.00,
}
for _crop_name in IRRIGATION_YIELD_GAIN_FACTOR:
    IRRIGATION_YIELD_GAIN_FACTOR[_crop_name]['by_dynasty'] = {}
    _typical = IRRIGATION_YIELD_GAIN_FACTOR[_crop_name]['typical']
    _min_val = IRRIGATION_YIELD_GAIN_FACTOR[_crop_name]['minimum']
    _max_val = IRRIGATION_YIELD_GAIN_FACTOR[_crop_name]['maximum']
    for _dyn, _coeff in _DYNASTY_IRRIG_COEFF.items():
        _gain = round(_typical * _coeff, 3)
        _gain = max(_min_val, min(_max_val, _gain))
        IRRIGATION_YIELD_GAIN_FACTOR[_crop_name]['by_dynasty'][_dyn] = _gain


# ========== FAO AquaCrop常量参数 ==========
# 参考AquaCrop v6.1官方手册默认值，针对中国古代农业背景微调
AQUACROP_CONSTANTS: Dict[str, float] = {
    'ET0_adjust_factor': 0.92,
    'soil_water_depletion_p_upper': 0.55,
    'soil_water_depletion_p_lower': 0.25,
    'total_available_water_mm_per_m': 150.0,
    'surface_storage_max_mm': 25.0,
    'canopy_growth_coeff': 0.0125,
    'canopy_decay_coeff': 0.0075,
    'soil_evaporation_ke_max': 1.10,
    'soil_evaporation_ke_min': 0.15,
    'z_topsoil_m': 0.10,
}


# ========== 受益区分级比例 ==========
# 以工程最大供水半径为基准，各受益带的半径比例
BENEFIT_ZONE_RADIUS_RATIOS: Dict[str, float] = {
    'core': 0.50,
    'radiating': 0.85,
    'marginal': 1.00,
}


# ========== 12区域平均农户密度 ==========
# 单位：人/百亩，基于中国历史人口地理研究估算
FARMER_DENSITY_PER_MU: Dict[str, float] = {
    '中原地区': 8.5,
    '关中地区': 7.2,
    '江南地区': 9.8,
    '巴蜀地区': 6.5,
    '岭南地区': 5.2,
    '江淮地区': 8.0,
    '山东地区': 8.8,
    '河北地区': 7.6,
    '河东地区': 6.0,
    '河西地区': 3.0,
    '辽东地区': 3.5,
    '滇黔地区': 4.2,
}


def get_crop_kc(crop_name: str, stage: str) -> float:
    """获取指定作物某生育阶段的Kc系数"""
    crop_params = CROP_KC.get(crop_name, {})
    return crop_params.get(stage, 0.80)


def get_baseline_yield(region: str, crop: str, dynasty_order: int) -> float:
    """获取指定区域、作物、朝代的基准亩产"""
    region_data = BASELINE_YIELDS.get(region, {})
    crop_data = region_data.get(crop, {})
    return crop_data.get(dynasty_order, 100.0)


def get_irrigation_gain(crop: str, dynasty_order: int) -> float:
    """获取指定作物在某朝代的灌溉增产率"""
    crop_factor = IRRIGATION_YIELD_GAIN_FACTOR.get(crop, {})
    by_dynasty = crop_factor.get('by_dynasty', {})
    return by_dynasty.get(dynasty_order, crop_factor.get('typical', 0.25))
