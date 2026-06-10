import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


class AHPSustainabilityAssessment:
    """
    AHP层次分析法 - 古代水利工程可持续性评估模型
    评估维度: 结构完整性、水文条件、经济价值、文化价值、环境协调性
    """

    DEFAULT_CRITERIA_WEIGHTS = {
        'structural': 0.30,
        'hydrological': 0.25,
        'economic': 0.15,
        'cultural': 0.15,
        'environmental': 0.15
    }

    CRITERIA_NAMES = {
        'structural': '结构完整性',
        'hydrological': '水文条件',
        'economic': '经济价值',
        'cultural': '文化价值',
        'environmental': '环境协调性'
    }

    def build_pairwise_matrix(self, weights: Dict[str, float]) -> np.ndarray:
        criteria_order = ['structural', 'hydrological', 'economic', 'cultural', 'environmental']
        n = len(criteria_order)
        matrix = np.ones((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                wi = weights[criteria_order[i]]
                wj = weights[criteria_order[j]]
                if wj > 0:
                    ratio = wi / wj
                else:
                    ratio = 1.0
                matrix[i][j] = self._scale_to_saaty(ratio)
                matrix[j][i] = 1.0 / matrix[i][j]
        return matrix

    def _scale_to_saaty(self, ratio: float) -> float:
        saaty_scale = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        if ratio <= 1:
            return 1.0
        for i in range(len(saaty_scale) - 1):
            if saaty_scale[i] <= ratio <= saaty_scale[i + 1]:
                return saaty_scale[i] if (ratio - saaty_scale[i]) < (saaty_scale[i + 1] - ratio) else saaty_scale[i + 1]
        return 9.0

    def check_consistency(self, matrix: np.ndarray) -> Tuple[bool, float]:
        n = matrix.shape[0]
        eigenvalues = np.linalg.eigvals(matrix)
        lambda_max = np.max(np.real(eigenvalues))
        ci = (lambda_max - n) / (n - 1) if n > 1 else 0
        ri = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
        cr = ci / ri.get(n, 1.49) if ri.get(n, 0) > 0 else 0
        return cr < 0.1, cr

    def calculate_eigenvector(self, matrix: np.ndarray) -> np.ndarray:
        eigenvalues, eigenvectors = np.linalg.eig(matrix)
        max_idx = np.argmax(np.real(eigenvalues))
        eigenvector = np.real(eigenvectors[:, max_idx])
        return eigenvector / np.sum(eigenvector)

    def evaluate_structural(self, site: Any) -> Tuple[float, Dict[str, float]]:
        score = 0.0
        details = {}

        status_scores = {'完好': 90, '部分损毁': 50, '完全废弃': 15}
        status_score = status_scores.get(site.preservation_status, 30)
        details['preservation_status'] = status_score
        score += status_score * 0.40

        if site.dam_height and site.dam_height > 0:
            dam_score = min(100, 30 + site.dam_height * 4)
            details['dam_height'] = dam_score
            score += dam_score * 0.25
        else:
            if site.site_type == '井':
                details['dam_height'] = 60
                score += 60 * 0.25
            else:
                details['dam_height'] = 20
                score += 20 * 0.25

        if site.canal_length and site.canal_length > 0:
            canal_score = min(100, 20 + site.canal_length * 1.5)
            details['canal_length'] = canal_score
            score += canal_score * 0.20
        else:
            if site.site_type in ['塘', '井']:
                details['canal_length'] = 50
                score += 50 * 0.20
            else:
                details['canal_length'] = 15
                score += 15 * 0.20

        area_score = min(100, 10 + np.log1p(site.irrigation_area) * 18)
        details['irrigation_area'] = area_score
        score += area_score * 0.15

        return round(score, 2), details

    def evaluate_hydrological(self, site: Any, modern_hydro: List[Any],
                                ancient_hydro: List[Any]) -> Tuple[float, Dict[str, float]]:
        score = 0.0
        details = {}

        if modern_hydro:
            modern_rain = np.mean([h.rainfall for h in modern_hydro])
            modern_runoff = np.mean([h.runoff for h in modern_hydro])
        else:
            modern_rain = 600.0
            modern_runoff = 150.0

        if ancient_hydro:
            ancient_rain = np.mean([h.rainfall for h in ancient_hydro])
            ancient_runoff = np.mean([h.runoff for h in ancient_hydro])
        else:
            ancient_rain = modern_rain
            ancient_runoff = modern_runoff

        if ancient_rain > 0:
            rain_ratio = min(modern_rain / ancient_rain, 1.5)
        else:
            rain_ratio = 1.0
        rain_stability = min(100, 30 + rain_ratio * 50)
        details['rainfall_stability'] = rain_stability
        score += rain_stability * 0.30

        if ancient_runoff > 0:
            runoff_ratio = min(modern_runoff / ancient_runoff, 1.5)
        else:
            runoff_ratio = 1.0
        runoff_stability = min(100, 30 + runoff_ratio * 50)
        details['runoff_stability'] = runoff_stability
        score += runoff_stability * 0.35

        if site.site_type == '井':
            groundwater_score = min(100, 40 + modern_runoff * 0.3)
        else:
            surface_score = min(100, 30 + modern_runoff * 0.4)
            groundwater_score = surface_score
        details['water_availability'] = groundwater_score
        score += groundwater_score * 0.35

        return round(score, 2), details

    def evaluate_economic(self, site: Any, original_capacity: float) -> Tuple[float, Dict[str, float]]:
        score = 0.0
        details = {}

        capacity_score = min(100, 10 + np.log1p(original_capacity) * 18)
        details['irrigation_potential'] = capacity_score
        score += capacity_score * 0.45

        type_economic = {'渠': 85, '堰': 80, '陂': 70, '塘': 60, '井': 50}
        type_score = type_economic.get(site.site_type, 60)
        details['type_efficiency'] = type_score
        score += type_score * 0.30

        status_factor = {'完好': 1.0, '部分损毁': 0.6, '完全废弃': 0.2}
        restoration_cost_score = min(100, 20 + (1 - status_factor.get(site.preservation_status, 0.5)) * 100)
        details['restoration_feasibility'] = restoration_cost_score
        score += restoration_cost_score * 0.25

        return round(score, 2), details

    def evaluate_cultural(self, site: Any) -> Tuple[float, Dict[str, float]]:
        score = 0.0
        details = {}

        dynasty_age = {1: 100, 2: 95, 3: 90, 4: 88, 5: 85, 6: 82, 7: 80, 8: 78,
                       9: 75, 10: 73, 11: 70, 12: 68, 13: 65, 14: 63, 15: 60,
                       16: 55, 17: 50}
        age_score = dynasty_age.get(site.dynasty_order, 50)
        details['historical_age'] = age_score
        score += age_score * 0.40

        type_significance = {'渠': 95, '堰': 90, '陂': 85, '塘': 70, '井': 75}
        significance_score = type_significance.get(site.site_type, 75)
        details['engineering_significance'] = significance_score
        score += significance_score * 0.35

        rarity_score = min(100, 30 + (1 - site.irrigation_area / 500) * 70)
        if rarity_score < 0:
            rarity_score = 30
        details['rarity'] = rarity_score
        score += rarity_score * 0.25

        return round(score, 2), details

    def evaluate_environmental(self, site: Any) -> Tuple[float, Dict[str, float]]:
        score = 0.0
        details = {}

        eco_compatibility = {'渠': 85, '堰': 80, '陂': 90, '塘': 88, '井': 95}
        eco_score = eco_compatibility.get(site.site_type, 80)
        details['ecosystem_compatibility'] = eco_score
        score += eco_score * 0.35

        status_env = {'完好': 90, '部分损毁': 60, '完全废弃': 30}
        env_score = status_env.get(site.preservation_status, 50)
        details['environmental_impact'] = env_score
        score += env_score * 0.35

        sustainability_score = min(100, 40 + np.log1p(site.irrigation_area) * 12)
        details['sustainability'] = sustainability_score
        score += sustainability_score * 0.30

        return round(score, 2), details

    def determine_grade(self, total_score: float) -> str:
        if total_score >= 85:
            return 'S'
        elif total_score >= 75:
            return 'A'
        elif total_score >= 60:
            return 'B'
        elif total_score >= 45:
            return 'C'
        elif total_score >= 30:
            return 'D'
        else:
            return 'E'

    def assess_site(self, site: Any, modern_hydro: List[Any],
                    ancient_hydro: List[Any], original_capacity: float,
                    custom_weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        weights = custom_weights or self.DEFAULT_CRITERIA_WEIGHTS

        pairwise_matrix = self.build_pairwise_matrix(weights)
        is_consistent, cr = self.check_consistency(pairwise_matrix)

        if not is_consistent:
            weights = self.DEFAULT_CRITERIA_WEIGHTS
            pairwise_matrix = self.build_pairwise_matrix(weights)
            _, cr = self.check_consistency(pairwise_matrix)

        eigenvector = self.calculate_eigenvector(pairwise_matrix)
        actual_weights = {
            'structural': eigenvector[0],
            'hydrological': eigenvector[1],
            'economic': eigenvector[2],
            'cultural': eigenvector[3],
            'environmental': eigenvector[4]
        }

        structural_score, structural_details = self.evaluate_structural(site)
        hydrological_score, hydrological_details = self.evaluate_hydrological(site, modern_hydro, ancient_hydro)
        economic_score, economic_details = self.evaluate_economic(site, original_capacity)
        cultural_score, cultural_details = self.evaluate_cultural(site)
        environmental_score, environmental_details = self.evaluate_environmental(site)

        total_score = (
            structural_score * actual_weights['structural'] +
            hydrological_score * actual_weights['hydrological'] +
            economic_score * actual_weights['economic'] +
            cultural_score * actual_weights['cultural'] +
            environmental_score * actual_weights['environmental']
        )

        grade = self.determine_grade(total_score)
        restoration_potential = total_score >= 50 and site.preservation_status != '完全废弃'

        return {
            'structural_score': round(structural_score, 2),
            'hydrological_score': round(hydrological_score, 2),
            'economic_score': round(economic_score, 2),
            'cultural_score': round(cultural_score, 2),
            'environmental_score': round(environmental_score, 2),
            'total_score': round(total_score, 2),
            'grade': grade,
            'restoration_potential': restoration_potential,
            'assessment_details': {
                'consistency_ratio': round(cr, 4),
                'is_consistent': is_consistent,
                'criteria_weights': {k: round(v, 4) for k, v in actual_weights.items()},
                'structural_details': structural_details,
                'hydrological_details': hydrological_details,
                'economic_details': economic_details,
                'cultural_details': cultural_details,
                'environmental_details': environmental_details,
                'recommendations': self._generate_recommendations(
                    total_score, grade, site.preservation_status, structural_score, hydrological_score
                )
            }
        }

    def _generate_recommendations(self, total_score: float, grade: str,
                                    preservation_status: str,
                                    structural_score: float,
                                    hydro_score: float) -> List[str]:
        recommendations = []

        if preservation_status == '完全废弃':
            recommendations.append('立即启动文物保护应急程序，防止进一步损毁')
            recommendations.append('组织考古调查，完整记录工程遗存信息')
        elif preservation_status == '部分损毁':
            recommendations.append('制定修复方案，优先加固关键结构部位')
            recommendations.append('定期监测结构变化，建立预警机制')

        if total_score >= 80:
            recommendations.append('具备极高修复价值，建议优先纳入修复计划')
            recommendations.append('可申报省级或国家级文物保护单位')
        elif total_score >= 60:
            recommendations.append('具备较好修复潜力，可作为区域水利文化展示点')
        elif total_score >= 40:
            recommendations.append('修复成本较高，建议以保护现状为主')

        if structural_score < 40:
            recommendations.append('结构完整性较差，需专业工程评估')

        if hydro_score < 40:
            recommendations.append('水文条件变化较大，建议补充水文地质调查')

        return recommendations
