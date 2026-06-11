"""
农业影响评估模块 - 通用工具函数
数值收敛保护、统计计算、安全运算
"""
import math
from typing import List, Optional


# ==============================================
# 数值收敛保护
# ==============================================

def _safe_log(x: float, epsilon: float = 1e-10) -> float:
    """安全对数运算，避免输入<=0导致异常"""
    return math.log(max(x, epsilon))


def _safe_sqrt(x: float) -> float:
    """安全平方根运算，避免输入为负数"""
    return math.sqrt(max(x, 0.0))


def _safe_div(a: float, b: float, default: float = 0.0, epsilon: float = 1e-10) -> float:
    """安全除法运算，避免除零错误"""
    if abs(b) < epsilon:
        return default
    return a / b


def _clamp(val: float, min_val: float, max_val: float) -> float:
    """将数值限制在指定范围内"""
    return max(min_val, min(val, max_val))


def _safe_exp(x: float, max_val: float = 1e6) -> float:
    """安全指数运算，避免溢出"""
    try:
        result = math.exp(min(x, math.log(max_val)))
        return result
    except Exception:
        return max_val


def _is_valid_number(x: float) -> bool:
    """检查数值是否有效（非NaN、非Inf）"""
    try:
        return not (math.isnan(x) or math.isinf(x))
    except Exception:
        return False


# ==============================================
# 统计计算工具
# ==============================================

def _safe_mean(values: List[float], default: float = 0.0) -> float:
    """安全计算均值，过滤无效值"""
    valid = [v for v in values if _is_valid_number(v)]
    if len(valid) == 0:
        return default
    return sum(valid) / len(valid)


def _safe_std(values: List[float], default: float = 0.0) -> float:
    """安全计算标准差（样本标准差），过滤无效值"""
    valid = [v for v in values if _is_valid_number(v)]
    if len(valid) < 2:
        return default
    mean_v = sum(valid) / len(valid)
    variance = sum((v - mean_v) ** 2 for v in valid) / (len(valid) - 1)
    return _safe_sqrt(variance)


def _safe_percentile(values: List[float], pct: float, default: float = 0.0) -> float:
    """安全计算百分位数，使用线性插值"""
    valid = sorted([v for v in values if _is_valid_number(v)])
    if len(valid) == 0:
        return default
    if len(valid) == 1:
        return valid[0]
    pct = _clamp(pct, 0.0, 100.0)
    k = (len(valid) - 1) * (pct / 100.0)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return valid[f]
    d0 = valid[f] * (c - k)
    d1 = valid[c] * (k - f)
    return d0 + d1
