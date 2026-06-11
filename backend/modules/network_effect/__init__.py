"""
网络效应分析独立模块
提供水利工程群网络构建、度量计算、中心性分析、协同效应评估、水系补全及不确定性量化等纯算法功能

不依赖 FastAPI、SQLAlchemy、Redis 等框架，可独立使用
"""

from .graph import HydraulicNetworkGraph

from .analyzer import (
    analyze_synergy_effects,
    NetworkAnalyzerService,
    get_network_service,
)

from .completion import (
    HydrologicalNetworkCompletor,
    UncertaintyAwareNetworkAnalyzer,
)

from .utils import (
    haversine_distance_km,
    get_approx_elevation,
    is_downstream_flow,
    percentile,
    compute_stats,
    text_contains_hydrology_keyword,
)

__all__ = [
    'HydraulicNetworkGraph',
    'analyze_synergy_effects',
    'NetworkAnalyzerService',
    'get_network_service',
    'HydrologicalNetworkCompletor',
    'UncertaintyAwareNetworkAnalyzer',
    'haversine_distance_km',
    'get_approx_elevation',
    'is_downstream_flow',
    'percentile',
    'compute_stats',
    'text_contains_hydrology_keyword',
]
