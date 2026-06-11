"""
AquaCrop简化版作物模型 - 核心算法
FAO参考蒸散、土壤水平衡、生物量积累、产量估算
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import math
import random
import hashlib
import numpy as np
from typing import Dict, Tuple, Optional, List, Any
from shapely.geometry import Polygon, mapping
from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

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
from common.models import WaterHeritageSite, FunctionalRestoration, PaleoHydrologyData, DynastyDict


# ==============================================
# 兼容：REGIONAL_CLIMATE 回退
# ==============================================

_REGIONAL_CLIMATE_FALLBACK: Dict[str, Dict[str, float]] = {
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


def _safe_get_regional_climate(region: str) -> Dict[str, float]:
    try:
        from common.params.climate_params import get_regional_climate as _grc
        result = _grc(region)
        if result and len(result) > 0:
            return result
    except Exception:
        pass
    return _REGIONAL_CLIMATE_FALLBACK.get(region, _REGIONAL_CLIMATE_FALLBACK['中原地区'])


# ==============================================
# 数值收敛保护
# ==============================================

def _safe_log(x: float, epsilon: float = 1e-10) -> float:
    return math.log(max(x, epsilon))


def _safe_sqrt(x: float) -> float:
    return math.sqrt(max(x, 0.0))


def _safe_div(a: float, b: float, default: float = 0.0, epsilon: float = 1e-10) -> float:
    if abs(b) < epsilon:
        return default
    return a / b


def _clamp(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(val, max_val))


def _safe_exp(x: float, max_val: float = 1e6) -> float:
    try:
        result = math.exp(min(x, math.log(max_val)))
        return result
    except Exception:
        return max_val


# ==============================================
# AquaCrop简化版作物模型
# ==============================================

class AquaCropSimplifiedModel:
    """AquaCrop简化版作物模型
    参考FAO AquaCrop v6.1，针对中国古代农业背景简化
    """

    def __init__(self, crop_type: str, region: str):
        self.crop_type = crop_type
        self.region = region

        self.kc_params = CROP_KC.get(crop_type, CROP_KC['粟'])
        self.stress_params = CROP_WATER_STRESS.get(crop_type, CROP_WATER_STRESS['粟'])
        self.constants = AQUACROP_CONSTANTS

        self.length_init = self.kc_params['length_init_days']
        self.length_dev = self.kc_params['length_dev_days']
        self.length_mid = self.kc_params['length_mid_days']
        self.length_late = self.kc_params['length_late_days']
        self.total_growing_days = self.length_init + self.length_dev + self.length_mid + self.length_late

        self.rooting_depth = self.kc_params['rooting_depth_m']
        self.harvest_index = self.kc_params['harvest_index']

        self.TAW_mm = self.constants['total_available_water_mm_per_m'] * self.rooting_depth
        self.p_upper = self.constants['soil_water_depletion_p_upper']

        self.WP = 15.0 + (hash(crop_type) % 10) * 0.5
        self.WP = _clamp(self.WP, 10.0, 25.0)

    def _calculate_et0_penman_monteith(self, temp_c: float, humidity_pct: float,
                                       wind_ms: float, solar_rad: float,
                                       elevation_m: float = 100.0) -> float:
        try:
            temp_k = temp_c + 273.16
            es = 0.6108 * _safe_exp(17.27 * temp_c / (temp_c + 237.3))
            ea = es * (humidity_pct / 100.0)
            Delta = 4098.0 * es / ((temp_c + 237.3) ** 2)
            P = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
            gamma = 0.000665 * P
            u2 = wind_ms * 4.87 / _safe_log(67.8 * 10 - 5.42)

            Rn = solar_rad * 0.75
            G = 0.0

            numerator = 0.408 * Delta * (Rn - G) + gamma * (900.0 / temp_k) * u2 * (es - ea)
            denominator = Delta + gamma * (1 + 0.34 * u2)
            et0 = _safe_div(numerator, denominator, 0.0)

            et0 = et0 * self.constants['ET0_adjust_factor']
            return _clamp(et0, 0.0, 15.0)
        except Exception as e:
            return _clamp(2.0 + temp_c * 0.05, 0.0, 15.0)

    def _calculate_crop_et(self, et0_mm: float, growth_stage: str) -> float:
        try:
            kc = get_crop_kc(self.crop_type, growth_stage)
            etc = kc * et0_mm
            return _clamp(etc, 0.0, 20.0)
        except Exception:
            return _clamp(0.8 * et0_mm, 0.0, 20.0)

    def _get_growth_stage(self, day_of_season: int) -> str:
        if day_of_season < self.length_init:
            return 'initial'
        elif day_of_season < self.length_init + self.length_dev:
            return 'development'
        elif day_of_season < self.length_init + self.length_dev + self.length_mid:
            return 'mid'
        else:
            return 'late'

    def _simulate_soil_water_balance(self, daily_data: List[Dict],
                                     initial_soil_water_mm: float,
                                     irrigation_enabled: bool = False,
                                     irrigation_capability_m3_per_day: float = 0.0,
                                     irrigation_area_mu: float = 100.0) -> List[Dict]:
        try:
            results = []
            current_water = _clamp(initial_soil_water_mm, 0.0, self.TAW_mm)
            total_irrigation_mm = 0.0

            irrigation_mm_per_day = 0.0
            if irrigation_enabled and irrigation_area_mu > 0 and irrigation_capability_m3_per_day > 0:
                area_m2 = irrigation_area_mu * 666.67
                irrigation_mm_per_day = (irrigation_capability_m3_per_day / area_m2) * 1000.0
                irrigation_mm_per_day = _clamp(irrigation_mm_per_day, 0.0, 50.0)

            for day_idx, day in enumerate(daily_data):
                precip = day.get('precip_mm', 0.0)
                et0 = day.get('et0_mm', 0.0)
                temp = day.get('temp_c', 15.0)
                stage = self._get_growth_stage(day_idx)
                etc = self._calculate_crop_et(et0, stage)

                runoff = precip * 0.15
                effective_rain = max(0.0, precip - runoff)

                current_water += effective_rain

                deep_percolation = 0.0
                if current_water > self.TAW_mm:
                    deep_percolation = current_water - self.TAW_mm
                    current_water = self.TAW_mm

                irrigation_applied = 0.0
                if irrigation_enabled:
                    water_ratio = _safe_div(current_water, self.TAW_mm, 1.0)
                    if water_ratio < (1 - self.p_upper):
                        deficit = (1 - self.p_upper) * self.TAW_mm - current_water
                        irrigation_applied = min(deficit, irrigation_mm_per_day)
                        current_water += irrigation_applied
                        total_irrigation_mm += irrigation_applied

                ks = self._calculate_water_stress_ks(_safe_div(current_water, self.TAW_mm, 1.0))
                actual_etc = etc * ks

                current_water = max(0.0, current_water - actual_etc)

                cc = self._canopy_cover_dynamics(day_idx)
                kcb = get_crop_kc(self.crop_type, 'mid') if stage in ('development', 'mid') else get_crop_kc(self.crop_type, stage)
                daily_biomass = self._biomass_accumulation(et0, kcb, ks, cc)

                results.append({
                    'day_index': day_idx,
                    'date': day.get('date', f'D{day_idx}'),
                    'growth_stage': stage,
                    'precip_mm': round(precip, 2),
                    'runoff_mm': round(runoff, 2),
                    'et0_mm': round(et0, 2),
                    'etc_potential_mm': round(etc, 2),
                    'etc_actual_mm': round(actual_etc, 2),
                    'ks_stress_coeff': round(ks, 3),
                    'soil_water_mm': round(current_water, 2),
                    'deep_percolation_mm': round(deep_percolation, 2),
                    'irrigation_applied_mm': round(irrigation_applied, 2),
                    'canopy_cover': round(cc, 3),
                    'daily_biomass_kg_per_ha': round(daily_biomass, 2),
                })

            return results
        except Exception as e:
            return [{
                'day_index': i,
                'date': f'D{i}',
                'growth_stage': 'mid',
                'precip_mm': 0.0,
                'runoff_mm': 0.0,
                'et0_mm': 0.0,
                'etc_potential_mm': 0.0,
                'etc_actual_mm': 0.0,
                'ks_stress_coeff': 0.8,
                'soil_water_mm': self.TAW_mm * 0.5,
                'deep_percolation_mm': 0.0,
                'irrigation_applied_mm': 0.0,
                'canopy_cover': 0.5,
                'daily_biomass_kg_per_ha': 20.0,
            } for i in range(len(daily_data) if daily_data else 90)]

    def _calculate_water_stress_ks(self, soil_water_ratio: float) -> float:
        try:
            ks_upper = self.stress_params['Ks_upper_pct']
            ks_lower = self.stress_params['Ks_lower_pct']

            ratio = _clamp(soil_water_ratio, 0.0, 1.0)

            if ratio >= ks_upper:
                return 1.0
            elif ratio <= ks_lower:
                return 0.05
            else:
                ks = (ratio - ks_lower) / (ks_upper - ks_lower)
                return _clamp(ks, 0.05, 1.0)
        except Exception:
            return 0.8

    def _canopy_cover_dynamics(self, day_of_season: int, kcb: float = 1.0) -> float:
        try:
            CGC = self.constants['canopy_growth_coeff']
            CDC = self.constants['canopy_decay_coeff']
            CCx = 0.90

            dev_start = self.length_init
            mid_start = dev_start + self.length_dev
            late_start = mid_start + self.length_mid

            if day_of_season < dev_start:
                cc = 0.05 + (0.15 - 0.05) * (day_of_season / max(1, self.length_init))
            elif day_of_season < mid_start:
                t = day_of_season - dev_start
                cc = CCx * (1 - 0.05 / CCx * _safe_exp(-CGC * t))
            elif day_of_season < late_start:
                cc = CCx
            else:
                t = day_of_season - late_start
                cc = CCx * _safe_exp(-CDC * t)
                cc = max(cc, 0.10)

            return _clamp(cc, 0.0, 1.0)
        except Exception:
            return 0.5

    def _biomass_accumulation(self, et0: float, kcb: float, ks: float, cc: float) -> float:
        try:
            term1 = ks * kcb * et0
            term2 = 1.0 - _safe_exp(-0.65 * cc * max(kcb, 0.1))
            biomass = self.WP * term1 * max(term2, 0.0)
            return _clamp(biomass, 0.0, 200.0)
        except Exception:
            return 10.0

    def run_full_simulation(self,
                            precipitation_mm_per_day: List[float],
                            et0_mm_per_day: List[float],
                            temperatures_c: List[float],
                            irrigation_capability_m3_per_day: float = 0.0,
                            irrigation_area_mu: float = 100.0,
                            historical_baseline_yield_kg_per_mu: float = None) -> Dict:
        try:
            n_days = min(len(precipitation_mm_per_day), len(et0_mm_per_day), len(temperatures_c))
            n_days = min(n_days, self.total_growing_days)

            daily_data = []
            for i in range(n_days):
                daily_data.append({
                    'date': f'D{i+1:03d}',
                    'precip_mm': precipitation_mm_per_day[i],
                    'et0_mm': et0_mm_per_day[i],
                    'temp_c': temperatures_c[i],
                })

            for i in range(n_days, self.total_growing_days):
                avg_precip = sum(precipitation_mm_per_day[:n_days]) / max(1, n_days)
                avg_et0 = sum(et0_mm_per_day[:n_days]) / max(1, n_days)
                avg_temp = sum(temperatures_c[:n_days]) / max(1, n_days)
                daily_data.append({
                    'date': f'D{i+1:03d}',
                    'precip_mm': avg_precip + (random.random() - 0.5) * avg_precip * 0.3,
                    'et0_mm': avg_et0 + (random.random() - 0.5) * avg_et0 * 0.2,
                    'temp_c': avg_temp + (random.random() - 0.5) * 3.0,
                })

            n_days = self.total_growing_days
            initial_water = self.TAW_mm * 0.6

            results_no_irrig = self._simulate_soil_water_balance(
                daily_data, initial_water, irrigation_enabled=False
            )
            results_with_irrig = self._simulate_soil_water_balance(
                daily_data, initial_water,
                irrigation_enabled=True,
                irrigation_capability_m3_per_day=irrigation_capability_m3_per_day,
                irrigation_area_mu=irrigation_area_mu,
            )

            total_biomass_no = sum(r['daily_biomass_kg_per_ha'] for r in results_no_irrig)
            total_biomass_with = sum(r['daily_biomass_kg_per_ha'] for r in results_with_irrig)

            baseline_yield = historical_baseline_yield_kg_per_mu
            if baseline_yield is None:
                baseline_yield = 100.0

            biomass_to_yield_factor = _safe_div(baseline_yield, (total_biomass_no / 15.0) * self.harvest_index, 1.0)
            biomass_to_yield_factor = _clamp(biomass_to_yield_factor, 0.5, 3.0)

            yield_no_irrigation = (total_biomass_no / 15.0) * self.harvest_index * biomass_to_yield_factor
            yield_with_irrigation = (total_biomass_with / 15.0) * self.harvest_index * biomass_to_yield_factor

            irrigation_gain_factor = get_irrigation_gain(self.crop_type, 11)
            expected_yield_with = baseline_yield * (1 + irrigation_gain_factor)
            weight_model = 0.6
            weight_factor = 0.4
            yield_with_irrigation = (yield_with_irrigation * weight_model
                                     + expected_yield_with * weight_factor)
            yield_no_irrigation = baseline_yield * 0.92

            yield_no_irrigation = _clamp(yield_no_irrigation, baseline_yield * 0.5, baseline_yield * 1.1)
            yield_with_irrigation = _clamp(yield_with_irrigation, baseline_yield * 0.8, baseline_yield * 2.0)

            yield_increase_rate = _safe_div(
                yield_with_irrigation - yield_no_irrigation,
                yield_no_irrigation, 0.0
            )
            yield_increase_rate = _clamp(yield_increase_rate, 0.0, 1.0)

            total_irrig_mm = sum(r['irrigation_applied_mm'] for r in results_with_irrig)
            area_m2 = max(irrigation_area_mu, 1.0) * 666.67
            total_water_applied_m3 = (total_irrig_mm / 1000.0) * area_m2

            yield_increase_kg_per_mu = yield_with_irrigation - yield_no_irrigation
            total_yield_increase_kg = yield_increase_kg_per_mu * max(irrigation_area_mu, 1.0)
            water_use_efficiency = _safe_div(total_yield_increase_kg, max(total_water_applied_m3, 1.0), 0.0)
            water_use_efficiency = _clamp(water_use_efficiency, 0.0, 10.0)

            markers = {
                'initial_stage_end': self.length_init,
                'development_stage_end': self.length_init + self.length_dev,
                'mid_stage_end': self.length_init + self.length_dev + self.length_mid,
                'late_stage_end': self.total_growing_days,
                'total_days': self.total_growing_days,
            }

            daily_results_combined = []
            for i in range(n_days):
                r_no = results_no_irrig[i] if i < len(results_no_irrig) else {}
                r_with = results_with_irrig[i] if i < len(results_with_irrig) else {}
                daily_results_combined.append({
                    'day': i + 1,
                    'no_irrigation': r_no,
                    'with_irrigation': r_with,
                })

            return {
                'yield_without_irrigation_kg_per_mu': round(yield_no_irrigation, 2),
                'yield_with_irrigation_kg_per_mu': round(yield_with_irrigation, 2),
                'yield_increase_rate': round(yield_increase_rate, 4),
                'total_water_applied_m3': round(total_water_applied_m3, 1),
                'water_use_efficiency_kg_per_m3': round(water_use_efficiency, 4),
                'daily_results': daily_results_combined,
                'growth_stages_markers': markers,
                'total_biomass_no_irrigation_kg_per_ha': round(total_biomass_no, 1),
                'total_biomass_with_irrigation_kg_per_ha': round(total_biomass_with, 1),
                'harvest_index': self.harvest_index,
            }
        except Exception as e:
            baseline = historical_baseline_yield_kg_per_mu or 100.0
            gain = get_irrigation_gain(self.crop_type, 11)
            return {
                'yield_without_irrigation_kg_per_mu': round(baseline * 0.92, 2),
                'yield_with_irrigation_kg_per_mu': round(baseline * (1 + gain), 2),
                'yield_increase_rate': round(gain, 4),
                'total_water_applied_m3': round(irrigation_capability_m3_per_day * 60, 1),
                'water_use_efficiency_kg_per_m3': 1.5,
                'daily_results': [],
                'growth_stages_markers': {
                    'initial_stage_end': self.length_init,
                    'development_stage_end': self.length_init + self.length_dev,
                    'mid_stage_end': self.length_init + self.length_dev + self.length_mid,
                    'late_stage_end': self.total_growing_days,
                    'total_days': self.total_growing_days,
                },
                'degraded': True,
                'error': str(e),
            }


# ==============================================
# 农业影响分析器
# ==============================================

class AgriculturalImpactAnalyzer:
    """农业影响综合评估分析器
    整合AquaCrop模型、受益区生成、农户估算等功能
    """

    def __init__(self):
        self._model_cache: Dict[str, AquaCropSimplifiedModel] = {}

    def _get_model(self, crop_type: str, region: str) -> AquaCropSimplifiedModel:
        key = f"{crop_type}|{region}"
        if key not in self._model_cache:
            self._model_cache[key] = AquaCropSimplifiedModel(crop_type, region)
        return self._model_cache[key]

    def _load_site_context(self, db: Session, site_id: int) -> Dict:
        try:
            site = db.query(WaterHeritageSite).filter(WaterHeritageSite.id == site_id).first()
            if not site:
                return {}

            restoration = db.query(FunctionalRestoration).filter(
                FunctionalRestoration.site_id == site_id
            ).first()

            dynasty = db.query(DynastyDict).filter(
                DynastyDict.order == site.dynasty_order
            ).first()

            idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
            region = REGIONS[idx]

            return {
                'site': site,
                'restoration': restoration,
                'dynasty': dynasty,
                'region': region,
                'site_id': site_id,
                'site_name': site.name,
                'dynasty_order': site.dynasty_order,
                'site_type': site.site_type,
                'longitude': site.longitude,
                'latitude': site.latitude,
                'preservation_status': site.preservation_status,
                'recorded_irrigation_area': site.irrigation_area,
                'actual_irrigation_capacity_mu': (
                    restoration.actual_irrigation_capacity if restoration else site.irrigation_area
                ),
                'original_irrigation_capacity_mu': (
                    restoration.original_irrigation_capacity if restoration else site.irrigation_area * 1.2
                ),
            }
        except Exception as e:
            return {'error': str(e)}

    def _select_dominant_crops(self, region: str, dynasty_order: int,
                               site_type: str) -> List[str]:
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

    def _generate_historical_climate_series(self, region: str, dynasty_order: int,
                                            growing_days: int) -> Dict[str, List[float]]:
        try:
            climate = _safe_get_regional_climate(region)

            avg_temp = climate.get('avg_temp_c', 15.0)
            temp_amp = climate.get('seasonal_temp_amp', 12.0)
            annual_precip = climate.get('annual_precipitation_mm', 800.0)
            avg_et0 = climate.get('avg_et0_mm_per_day', 3.5)

            db = None
            try:
                from common.database import SessionLocal
                db = SessionLocal()
                dynasty = db.query(DynastyDict).filter(DynastyDict.order == dynasty_order).first()
                if dynasty:
                    hydro_list = db.query(PaleoHydrologyData).filter(
                        PaleoHydrologyData.region == region,
                        PaleoHydrologyData.year >= dynasty.start_year,
                        PaleoHydrologyData.year <= dynasty.end_year,
                    ).limit(30).all()
                    if hydro_list:
                        avg_rainfall = sum(h.rainfall for h in hydro_list) / len(hydro_list)
                        annual_precip = avg_rainfall
                        if hydro_list[0].temperature:
                            avg_temp = sum(h.temperature for h in hydro_list if h.temperature) / max(1, sum(1 for h in hydro_list if h.temperature))
                db.close()
            except Exception:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

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

    def _generate_benefit_zones(self, site: WaterHeritageSite,
                                irrigation_area_mu: float,
                                yield_increase_rate: float) -> Tuple[Dict, bytes]:
        try:
            lon = site.longitude
            lat = site.latitude

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

            features = []
            polygons = {}

            for zone_name, zone_ratio, zone_label in zones_config:
                r = radius_deg * zone_ratio * zone_multiplier
                n_points = 48
                noise_amp = 0.12

                points = []
                for i in range(n_points):
                    angle = 2 * math.pi * i / n_points
                    noise = 1.0 + (random.random() - 0.5) * 2.0 * noise_amp
                    r_i = r * noise
                    x = lon + r_i * math.cos(angle)
                    y = lat + r_i * math.sin(angle) / math.cos(math.radians(lat))
                    points.append((x, y))
                points.append(points[0])

                poly = Polygon(points)
                polygons[zone_name] = poly

                features.append({
                    'type': 'Feature',
                    'properties': {
                        'zone_type': zone_name,
                        'zone_label': zone_label,
                        'site_id': site.id,
                        'site_name': site.name,
                        'yield_increase_rate': round(yield_increase_rate * (1.0 if zone_name == 'core' else 0.75 if zone_name == 'radiating' else 0.5), 4),
                        'color': yield_colors[zone_name],
                        'area_mu': round(irrigation_area_mu * (zone_ratio ** 2), 1),
                    },
                    'geometry': mapping(poly),
                })

            geojson = {
                'type': 'FeatureCollection',
                'features': features,
                'metadata': {
                    'site_id': site.id,
                    'site_name': site.name,
                    'total_influenced_area_mu': round(irrigation_area_mu, 1),
                    'yield_increase_rate': round(yield_increase_rate, 4),
                    'generation_method': 'radius_based_noise',
                }
            }

            outer_poly = polygons['marginal']
            try:
                wkb_bytes = from_shape(outer_poly, srid=4326).data
            except Exception:
                wkb_bytes = b''

            return geojson, wkb_bytes
        except Exception as e:
            empty_geojson = {'type': 'FeatureCollection', 'features': [], 'metadata': {'error': str(e)}}
            return empty_geojson, b''

    def _estimate_farmers_benefited(self, region: str, influenced_area_mu: float) -> int:
        try:
            density = FARMER_DENSITY_PER_MU.get(region, 5.0)
            people_count = influenced_area_mu * density / 100.0
            household_count = int(people_count / 5.0)
            return max(10, household_count)
        except Exception:
            return max(10, int(influenced_area_mu * 0.05))

    def analyze_site_impact(self, db: Session, site_id: int,
                            crop_types: List[str] = None,
                            scenario: str = 'typical') -> Optional['AgriculturalImpactAssessment']:
        from common.models import AgriculturalImpactAssessment as AIAModel

        try:
            context = self._load_site_context(db, site_id)
            if not context or 'site' not in context:
                return None

            site = context['site']
            region = context['region']
            dynasty_order = context['dynasty_order']
            irrigation_area_mu = context['actual_irrigation_capacity_mu']

            if crop_types is None or len(crop_types) == 0:
                crop_types = self._select_dominant_crops(region, dynasty_order, site.site_type)

            restoration = context.get('restoration')
            irrigation_capability_m3_per_day = 0.0
            if restoration and restoration.actual_irrigation_capacity:
                area_m2 = max(restoration.actual_irrigation_capacity, 0.1) * 666.67
                irrigation_capability_m3_per_day = (area_m2 * 50.0) / 1000.0 / 30.0
                irrigation_capability_m3_per_day = _clamp(irrigation_capability_m3_per_day, 0.0, 10000.0)

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
                return None

            avg_yield_no = weighted_yield_no / total_weight
            avg_yield_with = weighted_yield_with / total_weight
            avg_wue = weighted_wue / total_weight
            avg_water = weighted_water / total_weight

            yield_increase_rate = _safe_div(avg_yield_with - avg_yield_no, avg_yield_no, 0.0)
            yield_increase_rate = _clamp(yield_increase_rate, 0.0, 1.0)

            yield_increase_kg_per_mu = avg_yield_with - avg_yield_no
            total_influenced_area = max(irrigation_area_mu, 1.0)
            annual_yield_increase_kg = yield_increase_kg_per_mu * total_influenced_area

            benefit_zone_geojson, benefit_zone_wkb = self._generate_benefit_zones(
                site, total_influenced_area, yield_increase_rate
            )

            farmers_count = self._estimate_farmers_benefited(region, total_influenced_area)

            confidence = 100.0
            if not restoration:
                confidence -= 15
            if len(crop_results) < 3:
                confidence -= 10
            if irrigation_area_mu != site.irrigation_area:
                confidence -= 5
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

            existing = db.query(AIAModel).filter(AIAModel.site_id == site_id).first()

            if existing:
                existing.dominant_crop = dominant_crop
                existing.total_influenced_area_mu = round(total_influenced_area, 4)
                existing.yield_increase_rate = round(yield_increase_rate, 4)
                existing.annual_yield_increase_kg = round(annual_yield_increase_kg, 4)
                existing.farmers_benefited_count = farmers_count
                existing.water_use_efficiency_kg_per_m3 = round(avg_wue, 4)
                existing.yield_simulation_raw = simulation_raw
                existing.benefit_zone_geojson = benefit_zone_geojson
                existing.confidence_score = round(confidence, 4)
                assessment = existing
            else:
                assessment = AIAModel(
                    site_id=site_id,
                    dominant_crop=dominant_crop,
                    total_influenced_area_mu=round(total_influenced_area, 4),
                    yield_increase_rate=round(yield_increase_rate, 4),
                    annual_yield_increase_kg=round(annual_yield_increase_kg, 4),
                    farmers_benefited_count=farmers_count,
                    water_use_efficiency_kg_per_m3=round(avg_wue, 4),
                    yield_simulation_raw=simulation_raw,
                    benefit_zone_geojson=benefit_zone_geojson,
                    confidence_score=round(confidence, 4),
                )
                db.add(assessment)

            db.commit()
            db.refresh(assessment)

            return assessment
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def analyze_batch(self, db: Session, region: str = None,
                      site_ids: List[int] = None) -> List[int]:
        try:
            query = db.query(WaterHeritageSite)
            if site_ids and len(site_ids) > 0:
                query = query.filter(WaterHeritageSite.id.in_(site_ids))
            sites = query.all()

            success_ids = []
            for site in sites:
                try:
                    result = self.analyze_site_impact(db, site.id)
                    if result:
                        success_ids.append(site.id)
                except Exception:
                    continue
            return success_ids
        except Exception:
            return []
