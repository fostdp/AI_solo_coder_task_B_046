"""
气候变化情景参数 - 外置配置
RCP排放情景、温度降水变化、极端事件及脆弱性评估参数
"""
from typing import Dict, List, Any


# ========== 气候情景定义 ==========
# 基于IPCC第五次评估报告(AR5)典型浓度路径
CLIMATE_SCENARIOS: Dict[str, Dict[str, str]] = {
    'RCP2.6': {
        'name': '低排放',
        'description': '2100升温<2℃，辐射强迫峰值后下降',
        'color': '#2ecc71',
    },
    'RCP4.5': {
        'name': '中低排放',
        'description': '2100升温2-3℃，辐射强迫稳定在4.5W/m²',
        'color': '#f1c40f',
    },
    'RCP8.5': {
        'name': '高排放',
        'description': '2100升温>4℃，辐射强迫持续上升至8.5W/m²',
        'color': '#e74c3c',
    },
}


# ========== 未来预测年份 ==========
FUTURE_YEARS: List[int] = [2030, 2050, 2070, 2100]


# ========== 温度变化幅度 ==========
# 单位：℃，相对于1986-2005基准期，基于CMIP5多模式集合平均估算
TEMPERATURE_CHANGE: Dict[str, Dict[int, float]] = {
    'RCP2.6': {
        2030: 0.9,
        2050: 1.3,
        2070: 1.5,
        2100: 1.6,
    },
    'RCP4.5': {
        2030: 1.0,
        2050: 1.9,
        2070: 2.5,
        2100: 2.8,
    },
    'RCP8.5': {
        2030: 1.2,
        2050: 2.4,
        2070: 3.9,
        2100: 5.2,
    },
}


# ========== 降水变化率 ==========
# 单位：%，相对于基准期，全国平均水平
# 规律：总体暖湿化趋势，南方增幅大于北方
PRECIPITATION_CHANGE: Dict[str, Dict[int, Dict[str, float]]] = {
    'RCP2.6': {
        2030: {'春': 1.5, '夏': 3.0, '秋': 0.5, '冬': 2.0},
        2050: {'春': 2.5, '夏': 4.5, '秋': 1.0, '冬': 3.0},
        2070: {'春': 3.0, '夏': 5.0, '秋': 1.5, '冬': 3.5},
        2100: {'春': 3.5, '夏': 5.5, '秋': 2.0, '冬': 4.0},
    },
    'RCP4.5': {
        2030: {'春': 2.0, '夏': 4.0, '秋': 1.0, '冬': 2.5},
        2050: {'春': 4.0, '夏': 7.0, '秋': 2.0, '冬': 4.5},
        2070: {'春': 5.5, '夏': 9.0, '秋': 3.0, '冬': 6.0},
        2100: {'春': 6.5, '夏': 10.5, '秋': 3.5, '冬': 7.0},
    },
    'RCP8.5': {
        2030: {'春': 2.5, '夏': 5.0, '秋': 1.5, '冬': 3.0},
        2050: {'春': 5.5, '夏': 10.0, '秋': 2.5, '冬': 5.5},
        2070: {'春': 9.0, '夏': 15.0, '秋': 4.5, '冬': 8.5},
        2100: {'春': 12.0, '夏': 19.0, '秋': 6.0, '冬': 11.0},
    },
}

# 区域降水调整系数（体现南北差异）
# 南方(江南、巴蜀、岭南、江淮、滇黔)降水增幅大于全国平均
# 北方(中原、关中、山东、河北、河东、河西、辽东)降水增幅小于全国平均，河西、辽东西北东北部分地区甚至减少
REGION_PRECIP_ADJUST: Dict[str, float] = {
    '中原地区': 0.80,
    '关中地区': 0.70,
    '江南地区': 1.35,
    '巴蜀地区': 1.25,
    '岭南地区': 1.40,
    '江淮地区': 1.20,
    '山东地区': 0.75,
    '河北地区': 0.65,
    '河东地区': 0.70,
    '河西地区': 0.40,
    '辽东地区': 0.55,
    '滇黔地区': 1.30,
}


# ========== 极端事件变化倍数 ==========
# 相对于基准期发生频率/强度的倍数
EXTREME_EVENT_CHANGE: Dict[str, Dict[int, Dict[str, float]]] = {
    'RCP2.6': {
        2030: {'flood_freq_multiple': 1.15, 'drought_freq_multiple': 1.10, 'storm_intensity_multiple': 1.08},
        2050: {'flood_freq_multiple': 1.30, 'drought_freq_multiple': 1.25, 'storm_intensity_multiple': 1.18},
        2070: {'flood_freq_multiple': 1.40, 'drought_freq_multiple': 1.35, 'storm_intensity_multiple': 1.25},
        2100: {'flood_freq_multiple': 1.45, 'drought_freq_multiple': 1.40, 'storm_intensity_multiple': 1.28},
    },
    'RCP4.5': {
        2030: {'flood_freq_multiple': 1.25, 'drought_freq_multiple': 1.20, 'storm_intensity_multiple': 1.15},
        2050: {'flood_freq_multiple': 1.60, 'drought_freq_multiple': 1.50, 'storm_intensity_multiple': 1.35},
        2070: {'flood_freq_multiple': 1.95, 'drought_freq_multiple': 1.85, 'storm_intensity_multiple': 1.55},
        2100: {'flood_freq_multiple': 2.15, 'drought_freq_multiple': 2.05, 'storm_intensity_multiple': 1.68},
    },
    'RCP8.5': {
        2030: {'flood_freq_multiple': 1.35, 'drought_freq_multiple': 1.30, 'storm_intensity_multiple': 1.22},
        2050: {'flood_freq_multiple': 2.00, 'drought_freq_multiple': 1.90, 'storm_intensity_multiple': 1.55},
        2070: {'flood_freq_multiple': 3.10, 'drought_freq_multiple': 2.95, 'storm_intensity_multiple': 2.05},
        2100: {'flood_freq_multiple': 4.20, 'drought_freq_multiple': 4.00, 'storm_intensity_multiple': 2.60},
    },
}


