#!/usr/bin/env python3
"""
版本一致性检查器
在 git commit 前自动运行，确保所有文件的 version 字段一致
"""
import json
import subprocess
import sys
from pathlib import Path

# 从 version.json 读取标准版本
# bin -> hooks -> harness -> ROOT (4层向上)
SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parent.parent.parent.parent
VERSION_JSON = ROOT / "harness" / "_core" / "version.json"

# 如果找不到，尝试备用路径
if not VERSION_JSON.exists():
    VERSION_JSON = ROOT / "_core" / "version.json"

# 安全检查
if not VERSION_JSON.exists():
    print(f"❌ version.json not found at {VERSION_JSON}")
    sys.exit(1)

# 需要同步版本的文件
VERSION_FILES = [
    "package.json",
    "package-lock.json",
    "index.js",
    ".claude-plugin/plugin.json",
    "harness/marketplace.json",
    ".claude-plugin/marketplace.json",
]


def get_standard_version() -> str:
    """获取标准版本号"""
    if not VERSION_JSON.exists():
        print(f"❌ {VERSION_JSON} 不存在")
        sys.exit(1)
    data = json.loads(VERSION_JSON.read_text())
    return data.get("version", "unknown")


def get_file_version(path: Path) -> str | None:
    """从文件中提取 version 字段"""
    if not path.exists():
        return None
    try:
        content = path.read_text()
        def find_version(obj):
            if isinstance(obj, dict):
                if "version" in obj:
                    return obj["version"]
                # 搜索嵌套对象 (如 metadata.version)
                for key in ["metadata", "info", "package"]:
                    if key in obj and isinstance(obj[key], dict):
                        v = find_version(obj[key])
                        if v:
                            return v
            return None

        # JSON 文件 - 支持嵌套 version 字段
        if path.suffix == ".json":
            parsed = json.loads(content)
            return find_version(parsed)
        # JS 文件 - 查找 module.exports.version 或 exports.version
        elif path.suffix == ".js":
            import re
            # 匹配: module.exports.version = "x.x.x" 或 exports.version = "x.x.x"
            patterns = [
                r'module\.exports\.version\s*=\s*["\']([^"\']+)["\']',
                r'exports\.version\s*=\s*["\']([^"\']+)["\']',
                r'version:\s*["\']([^"\']+)["\']',
            ]
            for pattern in patterns:
                m = re.search(pattern, content)
                if m:
                    return m.group(1)
        return None
    except Exception:
        return None


def check_versions() -> bool:
    """检查所有文件的版本是否一致"""
    standard = get_standard_version()
    print(f"📦 标准版本: {standard}\n")

    mismatches = []
    for rel_path in VERSION_FILES:
        path = ROOT / rel_path
        ver = get_file_version(path)
        if ver is None:
            print(f"  ⚠️  {rel_path:<35} (文件不存在或无法解析)")
        elif ver == standard:
            print(f"  ✅ {rel_path:<35} v{ver}")
        else:
            print(f"  ❌ {rel_path:<35} v{ver} (应为 v{standard})")
            mismatches.append(rel_path)

    print()
    if mismatches:
        print(f"❌ 版本不一致！以下 {len(mismatches)} 个文件需要同步：")
        for f in mismatches:
            print(f"   - {f}")
        print(f"\n💡 运行以下命令修复：")
        print(f"   cd {ROOT}")
        print(f"   python harness/_core/bump_version.py auto")
        return False

    print("✅ 所有文件版本一致")
    return True


def main():
    # 检查是否是 git commit 操作
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, cwd=ROOT
    )
    if result.returncode != 0:
        sys.exit(0)

    if not check_versions():
        sys.exit(1)


if __name__ == "__main__":
    main()