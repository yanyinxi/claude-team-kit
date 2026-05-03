"""
ConfigLoader - 统一配置加载器

统一管理 CHK 项目的所有配置文件：
- package.json
- harness/_core/version.json
- .claude/settings.json / settings.local.json
- harness/evolve-daemon/config.yaml
- harness/hooks/hooks.json
- harness/.mcp.json
- harness/cli/modes/*.json
"""
import json
import os
from pathlib import Path
from typing import Any, Optional, Union
import yaml


class ConfigLoader:
    """统一配置加载器"""

    DEFAULTS = {
        "core": {
            "version": "0.0.0",
            "version_info": [0, 0, 0],
            "name": "claude-harness-kit"
        },
        "daemon": {
            "mode": "both",
            "scheduler_interval": "30 minutes",
            "run_on_startup": False
        },
        "hooks": {
            "hooks": {}
        },
        "cli": {},
        "settings": {},
        "package": {},
        "mcp": {}
    }

    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化配置加载器

        Args:
            project_root: 项目根目录，默认为当前文件所在目录的父级父级
        """
        if project_root is None:
            # 默认指向项目根目录 (harness/_core/ 的父级父级)
            self.project_root = Path(__file__).resolve().parent.parent.parent
        else:
            self.project_root = Path(project_root)
        self._cache: dict[str, dict] = {}
        self._version: Optional[str] = None

    def get_config(self, config_type: str, use_cache: bool = True) -> dict:
        """
        获取指定类型的配置

        Args:
            config_type: 配置类型 (core/daemon/hooks/cli/settings/package/mcp)
            use_cache: 是否使用缓存

        Returns:
            配置字典

        Raises:
            ValueError: 不支持的配置类型
            FileNotFoundError: 配置文件不存在
        """
        config_type = config_type.lower()
        if use_cache and config_type in self._cache:
            return self._cache[config_type]

        if config_type not in self.DEFAULTS:
            raise ValueError(f"Unsupported config type: {config_type}. "
                             f"Supported: {list(self.DEFAULTS.keys())}")

        loader_method = getattr(self, f"_load_{config_type}", None)
        if loader_method is None:
            raise ValueError(f"No loader for config type: {config_type}")

        config = loader_method()
        self._cache[config_type] = config
        return config

    def _load_core(self) -> dict:
        """加载核心版本配置"""
        version_path = self.project_root / "harness" / "_core" / "version.json"
        if not version_path.exists():
            return self.DEFAULTS["core"].copy()

        with open(version_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_daemon(self) -> dict:
        """加载守护进程配置"""
        config_path = self.project_root / "harness" / "evolve-daemon" / "config.yaml"
        if not config_path.exists():
            return self.DEFAULTS["daemon"].copy()

        with open(config_path, encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}
        # 提取 daemon 相关配置
        daemon_config = yaml_config.get("daemon", {})
        return daemon_config

    def _load_hooks(self) -> dict:
        """加载 Hooks 配置"""
        hooks_path = self.project_root / "harness" / "hooks" / "hooks.json"
        if not hooks_path.exists():
            return self.DEFAULTS["hooks"].copy()

        with open(hooks_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_cli(self) -> dict:
        """加载 CLI 模式配置"""
        modes_dir = self.project_root / "harness" / "cli" / "modes"
        if not modes_dir.exists():
            return self.DEFAULTS["cli"].copy()

        cli_config = {}
        if modes_dir.is_dir():
            for json_file in modes_dir.glob("*.json"):
                mode_name = json_file.stem
                try:
                    with open(json_file, encoding="utf-8") as f:
                        cli_config[mode_name] = json.load(f)
                except json.JSONDecodeError:
                    cli_config[mode_name] = {"error": "Invalid JSON"}

        return cli_config

    def _load_settings(self) -> dict:
        """加载 Claude Code 设置配置（支持本地覆盖）"""
        settings_path = self.project_root / ".claude" / "settings.json"
        local_path = self.project_root / ".claude" / "settings.local.json"

        result = {}
        # 加载默认设置
        if settings_path.exists():
            with open(settings_path, encoding="utf-8") as f:
                result = json.load(f) or {}

        # 本地覆盖
        if local_path.exists():
            with open(local_path, encoding="utf-8") as f:
                local = json.load(f) or {}
                result = self._merge(result, local)

        return result

    def _load_package(self) -> dict:
        """加载 package.json 配置"""
        package_path = self.project_root / "package.json"
        if not package_path.exists():
            return self.DEFAULTS["package"].copy()

        with open(package_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_mcp(self) -> dict:
        """加载 MCP 服务器配置"""
        mcp_path = self.project_root / "harness" / ".mcp.json"
        if not mcp_path.exists():
            return self.DEFAULTS["mcp"].copy()

        with open(mcp_path, encoding="utf-8") as f:
            return json.load(f)

    def _merge(self, base: dict, override: dict) -> dict:
        """深度合并两个字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result

    def validate_all(self) -> dict:
        """
        验证所有配置文件

        Returns:
            验证结果字典，包含每个配置类型的状态
        """
        results = {}
        for config_type in self.DEFAULTS.keys():
            try:
                config = self.get_config(config_type)
                results[config_type] = {
                    "status": "ok",
                    "path": self._get_config_path(config_type),
                    "exists": True,
                    "keys": list(config.keys()) if config else []
                }
            except FileNotFoundError:
                results[config_type] = {
                    "status": "missing",
                    "path": self._get_config_path(config_type),
                    "exists": False
                }
            except Exception as e:
                results[config_type] = {
                    "status": "error",
                    "path": self._get_config_path(config_type),
                    "error": str(e)
                }

        return results

    def _get_config_path(self, config_type: str) -> Optional[Path]:
        """获取配置文件的路径"""
        paths = {
            "core": self.project_root / "harness" / "_core" / "version.json",
            "daemon": self.project_root / "harness" / "evolve-daemon" / "config.yaml",
            "hooks": self.project_root / "harness" / "hooks" / "hooks.json",
            "cli": self.project_root / "harness" / "cli" / "modes",
            "settings": self.project_root / ".claude" / "settings.json",
            "package": self.project_root / "package.json",
            "mcp": self.project_root / "harness" / ".mcp.json"
        }
        return paths.get(config_type)

    def get_version(self) -> str:
        """
        获取 CHK 版本

        Returns:
            版本字符串，如 "0.6.1"
        """
        if self._version:
            return self._version

        # 优先从 package.json 获取版本
        try:
            package_config = self.get_config("package")
            version = package_config.get("version")
            if version:
                self._version = version
                return version
        except Exception:
            pass

        # 备选从 version.json 获取
        try:
            core_config = self.get_config("core")
            version = core_config.get("version")
            if version:
                self._version = version
                return version
        except Exception:
            pass

        return "0.0.0"

    def get_version_info(self) -> list[int]:
        """
        获取 CHK 版本信息

        Returns:
            版本号列表，如 [0, 6, 1]
        """
        try:
            core_config = self.get_config("core")
            return core_config.get("version_info", [0, 0, 0])
        except Exception:
            return [0, 0, 0]

    def reload(self, config_type: Optional[str] = None) -> None:
        """
        重新加载配置

        Args:
            config_type: 指定要重载的配置类型，None 表示全部
        """
        if config_type:
            config_type = config_type.lower()
            if config_type in self._cache:
                del self._cache[config_type]
            if config_type == "core" or config_type == "all":
                self._version = None
        else:
            self._cache.clear()
            self._version = None

    def get_cli_mode(self, mode_name: str) -> Optional[dict]:
        """
        获取指定 CLI 模式的配置

        Args:
            mode_name: 模式名称 (solo/team/ultra/ralph/ccg/auto/gc)

        Returns:
            模式配置字典，如果不存在返回 None
        """
        cli_config = self.get_config("cli")
        return cli_config.get(mode_name)

    def get_all_cli_modes(self) -> list[str]:
        """
        获取所有可用的 CLI 模式

        Returns:
            模式名称列表
        """
        cli_config = self.get_config("cli")
        return list(cli_config.keys())

    def get_daemon_config(self, key: str = None) -> Any:
        """
        获取守护进程配置

        Args:
            key: 配置键名，None 表示返回整个 daemon 配置

        Returns:
            配置值
        """
        daemon_config = self.get_config("daemon")
        if key is None:
            return daemon_config
        return daemon_config.get(key)

    def clear_cache(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        self._version = None

    def __repr__(self) -> str:
        return f"ConfigLoader(project_root={self.project_root})"


# 全局单例实例
_default_loader: Optional[ConfigLoader] = None


def get_loader(project_root: Optional[Path] = None) -> ConfigLoader:
    """
    获取全局配置加载器实例

    Args:
        project_root: 项目根目录

    Returns:
        ConfigLoader 实例
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = ConfigLoader(project_root)
    return _default_loader


def reload() -> None:
    """重新加载全局配置"""
    global _default_loader
    if _default_loader:
        _default_loader.reload()
    else:
        _default_loader = ConfigLoader()


# 便捷函数
def get_version() -> str:
    """获取 CHK 版本"""
    return get_loader().get_version()


def get_config(config_type: str) -> dict:
    """获取指定类型的配置"""
    return get_loader().get_config(config_type)


def validate_all() -> dict:
    """验证所有配置"""
    return get_loader().validate_all()