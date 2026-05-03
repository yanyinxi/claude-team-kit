"""CHK 版本管理 - 从 version.json 读取"""
import json
from pathlib import Path

VERSION_JSON = Path(__file__).parent / "version.json"

def get_version() -> str:
    """获取当前版本"""
    if VERSION_JSON.exists():
        data = json.loads(VERSION_JSON.read_text())
        return data.get("version", "0.0.0")
    return "0.0.0"

def get_version_info() -> tuple:
    """获取版本信息 (major, minor, patch)"""
    if VERSION_JSON.exists():
        data = json.loads(VERSION_JSON.read_text())
        return tuple(data.get("version_info", [0, 0, 0]))
    return (0, 0, 0)

__version__ = get_version()
__version_info__ = get_version_info()