#!/usr/bin/env python3
"""版本更新脚本 - 自动更新所有版本文件"""
import sys
import re
from pathlib import Path

VERSION_FILE = Path(__file__).parent.parent / "_core" / "version.py"
VERSION_TEMPLATE = '''"""CHK 版本管理 - 单一信源"""
__version__ = "{version}"
__version_info__ = ({major}, {minor}, {patch})

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
    new_version = f"{{major}}.{{minor}}.{{patch}}"
    return new_version
'''

UPDATE_FILES = {
    "package.json": [
        ('"version": "', '"'),
    ],
    "index.js": [
        ("version: '", "'"),
    ],
    ".claude-plugin/plugin.json": [
        ('"version": "', '"'),
    ],
}

def read_version() -> tuple:
    """从 version.py 读取当前版本"""
    content = VERSION_FILE.read_text()
    match = re.search(r'__version_info__\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)', content)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return 0, 0, 0

def write_version(major: int, minor: int, patch: int):
    """更新 version.py"""
    version = f"{major}.{minor}.{patch}"
    content = VERSION_TEMPLATE.format(version=version, major=major, minor=minor, patch=patch)
    VERSION_FILE.write_text(content)
    print(f"Updated version.py -> {version}")

def update_file(path: Path, old_ver: str, new_ver: str):
    """更新单个文件中的版本号"""
    if not path.exists():
        print(f"  [SKIP] {path} not found")
        return
    content = path.read_text()
    if old_ver in content:
        new_content = content.replace(old_ver, new_ver)
        path.write_text(new_content)
        print(f"  [UPDATE] {path}")
    else:
        print(f"  [SKIP] {path} no change needed")

def main():
    if len(sys.argv) < 2:
        # 读取当前版本
        major, minor, patch = read_version()
        print(f"Current version: {major}.{minor}.{patch}")
        return

    part = sys.argv[1]  # major/minor/patch
    old_major, old_minor, old_patch = read_version()

    if part == "major":
        new_major, new_minor, new_patch = old_major + 1, 0, 0
    elif part == "minor":
        new_major, new_minor, new_patch = old_major, old_minor + 1, 0
    elif part == "patch":
        new_major, new_minor, new_patch = old_major, old_minor, old_patch + 1
    else:
        print(f"Invalid part: {part} (use major/minor/patch)")
        sys.exit(1)

    old_ver = f"{old_major}.{old_minor}.{old_patch}"
    # 写入新版本
    write_version(new_major, new_minor, new_patch)

    # 用计算出的新版本号
    new_ver = f"{new_major}.{new_minor}.{new_patch}"

    root = Path(__file__).parent.parent.parent
    print(f"\nUpdating files from {old_ver} to {new_ver}:")

    for rel_path in UPDATE_FILES:
        path = root / rel_path
        update_file(path, old_ver, new_ver)

    print(f"\nVersion bumped: {old_ver} -> {new_ver}")

if __name__ == "__main__":
    main()