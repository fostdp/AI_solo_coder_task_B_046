"""
水系补全与不确定性感知网络分析模块
解决水系数据不完整导致的连通度误判问题，提供多源证据补全、蒙特卡洛不确定性量化
"""
import math
import random
from collections import defaultdict, deque
from typing import List, Dict, Set, Tuple, Optional, Any
from datetime import datetime

from common.params.network_params import (
    REGION_WATERSHEDS,
    NODE_ROLE_THRESHOLDS,
)

from .utils import (
    haversine_distance_km,
    get_approx_elevation,
    is_downstream_flow,
    percentile,
    compute_stats,
    text_contains_hydrology_keyword,
)


class HydrologicalNetworkCompletor:
    """水系补全引擎：基于多源考古证据推理缺失的水系连接"""

    HYDROLOGY_KEYWORDS = ['河', '渠', '溪', '塘', '陂', '堰', '沟', '渎', '川', '江', '湖', '池', '泽', '泉', '井', '堤', '坝', '闸']

    TYPE_COMPATIBILITY_MATRIX: Dict[str, Dict[str, float]] = {
        '堰': {'堰': 0.5, '渠': 1.0, '塘': 0.8, '陂': 0.7},
        '渠': {'堰': 1.0, '渠': 0.6, '塘': 1.0, '陂': 0.9},
        '塘': {'堰': 0.8, '渠': 1.0, '塘': 0.5, '陂': 0.9},
        '陂': {'堰': 0.7, '渠': 0.9, '塘': 0.9, '陂': 0.4},
    }

    EVIDENCE_WEIGHTS: Dict[str, float] = {
        'distance_score': 0.25,
        'watershed_score': 0.25,
        'downstream_score': 0.15,
        'dynasty_score': 0.10,
        'type_compatibility': 0.15,
        'archaeological_cluster': 0.10,
    }

    DYNASTY_CONTINUITY: Dict[str, List[str]] = {
        '夏': ['商'],
        '商': ['周', '西周'],
        '西周': ['东周', '春秋'],
        '春秋': ['战国'],
        '战国': ['秦'],
        '秦': ['西汉', '汉'],
        '西汉': ['东汉', '汉'],
        '东汉': ['三国', '魏晋'],
        '三国': ['西晋', '魏晋'],
        '西晋': ['东晋', '南北朝'],
        '东晋': ['南北朝'],
        '南北朝': ['隋'],
        '隋': ['唐'],
        '唐': ['五代', '宋'],
        '五代': ['宋', '北宋'],
        '北宋': ['南宋', '金'],
        '南宋': ['元'],
        '金': ['元'],
        '元': ['明'],
        '明': ['清'],
        '清': ['近代'],
    }

    def __init__(self, region: str):
        self.region = region
        self._watershed_info = REGION_WATERSHEDS.get(region, REGION_WATERSHEDS['中原地区'])
        self.known_river_nodes: Set[int] = set()
        self.completion_threshold: float = 0.6
        self._audit_log: List[Dict[str, Any]] = []

    def extract_known_hydrology(self, sites: List) -> Dict[str, Any]:
        """
        从已有遗址中提取水文线索
        - 遗址名/描述含水文关键词 → 标记为水系节点
        - 同区域、同朝代、同类型聚类 → 可能属同一渠系

        Args:
            sites: 遗址列表

        Returns:
            {known_edges: [], inferred_river_nodes: []}
        """
        inferred_river_nodes: List[int] = []
        known_edges: List[Dict[str, Any]] = []

        for i, site in enumerate(sites):
            name_match = text_contains_hydrology_keyword(site.name, self.HYDROLOGY_KEYWORDS)
            desc_match = False
            if hasattr(site, 'description') and site.description:
                desc_match = text_contains_hydrology_keyword(site.description, self.HYDROLOGY_KEYWORDS)
            if name_match or desc_match:
                inferred_river_nodes.append(site.id)
                self.known_river_nodes.add(i)

        n = len(sites)
        cluster_groups: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
        for i, site in enumerate(sites):
            key = (self.region, site.dynasty or '未知', site.site_type or '未知')
            cluster_groups[key].append(i)

        for key, indices in cluster_groups.items():
            if len(indices) >= 3:
                for idx_i in range(len(indices)):
                    for idx_j in range(idx_i + 1, len(indices)):
                        i1, i2 = indices[idx_i], indices[idx_j]
                        s1, s2 = sites[i1], sites[i2]
                        dist = haversine_distance_km(
                            s1.longitude, s1.latitude, s2.longitude, s2.latitude
                        )
                        if dist <= 10.0:
                            known_edges.append({
                                'u': i1,
                                'v': i2,
                                'u_site_id': s1.id,
                                'v_site_id': s2.id,
                                'evidence': 'archaeological_cluster',
                                'confidence': 0.6,
                                'inferred': True,
                            })

        return {
            'known_edges': known_edges,
            'inferred_river_nodes': inferred_river_nodes,
        }

    def _compute_distance_score(self, d: float, max_d: float) -> float:
        if max_d <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - d / max_d))

    def _compute_watershed_score(self, s1, s2) -> float:
        rivers = self._watershed_info.get('rivers', [])
        if not rivers:
            return 0.5
        name1 = getattr(s1, 'name', '') or ''
        name2 = getattr(s2, 'name', '') or ''
        desc1 = getattr(s1, 'description', '') or ''
        desc2 = getattr(s2, 'description', '') or ''
        text1 = name1 + desc1
        text2 = name2 + desc2
        shared_rivers = 0
        for river in rivers:
            if river in text1 and river in text2:
                shared_rivers += 1
        if shared_rivers > 0:
            return 1.0
        s1_mentions = any(r in text1 for r in rivers)
        s2_mentions = any(r in text2 for r in rivers)
        if s1_mentions and s2_mentions:
            return 0.7
        return 0.0

    def _compute_downstream_score(self, s1, s2) -> float:
        elev1 = get_approx_elevation(s1, self.region)
        elev2 = get_approx_elevation(s2, self.region)
        elev_diff = abs(elev1 - elev2)
        max_elev = self._watershed_info.get('elevation_range_m', [50, 500])
        elev_range = max(1.0, max_elev[1] - max_elev[0])
        elev_score = min(1.0, elev_diff / elev_range)
        direction_ok = is_downstream_flow(s1, s2, self.region) or is_downstream_flow(s2, s1, self.region)
        direction_score = 1.0 if direction_ok else 0.0
        return 0.5 * elev_score + 0.5 * direction_score

    def _compute_dynasty_score(self, dynasty1: str, dynasty2: str) -> float:
        if not dynasty1 or not dynasty2:
            return 0.3
        if dynasty1 == dynasty2:
            return 1.0
        cont1 = self.DYNASTY_CONTINUITY.get(dynasty1, [])
        cont2 = self.DYNASTY_CONTINUITY.get(dynasty2, [])
        if dynasty2 in cont1 or dynasty1 in cont2:
            return 0.7
        if any(d in cont2 for d in cont1) or any(d in cont1 for d in cont2):
            return 0.4
        return 0.0

    def _compute_type_compatibility(self, type1: str, type2: str) -> float:
        if not type1 or not type2:
            return 0.5
        row = self.TYPE_COMPATIBILITY_MATRIX.get(type1, {})
        if type2 in row:
            return row[type2]
        row = self.TYPE_COMPATIBILITY_MATRIX.get(type2, {})
        if type1 in row:
            return row[type1]
        if type1 == type2:
            return 0.5
        return 0.3

    def _compute_cluster_score(self, s1, s2, cluster_labels: Dict[int, int],
                               idx1: int, idx2: int) -> float:
        if idx1 in cluster_labels and idx2 in cluster_labels:
            if cluster_labels[idx1] == cluster_labels[idx2]:
                return 1.0
        dist = haversine_distance_km(
            s1.longitude, s1.latitude, s2.longitude, s2.latitude
        )
        if dist <= 5.0:
            return 0.7
        if dist <= 15.0:
            return 0.4
        return 0.0

    def infer_missing_connections(self, sites: List, known_edges: List[Dict],
                                  max_distance_km: float = 50) -> List[Dict[str, Any]]:
        """
        基于多源证据推理缺失连接
        计算6个证据分并加权综合，超过阈值判定为补全连接

        Args:
            sites: 遗址列表
            known_edges: 已知边列表
            max_distance_km: 最大考虑距离

        Returns:
            新增边列表: [{u, v, composite_score, evidence, inferred: True}]
        """
        n = len(sites)
        if n < 2:
            return []

        existing_pairs: Set[Tuple[int, int]] = set()
        for edge in known_edges:
            u, v = edge['u'], edge['v']
            existing_pairs.add((min(u, v), max(u, v)))

        cluster_labels: Dict[int, int] = {}
        cluster_id = 0
        unvisited = set(range(n))
        while unvisited:
            seed = next(iter(unvisited))
            queue = deque([seed])
            cluster = set()
            while queue:
                node = queue.popleft()
                if node in cluster:
                    continue
                cluster.add(node)
                unvisited.discard(node)
                for other in list(unvisited):
                    s_node = sites[node]
                    s_other = sites[other]
                    d = haversine_distance_km(
                        s_node.longitude, s_node.latitude,
                        s_other.longitude, s_other.latitude
                    )
                    same_dynasty = (s_node.dynasty == s_other.dynasty) if s_node.dynasty and s_other.dynasty else False
                    same_type = (s_node.site_type == s_other.site_type) if s_node.site_type and s_other.site_type else False
                    if d <= 10.0 and same_dynasty and same_type:
                        queue.append(other)
            for node in cluster:
                cluster_labels[node] = cluster_id
            cluster_id += 1

        new_edges: List[Dict[str, Any]] = []

        for i in range(n):
            for j in range(i + 1, n):
                if (i, j) in existing_pairs:
                    continue

                s1, s2 = sites[i], sites[j]
                dist = haversine_distance_km(
                    s1.longitude, s1.latitude, s2.longitude, s2.latitude
                )
                if dist > max_distance_km:
                    continue

                distance_score = self._compute_distance_score(dist, max_distance_km)
                watershed_score = self._compute_watershed_score(s1, s2)
                downstream_score = self._compute_downstream_score(s1, s2)
                dynasty_score = self._compute_dynasty_score(s1.dynasty or '', s2.dynasty or '')
                type_compatibility = self._compute_type_compatibility(s1.site_type or '', s2.site_type or '')
                cluster_score = self._compute_cluster_score(s1, s2, cluster_labels, i, j)

                evidence = {
                    'distance_score': round(distance_score, 4),
                    'watershed_score': round(watershed_score, 4),
                    'downstream_score': round(downstream_score, 4),
                    'dynasty_score': round(dynasty_score, 4),
                    'type_compatibility': round(type_compatibility, 4),
                    'archaeological_cluster': round(cluster_score, 4),
                }

                composite_score = (
                    self.EVIDENCE_WEIGHTS['distance_score'] * distance_score +
                    self.EVIDENCE_WEIGHTS['watershed_score'] * watershed_score +
                    self.EVIDENCE_WEIGHTS['downstream_score'] * downstream_score +
                    self.EVIDENCE_WEIGHTS['dynasty_score'] * dynasty_score +
                    self.EVIDENCE_WEIGHTS['type_compatibility'] * type_compatibility +
                    self.EVIDENCE_WEIGHTS['archaeological_cluster'] * cluster_score
                )
                composite_score = round(min(1.0, max(0.0, composite_score)), 4)

                if composite_score >= self.completion_threshold:
                    new_edges.append({
                        'u': i,
                        'v': j,
                        'u_site_id': s1.id,
                        'v_site_id': s2.id,
                        'composite_score': composite_score,
                        'evidence': evidence,
                        'inferred': True,
                        'distance_km': round(dist, 3),
                    })

        new_edges.sort(key=lambda e: e['composite_score'], reverse=True)
        return new_edges

    def build_hydrological_prior_network(self, region: str, sites: List) -> Dict[str, Any]:
        """
        构建先验水系网络
        - 已知水系边（高置信度）
        - 考古学证据补全边
        - 距离-高程启发式边

        Args:
            region: 区域名称
            sites: 遗址列表

        Returns:
            {edges: [...], node_metadata: {id: {inferred_river, ...}}}
        """
        hydrology_extract = self.extract_known_hydrology(sites)
        known_edges = hydrology_extract['known_edges']
        inferred_river_nodes = set(hydrology_extract['inferred_river_nodes'])

        inferred_edges = self.infer_missing_connections(sites, known_edges)

        all_edges: List[Dict[str, Any]] = []

        for edge in known_edges:
            all_edges.append({
                **edge,
                'source': 'known_hydrology',
                'confidence': edge.get('confidence', 0.95),
            })

        for edge in inferred_edges:
            all_edges.append({
                **edge,
                'source': 'archaeological_inference',
                'confidence': edge.get('composite_score', 0.70),
            })

        n = len(sites)
        existing_pairs = set()
        for e in all_edges:
            existing_pairs.add((min(e['u'], e['v']), max(e['u'], e['v'])))

        for i in range(n):
            for j in range(i + 1, n):
                if (i, j) in existing_pairs:
                    continue
                s1, s2 = sites[i], sites[j]
                dist = haversine_distance_km(
                    s1.longitude, s1.latitude, s2.longitude, s2.latitude
                )
                if dist > 20.0:
                    continue
                elev1 = get_approx_elevation(s1, self.region)
                elev2 = get_approx_elevation(s2, self.region)
                elev_diff = abs(elev1 - elev2)
                if elev_diff > 80.0:
                    continue
                heuristic_score = round(max(0.0, min(1.0, 0.5 * (1.0 - dist / 20.0) + 0.5 * (1.0 - elev_diff / 80.0))), 4)
                if heuristic_score >= 0.4:
                    all_edges.append({
                        'u': i,
                        'v': j,
                        'u_site_id': s1.id,
                        'v_site_id': s2.id,
                        'composite_score': heuristic_score,
                        'evidence': {'heuristic': heuristic_score},
                        'inferred': True,
                        'source': 'distance_elevation_heuristic',
                        'confidence': 0.50,
                        'distance_km': round(dist, 3),
                    })

        node_metadata: Dict[int, Dict[str, Any]] = {}
        for i, site in enumerate(sites):
            node_metadata[site.id] = {
                'inferred_river': site.id in inferred_river_nodes,
                'index': i,
                'site_name': site.name,
            }

        return {
            'edges': all_edges,
            'node_metadata': node_metadata,
        }

    def apply_expert_correction(self, graph: Dict[str, Any],
                                corrections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        专家修正接口：逐条执行修正并记录审计轨迹

        Args:
            graph: 原图数据 {edges: [...], nodes: ...}
            corrections: 修正列表 [{action, u, v, node_id, new_role, reason, expert_id, confidence}]

        Returns:
            {graph: 修正后图, audit_log: 审计轨迹}
        """
        corrected_graph = {
            'edges': list(graph.get('edges', [])),
            'nodes': dict(graph.get('nodes', {})),
        }
        audit_log: List[Dict[str, Any]] = []

        for corr in corrections:
            action = corr.get('action')
            timestamp = datetime.now().isoformat()
            audit_entry = {
                'action': action,
                'expert_id': corr.get('expert_id', 'unknown'),
                'reason': corr.get('reason', ''),
                'confidence': corr.get('confidence', 1.0),
                'timestamp': timestamp,
            }

            if action == 'add_edge':
                u, v = corr.get('u'), corr.get('v')
                if u is not None and v is not None:
                    already_exists = any(
                        (e.get('u') == u and e.get('v') == v) or
                        (e.get('u') == v and e.get('v') == u)
                        for e in corrected_graph['edges']
                    )
                    if not already_exists:
                        new_edge = {
                            'u': u,
                            'v': v,
                            'u_site_id': corr.get('u_site_id'),
                            'v_site_id': corr.get('v_site_id'),
                            'source': 'expert_correction',
                            'confidence': corr.get('confidence', 0.95),
                            'inferred': False,
                            'expert_added': True,
                        }
                        corrected_graph['edges'].append(new_edge)
                        audit_entry['result'] = 'edge_added'
                        audit_entry['u'] = u
                        audit_entry['v'] = v
                    else:
                        audit_entry['result'] = 'edge_already_exists'
                        audit_entry['u'] = u
                        audit_entry['v'] = v

            elif action == 'remove_edge':
                u, v = corr.get('u'), corr.get('v')
                if u is not None and v is not None:
                    original_len = len(corrected_graph['edges'])
                    corrected_graph['edges'] = [
                        e for e in corrected_graph['edges']
                        if not ((e.get('u') == u and e.get('v') == v) or
                                (e.get('u') == v and e.get('v') == u))
                    ]
                    removed = original_len - len(corrected_graph['edges'])
                    audit_entry['result'] = f'edges_removed: {removed}'
                    audit_entry['u'] = u
                    audit_entry['v'] = v

            elif action == 'change_node_role':
                node_id = corr.get('node_id')
                new_role = corr.get('new_role')
                if node_id is not None and new_role:
                    if node_id not in corrected_graph['nodes']:
                        corrected_graph['nodes'][node_id] = {}
                    old_role = corrected_graph['nodes'][node_id].get('role', 'unknown')
                    corrected_graph['nodes'][node_id]['role'] = new_role
                    corrected_graph['nodes'][node_id]['role_expert_modified'] = True
                    audit_entry['result'] = 'role_changed'
                    audit_entry['node_id'] = node_id
                    audit_entry['old_role'] = old_role
                    audit_entry['new_role'] = new_role

            else:
                audit_entry['result'] = 'unknown_action'

            audit_log.append(audit_entry)
            self._audit_log.append(audit_entry)

        return {
            'graph': corrected_graph,
            'audit_log': audit_log,
        }

    def evaluate_completion_quality(self, original_graph: Dict[str, Any],
                                    completed_graph: Dict[str, Any],
                                    reference: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        补全质量评估

        Args:
            original_graph: 原始图 {edges: [...], nodes: {...}}
            completed_graph: 补全后图
            reference: 可选参考网络

        Returns:
            质量评估指标字典
        """
        orig_edges = original_graph.get('edges', [])
        comp_edges = completed_graph.get('edges', [])
        orig_nodes = original_graph.get('nodes', {})
        comp_nodes = completed_graph.get('nodes', {})

        n_orig_edges = len(orig_edges)
        n_comp_edges = len(comp_edges)
        n_orig_nodes = len(orig_nodes) if orig_nodes else (
            len(set(e['u'] for e in orig_edges) | set(e['v'] for e in orig_edges))
        )
        n_comp_nodes = len(comp_nodes) if comp_nodes else (
            len(set(e['u'] for e in comp_edges) | set(e['v'] for e in comp_edges))
        )

        orig_max_edges = n_orig_nodes * (n_orig_nodes - 1) / 2 if n_orig_nodes > 1 else 1
        comp_max_edges = n_comp_nodes * (n_comp_nodes - 1) / 2 if n_comp_nodes > 1 else 1

        orig_density = n_orig_edges / orig_max_edges if orig_max_edges > 0 else 0.0
        comp_density = n_comp_edges / comp_max_edges if comp_max_edges > 0 else 0.0

        density_change_rate = 0.0
        if orig_density > 0:
            density_change_rate = (comp_density - orig_density) / orig_density
        elif comp_density > 0:
            density_change_rate = 1.0

        completed_edge_count = n_comp_edges - n_orig_edges
        completed_edge_ratio = 0.0
        if n_comp_edges > 0:
            completed_edge_ratio = completed_edge_count / n_comp_edges

        def _count_components(edges: List[Dict], num_nodes: int) -> int:
            if num_nodes == 0:
                return 0
            adj: Dict[int, Set[int]] = defaultdict(set)
            for e in edges:
                u, v = e.get('u'), e.get('v')
                if u is not None and v is not None:
                    adj[u].add(v)
                    adj[v].add(u)
            visited: Set[int] = set()
            components = 0
            nodes_set = set()
            for e in edges:
                if e.get('u') is not None:
                    nodes_set.add(e['u'])
                if e.get('v') is not None:
                    nodes_set.add(e['v'])
            for node in nodes_set:
                if node not in visited:
                    components += 1
                    queue = deque([node])
                    visited.add(node)
                    while queue:
                        curr = queue.popleft()
                        for nb in adj.get(curr, set()):
                            if nb not in visited:
                                visited.add(nb)
                                queue.append(nb)
            isolated = num_nodes - len(nodes_set)
            return components + isolated

        orig_components = _count_components(orig_edges, n_orig_nodes)
        comp_components = _count_components(comp_edges, n_comp_nodes)
        connectivity_change = orig_components - comp_components

        result = {
            'original_edges': n_orig_edges,
            'completed_edges': n_comp_edges,
            'added_edges': completed_edge_count,
            'original_density': round(orig_density, 6),
            'completed_density': round(comp_density, 6),
            'density_change_rate': round(density_change_rate, 6),
            'completed_edge_ratio': round(completed_edge_ratio, 6),
            'original_connected_components': orig_components,
            'completed_connected_components': comp_components,
            'connectivity_change': connectivity_change,
        }

        if reference:
            ref_edges = reference.get('edges', [])
            ref_pairs = set()
            for e in ref_edges:
                u, v = e.get('u'), e.get('v')
                if u is not None and v is not None:
                    ref_pairs.add((min(u, v), max(u, v)))
            comp_pairs = set()
            for e in comp_edges:
                u, v = e.get('u'), e.get('v')
                if u is not None and v is not None:
                    comp_pairs.add((min(u, v), max(u, v)))
            overlap = len(ref_pairs & comp_pairs)
            ref_recall = overlap / len(ref_pairs) if ref_pairs else 0.0
            comp_precision = overlap / len(comp_pairs) if comp_pairs else 0.0
            f1 = 0.0
            if ref_recall + comp_precision > 0:
                f1 = 2 * ref_recall * comp_precision / (ref_recall + comp_precision)
            result['reference_edge_count'] = len(ref_pairs)
            result['overlap_with_reference'] = overlap
            result['recall_vs_reference'] = round(ref_recall, 6)
            result['precision_vs_reference'] = round(comp_precision, 6)
            result['f1_vs_reference'] = round(f1, 6)

        return result


class UncertaintyAwareNetworkAnalyzer:
    """不确定性感知网络分析器：蒙特卡洛采样量化网络指标与节点角色的不确定性"""

    EDGE_CONFIDENCE_DEFAULTS: Dict[str, float] = {
        'known_hydrology': 0.95,
        'expert_correction': 0.95,
        'archaeological_inference': 0.70,
        'archaeological_cluster': 0.70,
        'distance_elevation_heuristic': 0.50,
    }

    def __init__(self, base_graph: Any, edge_confidence: Optional[Dict[Tuple[int, int], float]] = None):
        """
        Args:
            base_graph: 原始图对象（HydraulicNetworkGraph 实例或兼容结构）
            edge_confidence: 每条边的置信度字典 {(u,v): 0.0-1.0}
        """
        self.base_graph = base_graph
        self.edge_confidence: Dict[Tuple[int, int], float] = {}

        edges = getattr(base_graph, 'edges', None)
        if edges is None and isinstance(base_graph, dict):
            edges = base_graph.get('edges', [])

        if edges:
            for edge in edges:
                u, v = edge.get('u'), edge.get('v')
                if u is None or v is None:
                    continue
                key = (min(u, v), max(u, v))
                if edge_confidence and key in edge_confidence:
                    self.edge_confidence[key] = edge_confidence[key]
                else:
                    source = edge.get('source', '')
                    explicit_conf = edge.get('confidence')
                    if explicit_conf is not None:
                        self.edge_confidence[key] = float(explicit_conf)
                    else:
                        self.edge_confidence[key] = self.EDGE_CONFIDENCE_DEFAULTS.get(source, 0.50)

        self._mc_cache: Dict[str, Any] = {}

    def _sample_graph(self, rng: random.Random) -> Dict[Tuple[int, int], Dict]:
        """按置信度采样生成一个网络实现"""
        sampled: Dict[Tuple[int, int], Dict] = {}
        for (u, v), conf in self.edge_confidence.items():
            if rng.random() <= conf:
                sampled[(u, v)] = {'u': u, 'v': v}
        return sampled

    def _calc_connectivity(self, sampled_edges: Dict[Tuple[int, int], Dict]) -> float:
        """计算采样网络的连通度"""
        if not sampled_edges:
            return 0.0
        nodes: Set[int] = set()
        adj: Dict[int, Set[int]] = defaultdict(set)
        for (u, v) in sampled_edges.keys():
            nodes.add(u)
            nodes.add(v)
            adj[u].add(v)
            adj[v].add(u)
        n = len(nodes)
        if n < 2:
            return 0.0
        visited: Set[int] = set()
        components = 0
        for node in nodes:
            if node not in visited:
                components += 1
                queue = deque([node])
                visited.add(node)
                while queue:
                    curr = queue.popleft()
                    for nb in adj.get(curr, set()):
                        if nb not in visited:
                            visited.add(nb)
                            queue.append(nb)
        return max(0.0, 1.0 - (components - 1) / max(1, n - 1))

    def _calc_redundancy(self, sampled_edges: Dict[Tuple[int, int], Dict]) -> float:
        """计算采样网络的冗余度"""
        if not sampled_edges:
            return 0.0
        nodes: Set[int] = set()
        for (u, v) in sampled_edges.keys():
            nodes.add(u)
            nodes.add(v)
        n = len(nodes)
        if n < 2:
            return 0.0
        m = len(sampled_edges)
        min_spanning = n - 1
        max_edges = n * (n - 1) / 2
        max_additional = max_edges - min_spanning
        if max_additional <= 0:
            return 0.0
        return max(0.0, min(1.0, (m - min_spanning) / max_additional))

    def _calc_cascade_efficiency(self, sampled_edges: Dict[Tuple[int, int], Dict],
                                 nodes_info: Dict[int, Dict]) -> float:
        """估算梯级效率（简化版）"""
        if not sampled_edges or not nodes_info:
            return 0.0
        cascade_count = 0
        total_pairs = 0
        for (u, v) in sampled_edges.keys():
            total_pairs += 1
            nu = nodes_info.get(u, {})
            nv = nodes_info.get(v, {})
            elev_u = nu.get('elevation', 0)
            elev_v = nv.get('elevation', 0)
            if abs(elev_u - elev_v) > 10:
                cascade_count += 1
        return cascade_count / max(1, total_pairs)

    def _calc_synergy_score(self, connectivity: float, redundancy: float,
                            cascade_eff: float) -> float:
        """计算协同得分"""
        return 0.30 * connectivity + 0.20 * redundancy + 0.25 * cascade_eff + 0.25 * 0.5

    def _get_node_degrees(self, sampled_edges: Dict[Tuple[int, int], Dict]) -> Dict[int, int]:
        """计算每个节点的度"""
        degrees: Dict[int, int] = defaultdict(int)
        for (u, v) in sampled_edges.keys():
            degrees[u] += 1
            degrees[v] += 1
        return dict(degrees)

    def monte_carlo_network_sampling(self, n_samples: int = 200,
                                     seed: int = 42) -> Dict[str, Any]:
        """
        蒙特卡洛网络采样：按边置信度概率采样，生成多个网络实现并计算指标分布

        Args:
            n_samples: 采样数量
            seed: 随机种子

        Returns:
            {metric: {mean, std, p5, p50, p95, samples: [...]}}
        """
        rng = random.Random(seed)
        cache_key = f"mc_{n_samples}_{seed}"
        if cache_key in self._mc_cache:
            return self._mc_cache[cache_key]

        nodes_info: Dict[int, Dict] = {}
        if hasattr(self.base_graph, 'nodes'):
            nodes_info = getattr(self.base_graph, 'nodes', {})
        elif isinstance(self.base_graph, dict):
            nodes_info = self.base_graph.get('nodes', {})

        connectivity_samples: List[float] = []
        redundancy_samples: List[float] = []
        cascade_samples: List[float] = []
        synergy_samples: List[float] = []
        all_degree_samples: List[Dict[int, int]] = []

        for _ in range(max(1, n_samples)):
            sampled = self._sample_graph(rng)
            conn = self._calc_connectivity(sampled)
            red = self._calc_redundancy(sampled)
            casc = self._calc_cascade_efficiency(sampled, nodes_info)
            syn = self._calc_synergy_score(conn, red, casc)
            connectivity_samples.append(conn)
            redundancy_samples.append(red)
            cascade_samples.append(casc)
            synergy_samples.append(syn)
            all_degree_samples.append(self._get_node_degrees(sampled))

        result = {
            'connectivity': {**compute_stats(connectivity_samples), 'samples': connectivity_samples},
            'redundancy': {**compute_stats(redundancy_samples), 'samples': redundancy_samples},
            'cascade_efficiency': {**compute_stats(cascade_samples), 'samples': cascade_samples},
            'synergy_score': {**compute_stats(synergy_samples), 'samples': synergy_samples},
            'degree_samples': all_degree_samples,
            'n_samples': n_samples,
        }

        self._mc_cache[cache_key] = result
        return result

    def calculate_robustness_metrics(self, network_samples: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算鲁棒性指标：变异系数、置信区间宽度、排序稳定性

        Args:
            network_samples: monte_carlo_network_sampling 的输出

        Returns:
            robustness_report
        """
        robustness_report: Dict[str, Any] = {}

        for metric in ['connectivity', 'redundancy', 'cascade_efficiency', 'synergy_score']:
            data = network_samples.get(metric, {})
            mean = data.get('mean', 0.0)
            std = data.get('std', 0.0)
            cv = std / mean if abs(mean) > 1e-10 else 0.0
            ci_width = data.get('p95', 0.0) - data.get('p5', 0.0)
            robustness_report[metric] = {
                'coefficient_of_variation': round(cv, 6),
                'ci95_width': round(ci_width, 6),
                'mean': round(mean, 6),
                'std': round(std, 6),
            }

        degree_samples = network_samples.get('degree_samples', [])
        if len(degree_samples) >= 2:
            all_nodes: Set[int] = set()
            for ds in degree_samples:
                all_nodes.update(ds.keys())
            avg_degrees: Dict[int, float] = defaultdict(float)
            for ds in degree_samples:
                for node in all_nodes:
                    avg_degrees[node] += ds.get(node, 0)
            n_s = len(degree_samples)
            for node in avg_degrees:
                avg_degrees[node] /= max(1, n_s)
            baseline_rank = sorted(all_nodes, key=lambda n: avg_degrees[n], reverse=True)

            tau_values: List[float] = []
            for ds in degree_samples:
                sample_rank = sorted(all_nodes, key=lambda n: ds.get(n, 0), reverse=True)
                concordant = 0
                discordant = 0
                rank_map = {node: i for i, node in enumerate(sample_rank)}
                for i_idx in range(len(baseline_rank)):
                    for j_idx in range(i_idx + 1, len(baseline_rank)):
                        a, b = baseline_rank[i_idx], baseline_rank[j_idx]
                        if rank_map.get(a, 0) < rank_map.get(b, 0):
                            concordant += 1
                        else:
                            discordant += 1
                total = concordant + discordant
                tau = (concordant - discordant) / total if total > 0 else 0.0
                tau_values.append(tau)

            avg_tau = sum(tau_values) / len(tau_values) if tau_values else 0.0
            robustness_report['degree_ranking'] = {
                'kendalls_tau_mean': round(avg_tau, 6),
                'ranking_stability': round(max(0.0, (avg_tau + 1.0) / 2.0), 6),
            }

        return robustness_report

    def propagate_edge_uncertainty_to_node_roles(self) -> Dict[int, Dict[str, Any]]:
        """
        边不确定性传播到节点角色：基于采样网络的度分布，输出每个节点属于各角色的概率

        Returns:
            {node_id: {hub_prob, terminal_prob, isolated_prob, intermediary_prob, expected_role}}
        """
        mc_result = self.monte_carlo_network_sampling(n_samples=200, seed=42)
        degree_samples = mc_result.get('degree_samples', [])

        nodes_info: Dict[int, Dict] = {}
        if hasattr(self.base_graph, 'nodes'):
            raw_nodes = getattr(self.base_graph, 'nodes', {})
            for idx, info in raw_nodes.items():
                if isinstance(info, dict) and 'id' in info:
                    nodes_info[info['id']] = {'index': idx, **info}
                else:
                    nodes_info[idx] = {'index': idx, 'id': idx}
        elif isinstance(self.base_graph, dict):
            raw_nodes = self.base_graph.get('nodes', {})
            for idx, info in raw_nodes.items():
                if isinstance(info, dict) and 'id' in info:
                    nodes_info[info['id']] = {'index': idx, **info}
                else:
                    nodes_info[idx] = {'index': idx, 'id': idx}

        all_indices: Set[int] = set()
        for ds in degree_samples:
            all_indices.update(ds.keys())

        hub_threshold = NODE_ROLE_THRESHOLDS.get('hub_min_degree', 5)
        terminal_threshold = NODE_ROLE_THRESHOLDS.get('terminal_max_degree', 1)

        result: Dict[int, Dict[str, Any]] = {}
        n_samples = max(1, len(degree_samples))

        for idx in all_indices:
            degree_counts: List[int] = [ds.get(idx, 0) for ds in degree_samples]
            hub_count = sum(1 for d in degree_counts if d >= hub_threshold)
            terminal_count = sum(1 for d in degree_counts if d <= terminal_threshold and d > 0)
            isolated_count = sum(1 for d in degree_counts if d == 0)
            intermediary_count = n_samples - hub_count - terminal_count - isolated_count

            hub_prob = hub_count / n_samples
            terminal_prob = terminal_count / n_samples
            isolated_prob = isolated_count / n_samples
            intermediary_prob = max(0.0, intermediary_count / n_samples)

            probs = {
                'hub': hub_prob,
                'terminal': terminal_prob,
                'isolated': isolated_prob,
                'intermediary': intermediary_prob,
            }
            expected_role = max(probs, key=probs.get)

            role_cn_map = {
                'hub': '核心枢纽',
                'intermediary': '中转节点',
                'terminal': '终端节点',
                'isolated': '孤立节点',
            }

            result[idx] = {
                'hub_prob': round(hub_prob, 6),
                'terminal_prob': round(terminal_prob, 6),
                'isolated_prob': round(isolated_prob, 6),
                'intermediary_prob': round(intermediary_prob, 6),
                'expected_role': role_cn_map.get(expected_role, '终端节点'),
                'expected_role_en': expected_role,
                'avg_degree': round(sum(degree_counts) / n_samples, 4),
            }

        return result

    def generate_completion_confidence_report(self) -> Dict[str, Any]:
        """
        生成置信度报告：边来源占比、节点角色确定性、指标可靠性等级、验证建议

        Returns:
            置信度报告字典
        """
        source_counts: Dict[str, int] = defaultdict(int)
        low_confidence_edges: List[Dict[str, Any]] = []

        edges = getattr(self.base_graph, 'edges', None)
        if edges is None and isinstance(self.base_graph, dict):
            edges = self.base_graph.get('edges', [])

        total_edges = 0
        if edges:
            for edge in edges:
                total_edges += 1
                source = edge.get('source', 'unknown')
                source_counts[source] += 1
                conf = edge.get('confidence', 0.5)
                if conf < 0.6:
                    low_confidence_edges.append({
                        'u': edge.get('u'),
                        'v': edge.get('v'),
                        'u_site_id': edge.get('u_site_id'),
                        'v_site_id': edge.get('v_site_id'),
                        'confidence': conf,
                        'source': source,
                    })

        source_ratio: Dict[str, float] = {}
        for src, cnt in source_counts.items():
            source_ratio[src] = round(cnt / max(1, total_edges), 6)

        mc_result = self.monte_carlo_network_sampling(n_samples=200, seed=42)
        robustness = self.calculate_robustness_metrics(mc_result)
        node_role_probs = self.propagate_edge_uncertainty_to_node_roles()

        questionable_nodes: List[Dict[str, Any]] = []
        for node_id, probs in node_role_probs.items():
            max_prob = max(
                probs.get('hub_prob', 0),
                probs.get('terminal_prob', 0),
                probs.get('isolated_prob', 0),
                probs.get('intermediary_prob', 0),
            )
            if max_prob < 0.6:
                questionable_nodes.append({
                    'node_index': node_id,
                    'max_role_probability': round(max_prob, 6),
                    'role_distribution': {
                        'hub': probs.get('hub_prob', 0),
                        'terminal': probs.get('terminal_prob', 0),
                        'isolated': probs.get('isolated_prob', 0),
                        'intermediary': probs.get('intermediary_prob', 0),
                    },
                })

        metric_reliability: Dict[str, str] = {}
        for metric, data in robustness.items():
            if metric == 'degree_ranking':
                continue
            cv = data.get('coefficient_of_variation', 1.0)
            if cv <= 0.05:
                metric_reliability[metric] = '高'
            elif cv <= 0.15:
                metric_reliability[metric] = '中'
            elif cv <= 0.30:
                metric_reliability[metric] = '低'
            else:
                metric_reliability[metric] = '极低'

        recommendations: List[str] = []
        if low_confidence_edges:
            recommendations.append(f"建议优先对 {len(low_confidence_edges)} 条低置信度边（置信度<0.6）进行考古验证")
        if questionable_nodes:
            recommendations.append(f"建议对 {len(questionable_nodes)} 个角色存疑的节点（最高角色概率<0.6）补充考古证据")

        ranking_stability = robustness.get('degree_ranking', {}).get('ranking_stability', 0.0)
        if ranking_stability < 0.5:
            recommendations.append("节点度排序稳定性较低，建议谨慎使用度排名作为决策依据")

        return {
            'edge_source_distribution': source_ratio,
            'edge_source_counts': dict(source_counts),
            'total_edges': total_edges,
            'low_confidence_edges': low_confidence_edges,
            'low_confidence_edge_count': len(low_confidence_edges),
            'node_role_determinacy': node_role_probs,
            'questionable_nodes': questionable_nodes,
            'questionable_node_count': len(questionable_nodes),
            'metric_reliability': metric_reliability,
            'robustness_metrics': robustness,
            'recommendations': recommendations,
            'generated_at': datetime.now().isoformat(),
        }
