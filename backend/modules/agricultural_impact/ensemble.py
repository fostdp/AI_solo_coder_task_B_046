"""
AquaCrop集合模拟与敏感性分析 - 增强算法
参数敏感性分析、拉丁超立方抽样、集合模拟、不确定性量化
纯算法实现，不依赖数据库、Web框架等外部组件
"""
import sys
import os
import math
import random
import copy
import numpy as np
from typing import Dict, Tuple, Optional, List, Any, Type

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

try:
    from common.params.crop_params import (
        CROP_KC,
        CROP_WATER_STRESS,
        AQUACROP_CONSTANTS,
        get_baseline_yield,
        get_irrigation_gain,
    )
except ImportError:
    from .crop_model import (
        CROP_KC,
        CROP_WATER_STRESS,
        AQUACROP_CONSTANTS,
        get_irrigation_gain,
    )

    def get_baseline_yield(region: str, crop: str, dynasty_order: int) -> float:
        baselines = {
            '中原地区': {'粟': 175, '稻': 145, '麦': 210, '黍': 125, '豆': 105},
            '关中地区': {'粟': 165, '稻': 120, '麦': 195, '黍': 115, '豆': 100},
            '江南地区': {'粟': 110, '稻': 280, '麦': 125, '黍': 80, '豆': 105},
            '巴蜀地区': {'粟': 130, '稻': 250, '麦': 140, '黍': 95, '豆': 110},
        }
        region_data = baselines.get(region, {})
        return region_data.get(crop, 100.0)

from .crop_model import AquaCropSimplifiedModel
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


