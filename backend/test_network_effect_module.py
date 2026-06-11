"""
测试 network_effect 模块
"""
import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.network_effect import (
    haversine_distance_km,
    is_downstream_flow,
    percentile,
    compute_stats,
    HydraulicNetworkGraph,
    analyze_synergy_effects,
    HydrologicalNetworkCompletor,
    UncertaintyAwareNetworkAnalyzer,
)


def test_utils():
    """测试工具函数"""
    print("=== 工具函数测试 ===")
    
    dist = haversine_distance_km(113.65, 34.76, 113.70, 34.80)
    print(f"haversine_distance_km(郑州附近两点) = {round(dist, 3)} km")
    
    s1 = SimpleNamespace(longitude=113.65, latitude=34.76)
    s2 = SimpleNamespace(longitude=113.70, latitude=34.70)
    downstream = is_downstream_flow(s1, s2, "中原地区")
    print(f"is_downstream_flow(中原地区) = {downstream}")
    
    p50 = percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50)
    print(f"percentile([1..10], 50) = {p50}")
    
    stats = compute_stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    print(f"compute_stats([1..10]):")
    print(f"  mean = {stats['mean']}")
    print(f"  std = {stats['std']}")
    print(f"  p5 = {stats['p5']}")
    print(f"  p50 = {stats['p50']}")
    print(f"  p95 = {stats['p95']}")
    
    print("工具函数测试通过\n")


