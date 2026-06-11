"""
水利工程网络分析参数 - 外置配置
工程连通性判定、节点角色、网络度量权重、水系信息及可视化样式
"""
from typing import Dict, List, Any


# ========== 工程连通判定标准 ==========
CONNECTION_CRITERIA: Dict[str, Any] = {
    'max_distance_km': 50,
    'same_watershed_required': True,
    'elevation_difference_max_m': 100,
    'downstream_flow_required': True,
}


# ========== 节点角色阈值 ==========
# 基于网络拓扑属性判定节点功能角色
NODE_ROLE_THRESHOLDS: Dict[str, float] = {
    'hub_min_degree': 5,
    'intermediary_min_betweenness': 0.15,
    'terminal_max_degree': 1,
    'isolated_degree': 0,
}


# ========== 网络度量权重 ==========
# 协同效应综合得分的权重分配
NETWORK_METRIC_WEIGHTS: Dict[str, float] = {
    'connectivity': 0.30,
    'redundancy': 0.20,
    'cascade_efficiency': 0.25,
    'flood_regulation': 0.25,
}


# ========== 梯级灌溉效率分级 ==========
# 级联灌溉系统输水效率等级阈值
CASCADE_IRRIGATION_THRESHOLDS: Dict[str, float] = {
    'optimal': 0.85,
    'good': 0.65,
    'medium': 0.45,
    'poor': 0.25,
}


# ========== 防洪调蓄容量因子 ==========
# 各类水利设施对区域综合防洪能力的贡献系数
FLOOD_REGULATION_CAPACITY_FACTORS: Dict[str, float] = {
    'single_reservoir_factor': 0.12,
    'cascade_factor': 0.28,
    'channel_network_factor': 0.35,
    'levee_factor': 0.25,
}


# ========== 12区域水系信息 ==========
# 基于中国历史自然地理分区及河流水系分布
REGION_WATERSHEDS: Dict[str, Dict[str, Any]] = {
    '中原地区': {
        'name': '中原水系',
        'rivers': ['黄河', '洛水', '伊水', '沁水', '济水'],
        'avg_slope_pct': 1.2,
        'elevation_range_m': [50, 800],
    },
    '关中地区': {
        'name': '关中水系',
        'rivers': ['渭河', '泾河', '洛河', '灞河', '浐河'],
        'avg_slope_pct': 2.5,
        'elevation_range_m': [350, 1500],
    },
    '江南地区': {
        'name': '江南水系',
        'rivers': ['长江', '太湖', '钱塘江', '秦淮河', '吴淞江'],
        'avg_slope_pct': 0.3,
        'elevation_range_m': [2, 500],
    },
    '巴蜀地区': {
        'name': '巴蜀水系',
        'rivers': ['岷江', '沱江', '嘉陵江', '长江', '都江堰灌区'],
        'avg_slope_pct': 3.0,
        'elevation_range_m': [200, 3000],
    },
    '岭南地区': {
        'name': '岭南水系',
        'rivers': ['珠江', '西江', '北江', '东江', '韩江'],
        'avg_slope_pct': 0.8,
        'elevation_range_m': [0, 1000],
    },
    '江淮地区': {
        'name': '江淮水系',
        'rivers': ['淮河', '长江', '洪泽湖', '高邮湖', '巢湖'],
        'avg_slope_pct': 0.5,
        'elevation_range_m': [5, 300],
    },
    '山东地区': {
        'name': '山东水系',
        'rivers': ['黄河', '汶水', '泗水', '沂河', '小清河'],
        'avg_slope_pct': 1.8,
        'elevation_range_m': [2, 1100],
    },
    '河北地区': {
        'name': '河北水系',
        'rivers': ['海河', '永定河', '大清河', '子牙河', '南运河'],
        'avg_slope_pct': 1.0,
        'elevation_range_m': [5, 1500],
    },
    '河东地区': {
        'name': '河东水系',
        'rivers': ['汾河', '涑水', '黄河', '沁河', '浍河'],
        'avg_slope_pct': 2.8,
        'elevation_range_m': [300, 2500],
    },
    '河西地区': {
        'name': '河西走廊水系',
        'rivers': ['疏勒河', '黑河', '石羊河', '党河', '北大河'],
        'avg_slope_pct': 4.5,
        'elevation_range_m': [1000, 5000],
    },
    '辽东地区': {
        'name': '辽河水系',
        'rivers': ['辽河', '浑河', '太子河', '鸭绿江', '大凌河'],
        'avg_slope_pct': 2.2,
        'elevation_range_m': [0, 1300],
    },
    '滇黔地区': {
        'name': '西南水系',
        'rivers': ['金沙江', '乌江', '澜沧江', '怒江', '滇池'],
        'avg_slope_pct': 5.0,
        'elevation_range_m': [500, 4500],
    },
}


# ========== 图形可视化样式 ==========
GRAPH_VISUALIZATION_STYLES: Dict[str, Any] = {
    'node_colors_by_role': {
        'hub': '#e74c3c',
        'intermediary': '#3498db',
        'terminal': '#2ecc71',
        'isolated': '#95a5a6',
    },
    'edge_width_by_strength': {
        'strong': 3,
        'medium': 2,
        'weak': 1,
    },
}


def get_connection_eligible(distance_km: float, same_watershed: bool,
                            elevation_diff_m: float, downstream: bool) -> bool:
    """判定两个工程是否满足连通条件"""
    criteria = CONNECTION_CRITERIA
    if distance_km > criteria['max_distance_km']:
        return False
    if criteria['same_watershed_required'] and not same_watershed:
        return False
    if elevation_diff_m > criteria['elevation_difference_max_m']:
        return False
    if criteria['downstream_flow_required'] and not downstream:
        return False
    return True


def determine_node_role(degree: int, betweenness: float) -> str:
    """根据度和介数中心性判定节点角色"""
    thresholds = NODE_ROLE_THRESHOLDS
    if degree <= thresholds['isolated_degree']:
        return 'isolated'
    if degree <= thresholds['terminal_max_degree']:
        return 'terminal'
    if betweenness >= thresholds['intermediary_min_betweenness']:
        return 'intermediary'
    if degree >= thresholds['hub_min_degree']:
        return 'hub'
    if betweenness >= thresholds['intermediary_min_betweenness'] * 0.5:
        return 'intermediary'
    return 'terminal'


def calc_cascade_grade(efficiency: float) -> str:
    """根据梯级灌溉效率判定等级"""
    thresholds = CASCADE_IRRIGATION_THRESHOLDS
    if efficiency >= thresholds['optimal']:
        return 'optimal'
    if efficiency >= thresholds['good']:
        return 'good'
    if efficiency >= thresholds['medium']:
        return 'medium'
    if efficiency >= thresholds['poor']:
        return 'poor'
    return 'none'


def get_node_color(role: str) -> str:
    """获取节点角色对应的颜色"""
    colors = GRAPH_VISUALIZATION_STYLES['node_colors_by_role']
    return colors.get(role, '#95a5a6')


def get_edge_width(strength: str) -> int:
    """获取边强度对应的宽度"""
    widths = GRAPH_VISUALIZATION_STYLES['edge_width_by_strength']
    return widths.get(strength, 1)