class ParameterSensitivityAnalyzer:
    """参数敏感性分析器
    局部OAT分析和全局Sobol敏感性分析，识别模型关键参数
    """

    SENSITIVITY_PARAMS: List[str] = [
        'Kc_mid',
        'rooting_depth',
        'harvest_index',
        'soil_TAW_mm',
        'initial_soil_water_pct',
        'stomatal_p50',
        'yield_response_Ky',
        'rainfall_multiplier',
        'et0_multiplier',
        'irrigation_efficiency',
    ]

    def __init__(self, crop_type: str, region: str):
        """初始化参数敏感性分析器

        Args:
            crop_type: 作物类型
            region: 区域名称
        """
        self.crop_type = crop_type
        self.region = region

        self.kc_params = CROP_KC.get(crop_type, CROP_KC['粟'])
        self.stress_params = CROP_WATER_STRESS.get(crop_type, CROP_WATER_STRESS['粟'])
        self.constants = AQUACROP_CONSTANTS

        self.param_ranges: Dict[str, Tuple[float, float]] = {}
        self.param_baselines: Dict[str, float] = {}
        self._build_param_distributions()

    def _build_param_distributions(self):
        """构建参数基准值和扰动范围"""
        kc_mid = self.kc_params.get('mid', 1.0)
        rooting_depth = self.kc_params.get('rooting_depth_m', 1.2)
        harvest_index = self.kc_params.get('harvest_index', 0.4)
        soil_taw = self.constants.get('total_available_water_mm_per_m', 150.0) * rooting_depth
        initial_water_pct = 0.6
        stomatal_p50 = self.stress_params.get('stomatal_conductance_p50', 0.45)
        yield_ky = self.stress_params.get('yield_response_factor_Ky', 1.0)

        baselines = {
            'Kc_mid': kc_mid,
            'rooting_depth': rooting_depth,
            'harvest_index': harvest_index,
            'soil_TAW_mm': soil_taw,
            'initial_soil_water_pct': initial_water_pct,
            'stomatal_p50': stomatal_p50,
            'yield_response_Ky': yield_ky,
            'rainfall_multiplier': 1.0,
            'et0_multiplier': 1.0,
            'irrigation_efficiency': 0.7,
        }

        for param, base_val in baselines.items():
            self.param_baselines[param] = base_val
            if param in ('rainfall_multiplier', 'et0_multiplier', 'irrigation_efficiency'):
                self.param_ranges[param] = (
                    _clamp(base_val * 0.7, 0.1, 5.0),
                    _clamp(base_val * 1.3, 0.1, 5.0),
                )
            else:
                self.param_ranges[param] = (
                    _clamp(base_val * 0.8, 1e-6, 1e6),
                    _clamp(base_val * 1.2, 1e-6, 1e6),
                )

    def _apply_params_to_model(self, model: AquaCropSimplifiedModel,
                               params: Dict[str, float]) -> AquaCropSimplifiedModel:
        """将参数值应用到模型实例（通过修改副本）

        Args:
            model: 基准模型实例
            params: 参数名-值字典

        Returns:
            修改后的模型副本
        """
        model_copy = copy.copy(model)
        for param, value in params.items():
            if param == 'Kc_mid':
                model_copy.kc_params = dict(model_copy.kc_params)
                model_copy.kc_params['mid'] = value
            elif param == 'rooting_depth':
                model_copy.rooting_depth = value
                model_copy.TAW_mm = self.constants['total_available_water_mm_per_m'] * value
            elif param == 'harvest_index':
                model_copy.harvest_index = value
            elif param == 'soil_TAW_mm':
                model_copy.TAW_mm = value
        return model_copy

    def _run_with_modified_params(self, baseline_params: Dict[str, float],
                                  param_override: Dict[str, float],
                                  precip_list: List[float],
                                  et0_list: List[float],
                                  temp_list: List[float],
                                  irrigation_capability: float = 0.0,
                                  irrigation_area: float = 100.0,
                                  baseline_yield: float = None) -> float:
        """运行带参数修改的模型单次模拟

        Args:
            baseline_params: 基准参数字典
            param_override: 覆盖的参数字典
            precip_list: 降雨序列
            et0_list: ET0序列
            temp_list: 温度序列
            irrigation_capability: 灌溉能力
            irrigation_area: 灌溉面积
            baseline_yield: 基准产量

        Returns:
            灌溉后产量 (kg/亩)
        """
        try:
            effective_params = dict(baseline_params)
            effective_params.update(param_override)

            rainfall_mult = effective_params.get('rainfall_multiplier', 1.0)
            et0_mult = effective_params.get('et0_multiplier', 1.0)
            irrig_eff = effective_params.get('irrigation_efficiency', 0.7)
            initial_water_pct = effective_params.get('initial_soil_water_pct', 0.6)
            stomatal_p50 = effective_params.get('stomatal_p50', 0.45)
            yield_ky = effective_params.get('yield_response_Ky', 1.0)

            modified_precip = [p * rainfall_mult for p in precip_list]
            modified_et0 = [e * et0_mult for e in et0_list]

            base_model = AquaCropSimplifiedModel(self.crop_type, self.region)
            model = self._apply_params_to_model(base_model, {
                k: v for k, v in effective_params.items()
                if k in ('Kc_mid', 'rooting_depth', 'harvest_index', 'soil_TAW_mm')
            })

            effective_irrigation = irrigation_capability * irrig_eff

            result = model.run_full_simulation(
                precipitation_mm_per_day=modified_precip,
                et0_mm_per_day=modified_et0,
                temperatures_c=temp_list,
                irrigation_capability_m3_per_day=effective_irrigation,
                irrigation_area_mu=irrigation_area,
                historical_baseline_yield_kg_per_mu=baseline_yield,
            )

            raw_yield = result.get('yield_with_irrigation_kg_per_mu', baseline_yield or 100.0)
            stress_factor = _clamp(0.5 + 0.5 * stomatal_p50 / 0.5, 0.7, 1.3)
            ky_factor = _clamp(yield_ky, 0.5, 1.5)
            adjusted_yield = raw_yield * stress_factor * (0.8 + 0.2 * ky_factor)

            return _clamp(adjusted_yield, 10.0, 1000.0)
        except Exception:
            return baseline_yield or 100.0

    def analyze_local_sensitivity(self, model_class: Type[AquaCropSimplifiedModel],
                                   baseline_params: Dict[str, float],
                                   precip_list: List[float],
                                   et0_list: List[float],
                                   temp_list: List[float],
                                   irrigation_capability: float = 0.0,
                                   irrigation_area: float = 100.0,
                                   baseline_yield: float = None,
                                   n_levels: int = 5) -> Dict[str, Dict[str, Any]]:
        """局部敏感性分析（OAT：One-At-a-Time）

        Args:
            model_class: 模型类
            baseline_params: 基准参数
            precip_list: 降雨序列
            et0_list: ET0序列
            temp_list: 温度序列
            irrigation_capability: 灌溉能力
            irrigation_area: 灌溉面积
            baseline_yield: 基准产量
            n_levels: 每个参数采样水平数

        Returns:
            {param: {sensitivity, rank, min_yield, max_yield, pct_change}}
        """
        try:
            results: Dict[str, Dict[str, Any]] = {}

            baseline_yield_val = self._run_with_modified_params(
                baseline_params, {},
                precip_list, et0_list, temp_list,
                irrigation_capability, irrigation_area, baseline_yield
            )

            for param in self.SENSITIVITY_PARAMS:
                param_range = self.param_ranges.get(param)
                if not param_range:
                    continue
                lo, hi = param_range

                yields = []
                for level in range(n_levels):
                    t = level / max(1, n_levels - 1)
                    param_val = lo + (hi - lo) * t
                    y = self._run_with_modified_params(
                        baseline_params, {param: param_val},
                        precip_list, et0_list, temp_list,
                        irrigation_capability, irrigation_area, baseline_yield
                    )
                    yields.append(y)

                min_yield = min(yields)
                max_yield = max(yields)
                delta_y = max_yield - min_yield
                delta_p = hi - lo
                base_p = self.param_baselines.get(param, (lo + hi) / 2.0)

                sensitivity = abs(_safe_div(
                    _safe_div(delta_y, baseline_yield_val, 0.0),
                    _safe_div(delta_p, base_p, 1.0),
                    0.0
                ))

                pct_change = _safe_div(delta_y, baseline_yield_val, 0.0) * 100.0

                results[param] = {
                    'sensitivity': round(sensitivity, 4),
                    'min_yield': round(min_yield, 2),
                    'max_yield': round(max_yield, 2),
                    'pct_change': round(pct_change, 2),
                    'baseline': round(base_p, 4),
                    'range': [round(lo, 4), round(hi, 4)],
                }

            sorted_params = sorted(
                results.keys(),
                key=lambda p: results[p]['sensitivity'],
                reverse=True
            )
            for rank, param in enumerate(sorted_params, 1):
                results[param]['rank'] = rank

            return results
        except Exception:
            return {}

    def analyze_sobol_sensitivity(self, model_class: Type[AquaCropSimplifiedModel],
                                   baseline_params: Dict[str, float],
                                   precip_list: List[float],
                                   et0_list: List[float],
                                   temp_list: List[float],
                                   irrigation_capability: float = 0.0,
                                   irrigation_area: float = 100.0,
                                   baseline_yield: float = None,
                                   n_samples: int = 512) -> Dict[str, Dict[str, Any]]:
        """Sobol全局敏感性分析（简化版）

        Args:
            model_class: 模型类
            baseline_params: 基准参数
            precip_list: 降雨序列
            et0_list: ET0序列
            temp_list: 温度序列
            irrigation_capability: 灌溉能力
            irrigation_area: 灌溉面积
            baseline_yield: 基准产量
            n_samples: 基础样本数

        Returns:
            {param: {S1, ST, confidence}}
        """
        try:
            d = len(self.SENSITIVITY_PARAMS)
            n = max(32, n_samples)

            param_names = [p for p in self.SENSITIVITY_PARAMS if p in self.param_ranges]
            d_eff = len(param_names)

            A = np.random.uniform(0.0, 1.0, size=(n, d_eff))
            B = np.random.uniform(0.0, 1.0, size=(n, d_eff))

            def _matrix_to_params(matrix: np.ndarray) -> List[Dict[str, float]]:
                param_sets = []
                for row in matrix:
                    p = {}
                    for j, name in enumerate(param_names):
                        lo, hi = self.param_ranges[name]
                        p[name] = lo + (hi - lo) * _clamp(row[j], 0.0, 1.0)
                    param_sets.append(p)
                return param_sets

            Y_A = []
            for params in _matrix_to_params(A):
                y = self._run_with_modified_params(
                    baseline_params, params,
                    precip_list, et0_list, temp_list,
                    irrigation_capability, irrigation_area, baseline_yield
                )
                Y_A.append(y)

            Y_B = []
            for params in _matrix_to_params(B):
                y = self._run_with_modified_params(
                    baseline_params, params,
                    precip_list, et0_list, temp_list,
                    irrigation_capability, irrigation_area, baseline_yield
                )
                Y_B.append(y)

            Y_A_arr = np.array(Y_A, dtype=np.float64)
            Y_B_arr = np.array(Y_B, dtype=np.float64)

            total_variance = float(np.var(np.concatenate([Y_A_arr, Y_B_arr])))
            if total_variance < 1e-10:
                total_variance = 1.0

            results: Dict[str, Dict[str, Any]] = {}

            for i, name in enumerate(param_names):
                AB = A.copy()
                AB[:, i] = B[:, i]
                BA = B.copy()
                BA[:, i] = A[:, i]

                Y_AB = []
                for params in _matrix_to_params(AB):
                    y = self._run_with_modified_params(
                        baseline_params, params,
                        precip_list, et0_list, temp_list,
                        irrigation_capability, irrigation_area, baseline_yield
                    )
                    Y_AB.append(y)

                Y_BA = []
                for params in _matrix_to_params(BA):
                    y = self._run_with_modified_params(
                        baseline_params, params,
                        precip_list, et0_list, temp_list,
                        irrigation_capability, irrigation_area, baseline_yield
                    )
                    Y_BA.append(y)

                Y_AB_arr = np.array(Y_AB, dtype=np.float64)
                Y_BA_arr = np.array(Y_BA, dtype=np.float64)

                f0_sq = (np.mean(Y_A_arr) * np.mean(Y_B_arr))
                V_i = np.mean(Y_B_arr * (Y_AB_arr - Y_A_arr))
                S1 = _safe_div(V_i, total_variance, 0.0)

                E_Vi = 0.5 * np.mean((Y_A_arr - Y_BA_arr) ** 2)
                ST = _safe_div(E_Vi, total_variance, 0.0)

                S1 = _clamp(S1, 0.0, 1.0)
                ST = _clamp(ST, 0.0, 1.0)
                if ST < S1:
                    ST = S1

                std_error = _safe_div(1.0, _safe_sqrt(n), 0.1)
                confidence = _clamp(1.0 - std_error, 0.5, 0.99)

                results[name] = {
                    'S1': round(S1, 4),
                    'ST': round(ST, 4),
                    'confidence': round(confidence, 4),
                }

            return results
        except Exception:
            return {}

    def generate_sensitivity_report(self, sensitivity_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """生成人类可读的敏感性分析报告

        Args:
            sensitivity_results: analyze_local_sensitivity 的输出

        Returns:
            结构化报告字典
        """
        try:
            high_sensitivity: List[str] = []
            medium_sensitivity: List[str] = []
            low_sensitivity: List[str] = []

            for param, data in sensitivity_results.items():
                s = data.get('sensitivity', 0.0)
                if s > 0.3:
                    high_sensitivity.append(param)
                elif s >= 0.1:
                    medium_sensitivity.append(param)
                else:
                    low_sensitivity.append(param)

            sorted_items = sorted(
                sensitivity_results.items(),
                key=lambda x: x[1].get('sensitivity', 0.0),
                reverse=True
            )
            top3 = [item[0] for item in sorted_items[:3]]

            total_sensitivity = sum(
                d.get('sensitivity', 0.0) for d in sensitivity_results.values()
            )
            uncertainty_contribution: Dict[str, float] = {}
            for param, data in sensitivity_results.items():
                uncertainty_contribution[param] = round(
                    _safe_div(data.get('sensitivity', 0.0), total_sensitivity, 0.0) * 100.0,
                    2
                )

            avg_pct_change = _safe_mean([
                abs(d.get('pct_change', 0.0)) for d in sensitivity_results.values()
            ])

            return {
                'summary': {
                    'total_params_analyzed': len(sensitivity_results),
                    'high_sensitivity_count': len(high_sensitivity),
                    'medium_sensitivity_count': len(medium_sensitivity),
                    'low_sensitivity_count': len(low_sensitivity),
                    'avg_pct_change_per_param': round(avg_pct_change, 2),
                },
                'classifications': {
                    'high': high_sensitivity,
                    'medium': medium_sensitivity,
                    'low': low_sensitivity,
                },
                'top3_critical_params': top3,
                'insensitive_params': low_sensitivity,
                'uncertainty_contribution_pct': uncertainty_contribution,
                'ranking': [
                    {
                        'param': param,
                        'rank': data.get('rank', 0),
                        'sensitivity': data.get('sensitivity', 0.0),
                        'pct_change': data.get('pct_change', 0.0),
                    }
                    for param, data in sorted_items
                ],
            }
        except Exception:
            return {}


class EnsembleAquaCropSimulator:
    """集合AquaCrop模拟引擎
    多成员集合模拟、不确定性量化、后处理与收敛检验
    """

    def __init__(self, crop_type: str, region: str, n_members: int = 50):
        """初始化集合模拟引擎

        Args:
            crop_type: 作物类型
            region: 区域名称
            n_members: 集合成员数 (20-200)
        """
        self.crop_type = crop_type
        self.region = region
        self.n_members = _clamp(n_members, 20, 200)

        self.kc_params = CROP_KC.get(crop_type, CROP_KC['粟'])
        self.stress_params = CROP_WATER_STRESS.get(crop_type, CROP_WATER_STRESS['粟'])
        self.constants = AQUACROP_CONSTANTS

        self.param_names: List[str] = [
            'Kc_mid', 'rooting_depth', 'harvest_index',
            'soil_TAW_mm', 'initial_soil_water_pct',
            'stomatal_p50', 'yield_response_Ky',
            'rainfall_multiplier', 'et0_multiplier', 'irrigation_efficiency',
        ]

        self.param_ranges: Dict[str, Tuple[float, float]] = {}
        self._build_ensemble_param_ranges()

    def _build_ensemble_param_ranges(self):
        """构建集合参数扰动范围"""
        kc_mid = self.kc_params.get('mid', 1.0)
        rooting_depth = self.kc_params.get('rooting_depth_m', 1.2)
        harvest_index = self.kc_params.get('harvest_index', 0.4)
        soil_taw = self.constants.get('total_available_water_mm_per_m', 150.0) * rooting_depth

        ranges = {
            'Kc_mid': (kc_mid * 0.95, kc_mid * 1.05),
            'rooting_depth': (rooting_depth * 0.85, rooting_depth * 1.15),
            'harvest_index': (harvest_index * 0.97, harvest_index * 1.03),
            'soil_TAW_mm': (soil_taw * 0.80, soil_taw * 1.20),
            'initial_soil_water_pct': (0.45, 0.75),
            'stomatal_p50': (0.35, 0.55),
            'yield_response_Ky': (0.7, 1.3),
            'rainfall_multiplier': (0.90, 1.10),
            'et0_multiplier': (0.92, 1.08),
            'irrigation_efficiency': (0.55, 0.85),
        }

        for name, (lo, hi) in ranges.items():
            self.param_ranges[name] = (max(lo, 1e-6), max(hi, lo + 1e-6))

    def _latin_hypercube_sampling(self, n_samples: int,
                                    param_ranges: Dict[str, Tuple[float, float]]) -> List[Dict[str, float]]:
        """拉丁超立方抽样

        Args:
            n_samples: 样本数
            param_ranges: 参数范围字典 {param: (lo, hi)}

        Returns:
            参数字典列表
        """
        try:
            param_names = list(param_ranges.keys())
            d = len(param_names)
            n = max(1, n_samples)

            samples: List[Dict[str, float]] = []

            for j, name in enumerate(param_names):
                lo, hi = param_ranges[name]
                interval_size = (hi - lo) / n
                column = []
                for i in range(n):
                    u = random.random()
                    val = lo + i * interval_size + u * interval_size
                    column.append(_clamp(val, lo, hi))
                random.shuffle(column)
                for i in range(n):
                    if len(samples) <= i:
                        samples.append({})
                    samples[i][name] = column[i]

            return samples
        except Exception:
            samples = []
            for _ in range(max(1, n_samples)):
                s = {}
                for name, (lo, hi) in param_ranges.items():
                    s[name] = lo + random.random() * (hi - lo)
                samples.append(s)
            return samples

    def _random_sampling(self, n_samples: int,
                          param_ranges: Dict[str, Tuple[float, float]]) -> List[Dict[str, float]]:
        """简单蒙特卡洛抽样"""
        samples = []
        for _ in range(n_samples):
            s = {}
            for name, (lo, hi) in param_ranges.items():
                s[name] = lo + random.random() * (hi - lo)
            samples.append(s)
        return samples

    def _run_member(self, params: Dict[str, float],
                    precip_list: List[float],
                    et0_list: List[float],
                    temp_list: List[float],
                    irrigation_capability: float,
                    irrigation_area: float,
                    baseline_yield: Optional[float]) -> Dict[str, Any]:
        """运行单个集合成员

        Args:
            params: 该成员的参数字典
            precip_list: 基准降雨序列
            et0_list: 基准ET0序列
            temp_list: 基准温度序列
            irrigation_capability: 灌溉能力
            irrigation_area: 灌溉面积
            baseline_yield: 基准产量

        Returns:
            成员模拟结果字典
        """
        try:
            rainfall_mult = params.get('rainfall_multiplier', 1.0)
            et0_mult = params.get('et0_multiplier', 1.0)
            irrig_eff = params.get('irrigation_efficiency', 0.7)
            initial_water_pct = params.get('initial_soil_water_pct', 0.6)
            stomatal_p50 = params.get('stomatal_p50', 0.45)
            yield_ky = params.get('yield_response_Ky', 1.0)

            modified_precip = [p * rainfall_mult + random.gauss(0, abs(p) * 0.02) for p in precip_list]
            modified_et0 = [e * et0_mult + random.gauss(0, abs(e) * 0.015) for e in et0_list]

            model = AquaCropSimplifiedModel(self.crop_type, self.region)
            model = copy.copy(model)

            if 'Kc_mid' in params:
                model.kc_params = dict(model.kc_params)
                model.kc_params['mid'] = params['Kc_mid']
            if 'rooting_depth' in params:
                model.rooting_depth = params['rooting_depth']
                model.TAW_mm = self.constants['total_available_water_mm_per_m'] * params['rooting_depth']
            if 'harvest_index' in params:
                model.harvest_index = params['harvest_index']
            if 'soil_TAW_mm' in params:
                model.TAW_mm = params['soil_TAW_mm']

            effective_irrigation = irrigation_capability * irrig_eff

            result = model.run_full_simulation(
                precipitation_mm_per_day=modified_precip,
                et0_mm_per_day=modified_et0,
                temperatures_c=temp_list,
                irrigation_capability_m3_per_day=effective_irrigation,
                irrigation_area_mu=irrigation_area,
                historical_baseline_yield_kg_per_mu=baseline_yield,
            )

            raw_yield = result.get('yield_with_irrigation_kg_per_mu', baseline_yield or 100.0)
            stress_factor = _clamp(0.5 + 0.5 * stomatal_p50 / 0.5, 0.85, 1.15)
            ky_factor = _clamp(yield_ky, 0.8, 1.2)
            adjusted_yield = raw_yield * stress_factor * ky_factor

            return {
                'yield': _clamp(adjusted_yield, 10.0, 1000.0),
                'yield_no_irrigation': result.get('yield_without_irrigation_kg_per_mu', adjusted_yield * 0.8),
                'biomass': result.get('total_biomass_with_irrigation_kg_per_ha', 5000.0),
                'water_applied': result.get('total_water_applied_m3', 0.0),
                'wue': result.get('water_use_efficiency_kg_per_m3', 0.0),
                'params_used': {k: round(v, 4) for k, v in params.items()},
                'success': True,
            }
        except Exception as e:
            return {
                'yield': baseline_yield or 100.0,
                'yield_no_irrigation': (baseline_yield or 100.0) * 0.8,
                'biomass': 5000.0,
                'water_applied': 0.0,
                'wue': 0.0,
                'params_used': {k: round(v, 4) for k, v in params.items()},
                'success': False,
                'error': str(e),
            }

    def run_ensemble_simulation(self, precip_list: List[float],
                                 et0_list: List[float],
                                 temp_list: List[float],
                                 irrigation_capability: float = 0.0,
                                 irrigation_area: float = 100.0,
                                 baseline_yield: Optional[float] = None,
                                 dynasty_order: int = 11,
                                 method: str = 'lhs') -> Dict[str, Any]:
        """集合模拟核心方法

        Args:
            precip_list: 降雨序列
            et0_list: ET0序列
            temp_list: 温度序列
            irrigation_capability: 灌溉能力 (m3/天)
            irrigation_area: 灌溉面积 (亩)
            baseline_yield: 基准产量 (kg/亩)
            dynasty_order: 朝代顺序
            method: 'lhs' (拉丁超立方) 或 'mc' (蒙特卡洛)

        Returns:
            集合模拟结果字典
        """
        try:
            if baseline_yield is None:
                baseline_yield = get_baseline_yield(self.region, self.crop_type, dynasty_order)

            if method == 'lhs':
                param_sets = self._latin_hypercube_sampling(self.n_members, self.param_ranges)
            else:
                param_sets = self._random_sampling(self.n_members, self.param_ranges)

            member_results: List[Dict[str, Any]] = []
            yields: List[float] = []

            for member_idx, params in enumerate(param_sets):
                result = self._run_member(
                    params, precip_list, et0_list, temp_list,
                    irrigation_capability, irrigation_area, baseline_yield
                )
                result['member_id'] = member_idx
                member_results.append(result)
                yields.append(result['yield'])

            mean_yield = _safe_mean(yields, baseline_yield)
            median_yield = _safe_percentile(yields, 50.0, baseline_yield)
            std_yield = _safe_std(yields, 0.0)
            cv = _safe_div(std_yield, mean_yield, 0.0)

            p5 = _safe_percentile(yields, 5.0, mean_yield)
            p25 = _safe_percentile(yields, 25.0, mean_yield)
            p50 = _safe_percentile(yields, 50.0, mean_yield)
            p75 = _safe_percentile(yields, 75.0, mean_yield)
            p95 = _safe_percentile(yields, 95.0, mean_yield)
            p2_5 = _safe_percentile(yields, 2.5, mean_yield)
            p97_5 = _safe_percentile(yields, 97.5, mean_yield)

            spread = max(yields) - min(yields) if yields else 0.0

            upper_3sigma = mean_yield + 3.0 * std_yield
            lower_3sigma = mean_yield - 3.0 * std_yield
            outlier_members: List[int] = []
            for i, y in enumerate(yields):
                if y > upper_3sigma or y < lower_3sigma:
                    outlier_members.append(i)

            pit_values: List[float] = []
            for i in range(len(yields)):
                count_le = sum(1 for y in yields if y <= yields[i])
                pit_values.append(count_le / len(yields))
            pit_mean = _safe_mean(pit_values, 0.5)
            pit_uniformity = 1.0 - abs(pit_mean - 0.5) * 2.0
            pit_uniformity = _clamp(pit_uniformity, 0.0, 1.0)

            return {
                'config': {
                    'crop_type': self.crop_type,
                    'region': self.region,
                    'n_members': self.n_members,
                    'sampling_method': method,
                    'baseline_yield': round(baseline_yield, 2),
                },
                'statistics': {
                    'mean_yield': round(mean_yield, 2),
                    'median_yield': round(median_yield, 2),
                    'std': round(std_yield, 2),
                    'cv': round(cv, 4),
                    'p5': round(p5, 2),
                    'p25': round(p25, 2),
                    'p50': round(p50, 2),
                    'p75': round(p75, 2),
                    'p95': round(p95, 2),
                    'ci_95_lower': round(p2_5, 2),
                    'ci_95_upper': round(p97_5, 2),
                    'spread': round(spread, 2),
                    'min_yield': round(min(yields) if yields else 0.0, 2),
                    'max_yield': round(max(yields) if yields else 0.0, 2),
                },
                'reliability': {
                    'pit_uniformity': round(pit_uniformity, 4),
                    'outlier_count': len(outlier_members),
                    'outlier_member_ids': outlier_members,
                    'successful_members': sum(1 for r in member_results if r.get('success', True)),
                },
                'members': member_results,
            }
        except Exception as e:
            return {
                'config': {
                    'crop_type': self.crop_type,
                    'region': self.region,
                    'n_members': self.n_members,
                    'sampling_method': method,
                    'error': str(e),
                },
                'statistics': {
                    'mean_yield': round(baseline_yield or 100.0, 2),
                    'median_yield': round(baseline_yield or 100.0, 2),
                    'std': 0.0,
                    'cv': 0.0,
                    'error': str(e),
                },
                'reliability': {},
                'members': [],
            }

    def _calculate_ensemble_weights(self, model_outputs: List[Dict[str, Any]],
                                     observations: Optional[List[float]] = None) -> List[float]:
        """计算集合成员权重

        Args:
            model_outputs: 成员输出列表
            observations: 观测数据列表（可选）

        Returns:
            权重列表
        """
        n = len(model_outputs)
        if n == 0:
            return []

        if observations is None or len(observations) == 0:
            return [1.0 / n] * n

        errors: List[float] = []
        for output in model_outputs:
            yield_val = output.get('yield', 100.0)
            member_errors = []
            for obs in observations:
                member_errors.append(abs(yield_val - obs))
            errors.append(_safe_mean(member_errors, 1e6))

        weights: List[float] = []
        for err in errors:
            w = _safe_div(1.0, max(err, 1e-6), 0.0)
            weights.append(w)

        total_w = sum(weights)
        if total_w < 1e-10:
            return [1.0 / n] * n

        return [w / total_w for w in weights]

    def post_process_ensemble_results(self, raw_results: Dict[str, Any],
                                       include_members: bool = False,
                                       observations: Optional[List[float]] = None) -> Dict[str, Any]:
        """结果后处理

        Args:
            raw_results: run_ensemble_simulation 的原始输出
            include_members: 是否包含每个成员的详细结果
            observations: 观测数据（用于加权）

        Returns:
            后处理结果字典
        """
        try:
            members = raw_results.get('members', [])
            yields = [m.get('yield', 0.0) for m in members]

            weights = self._calculate_ensemble_weights(members, observations)

            if len(yields) > 0 and len(weights) == len(yields):
                weighted_mean = sum(y * w for y, w in zip(yields, weights))
            else:
                weighted_mean = raw_results.get('statistics', {}).get('mean_yield', 100.0)

            raw_mean = raw_results.get('statistics', {}).get('mean_yield', weighted_mean)
            bias_correction = 1.0
            if observations and len(observations) > 0:
                obs_mean = _safe_mean(observations, raw_mean)
                bias_correction = _safe_div(obs_mean, raw_mean, 1.0)
                bias_correction = _clamp(bias_correction, 0.7, 1.3)

            corrected_mean = weighted_mean * bias_correction

            n = len(yields)
            converged = False
            convergence_diff_pct = 0.0
            if n >= 10:
                half = n // 2
                first_half_mean = _safe_mean(yields[:half], 0.0)
                second_half_mean = _safe_mean(yields[half:], 0.0)
                combined_mean = _safe_mean([first_half_mean, second_half_mean], 1.0)
                convergence_diff_pct = _safe_div(
                    abs(first_half_mean - second_half_mean),
                    combined_mean,
                    0.0
                ) * 100.0
                converged = convergence_diff_pct < 5.0

            result = {
                'config': raw_results.get('config', {}),
                'post_processed': {
                    'bias_corrected_mean_yield': round(corrected_mean, 2),
                    'weighted_mean_yield': round(weighted_mean, 2),
                    'raw_mean_yield': round(raw_mean, 2),
                    'bias_correction_factor': round(bias_correction, 4),
                    'converged': converged,
                    'convergence_diff_pct': round(convergence_diff_pct, 2),
                    'weights_summary': {
                        'min': round(min(weights), 6) if weights else 0.0,
                        'max': round(max(weights), 6) if weights else 0.0,
                        'effective_n': round(
                            _safe_div(1.0, sum(w * w for w in weights), float(len(weights))),
                            1
                        ) if weights else 0.0,
                    },
                },
                'statistics': raw_results.get('statistics', {}),
                'reliability': raw_results.get('reliability', {}),
            }

            if include_members:
                result['members'] = []
                for i, m in enumerate(members):
                    member_data = dict(m)
                    if i < len(weights):
                        member_data['weight'] = round(weights[i], 6)
                    result['members'].append(member_data)

            return result
        except Exception as e:
            return {
                'error': str(e),
                'config': raw_results.get('config', {}),
                'statistics': raw_results.get('statistics', {}),
            }
