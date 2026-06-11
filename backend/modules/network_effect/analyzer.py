"""
网络分析业务逻辑模块
封装协同效应分析、网络分析服务等业务逻辑
"""
import math
from typing import List, Dict, Optional, Any

from common.params.network_params import (
    NETWORK_METRIC_WEIGHTS,
    FLOOD_REGULATION_CAPACITY_FACTORS,
)

from .graph import HydraulicNetworkGraph


def analyze_synergy_effects(graph: HydraulicNetworkGraph,
                            restorations: Dict[int, Any] = None) -> Dict[str, Any]:
    """
    分析网络协同效应

    Args:
        graph: 水利网络图实例
        restorations: 修复工程字典 {site_id: restoration_obj}，
                     修复对象需包含 actual_irrigation_capacity 属性

    Returns:
        协同效应分析结果字典
    """
    if restorations is None:
        restorations = {}

    n = len(graph.nodes)
    capacities: Dict[int, float] = {}

    for i in range(n):
        site_id = graph.idx_to_site_id[i]
        node_info = graph.nodes[i]
        if site_id in restorations and hasattr(restorations[site_id], 'actual_irrigation_capacity'):
            capacities[i] = float(restorations[site_id].actual_irrigation_capacity)
        else:
            capacities[i] = float(node_info.get('irrigation_area', 0.0)) * 0.8

    total_capacity = sum(capacities.values())
    loss_per_km = 0.005
    cascade_factor = 0.85

    all_cascade_paths = []
    for s in range(n):
        all_shortest = graph._dijkstra_shortest_path(s)
        for t in range(n):
            if s == t or t not in all_shortest:
                continue
            if capacities[s] <= 0:
                continue

            path_len = all_shortest[t]
            elev_s = graph.nodes[s]['elevation']
            elev_t = graph.nodes[t]['elevation']
            if elev_s <= elev_t:
                continue

            loss_factor = math.exp(-loss_per_km * path_len)
            cumulative_cap = capacities[s] * cascade_factor * loss_factor
            all_cascade_paths.append({
                'source': s,
                'target': t,
                'path_len_km': path_len,
                'base_capacity': capacities[s],
                'delivered_capacity': cumulative_cap,
                'efficiency': cascade_factor * loss_factor,
            })

    cascade_irrigation_efficiency = 0.0
    if total_capacity > 0 and all_cascade_paths:
        total_delivered = sum(p['delivered_capacity'] for p in all_cascade_paths)
        unique_paths_eff = total_delivered / (total_capacity * max(1, len(all_cascade_paths) / n))
        cascade_irrigation_efficiency = min(1.0, unique_paths_eff)

    reservoir_count = 0
    levee_count = 0
    channel_count = 0
    cascade_count = len(all_cascade_paths)

    for i in range(n):
        site_type = graph.nodes[i].get('type', '')
        if site_type == '陂':
            reservoir_count += 1
        elif site_type == '塘':
            reservoir_count += 1
        elif site_type == '堰':
            levee_count += 1
        elif site_type == '渠':
            channel_count += 1

    channel_density = 0.0
    if n > 0:
        channel_density = len(graph.edges) / n

    factors = FLOOD_REGULATION_CAPACITY_FACTORS
    raw_flood = (
        reservoir_count * factors['single_reservoir_factor'] +
        cascade_count * factors['cascade_factor'] +
        channel_density * factors['channel_network_factor'] +
        levee_count * factors['levee_factor']
    )
    flood_regulation_capacity = 1.0 - math.exp(-raw_flood / 2.0)
    flood_regulation_capacity = min(1.0, max(0.0, flood_regulation_capacity))

    metrics = graph.calculate_graph_metrics()
    weights = NETWORK_METRIC_WEIGHTS

    synergy_score = (
        metrics['network_connectivity'] * weights['connectivity'] +
        metrics['network_redundancy'] * weights['redundancy'] +
        cascade_irrigation_efficiency * weights['cascade_efficiency'] +
        flood_regulation_capacity * weights['flood_regulation']
    )
    synergy_score = min(1.0, max(0.0, synergy_score))

    if synergy_score >= 0.80:
        synergy_level = '优秀'
    elif synergy_score >= 0.65:
        synergy_level = '良好'
    elif synergy_score >= 0.50:
        synergy_level = '中等'
    elif synergy_score >= 0.30:
        synergy_level = '一般'
    else:
        synergy_level = '较弱'

    return {
        'cascade_irrigation_efficiency': round(cascade_irrigation_efficiency, 4),
        'flood_regulation_capacity': round(flood_regulation_capacity, 4),
        'synergy_score': round(synergy_score, 4),
        'synergy_level': synergy_level,
        'cascade_path_count': cascade_count,
        'reservoir_count': reservoir_count,
        'levee_count': levee_count,
        'channel_count': channel_count,
        'channel_density': round(channel_density, 4),
        'total_irrigation_capacity': round(total_capacity, 2),
    }


class NetworkAnalyzerService:
    """
    网络分析服务类（简化版，纯算法）
    封装图构建、度量计算、中心性分析、协同效应分析的完整流程
    """

    def __init__(self):
        self._graph_cache: Dict[str, HydraulicNetworkGraph] = {}

    def build_graph(self, region: str, sites: List) -> HydraulicNetworkGraph:
        """
        构建区域水利网络图

        Args:
            region: 区域名称
            sites: 遗址列表

        Returns:
            水利网络图实例
        """
        graph = HydraulicNetworkGraph(region)
        graph.build_graph_from_sites(sites)
        self._graph_cache[region] = graph
        return graph

    def get_cached_graph(self, region: str) -> Optional[HydraulicNetworkGraph]:
        """
        获取缓存的区域网络图

        Args:
            region: 区域名称

        Returns:
            缓存的网络图实例，不存在则返回 None
        """
        return self._graph_cache.get(region)

    def run_analysis(self, region: str, sites: List,
                     restorations: Dict[int, Any] = None) -> Dict[str, Any]:
        """
        执行完整的网络分析

        Args:
            region: 区域名称
            sites: 遗址列表
            restorations: 修复工程字典

        Returns:
            完整分析结果字典 {metrics, centralities, synergy, graph}
        """
        if len(sites) < 2:
            raise ValueError("遗址数量不足（至少需要2个）")

        graph = self.build_graph(region, sites)

        metrics = graph.calculate_graph_metrics()
        centralities = graph.calculate_node_centralities()
        synergy = analyze_synergy_effects(graph, restorations)

        critical_nodes_list = list(metrics['articulation_points'])
        degree_sorted = sorted(
            centralities.items(),
            key=lambda x: x[1]['degree'],
            reverse=True
        )[:10]
        top_degree_ids = [site_id for site_id, _ in degree_sorted]
        for sid in top_degree_ids:
            if sid not in critical_nodes_list:
                critical_nodes_list.append(sid)

        critical_nodes_data = {
            'articulation_points': list(metrics['articulation_points']),
            'top_degree_nodes': top_degree_ids,
            'all_critical': critical_nodes_list,
        }

        return {
            'graph': graph,
            'metrics': metrics,
            'centralities': centralities,
            'synergy': synergy,
            'critical_nodes': critical_nodes_data,
        }


_service_instance = None


def get_network_service() -> NetworkAnalyzerService:
    """
    获取网络分析服务单例

    Returns:
        NetworkAnalyzerService 单例实例
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = NetworkAnalyzerService()
    return _service_instance