# ========== 洪水深度阈值 ==========
# 单位：m，映射到风险等级
FLOOD_DEPTH_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    '极低': {'min': 0.0, 'max': 0.3, 'risk_level': '无'},
    '低': {'min': 0.3, 'max': 0.5, 'risk_level': '低'},
    '中': {'min': 0.5, 'max': 1.0, 'risk_level': '中'},
    '高': {'min': 1.0, 'max': 2.0, 'risk_level': '高'},
    '极高': {'min': 2.0, 'max': 999.0, 'risk_level': '极高'},
}


# ========== 干旱SPEI阈值 ==========
# 标准化降水蒸散指数(SPEI)到干旱等级映射
DROUGHT_SPEI_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    '无': {'min': -0.5, 'max': 999.0, 'description': '无旱'},
    '低': {'min': -1.0, 'max': -0.5, 'description': '轻旱'},
    '中': {'min': -1.5, 'max': -1.0, 'description': '中旱'},
    '高': {'min': -2.0, 'max': -1.5, 'description': '重旱'},
    '极高': {'min': -999.0, 'max': -2.0, 'description': '特旱'},
}


# ========== 综合脆弱性矩阵 ==========
# 权重分配：洪灾权重0.45、旱灾权重0.35、工程结构状况权重0.20
VULNERABILITY_MATRIX: Dict[str, Any] = {
    'weights': {
        'flood_weight': 0.45,
        'drought_weight': 0.35,
        'structural_condition_weight': 0.20,
    },
    'thresholds': {
        '低': {'min': 0, 'max': 30},
        '较低': {'min': 30, 'max': 45},
        '中': {'min': 45, 'max': 60},
        '较高': {'min': 60, 'max': 75},
        '高': {'min': 75, 'max': 100},
    },
}


# ========== 适应性策略建议 ==========
# 按脆弱性等级给出对应的适应性措施建议
ADAPTATION_STRATEGIES: Dict[str, List[str]] = {
    '低': [
        '维持现有水利工程日常维护',
        '加强水文监测网络建设',
        '推广节水灌溉技术宣传',
    ],
    '较低': [
        '实施水利工程定期检修加固',
        '建立区域干旱预警机制',
        '优化作物种植结构',
        '开展小型农田水利建设',
    ],
    '中': [
        '对重点工程进行防渗加固改造',
        '建设区域应急备用水源',
        '推广高效节水灌溉面积',
        '制定流域水量统一调度方案',
        '开展洪水风险区划制图',
    ],
    '较高': [
        '启动病险水库除险加固工程',
        '新建/扩建区域性调蓄水库',
        '实施灌区续建配套与节水改造',
        '建立洪水保险与风险分担机制',
        '组织开展应急避难场所建设',
        '推进河湖水系连通工程',
    ],
    '高': [
        '实施大型水利枢纽新建工程',
        '建设跨流域调水工程体系',
        '开展全流域综合治理规划',
        '建立重大水安全保障体系',
        '实施生态移民与适应性搬迁',
        '构建多部门应急联动指挥平台',
        '投入专项资金长期投入机制',
        '开展气候变化适应性立法',
    ],
}


def get_temperature_change(scenario: str, year: int) -> float:
    """获取指定情景和年份的温度变化"""
    scenario_data = TEMPERATURE_CHANGE.get(scenario, {})
    return scenario_data.get(year, 0.0)


def get_precipitation_change(scenario: str, year: int, season: str, region: str = None) -> float:
    """获取指定情景、年份、季节的降水变化率，可按区域调整"""
    scenario_data = PRECIPITATION_CHANGE.get(scenario, {})
    year_data = scenario_data.get(year, {})
    base_pct = year_data.get(season, 0.0)
    if region:
        adjust = REGION_PRECIP_ADJUST.get(region, 1.0)
        return round(base_pct * adjust, 2)
    return base_pct


def get_flood_risk_level(depth_m: float) -> str:
    """根据洪水深度获取风险等级"""
    for level_name, level_info in FLOOD_DEPTH_THRESHOLDS.items():
        if level_info['min'] <= depth_m < level_info['max']:
            return level_info['risk_level']
    return '极高'


def get_drought_level(spei: float) -> str:
    """根据SPEI值获取干旱等级"""
    for level_name, level_info in DROUGHT_SPEI_THRESHOLDS.items():
        if level_info['min'] <= spei < level_info['max']:
            return level_info['description']
    return '特旱'


def calc_vulnerability_score(flood_score: float, drought_score: float, structural_score: float) -> float:
    """计算综合脆弱性得分(0-100)"""
    weights = VULNERABILITY_MATRIX['weights']
    score = (
        flood_score * weights['flood_weight']
        + drought_score * weights['drought_weight']
        + structural_score * weights['structural_condition_weight']
    )
    return round(min(100.0, max(0.0, score)), 1)


def get_vulnerability_level(score: float) -> str:
    """根据脆弱性得分获取等级"""
    for level_name, level_info in VULNERABILITY_MATRIX['thresholds'].items():
        if level_info['min'] <= score < level_info['max']:
            return level_name
    return '高'