def _create_test_sites(n=10):
    """创建测试用的遗址对象列表"""
    sites = []
    base_lon, base_lat = 113.65, 34.76
    site_types = ['陂', '塘', '堰', '渠', '陂', '塘', '堰', '渠', '陂', '塘']
    dynasties = ['汉', '唐', '宋', '明', '清', '汉', '唐', '宋', '明', '清']
    dynasty_orders = [5, 8, 11, 14, 15, 5, 8, 11, 14, 15]
    
    for i in range(n):
        lon = base_lon + (i % 5) * 0.08
        lat = base_lat + (i // 5) * 0.06
        site = SimpleNamespace(
            id=i + 1,
            name=f"测试遗址{i + 1}",
            site_type=site_types[i % len(site_types)],
            longitude=lon,
            latitude=lat,
            irrigation_area=100.0 + i * 20.0,
            dynasty=dynasties[i % len(dynasties)],
            dynasty_order=dynasty_orders[i % len(dynasty_orders)],
        )
        sites.append(site)
    return sites


def test_hydraulic_network_graph():
    """测试水利网络图类"""
    print("=== HydraulicNetworkGraph 测试 ===")
    
    graph = HydraulicNetworkGraph(region="中原地区")
    print(f"区域: {graph.region}")
    
    sites = _create_test_sites(10)
    print(f"测试遗址数: {len(sites)}")
    
    graph.build_graph_from_sites(sites)
    print(f"节点数: {len(graph.nodes)}")
    print(f"边数: {len(graph.edges)}")
    
    metrics = graph.calculate_graph_metrics()
    print(f"\n图度量指标:")
    print(f"  节点数: {metrics['total_nodes']}")
    print(f"  边数: {metrics['total_edges']}")
    print(f"  连通度: {metrics['network_connectivity']}")
    print(f"  冗余度: {metrics['network_redundancy']}")
    print(f"  平均路径长度: {metrics['avg_path_length']}")
    print(f"  聚类系数: {metrics['clustering_coefficient']}")
    print(f"  连通分量: {metrics['connected_components']}")
    print(f"  关节点数: {len(metrics['articulation_points'])}")
    
    centralities = graph.calculate_node_centralities()
    print(f"\n节点中心性分析:")
    print(f"  中心性字典大小: {len(centralities)}")
    if centralities:
        first_id = list(centralities.keys())[0]
        first_data = centralities[first_id]
        print(f"  首个节点(site_id={first_id}):")
        print(f"    度: {first_data['degree']}")
        print(f"    度中心性: {first_data['degree_centrality']}")
        print(f"    介数中心性: {first_data['betweenness']}")
        print(f"    接近中心性: {first_data['closeness']}")
        print(f"    特征向量中心性: {first_data['eigenvector']}")
        print(f"    角色: {first_data['role']}")
    
    aps = graph._tarjan_articulation_points()
    print(f"\nTarjan关节点索引: {aps}")
    
    if len(graph.nodes) > 0:
        shortest = graph._dijkstra_shortest_path(0)
        print(f"Dijkstra最短路径(从节点0): {len(shortest)} 个可达节点")
        if len(shortest) > 1:
            for k in list(shortest.keys())[:3]:
                print(f"  到节点{k}: {round(shortest[k], 3)} km")
    
    print("HydraulicNetworkGraph 测试通过\n")


def test_synergy_effects():
    """测试协同效应分析"""
    print("=== 协同效应分析测试 ===")
    
    graph = HydraulicNetworkGraph(region="中原地区")
    sites = _create_test_sites(10)
    graph.build_graph_from_sites(sites)
    
    synergy = analyze_synergy_effects(graph)
    print(f"协同效应分析结果:")
    print(f"  协同得分: {synergy['synergy_score']}")
    print(f"  协同等级: {synergy['synergy_level']}")
    print(f"  梯级灌溉效率: {synergy['cascade_irrigation_efficiency']}")
    print(f"  防洪能力: {synergy['flood_regulation_capacity']}")
    print(f"  梯级路径数: {synergy['cascade_path_count']}")
    print(f"  水库数: {synergy['reservoir_count']}")
    print(f"  堤防数: {synergy['levee_count']}")
    print(f"  渠道数: {synergy['channel_count']}")
    print(f"  渠道密度: {synergy['channel_density']}")
    print(f"  总灌溉能力: {synergy['total_irrigation_capacity']}")
    
    print("协同效应分析测试通过\n")


def test_hydrological_network_completor():
    """测试水系补全引擎"""
    print("=== HydrologicalNetworkCompletor 测试 ===")
    
    completor = HydrologicalNetworkCompletor(region="中原地区")
    print(f"区域: {completor.region}")
    print(f"补全阈值: {completor.completion_threshold}")
    
    sites = _create_test_sites(10)
    
    known_edges = [
        {'u': 0, 'v': 1, 'u_site_id': 1, 'v_site_id': 2},
        {'u': 1, 'v': 2, 'u_site_id': 2, 'v_site_id': 3},
    ]
    
    inferred_edges = completor.infer_missing_connections(sites, known_edges, max_distance_km=50)
    print(f"\n推断缺失连接:")
    print(f"  已知边数: {len(known_edges)}")
    print(f"  推断边数: {len(inferred_edges)}")
    print(f"  返回类型是列表: {isinstance(inferred_edges, list)}")
    
    if inferred_edges:
        top = inferred_edges[0]
        print(f"  Top1推断边:")
        print(f"    u={top['u']}, v={top['v']}")
        print(f"    综合得分: {top['composite_score']}")
        print(f"    距离: {top['distance_km']} km")
        print(f"    是否推断: {top['inferred']}")
    
    print("HydrologicalNetworkCompletor 测试通过\n")


def test_uncertainty_aware_analyzer():
    """测试不确定性感知网络分析器"""
    print("=== UncertaintyAwareNetworkAnalyzer 测试 ===")
    
    graph = HydraulicNetworkGraph(region="中原地区")
    sites = _create_test_sites(10)
    graph.build_graph_from_sites(sites)
    
    analyzer = UncertaintyAwareNetworkAnalyzer(base_graph=graph)
    print(f"边置信度字典大小: {len(analyzer.edge_confidence)}")
    
    result = analyzer.monte_carlo_network_sampling(n_samples=50, seed=42)
    print(f"\n蒙特卡洛采样结果 (n_samples={result['n_samples']}):")
    print(f"  连通度均值: {result['connectivity']['mean']}")
    print(f"  连通度标准差: {result['connectivity']['std']}")
    print(f"  连通度P5: {result['connectivity']['p5']}")
    print(f"  连通度P95: {result['connectivity']['p95']}")
    print(f"  冗余度均值: {result['redundancy']['mean']}")
    print(f"  协同得分均值: {result['synergy_score']['mean']}")
    
    connectivity = result['connectivity']
    ci_lower = connectivity['p5']
    ci_upper = connectivity['p95']
    mean_conn = connectivity['mean']
    std_conn = connectivity['std']
    
    print(f"\n整理后的结果:")
    print(f"  mean_connectivity: {mean_conn}")
    print(f"  std_connectivity: {std_conn}")
    print(f"  confidence_interval: [{ci_lower}, {ci_upper}]")
    
    robustness = analyzer.calculate_robustness_metrics(result)
    print(f"\n鲁棒性指标:")
    for metric in ['connectivity', 'redundancy', 'synergy_score']:
        if metric in robustness:
            r = robustness[metric]
            print(f"  {metric}:")
            print(f"    变异系数: {r['coefficient_of_variation']}")
            print(f"    95%CI宽度: {r['ci95_width']}")
    
    print("UncertaintyAwareNetworkAnalyzer 测试通过\n")


def main():
    """主测试函数"""
    print("=" * 60)
    print("network_effect 模块验证测试")
    print("=" * 60)
    print()
    
    try:
        test_utils()
        test_hydraulic_network_graph()
        test_synergy_effects()
        test_hydrological_network_completor()
        test_uncertainty_aware_analyzer()
        
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
