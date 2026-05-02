"""BaseConfig — 模块配置加载器"""
import os
from pathlib import Path
from typing import Any, Optional, TypeVar
import yaml

T = TypeVar("T", bound="BaseConfig")

class BaseConfig:
    DEFAULTS: dict = {}
    _cache: Optional[dict] = None

    @classmethod
    def load(cls, harness_root: Optional[Path] = None) -> dict:
        if cls._cache:
            return cls._cache
        base = cls.DEFAULTS.copy()
        path = cls._config_path(harness_root)
        if path and path.exists():
            with open(path) as f:
                user = yaml.safe_load(f) or {}
            base = cls._merge(base, user)
        base = cls._apply_env(base)
        cls._cache = base
        return base

    @classmethod
    def _config_path(cls, harness_root) -> Optional[Path]:
        return None

    @classmethod
    def _merge(cls, base: dict, override: dict) -> dict:
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = cls._merge(result[k], v)
            else:
                result[k] = v
        return result

    @classmethod
    def _apply_env(cls, cfg: dict) -> dict:
        for key in list(cfg.keys()):
            env_key = f"{cls._env_prefix()}_{key.upper()}"
            if env_key in os.environ:
                cfg[key] = os.environ[env_key]
        return cfg

    @classmethod
    def _env_prefix(cls) -> str:
        return "CHK"
