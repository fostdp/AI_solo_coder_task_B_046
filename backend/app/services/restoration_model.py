import math
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from shapely.geometry import Point, Polygon
from shapely.ops import transform
import json


class HydraulicRestorationModel:
    """
    古代水利工程功能复原模型
    基于工程结构参数和古代水文数据反推原始灌溉能力和供水范围
    """

    CROP_WATER_REQUIREMENT = 450.0
    IRRIGATION_EFFICIENCY = {
        '渠': 0.75,
        '堰': 0.70,
        '陂': 0.80,
        '塘': 0.65,
        '井': 0.50
    }

    PRESERVATION_FACTOR = {
        '完好': 0.95,
        '部分损毁': 0.55,
        '完全废弃': 0.10
    }

    TYPE_DIVERSION_COEFFICIENT = {
        '渠': 0.60,
        '堰': 0.50,
        '陂': 0.35,
        '塘': 0.25,
        '井': 0.08
    }

    def calculate_weir_flow(self, dam_height: float, weir_length: float = 50.0) -> float:
        if dam_height is None or dam_height <= 0:
            return 0.0
        Cd = 0.62
        g = 9.81
        h = max(dam_height * 0.7, 0.5)
        return Cd * (2.0 / 3.0) * math.sqrt(2 * g) * weir_length * (h ** 1.5)

    def calculate_canal_capacity(self, canal_length: float, dam_height: float = 2.0) -> float:
        if canal_length is None or canal_length <= 0:
            return 0.0
        width = 1.5 + math.sqrt(canal_length) * 0.3
        depth = max(0.5, (dam_height or 2.0) * 0.4)
        area = width * depth
        n = 0.03
        s = 0.0005
        hydraulic_radius = area / (width + 2 * depth)
        velocity = (1.0 / n) * (hydraulic_radius ** (2.0 / 3.0)) * (s ** 0.5)
        return area * velocity

    def calculate_reservoir_capacity(self, dam_height: float, irrigation_area: float) -> float:
        if dam_height is None or dam_height <= 0:
            return max(irrigation_area * 100, 1000.0)
        surface_area = irrigation_area * 80
        return (1.0 / 3.0) * dam_height * surface_area * (0.4 + 0.1 * dam_height / 10.0)

    def calculate_well_yield(self, irrigation_area: float) -> float:
        depth = 20.0 + irrigation_area * 2.0
        radius = 0.15
        k = 2.5
        h0 = depth * 0.8
        hw = depth * 0.5
        return (math.pi * k * (h0 ** 2 - hw ** 2)) / (math.log(1000.0 / radius) / 2.3026)

    def calculate_available_water(self, site_type: str, dam_height: Optional[float],
                                  canal_length: Optional[float], avg_runoff: float) -> float:
        annual_runoff_volume = avg_runoff * 10000.0

        if site_type == '渠':
            diversion = self.TYPE_DIVERSION_COEFFICIENT[site_type]
            canal_flow = self.calculate_canal_capacity(canal_length or 50, dam_height or 2)
            canal_annual = canal_flow * 86400 * 200
            return min(annual_runoff_volume * diversion, canal_annual)

        elif site_type == '堰':
            diversion = self.TYPE_DIVERSION_COEFFICIENT[site_type]
            weir_flow = self.calculate_weir_flow(dam_height or 5)
            weir_annual = weir_flow * 86400 * 180
            return min(annual_runoff_volume * diversion, weir_annual)

        elif site_type == '陂':
            reservoir_cap = self.calculate_reservoir_capacity(dam_height or 10, 1.0)
            diversion = self.TYPE_DIVERSION_COEFFICIENT[site_type]
            return min(annual_runoff_volume * diversion, reservoir_cap * 1.5)

        elif site_type == '塘':
            reservoir_cap = self.calculate_reservoir_capacity(dam_height or 5, 1.0)
            return reservoir_cap * 1.2

        elif site_type == '井':
            well_yield = self.calculate_well_yield(0.1)
            return well_yield * 86400 * 250

        return annual_runoff_volume * 0.3

    def calculate_irrigation_capacity(self, available_water: float, site_type: str,
                                      avg_rainfall: float) -> float:
        efficiency = self.IRRIGATION_EFFICIENCY.get(site_type, 0.6)
        net_rain = avg_rainfall * 0.6 * 10
        net_requirement = max(self.CROP_WATER_REQUIREMENT * 10 - net_rain,
                              self.CROP_WATER_REQUIREMENT * 5)
        effective_water = available_water * efficiency
        if net_requirement <= 0:
            return effective_water / 100
        return effective_water / net_requirement

    def generate_supply_polygon(self, lng: float, lat: float,
                                  irrigation_capacity: float,
                                  site_type: str) -> Dict[str, Any]:
        if irrigation_capacity <= 0:
            return None

        base_radius = math.sqrt(irrigation_capacity / math.pi) * 0.003
        type_factors = {'渠': 1.5, '堰': 1.0, '陂': 0.8, '塘': 0.6, '井': 0.3}
        radius = base_radius * type_factors.get(site_type, 1.0)
        radius = max(0.01, min(radius, 1.0))

        num_points = 24
        points = []
        for i in range(num_points):
            angle = 2 * math.pi * i / num_points
            noise = 0.75 + 0.5 * math.sin(angle * 3) * math.cos(angle * 2)
            r = radius * noise
            x = lng + r * math.cos(angle) / math.cos(math.radians(lat))
            y = lat + r * math.sin(angle)
            points.append((x, y))
        points.append(points[0])

        polygon = Polygon(points)
        geojson = {
            "type": "Polygon",
            "coordinates": [list(polygon.exterior.coords)]
        }
        return geojson

    def estimate_supply_population(self, irrigation_capacity: float) -> int:
        per_capita_food = 250.0
        grain_per_mu = 150.0
        total_grain = irrigation_capacity * grain_per_mu * 0.0015
        if total_grain <= 0:
            return 0
        return int(total_grain / per_capita_food * 3)

    def restore_site(self, site: Any, hydrology_data: List[Any]) -> Dict[str, Any]:
        dynasty_order = site.dynasty_order

        filtered = [h for h in hydrology_data if
                    ((dynasty_order <= 4 and -770 <= h.year <= 220) or
                     (5 <= dynasty_order <= 9 and 220 < h.year <= 618) or
                     (10 <= dynasty_order <= 12 and 581 < h.year <= 960) or
                     (13 <= dynasty_order <= 14 and 960 < h.year <= 1279) or
                     (dynasty_order >= 15 and h.year > 1279))]

        if not filtered:
            filtered = hydrology_data[:50]

        avg_rainfall = np.mean([h.rainfall for h in filtered])
        avg_runoff = np.mean([h.runoff for h in filtered])

        available_water = self.calculate_available_water(
            site.site_type, site.dam_height, site.canal_length, avg_runoff
        )

        original_capacity = self.calculate_irrigation_capacity(
            available_water, site.site_type, avg_rainfall
        )

        preservation_factor = self.PRESERVATION_FACTOR.get(site.preservation_status, 0.3)
        actual_capacity = original_capacity * preservation_factor

        supply_polygon = self.generate_supply_polygon(
            site.longitude, site.latitude, original_capacity, site.site_type
        )

        supply_population = self.estimate_supply_population(original_capacity)

        notes_parts = []
        notes_parts.append(f"基于{len(filtered)}条同期水文记录重建")
        notes_parts.append(f"平均降雨量: {avg_rainfall:.1f}mm/年")
        notes_parts.append(f"平均径流量: {avg_runoff:.1f}万m³/km²")
        notes_parts.append(f"理论可用水量: {available_water:.1f}m³")
        if site.dam_height:
            notes_parts.append(f"坝高: {site.dam_height}m")
        if site.canal_length:
            notes_parts.append(f"渠长: {site.canal_length}km")
        notes = "；".join(notes_parts) + "。"

        return {
            "original_irrigation_capacity": round(max(0.1, original_capacity), 2),
            "actual_irrigation_capacity": round(max(0.0, actual_capacity), 2),
            "water_supply_range_geom": supply_polygon,
            "supply_population": max(0, supply_population),
            "restoration_notes": notes,
            "hydrology_summary": {
                "avg_rainfall": round(avg_rainfall, 1),
                "avg_runoff": round(avg_runoff, 1),
                "records_count": len(filtered)
            }
        }
