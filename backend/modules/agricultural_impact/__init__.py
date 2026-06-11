"""
农业影响评估模块 (agricultural_impact)
========================================

AquaCrop简化作物模型、农业影响评估、参数敏感性分析与集合模拟
纯算法实现，不依赖数据库、Web框架等外部组件

使用方式:
    from modules.agricultural_impact import (
        AquaCropSimplifiedModel,
        AgriculturalImpactAnalyzer,
        ParameterSensitivityAnalyzer,
        EnsembleAquaCropSimulator,
    )
"""

from .utils import (
    _safe_log,
    _safe_sqrt,
    _safe_div,
    _clamp,
    _safe_exp,
    _is_valid_number,
    _safe_mean,
    _safe_std,
    _safe_percentile,
)

from .crop_model import (
    AquaCropSimplifiedModel,
    CROP_KC,
    CROP_WATER_STRESS,
    AQUACROP_CONSTANTS,
    get_crop_kc,
    get_irrigation_gain,
)

from .impact_analyzer import (
    AgriculturalImpactAnalyzer,
    BENEFIT_ZONE_RADIUS_RATIOS,
    FARMER_DENSITY_PER_MU,
    REGIONS,
    get_baseline_yield,
)

from .ensemble import (
    ParameterSensitivityAnalyzer,
    EnsembleAquaCropSimulator,
)

__all__ = [
    # 核心类
    'AquaCropSimplifiedModel',
    'AgriculturalImpactAnalyzer',
    'ParameterSensitivityAnalyzer',
    'EnsembleAquaCropSimulator',
    # 工具函数
    '_safe_log',
    '_safe_sqrt',
    '_safe_div',
    '_clamp',
    '_safe_exp',
    '_is_valid_number',
    '_safe_mean',
    '_safe_std',
    '_safe_percentile',
    # 参数常量
    'CROP_KC',
    'CROP_WATER_STRESS',
    'AQUACROP_CONSTANTS',
    'BENEFIT_ZONE_RADIUS_RATIOS',
    'FARMER_DENSITY_PER_MU',
    'REGIONS',
    # 辅助函数
    'get_crop_kc',
    'get_baseline_yield',
    'get_irrigation_gain',
]

__version__ = '1.0.0'
__author__ = 'Agricultural Impact Module'
__description__ = 'AquaCrop简化作物模型与农业影响评估纯算法模块'
