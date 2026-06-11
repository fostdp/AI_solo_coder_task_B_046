"""
水利工程群网络分析算法模块
从遗址列表构建图拓扑，计算中心性、协同效应
"""
import math
import heapq
from collections import defaultdict, deque
from typing import List, Dict, Set, Tuple, Optional, Any

from common.params.network_params import (
    CONNECTION_CRITERIA,
    NODE_ROLE_THRESHOLDS,
    get_connection_eligible,
    determine_node_role,
)

from .utils import (
    haversine_distance_km,
    get_approx_elevation,
    is_downstream_flow,
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

    def build_graph_from_sites(self, sites: List) -> None:
        """
        从遗址列表构建网络图（纯算法版本，不依赖数据库）

        Args:
            sites: 遗址列表，每个遗址需包含 id, name, site_type, longitude,
                   latitude, irrigation_area, dynasty, dynasty_order 等属性
        """
        self.nodes = {}
        self.site_id_to_idx = {}
        self.idx_to_site_id = {}
        self.adj = defaultdict(dict)
        self.edges = []

        for i, site in enumerate(sites):
            elev = get_approx_elevation(site, self.region)
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

                dist_km = haversine_distance_km(
                    s1.longitude, s1.latitude,
                    s2.longitude, s2.latitude
                )

                elev1 = self.nodes[i]['elevation']
                elev2 = self.nodes[j]['elevation']
                elev_diff = abs(elev1 - elev2)

                same_watershed = True

                downstream = is_downstream_flow(s1, s2, self.region) or is_downstream_flow(s2, s1, self.region)

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
        """
        计算网络图全局度量指标

        Returns:
            图度量字典，包含节点数、边数、连通度、冗余度、平均路径长度、
            聚类系数、度分布、关节点、连通分量等
        """
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
        """计算全局聚类系数"""
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
        """
        Tarjan算法求解关节点（割点）

        Returns:
            关节点索引集合
        """
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
        """
        Dijkstra最短路径算法

        Args:
            source_id: 源节点索引

        Returns:
            从源节点到各节点的最短距离字典 {node_idx: distance}
        """
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
        """
        计算所有节点的中心性指标

        Returns:
            节点中心性字典 {site_id: {degree, degree_centrality, betweenness,
                                        closeness, eigenvector, role}}
        """
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
        """查找所有最短路径（DFS回溯，最多返回50条）"""
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
        """幂法计算特征向量中心性"""
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
