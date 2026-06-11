"""
农业影响评估分析器 - 业务逻辑层
整合AquaCrop模型、受益区估算、农户估算等功能
纯业务逻辑实现，不直接操作数据库
"""
import sys
import os
import math
import random
import hashlib
from typing import Dict, List, Optional, Tuple, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

try:
    from common.params.crop_params import (
        CROP_KC,
        CROP_WATER_STRESS,
        AQUACROP_CONSTANTS,
        BENEFIT_ZONE_RADIUS_RATIOS,
        FARMER_DENSITY_PER_MU,
        BASELINE_YIELDS,
        get_crop_kc,
        get_baseline_yield,
        get_irrigation_gain,
    )
    from common.params.hydraulic_params import REGIONS
except ImportError:
    from .crop_model import (
        CROP_KC,
        CROP_WATER_STRESS,
        AQUACROP_CONSTANTS,
        get_crop_kc,
        get_irrigation_gain,
    )
    BENEFIT_ZONE_RADIUS_RATIOS = {'core': 0.50, 'radiating': 0.85, 'marginal': 1.00}
    FARMER_DENSITY_PER_MU = {
        '中原地区': 8.5, '关中地区': 7.2, '江南地区': 9.8, '巴蜀地区': 6.5,
        '岭南地区': 5.2, '江淮地区': 8.0, '山东地区': 8.8, '河北地区': 7.6,
        '河东地区': 6.0, '河西地区': 3.0, '辽东地区': 3.5, '滇黔地区': 4.2,
    }
    REGIONS = [
        '中原地区', '关中地区', '江南地区', '巴蜀地区', '岭南地区', '江淮地区',
        '山东地区', '河北地区', '河东地区', '河西地区', '辽东地区', '滇黔地区',
    ]

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
    _safe_div,
    _clamp,
    _safe_sqrt,
    _safe_mean,
)


