"""
水利工程群网络分析算法模块
从遗址列表构建图拓扑，计算中心性、协同效应，生成GeoJSON
"""
import math
import heapq
from collections import defaultdict, deque
from typing import List, Dict, Set, Tuple, Optional, Any
from datetime import datetime

from common.params.network_params import (
    CONNECTION_CRITERIA,
    NODE_ROLE_THRESHOLDS,
    NETWORK_METRIC_WEIGHTS,
    FLOOD_REGULATION_CAPACITY_FACTORS,
    REGION_WATERSHEDS,
    GRAPH_VISUALIZATION_STYLES,
    get_connection_eligible,
    determine_node_role,
    get_node_color,
)


class HydraulicNetworkGraph:
    """水利网络图分析：构建、度量、中心性、协同效应"""

    def __init__(self, region: str):
        self.region = region
        self.nodes: Dict[int, Dict] = {}
        self.site_id_to_idx: Dict[int, int] = {}
        self.idx_to_site_id: Dict[int, int] = {}
        self.adj: Dict[int, Dict[int, Dict]] = defaultdict(dict)
        self.edges: List[Dict] = []
        self.connection_criteria = CONNECTION_CRITERIA
        self._watershed_info = REGION_WATERSHEDS.get(region, REGION_WATERSHEDS['中原地区'])

    def _haversine_distance_km(self, lon1: float, lat1: float,
                               lon2: float, lat2: float) -> float:
        R = 6371.0
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    def _get_approx_elevation(self, site) -> float:
        elev_range = self._watershed_info.get('elevation_range_m', [50, 500])
        avg_slope = self._watershed_info.get('avg_slope_pct', 1.0)
        base_elev = elev_range[0]
        lon_factor = (site.longitude - 100.0) * 10.0
        lat_factor = (40.0 - site.latitude) * 20.0
        elev = base_elev + abs(lon_factor) * avg_slope + abs(lat_factor) * avg_slope
        return max(elev_range[0], min(elev_range[1], elev))

    def _is_downstream_flow(self, s1, s2) -> bool:
        if self.region in ('江南地区', '岭南地区', '巴蜀地区', '滇黔地区'):
            return s1.longitude <= s2.longitude
        else:
            return s1.latitude >= s2.latitude

    def build_graph_from_sites(self, sites: List) -> None:
        self.nodes = {}
        self.site_id_to_idx = {}
        self.idx_to_site_id = {}
        self.adj = defaultdict(dict)
        self.edges = []

        for i, site in enumerate(sites):
            elev = self._get_approx_elevation(site)
            self.nodes[i] = {
                'id': site.id,
                'name': site.name,
                'type': site.site_type,
                'geom_x': site.longitude,
                'geom_y': site.latitude,
                'irrigation_area': site.irrigation_area or 0.0,
                'dynasty': site.dynasty,
                'dynasty_order': site.dynasty_order,
                'elevation': elev,
            }
            self.site_id_to_idx[site.id] = i
            self.idx_to_site_id[i] = site.id

        n = len(sites)
        same_watershed_bonus = 1.2
        max_elev = self.connection_criteria['elevation_difference_max_m']

        for i in range(n):
            for j in range(i + 1, n):
                s1 = sites[i]
                s2 = sites[j]

                dist_km = self._haversine_distance_km(
                    s1.longitude, s1.latitude,
                    s2.longitude, s2.latitude
                )

                elev1 = self.nodes[i]['elevation']
                elev2 = self.nodes[j]['elevation']
                elev_diff = abs(elev1 - elev2)

                same_watershed = True

                downstream = self._is_downstream_flow(s1, s2) or self._is_downstream_flow(s2, s1)

                if not get_connection_eligible(dist_km, same_watershed, elev_diff, downstream):
                    continue

                dist_factor = 1.0 / (1.0 + dist_km / 20.0)
                elev_factor = 1.0 - (elev_diff / max_elev) if max_elev > 0 else 1.0
                elev_factor = max(0.0, elev_factor)
                watershed_factor = same_watershed_bonus if same_watershed else 1.0

                connection_strength = dist_factor * elev_factor * watershed_factor
                connection_strength = min(1.0, max(0.0, connection_strength))

                hydrological_path = 'cascade' if elev_diff > 20 else 'parallel'
                cascade_capable = elev_diff > 10 and downstream
                flood_regulation_capable = (
                    s1.site_type in ('陂', '塘') or s2.site_type in ('陂', '塘')
                )

                edge_attrs = {
                    'distance_km': round(dist_km, 3),
                    'elevation_diff_m': round(elev_diff, 2),
                    'connection_strength': round(connection_strength, 4),
                    'hydrological_path': hydrological_path,
                    'cascade_capable': cascade_capable,
                    'flood_regulation_capable': flood_regulation_capable,
                }

                self.adj[i][j] = edge_attrs
                self.adj[j][i] = edge_attrs
                self.edges.append({
                    'u': i, 'v': j,
                    'u_site_id': s1.id,
                    'v_site_id': s2.id,
                    **edge_attrs
                })

    def calculate_graph_metrics(self) -> Dict[str, Any]:
        n = len(self.nodes)
        m = len(self.edges)

        if n < 2:
            return {
                'total_nodes': n,
                'total_edges': m,
                'network_connectivity': 0.0,
                'network_redundancy': 0.0,
                'avg_path_length': 0.0,
                'clustering_coefficient': 0.0,
                'degree_distribution': {},
                'articulation_points': set(),
                'connected_components': 1,
                'component_sizes': [n] if n > 0 else [],
            }

        max_edges = n * (n - 1) / 2
        network_connectivity = m / max_edges if max_edges > 0 else 0.0

        min_spanning_edges = n - 1
        max_additional = max_edges - min_spanning_edges
        network_redundancy = 0.0
        if max_additional > 0:
            network_redundancy = max(0.0, (m - min_spanning_edges) / max_additional)

        all_shortest_paths = {}
        for i in range(n):
            all_shortest_paths[i] = self._dijkstra_shortest_path(i)

        path_lengths = []
        for i in range(n):
            for j in range(i + 1, n):
                if j in all_shortest_paths[i]:
                    path_lengths.append(all_shortest_paths[i][j])
        avg_path_length = sum(path_lengths) / len(path_lengths) if path_lengths else 0.0

        clustering_coeff = self._calculate_global_clustering(n)

        degrees = [len(self.adj[i]) for i in range(n)]
        degree_dist = defaultdict(int)
        for d in degrees:
            degree_dist[d] += 1
        degree_distribution = dict(sorted(degree_dist.items()))

        articulation_points = self._tarjan_articulation_points()
        articulation_site_ids = {self.idx_to_site_id[idx] for idx in articulation_points}

        visited = set()
        components = []
        for i in range(n):
            if i not in visited:
                comp = []
                queue = deque([i])
                visited.add(i)
                while queue:
                    node = queue.popleft()
                    comp.append(node)
                    for neighbor in self.adj[node]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                components.append(comp)

        return {
            'total_nodes': n,
            'total_edges': m,
            'network_connectivity': round(network_connectivity, 4),
            'network_redundancy': round(network_redundancy, 4),
            'avg_path_length': round(avg_path_length, 4),
            'clustering_coefficient': round(clustering_coeff, 4),
            'degree_distribution': degree_distribution,
            'articulation_points': articulation_site_ids,
            'connected_components': len(components),
            'component_sizes': sorted([len(c) for c in components], reverse=True),
        }

    def _calculate_global_clustering(self, n: int) -> float:
        total_triangles = 0
        total_triplets = 0

        for i in range(n):
            neighbors_i = set(self.adj[i].keys())
            k = len(neighbors_i)
            if k < 2:
                continue
            total_triplets += k * (k - 1) / 2

            for j in neighbors_i:
                for l in neighbors_i:
                    if j < l and l in self.adj[j]:
                        total_triangles += 1

        return (3.0 * total_triangles) / total_triplets if total_triplets > 0 else 0.0

    def _tarjan_articulation_points(self) -> Set[int]:
        n = len(self.nodes)
        if n == 0:
            return set()

        disc = [-1] * n
        low = [-1] * n
        parent = [-1] * n
        visited = [False] * n
        ap = set()
        time_counter = [0]

        def dfs(u: int):
            children = 0
            visited[u] = True
            disc[u] = low[u] = time_counter[0]
            time_counter[0] += 1

            for v in self.adj[u]:
                if not visited[v]:
                    parent[v] = u
                    children += 1
                    dfs(v)

                    low[u] = min(low[u], low[v])

                    if parent[u] == -1 and children > 1:
                        ap.add(u)
                    if parent[u] != -1 and low[v] >= disc[u]:
                        ap.add(u)
                elif v != parent[u]:
                    low[u] = min(low[u], disc[v])

        for i in range(n):
            if not visited[i]:
                dfs(i)

        return ap

    def _dijkstra_shortest_path(self, source_id: int) -> Dict[int, float]:
        dist = {source_id: 0.0}
        pq = [(0.0, source_id)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float('inf')):
                continue
            for v, attrs in self.adj[u].items():
                w = attrs.get('distance_km', 1.0)
                new_dist = d + w
                if new_dist < dist.get(v, float('inf')):
                    dist[v] = new_dist
                    heapq.heappush(pq, (new_dist, v))

        return dist

    def calculate_node_centralities(self) -> Dict[int, Dict[str, Any]]:
        n = len(self.nodes)
        if n == 0:
            return {}

        result: Dict[int, Dict[str, Any]] = {}

        degrees = {i: len(self.adj[i]) for i in range(n)}
        degree_centrality = {}
        max_degree = max(degrees.values()) if degrees else 1
        for i in range(n):
            degree_centrality[i] = degrees[i] / max_degree if max_degree > 0 else 0.0

        all_shortest_paths = {}
        for i in range(n):
            all_shortest_paths[i] = self._dijkstra_shortest_path(i)

        betweenness = {i: 0.0 for i in range(n)}
        for s in range(n):
            for t in range(n):
                if s == t or t not in all_shortest_paths[s]:
                    continue
                total_paths = 0
                node_on_path = {i: 0 for i in range(n)}

                paths = self._find_all_shortest_paths(s, t, all_shortest_paths[s][t])
                total_paths = len(paths)
                if total_paths == 0:
                    continue
                for path in paths:
                    for node in path[1:-1]:
                        node_on_path[node] += 1

                for i in range(n):
                    if i != s and i != t:
                        betweenness[i] += node_on_path[i] / total_paths

        norm_factor = (n - 1) * (n - 2) / 2 if n > 2 else 1
        betweenness_centrality = {}
        for i in range(n):
            betweenness_centrality[i] = betweenness[i] / norm_factor if norm_factor > 0 else 0.0

        closeness_centrality = {}
        for i in range(n):
            reachable = {k: v for k, v in all_shortest_paths[i].items() if k != i}
            if not reachable:
                closeness_centrality[i] = 0.0
                continue
            avg_dist = sum(reachable.values()) / len(reachable)
            closeness_centrality[i] = (len(reachable) / (n - 1)) * (1.0 / avg_dist if avg_dist > 0 else 0.0)

        eigenvector_centrality = self._power_method_eigenvector(n)

        for i in range(n):
            site_id = self.idx_to_site_id[i]
            deg = degrees[i]
            betw = betweenness_centrality[i]
            role_en = determine_node_role(deg, betw)

            role_map = {
                'hub': '核心枢纽',
                'intermediary': '中转节点',
                'terminal': '终端节点',
                'isolated': '孤立节点',
            }
            role_cn = role_map.get(role_en, '终端节点')

            result[site_id] = {
                'degree': deg,
                'degree_centrality': round(degree_centrality[i], 6),
                'betweenness': round(betw, 6),
                'closeness': round(closeness_centrality[i], 6),
                'eigenvector': round(eigenvector_centrality[i], 6),
                'role': role_cn,
            }

        return result

    def _find_all_shortest_paths(self, s: int, t: int, target_dist: float) -> List[List[int]]:
        paths = []
        stack = [(s, [s], 0.0)]
        max_paths = 50
        while stack and len(paths) < max_paths:
            node, path, dist = stack.pop()
            if node == t and abs(dist - target_dist) < 1e-9:
                paths.append(path)
                continue
            if dist > target_dist + 1e-9:
                continue
            for neighbor, attrs in self.adj[node].items():
                if neighbor not in path:
                    w = attrs.get('distance_km', 1.0)
                    stack.append((neighbor, path + [neighbor], dist + w))
        return paths

    def _power_method_eigenvector(self, n: int, max_iter: int = 100, tol: float = 1e-6) -> Dict[int, float]:
        if n == 0:
            return {}

        x = {i: 1.0 / math.sqrt(n) for i in range(n)}

        for _ in range(max_iter):
            x_new = {i: 0.0 for i in range(n)}
            for i in range(n):
                for j in self.adj[i]:
                    strength = self.adj[i][j].get('connection_strength', 1.0)
                    x_new[i] += strength * x[j]

            norm = math.sqrt(sum(v ** 2 for v in x_new.values()))
            if norm < 1e-10:
                break

            for i in range(n):
                x_new[i] /= norm

            diff = math.sqrt(sum((x_new[i] - x[i]) ** 2 for i in range(n)))
            x = x_new

            if diff < tol:
                break

        max_val = max(abs(v) for v in x.values()) if x else 1.0
        if max_val > 0:
            x = {i: v / max_val for i, v in x.items()}

        return x

    def analyze_synergy_effects(self, restorations: Dict[int, Any]) -> Dict[str, Any]:
        n = len(self.nodes)
        capacities: Dict[int, float] = {}

        for i in range(n):
            site_id = self.idx_to_site_id[i]
            node_info = self.nodes[i]
            if site_id in restorations and hasattr(restorations[site_id], 'actual_irrigation_capacity'):
                capacities[i] = float(restorations[site_id].actual_irrigation_capacity)
            else:
                capacities[i] = float(node_info.get('irrigation_area', 0.0)) * 0.8

        total_capacity = sum(capacities.values())
        loss_per_km = 0.005
        cascade_factor = 0.85

        all_cascade_paths = []
        for s in range(n):
            all_shortest = self._dijkstra_shortest_path(s)
            for t in range(n):
                if s == t or t not in all_shortest:
                    continue
                if capacities[s] <= 0:
                    continue

                path_len = all_shortest[t]
                elev_s = self.nodes[s]['elevation']
                elev_t = self.nodes[t]['elevation']
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
            site_type = self.nodes[i].get('type', '')
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
            channel_density = len(self.edges) / n

        factors = FLOOD_REGULATION_CAPACITY_FACTORS
        raw_flood = (
            reservoir_count * factors['single_reservoir_factor'] +
            cascade_count * factors['cascade_factor'] +
            channel_density * factors['channel_network_factor'] +
            levee_count * factors['levee_factor']
        )
        flood_regulation_capacity = 1.0 - math.exp(-raw_flood / 2.0)
        flood_regulation_capacity = min(1.0, max(0.0, flood_regulation_capacity))

        metrics = self.calculate_graph_metrics()
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

    def generate_network_geojson(self) -> Dict[str, Any]:
        centralities = self.calculate_node_centralities()

        point_features = []
        for i, node in self.nodes.items():
            site_id = self.idx_to_site_id[i]
            cent = centralities.get(site_id, {})
            role = cent.get('role', '终端节点')
            degree = cent.get('degree', 0)

            role_en_map = {
                '核心枢纽': 'hub',
                '中转节点': 'intermediary',
                '终端节点': 'terminal',
                '孤立节点': 'isolated',
            }
            role_en = role_en_map.get(role, 'terminal')
            color = get_node_color(role_en)

            point_features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [node['geom_x'], node['geom_y']]
                },
                'properties': {
                    'site_id': site_id,
                    'name': node['name'],
                    'site_type': node['type'],
                    'dynasty': node['dynasty'],
                    'irrigation_area': node['irrigation_area'],
                    'degree': degree,
                    'role': role,
                    'role_en': role_en,
                    'color': color,
                    'betweenness': cent.get('betweenness', 0.0),
                    'closeness': cent.get('closeness', 0.0),
                    'eigenvector': cent.get('eigenvector', 0.0),
                    'marker-color': color,
                    'marker-size': 'large' if role_en == 'hub' else ('medium' if role_en == 'intermediary' else 'small'),
                }
            })

        line_features = []
        for edge in self.edges:
            u = edge['u']
            v = edge['v']
            strength = edge['connection_strength']
            if strength >= 0.7:
                strength_label = 'strong'
            elif strength >= 0.4:
                strength_label = 'medium'
            else:
                strength_label = 'weak'

            widths = GRAPH_VISUALIZATION_STYLES['edge_width_by_strength']
            line_width = widths.get(strength_label, 1)

            node_u = self.nodes[u]
            node_v = self.nodes[v]

            line_features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [node_u['geom_x'], node_u['geom_y']],
                        [node_v['geom_x'], node_v['geom_y']]
                    ]
                },
                'properties': {
                    'u_site_id': edge['u_site_id'],
                    'v_site_id': edge['v_site_id'],
                    'distance_km': edge['distance_km'],
                    'elevation_diff_m': edge['elevation_diff_m'],
                    'connection_strength': round(strength, 4),
                    'strength_label': strength_label,
                    'hydrological_path': edge['hydrological_path'],
                    'cascade_capable': edge['cascade_capable'],
                    'flood_regulation_capable': edge['flood_regulation_capable'],
                    'stroke': '#2980b9' if strength >= 0.5 else '#95a5a6',
                    'stroke-width': line_width,
                    'stroke-opacity': min(1.0, 0.4 + strength * 0.6),
                }
            })

        all_features = point_features + line_features

        return {
            'type': 'FeatureCollection',
            'features': all_features,
            'metadata': {
                'region': self.region,
                'total_nodes': len(self.nodes),
                'total_edges': len(self.edges),
                'generated_at': datetime.now().isoformat(),
            }
        }


