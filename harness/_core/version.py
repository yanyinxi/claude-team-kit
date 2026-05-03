"""CHK 版本管理 - 单一信源"""
__version__ = "0.4.0"
__version_info__ = (0, 4, 0)

def get_version() -> str:
    return __version__

def get_version_info() -> tuple:
    return __version_info__

def bump_version(part: str = "patch") -> str:
    """自动升级版本"""
    major, minor, patch = __version_info__
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    new_version = f"{major}.{minor}.{patch}"
    return new_version
