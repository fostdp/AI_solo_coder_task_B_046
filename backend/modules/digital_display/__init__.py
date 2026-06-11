"""
数字化展示与虚拟修复 - 数字展示独立模块
==========================================

纯算法模块，提供3D重建、深度学习图像增强、质量评估等核心能力。

模块结构：
- reconstruction: 3D重建核心引擎
- enhancement: 多视角融合与深度学习图像增强
- quality: 质量评估与保证
- utils: 通用工具函数

不依赖 FastAPI、SQLAlchemy、Redis 等框架。
"""

from .utils import (
    hash_seed,
    create_rng,
    grade_quality,
    safe_get,
    clamp,
)

from .reconstruction import (
    RECONSTRUCTION_STAGES,
    RECONSTRUCTION_METHODS,
    PhotoPreprocessor,
    FeatureExtractor,
    SparseToDenseReconstructor,
    ThreeDModelExporter,
    DigitalReconstructionPipeline,
)

from .enhancement import (
    EnhanceStrategy,
    SR_MODEL_PARAMS,
    DENOISE_MODEL_PARAMS,
    MultiViewReconstructionFusionEngine,
    DeepLearningImageEnhancer,
)

from .quality import (
    QualityGuaranteedReconstructor,
    assess_point_cloud_quality,
    assess_mesh_quality,
)

__all__ = [
    # utils
    "hash_seed",
    "create_rng",
    "grade_quality",
    "safe_get",
    "clamp",
    # reconstruction
    "RECONSTRUCTION_STAGES",
    "RECONSTRUCTION_METHODS",
    "PhotoPreprocessor",
    "FeatureExtractor",
    "SparseToDenseReconstructor",
    "ThreeDModelExporter",
    "DigitalReconstructionPipeline",
    # enhancement
    "EnhanceStrategy",
    "SR_MODEL_PARAMS",
    "DENOISE_MODEL_PARAMS",
    "MultiViewReconstructionFusionEngine",
    "DeepLearningImageEnhancer",
    # quality
    "QualityGuaranteedReconstructor",
    "assess_point_cloud_quality",
    "assess_mesh_quality",
]

__version__ = "1.0.0"