class AgriculturalImpactAnalyzer:
    """农业影响综合评估分析器
    整合AquaCrop模型、受益区生成、农户估算等功能
    业务逻辑类，输入数据，输出评估结果，不直接操作数据库
    """

    def __init__(self):
        """初始化农业影响分析器"""
        self._model_cache: Dict[str, AquaCropSimplifiedModel] = {}

    def _get_model(self, crop_type: str, region: str) -> AquaCropSimplifiedModel:
        """获取或创建作物模型实例（带缓存）

        Args:
            crop_type: 作物类型
            region: 区域名称

        Returns:
            AquaCropSimplifiedModel 实例
        """
        key = f"{crop_type}|{region}"
        if key not in self._model_cache:
            self._model_cache[key] = AquaCropSimplifiedModel(crop_type, region)
        return self._model_cache[key]

    def _select_dominant_crops(self, region: str, dynasty_order: int,
                               site_type: str = None) -> List[str]:
        """选择区域主导作物

        Args:
            region: 区域名称
            dynasty_order: 朝代顺序
            site_type: 遗址类型（预留参数）

        Returns:
            主导作物列表（按重要性排序，最多3种）
        """
        try:
            southern_regions = ['江南地区', '巴蜀地区', '岭南地区', '江淮地区', '滇黔地区']
            northern_regions = ['中原地区', '关中地区', '山东地区', '河北地区', '河东地区', '河西地区', '辽东地区']

            is_southern = region in southern_regions
            is_northern = region in northern_regions

            early_dynasties = list(range(1, 10))
            mid_dynasties = list(range(10, 15))
            late_dynasties = list(range(15, 18))

            candidates = []

            if dynasty_order in early_dynasties:
                candidates.extend(['粟', '黍', '麦'])
                if is_southern:
                    candidates = ['稻', '粟', '豆']
            elif dynasty_order in mid_dynasties:
                if is_southern:
                    candidates = ['稻', '麦', '豆']
                else:
                    candidates = ['麦', '粟', '豆']
            else:
                if is_southern:
                    candidates = ['稻', '麦', '豆']
                else:
                    candidates = ['麦', '粟', '黍']

            crop_weights = {}
            for crop in candidates:
                baseline = get_baseline_yield(region, crop, dynasty_order)
                gain = get_irrigation_gain(crop, dynasty_order)
                crop_weights[crop] = baseline * (1 + gain * 0.5)

            sorted_crops = sorted(crop_weights.keys(), key=lambda c: crop_weights[c], reverse=True)

            seen = []
            for c in sorted_crops:
                if c not in seen:
                    seen.append(c)
                if len(seen) >= 3:
                    break

            return seen if seen else ['粟', '麦', '豆']
        except Exception:
            return ['粟', '麦', '豆']

    def _get_regional_climate(self, region: str) -> Dict[str, float]:
        """获取区域气候基准参数

        Args:
            region: 区域名称

        Returns:
            气候参数字典
        """
        climate_fallback = {
            '中原地区': {'avg_temp_c': 14.0, 'seasonal_temp_amp': 12.5, 'annual_precipitation_mm': 650.0, 'avg_et0_mm_per_day': 3.2},
            '关中地区': {'avg_temp_c': 13.5, 'seasonal_temp_amp': 13.0, 'annual_precipitation_mm': 580.0, 'avg_et0_mm_per_day': 3.3},
            '江南地区': {'avg_temp_c': 17.0, 'seasonal_temp_amp': 10.5, 'annual_precipitation_mm': 1200.0, 'avg_et0_mm_per_day': 3.8},
            '巴蜀地区': {'avg_temp_c': 16.5, 'seasonal_temp_amp': 10.0, 'annual_precipitation_mm': 1100.0, 'avg_et0_mm_per_day': 3.6},
            '岭南地区': {'avg_temp_c': 20.5, 'seasonal_temp_amp': 8.5, 'annual_precipitation_mm': 1600.0, 'avg_et0_mm_per_day': 4.0},
            '江淮地区': {'avg_temp_c': 15.5, 'seasonal_temp_amp': 11.5, 'annual_precipitation_mm': 1000.0, 'avg_et0_mm_per_day': 3.5},
            '山东地区': {'avg_temp_c': 13.0, 'seasonal_temp_amp': 13.0, 'annual_precipitation_mm': 680.0, 'avg_et0_mm_per_day': 3.3},
            '河北地区': {'avg_temp_c': 12.0, 'seasonal_temp_amp': 13.5, 'annual_precipitation_mm': 550.0, 'avg_et0_mm_per_day': 3.2},
            '河东地区': {'avg_temp_c': 11.5, 'seasonal_temp_amp': 13.5, 'annual_precipitation_mm': 500.0, 'avg_et0_mm_per_day': 3.1},
            '河西地区': {'avg_temp_c': 8.5, 'seasonal_temp_amp': 14.0, 'annual_precipitation_mm': 150.0, 'avg_et0_mm_per_day': 3.8},
            '辽东地区': {'avg_temp_c': 8.0, 'seasonal_temp_amp': 14.0, 'annual_precipitation_mm': 700.0, 'avg_et0_mm_per_day': 3.0},
            '滇黔地区': {'avg_temp_c': 15.5, 'seasonal_temp_amp': 9.5, 'annual_precipitation_mm': 1100.0, 'avg_et0_mm_per_day': 3.5},
        }
        return climate_fallback.get(region, climate_fallback['中原地区'])

    def _generate_historical_climate_series(self, region: str, dynasty_order: int,
                                            growing_days: int) -> Dict[str, List[float]]:
        """生成历史气候序列（随机模拟）

        Args:
            region: 区域名称
            dynasty_order: 朝代顺序
            growing_days: 生育期天数

        Returns:
            气候序列字典 {precipitation_mm, et0_mm, temperatures_c}
        """
        try:
            climate = self._get_regional_climate(region)

            avg_temp = climate.get('avg_temp_c', 15.0)
            temp_amp = climate.get('seasonal_temp_amp', 12.0)
            annual_precip = climate.get('annual_precipitation_mm', 800.0)
            avg_et0 = climate.get('avg_et0_mm_per_day', 3.5)

            precipitations = []
            et0s = []
            temperatures = []

            for i in range(growing_days):
                season_factor = math.sin(2 * math.pi * (i - 60) / 365)
                temp = avg_temp + temp_amp * season_factor
                temp += (random.random() - 0.5) * 3.0

                daily_precip = 0.0
                precip_prob = 0.28 if 90 <= i <= 240 else 0.18
                if random.random() < precip_prob:
                    daily_precip = max(0.0, random.gauss(annual_precip / 120, annual_precip / 200))
                daily_precip += (random.random() - 0.5) * 0.5

                et0 = avg_et0 + 1.5 * season_factor
                et0 = max(0.5, et0 + (random.random() - 0.5) * 0.8)

                precipitations.append(_clamp(daily_precip, 0.0, 80.0))
                et0s.append(_clamp(et0, 0.5, 10.0))
                temperatures.append(_clamp(temp, -5.0, 40.0))

            return {
                'precipitation_mm': precipitations,
                'et0_mm': et0s,
                'temperatures_c': temperatures,
            }
        except Exception as e:
            return {
                'precipitation_mm': [max(0.0, random.gauss(2.2, 3.0)) for _ in range(growing_days)],
                'et0_mm': [_clamp(3.5 + random.gauss(0, 0.8), 0.5, 10.0) for _ in range(growing_days)],
                'temperatures_c': [_clamp(18.0 + random.gauss(0, 3.0), -5.0, 40.0) for _ in range(growing_days)],
            }

    def estimate_benefit_zone(self, longitude: float, latitude: float,
                              irrigation_area_mu: float,
                              yield_increase_rate: float,
                              site_id: int = None,
                              site_name: str = None) -> Dict[str, Any]:
        """估算灌溉受益区范围

        Args:
            longitude: 遗址经度
            latitude: 遗址纬度
            irrigation_area_mu: 灌溉面积 (亩)
            yield_increase_rate: 增产率 (0-1)
            site_id: 遗址ID（可选，用于元数据）
            site_name: 遗址名称（可选，用于元数据）

        Returns:
            受益区信息字典，包含各等级受益区的半径、面积、增产率等
        """
        try:
            area = max(irrigation_area_mu, 1.0)
            area_km2 = area * 666.67 / 1_000_000.0
            base_radius = _safe_sqrt(area_km2 / math.pi)
            base_radius = _clamp(base_radius, 0.3, 15.0)
            radius_deg = base_radius / 111.0

            yield_colors = {
                'core': '#e74c3c',
                'radiating': '#e67e22',
                'marginal': '#f1c40f',
            }

            if yield_increase_rate >= 0.30:
                zone_multiplier = 1.2
            elif yield_increase_rate >= 0.15:
                zone_multiplier = 1.0
            else:
                zone_multiplier = 0.85

            zones_config = [
                ('core', BENEFIT_ZONE_RADIUS_RATIOS['core'], f'核心受益区(+{yield_increase_rate*100:.1f}%)'),
                ('radiating', BENEFIT_ZONE_RADIUS_RATIOS['radiating'], f'辐射受益区(+{yield_increase_rate*75:.1f}%)'),
                ('marginal', BENEFIT_ZONE_RADIUS_RATIOS['marginal'], f'边缘受益区(+{yield_increase_rate*50:.1f}%)'),
            ]

            zones = {}
            features = []

            for zone_name, zone_ratio, zone_label in zones_config:
                r = radius_deg * zone_ratio * zone_multiplier
                r_km = base_radius * zone_ratio * zone_multiplier
                area_zone_mu = irrigation_area_mu * (zone_ratio ** 2)

                zone_yield_rate = yield_increase_rate * (1.0 if zone_name == 'core' else 0.75 if zone_name == 'radiating' else 0.5)

                zone_points = []
                n_points = 48
                noise_amp = 0.12
                for i in range(n_points):
                    angle = 2 * math.pi * i / n_points
                    noise = 1.0 + (random.random() - 0.5) * 2.0 * noise_amp
                    r_i = r * noise
                    x = longitude + r_i * math.cos(angle)
                    y = latitude + r_i * math.sin(angle) / math.cos(math.radians(latitude))
                    zone_points.append([round(x, 6), round(y, 6)])
                zone_points.append(zone_points[0])

                zones[zone_name] = {
                    'zone_type': zone_name,
                    'zone_label': zone_label,
                    'radius_km': round(r_km, 3),
                    'radius_deg': round(r, 6),
                    'area_mu': round(area_zone_mu, 1),
                    'yield_increase_rate': round(zone_yield_rate, 4),
                    'color': yield_colors[zone_name],
                    'boundary_points': zone_points,
                }

                features.append({
                    'type': 'Feature',
                    'properties': {
                        'zone_type': zone_name,
                        'zone_label': zone_label,
                        'site_id': site_id,
                        'site_name': site_name,
                        'yield_increase_rate': round(zone_yield_rate, 4),
                        'color': yield_colors[zone_name],
                        'area_mu': round(area_zone_mu, 1),
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [zone_points],
                    },
                })

            geojson = {
                'type': 'FeatureCollection',
                'features': features,
                'metadata': {
                    'site_id': site_id,
                    'site_name': site_name,
                    'longitude': longitude,
                    'latitude': latitude,
                    'total_influenced_area_mu': round(irrigation_area_mu, 1),
                    'yield_increase_rate': round(yield_increase_rate, 4),
                    'base_radius_km': round(base_radius, 3),
                    'generation_method': 'radius_based_noise',
                }
            }

            return {
                'zones': zones,
                'geojson': geojson,
                'total_influenced_area_mu': round(irrigation_area_mu, 1),
                'base_radius_km': round(base_radius, 3),
            }
        except Exception as e:
            return {
                'zones': {},
                'geojson': {'type': 'FeatureCollection', 'features': [], 'metadata': {'error': str(e)}},
                'total_influenced_area_mu': 0.0,
                'base_radius_km': 0.0,
                'error': str(e),
            }

    def estimate_farmer_population(self, region: str, influenced_area_mu: float) -> Dict[str, Any]:
        """估算受益农户人口数量

        Args:
            region: 区域名称
            influenced_area_mu: 受影响面积 (亩)

        Returns:
            农户人口估算结果字典
        """
        try:
            density = FARMER_DENSITY_PER_MU.get(region, 5.0)
            people_count = influenced_area_mu * density / 100.0
            household_count = int(people_count / 5.0)
            household_count = max(10, household_count)
            people_count = household_count * 5

            return {
                'region': region,
                'influenced_area_mu': round(influenced_area_mu, 2),
                'farmer_density_per_100mu': density,
                'total_farmers': people_count,
                'households': household_count,
                'people_per_household': 5,
            }
        except Exception:
            return {
                'region': region,
                'influenced_area_mu': round(influenced_area_mu, 2),
                'farmer_density_per_100mu': 5.0,
                'total_farmers': max(10, int(influenced_area_mu * 0.05) * 5),
                'households': max(10, int(influenced_area_mu * 0.05)),
                'people_per_household': 5,
            }

    def analyze_site_impact(self,
                            longitude: float,
                            latitude: float,
                            region: str,
                            dynasty_order: int,
                            irrigation_area_mu: float,
                            irrigation_capability_m3_per_day: float = 0.0,
                            crop_types: List[str] = None,
                            site_type: str = None,
                            scenario: str = 'typical') -> Dict[str, Any]:
        """分析单个遗址的农业影响（纯数据输入输出）

        Args:
            longitude: 遗址经度
            latitude: 遗址纬度
            region: 区域名称
            dynasty_order: 朝代顺序
            irrigation_area_mu: 灌溉面积 (亩)
            irrigation_capability_m3_per_day: 日灌溉能力 (m³/天)
            crop_types: 作物类型列表（可选，为空则自动选择）
            site_type: 遗址类型（可选，用于作物选择）
            scenario: 情景模式（预留参数）

        Returns:
            农业影响评估结果字典
        """
        try:
            if crop_types is None or len(crop_types) == 0:
                crop_types = self._select_dominant_crops(region, dynasty_order, site_type)

            crop_results = []
            total_weight = 0.0
            weighted_yield_no = 0.0
            weighted_yield_with = 0.0
            weighted_wue = 0.0
            weighted_water = 0.0

            for crop in crop_types:
                try:
                    model = self._get_model(crop, region)
                    baseline = get_baseline_yield(region, crop, dynasty_order)
                    climate = self._generate_historical_climate_series(region, dynasty_order, model.total_growing_days)

                    result = model.run_full_simulation(
                        precipitation_mm_per_day=climate['precipitation_mm'],
                        et0_mm_per_day=climate['et0_mm'],
                        temperatures_c=climate['temperatures_c'],
                        irrigation_capability_m3_per_day=irrigation_capability_m3_per_day,
                        irrigation_area_mu=irrigation_area_mu,
                        historical_baseline_yield_kg_per_mu=baseline,
                    )

                    weight = baseline
                    crop_results.append({
                        'crop_type': crop,
                        'baseline_yield_kg_per_mu': baseline,
                        **result,
                        'weight': weight,
                    })

                    total_weight += weight
                    weighted_yield_no += result['yield_without_irrigation_kg_per_mu'] * weight
                    weighted_yield_with += result['yield_with_irrigation_kg_per_mu'] * weight
                    weighted_wue += result['water_use_efficiency_kg_per_m3'] * weight
                    weighted_water += result['total_water_applied_m3'] * weight
                except Exception:
                    continue

            if total_weight <= 0 or len(crop_results) == 0:
                return {'error': '无法计算作物产量', 'crop_types': crop_types}

            avg_yield_no = weighted_yield_no / total_weight
            avg_yield_with = weighted_yield_with / total_weight
            avg_wue = weighted_wue / total_weight
            avg_water = weighted_water / total_weight

            yield_increase_rate = _safe_div(avg_yield_with - avg_yield_no, avg_yield_no, 0.0)
            yield_increase_rate = _clamp(yield_increase_rate, 0.0, 1.0)

            yield_increase_kg_per_mu = avg_yield_with - avg_yield_no
            total_influenced_area = max(irrigation_area_mu, 1.0)
            annual_yield_increase_kg = yield_increase_kg_per_mu * total_influenced_area

            benefit_zone = self.estimate_benefit_zone(
                longitude, latitude, total_influenced_area, yield_increase_rate
            )

            farmer_pop = self.estimate_farmer_population(region, total_influenced_area)

            confidence = 100.0
            if len(crop_results) < 3:
                confidence -= 10
            for cr in crop_results:
                if cr.get('degraded'):
                    confidence -= 8
                    break
            confidence = _clamp(confidence, 20.0, 100.0) / 100.0

            dominant_crop = max(crop_results, key=lambda x: x['weight'])['crop_type']

            simulation_raw = {
                'scenario': scenario,
                'region': region,
                'dynasty_order': dynasty_order,
                'irrigation_capability_m3_per_day': round(irrigation_capability_m3_per_day, 1),
                'irrigation_area_mu': round(irrigation_area_mu, 1),
                'crop_results': [{k: v for k, v in cr.items() if k != 'daily_results'} for cr in crop_results],
                'dominant_crop': dominant_crop,
                'weighted_summary': {
                    'avg_yield_without_irrigation_kg_per_mu': round(avg_yield_no, 2),
                    'avg_yield_with_irrigation_kg_per_mu': round(avg_yield_with, 2),
                }
            }

            return {
                'dominant_crop': dominant_crop,
                'total_influenced_area_mu': round(total_influenced_area, 4),
                'yield_increase_rate': round(yield_increase_rate, 4),
                'annual_yield_increase_kg': round(annual_yield_increase_kg, 4),
                'farmers_benefited_count': farmer_pop['households'],
                'total_farmers': farmer_pop['total_farmers'],
                'water_use_efficiency_kg_per_m3': round(avg_wue, 4),
                'total_water_applied_m3': round(avg_water, 1),
                'yield_without_irrigation_kg_per_mu': round(avg_yield_no, 2),
                'yield_with_irrigation_kg_per_mu': round(avg_yield_with, 2),
                'confidence_score': round(confidence, 4),
                'benefit_zone': benefit_zone,
                'farmer_population': farmer_pop,
                'simulation_raw': simulation_raw,
                'crop_types_analyzed': crop_types,
            }
        except Exception as e:
            return {
                'error': str(e),
                'dominant_crop': crop_types[0] if crop_types else '粟',
                'total_influenced_area_mu': irrigation_area_mu,
                'yield_increase_rate': 0.0,
                'confidence_score': 0.0,
            }

    def analyze_batch(self, sites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量分析多个遗址的农业影响（简化版）

        Args:
            sites: 遗址信息列表，每个字典包含 longitude, latitude, region,
                   dynasty_order, irrigation_area_mu, irrigation_capability_m3_per_day 等

        Returns:
            分析结果列表
        """
        try:
            results = []
            for site in sites:
                try:
                    result = self.analyze_site_impact(
                        longitude=site.get('longitude', 0.0),
                        latitude=site.get('latitude', 0.0),
                        region=site.get('region', '中原地区'),
                        dynasty_order=site.get('dynasty_order', 11),
                        irrigation_area_mu=site.get('irrigation_area_mu', 100.0),
                        irrigation_capability_m3_per_day=site.get('irrigation_capability_m3_per_day', 0.0),
                        crop_types=site.get('crop_types'),
                        site_type=site.get('site_type'),
                        scenario=site.get('scenario', 'typical'),
                    )
                    result['site_id'] = site.get('site_id')
                    result['site_name'] = site.get('site_name')
                    results.append(result)
                except Exception:
                    continue
            return results
        except Exception:
            return []
