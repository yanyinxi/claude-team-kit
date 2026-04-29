"""
全维度自我进化系统 - 核心入口

让 .claude 目录"越用越聪明"的进化引擎。
"""

__version__ = "1.0.0"
__author__ = "Claude Self-Evolution System"

from .engine import EvolutionEngine
from .config import EvolutionConfig

__all__ = ["EvolutionEngine", "EvolutionConfig"]