class NetworkAnalyzerService:
    """网络分析服务类：封装数据库交互和完整分析流程"""

    def __init__(self):
        self._graph_cache: Dict[str, HydraulicNetworkGraph] = {}

    def _load_sites_in_region(self, db, region: str,
                              site_ids: List[int] = None) -> List:
        from common.models import WaterHeritageSite
        import hashlib
        from common.params.hydraulic_params import REGIONS

        query = db.query(WaterHeritageSite)

        if site_ids:
            query = query.filter(WaterHeritageSite.id.in_(site_ids))

        all_sites = query.all()

        if not site_ids:
            region_sites = []
            for site in all_sites:
                idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
                site_region = REGIONS[idx]
                if site_region == region:
                    region_sites.append(site)
            return region_sites

        return all_sites

    def _load_restorations(self, db, site_ids: List[int]) -> Dict[int, Any]:
        from common.models import FunctionalRestoration
        if not site_ids:
            return {}
        records = db.query(FunctionalRestoration).filter(
            FunctionalRestoration.site_id.in_(site_ids)
        ).all()
        return {r.site_id: r for r in records}

    def run_full_analysis(self, db, region: str,
                          site_ids: List[int] = None,
                          analysis_depth: str = 'deep'):
        from common.models import HydraulicNetworkAnalysis, NetworkMemberSite
        from common.redis_client import pubsub
        from common.config import channels

        sites = self._load_sites_in_region(db, region, site_ids)
        if not sites:
            raise ValueError(f"区域 {region} 内没有可分析的遗址")

        if len(sites) < 2:
            raise ValueError(f"区域 {region} 内遗址数量不足（至少需要2个）")

        graph = HydraulicNetworkGraph(region)
        graph.build_graph_from_sites(sites)
        self._graph_cache[region] = graph

        loaded_site_ids = [s.id for s in sites]
        restorations = self._load_restorations(db, loaded_site_ids)

        metrics = graph.calculate_graph_metrics()
        centralities = graph.calculate_node_centralities()
        synergy = graph.analyze_synergy_effects(restorations)
        geojson_data = graph.generate_network_geojson()

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

        analysis = HydraulicNetworkAnalysis(
            region=region,
            total_nodes=metrics['total_nodes'],
            total_edges=metrics['total_edges'],
            network_connectivity=metrics['network_connectivity'],
            network_redundancy=metrics['network_redundancy'],
            avg_path_length=metrics['avg_path_length'],
            clustering_coefficient=metrics['clustering_coefficient'],
            synergy_score=synergy['synergy_score'],
            cascade_irrigation_efficiency=synergy['cascade_irrigation_efficiency'],
            flood_regulation_capacity=synergy['flood_regulation_capacity'],
            critical_nodes=critical_nodes_data,
            network_edges_geojson=geojson_data,
        )
        db.add(analysis)
        db.flush()

        analysis_id = analysis.id

        for site in sites:
            site_id = site.id
            cent = centralities.get(site_id, {
                'degree': 0,
                'betweenness': 0.0,
                'closeness': 0.0,
                'role': '孤立节点',
            })

            member = NetworkMemberSite(
                network_analysis_id=analysis_id,
                site_id=site_id,
                node_degree=cent['degree'],
                node_betweenness=cent['betweenness'],
                node_closeness=cent['closeness'],
                node_role=cent['role'],
            )
            db.add(member)

        db.commit()
        db.refresh(analysis)

        if synergy['synergy_score'] >= 0.80:
            pubsub.publish(channels.SYNERGY_EFFECT_DETECTED, {
                "event_type": "synergy_effect_detected",
                "region": region,
                "analysis_id": analysis_id,
                "data": {
                    "synergy_score": synergy['synergy_score'],
                    "synergy_level": synergy['synergy_level'],
                    "total_nodes": metrics['total_nodes'],
                    "total_edges": metrics['total_edges'],
                    "critical_nodes": critical_nodes_list,
                }
            })

        pubsub.publish(channels.NETWORK_ANALYSIS_COMPLETED, {
            "event_type": "network_analysis_completed",
            "region": region,
            "analysis_id": analysis_id,
            "data": {
                "total_nodes": metrics['total_nodes'],
                "total_edges": metrics['total_edges'],
                "network_connectivity": metrics['network_connectivity'],
                "network_redundancy": metrics['network_redundancy'],
                "synergy_score": synergy['synergy_score'],
                "synergy_level": synergy['synergy_level'],
                "cascade_efficiency": synergy['cascade_irrigation_efficiency'],
                "flood_regulation": synergy['flood_regulation_capacity'],
            }
        })

        return analysis

    def get_latest_for_region(self, db, region: str):
        from common.models import HydraulicNetworkAnalysis
        return db.query(HydraulicNetworkAnalysis).filter(
            HydraulicNetworkAnalysis.region == region
        ).order_by(HydraulicNetworkAnalysis.analyzed_at.desc()).first()


_service_instance = None


def get_network_service() -> NetworkAnalyzerService:
    global _service_instance
    if _service_instance is None:
        _service_instance = NetworkAnalyzerService()
    return _service_instance
