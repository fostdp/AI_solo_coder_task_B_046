"""
网络效应分析工具函数
提供距离计算、高程估算、统计计算等通用工具
"""
import math
from typing import List, Dict, Any, Optional

from common.params.network_params import REGION_WATERSHEDS


def haversine_distance_km(lon1: float, lat1: float,
                          lon2: float, lat2: float) -> float:
    """
    计算两点之间的哈弗辛距离（公里）

    Args:
        lon1: 点1经度
        lat1: 点1纬度
        lon2: 点2经度
        lat2: 点2纬度

    Returns:
        两点之间的距离（公里）
    """
    R = 6371.0
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def get_approx_elevation(site: Any, region: str) -> float:
    """
    根据遗址位置和区域水系信息估算近似高程

    Args:
        site: 遗址对象（需包含 longitude, latitude 属性）
        region: 区域名称

    Returns:
        估算高程（米）
    """
    watershed_info = REGION_WATERSHEDS.get(region, REGION_WATERSHEDS['中原地区'])
    elev_range = watershed_info.get('elevation_range_m', [50, 500])
    avg_slope = watershed_info.get('avg_slope_pct', 1.0)
    base_elev = elev_range[0]
    lon_factor = (site.longitude - 100.0) * 10.0
    lat_factor = (40.0 - site.latitude) * 20.0
    elev = base_elev + abs(lon_factor) * avg_slope + abs(lat_factor) * avg_slope
    return max(elev_range[0], min(elev_range[1], elev))


def is_downstream_flow(s1: Any, s2: Any, region: str) -> bool:
    """
    判断两个遗址是否符合下游水流方向

    Args:
        s1: 遗址1
        s2: 遗址2
        region: 区域名称

    Returns:
        是否符合下游流向
    """
    if region in ('江南地区', '岭南地区', '巴蜀地区', '滇黔地区'):
        return s1.longitude <= s2.longitude
    else:
        return s1.latitude >= s2.latitude


def percentile(values: List[float], p: float) -> float:
    """
    计算百分位数（带数值保护）

    Args:
        values: 数值列表
        p: 百分位数（0-100）

    Returns:
        百分位数值
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return sorted_vals[f]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1


def compute_stats(values: List[float]) -> Dict[str, float]:
    """
    计算统计量：均值、标准差、百分位数

    Args:
        values: 数值列表

    Returns:
        统计量字典 {mean, std, p5, p50, p95}
    """
    n = len(values)
    if n == 0:
        return {'mean': 0.0, 'std': 0.0, 'p5': 0.0, 'p50': 0.0, 'p95': 0.0}
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / max(1, n)
    std = math.sqrt(var)
    return {
        'mean': round(mean, 6),
        'std': round(std, 6),
        'p5': round(percentile(values, 5), 6),
        'p50': round(percentile(values, 50), 6),
        'p95': round(percentile(values, 95), 6),
    }


def text_contains_hydrology_keyword(text: str, keywords: List[str]) -> bool:
    """
    检查文本是否包含水文关键词

    Args:
        text: 待检查文本
        keywords: 水文关键词列表

    Returns:
        是否包含关键词
    """
    if not text:
        return False
    for kw in keywords:
        if kw in text:
            return True
    return False
