"""
数字化展示与虚拟修复 - 通用工具函数
提供哈希种子生成、质量分级等通用工具
"""
import hashlib
import random
from typing import Any


def hash_seed(identifier: str) -> int:
    """
    根据标识符生成可重复的随机数种子

    Args:
        identifier: 用于生成种子的标识字符串

    Returns:
        整数种子值
    """
    return int(hashlib.md5(identifier.encode()).hexdigest()[:8], 16)


def create_rng(identifier: str) -> random.Random:
    """
    根据标识符创建可重复的随机数生成器

    Args:
        identifier: 用于生成种子的标识字符串

    Returns:
        带种子的 Random 实例
    """
    seed = hash_seed(identifier)
    return random.Random(seed)


def grade_quality(score: float) -> str:
    """
    根据质量分数评定等级

    Args:
        score: 质量分数 (0-100)

    Returns:
        质量等级：优秀/良好/中等/合格/不合格
    """
    if score >= 90:
        return "优秀"
    elif score >= 80:
        return "良好"
    elif score >= 70:
        return "中等"
    elif score >= 60:
        return "合格"
    else:
        return "不合格"


def safe_get(d: dict, key: str, default: Any = None) -> Any:
    """
    安全获取字典值，支持嵌套键用点号分隔

    Args:
        d: 字典
        key: 键名，支持 "a.b.c" 形式
        default: 默认值

    Returns:
        对应的值或默认值
    """
    if not d:
        return default
    keys = key.split(".")
    current = d
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    将值限制在范围内

    Args:
        value: 输入值
        min_val: 最小值
        max_val: 最大值

    Returns:
        限制后的值
    """
    return max(min_val, min(max_val, value))
