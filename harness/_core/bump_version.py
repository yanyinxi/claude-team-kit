#!/usr/bin/env python3
"""智能版本管理系统 - 自动分析变更类型"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

VERSION_JSON = Path(__file__).parent / "version.json"
CHANGELOG_FILE = Path(__file__).parent.parent.parent / "CHANGELOG.md"

# 需要同步版本的文件（统一从 version.json 读取）
UPDATE_FILES = [
    "package.json",
    "index.js",
    ".claude-plugin/plugin.json",
    "harness/marketplace.json",
    ".claude-plugin/marketplace.json",
]

VERSION_TYPES = {
    "patch": {"emoji": "🔧", "description": "Bug fixes"},
    "minor": {"emoji": "✨", "description": "New features"},
    "major": {"emoji": "💥", "description": "Breaking changes"},
}

def read_version() -> dict:
    if not VERSION_JSON.exists():
        return {"version": "0.0.0", "version_info": [0, 0, 0], "name": "unknown"}
    return json.loads(VERSION_JSON.read_text())

def write_version(data: dict):
    VERSION_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

def get_git_diff_count() -> int:
    """获取自上次 tag 后的提交数"""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, cwd=VERSION_JSON.parent.parent.parent
        )
        last_tag = result.stdout.strip()
        if last_tag:
            count = subprocess.run(
                ["git", "rev-list", f"{last_tag}..HEAD", "--count"],
                capture_output=True, text=True, cwd=VERSION_JSON.parent.parent.parent
            )
            return int(count.stdout.strip()) if count.returncode == 0 else 0
    except Exception:
        pass
    return 0

def analyze_commits() -> dict:
    """分析 git 提交，自动判断版本类型"""
    root = VERSION_JSON.parent.parent.parent

    try:
        # 获取最近10条提交
        result = subprocess.run(
            ["git", "log", "-10", "--pretty=format:%s"],
            capture_output=True, text=True, cwd=root
        )
        commits = result.stdout.strip().split("\n") if result.returncode == 0 else []

        has_breaking = any(w in c.lower() for c in commits for w in ["break", "major", "破坏"])
        has_feature = any(w in c.lower() for c in commits for w in ["feat", "feature", "new", "功能"])
        has_fix = any(w in c.lower() for c in commits for w in ["fix", "bug", "修复"])

        if has_breaking:
            return {"type": "major", "reason": "Breaking changes detected in commits"}
        if has_feature:
            return {"type": "minor", "reason": "New features detected in commits"}
        if has_fix:
            return {"type": "patch", "reason": "Bug fixes detected in commits"}

    except Exception:
        pass

    return {"type": "patch", "reason": "Default: patch update"}

def update_file(path: Path, old_ver: str, new_ver: str):
    if not path.exists():
        print(f"  [SKIP] {path} not found")
        return
    content = path.read_text()
    if old_ver in content:
        path.write_text(content.replace(old_ver, new_ver))
        print(f"  [UPDATE] {path}")

def generate_changelog(old_ver: str, new_ver: str, version_type: str) -> str:
    """生成 changelog 条目"""
    root = VERSION_JSON.parent.parent.parent
    date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = subprocess.run(
            ["git", "log", f"{old_ver}..HEAD", "--oneline"],
            capture_output=True, text=True, cwd=root
        )
        commits = result.stdout.strip().split("\n") if result.returncode == 0 else []
        commits = [c for c in commits if c][:10]
    except Exception:
        commits = []

    changes = "\n".join(f"- {c}" for c in commits) if commits else "- (no commits)"

    return f"""## {new_ver} ({date}) {VERSION_TYPES[version_type]['emoji']}

**Type:** {version_type} - {VERSION_TYPES[version_type]['description']}

### Changes
{changes}

"""

def smart_bump(force_type: str = None) -> dict:
    """智能升级版本"""
    data = read_version()
    old_ver = data["version"]
    major, minor, patch = data["version_info"]

    if force_type:
        version_type = force_type
        reason = f"Manual: {force_type} forced"
    else:
        analysis = analyze_commits()
        version_type = analysis["type"]
        reason = analysis["reason"]

    if version_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif version_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    new_ver = f"{major}.{minor}.{patch}"
    data["version"] = new_ver
    data["version_info"] = [major, minor, patch]
    data["last_bump"] = datetime.now().isoformat()
    data["last_type"] = version_type

    return {
        "old_ver": old_ver,
        "new_ver": new_ver,
        "type": version_type,
        "reason": reason,
        "data": data
    }

def main():
    data = read_version()
    old_ver = data.get("version", "0.0.0")

    if len(sys.argv) < 2:
        print(f"📦 Current version: {old_ver}")
        print(f"\n📖 Usage:")
        print(f"  python bump_version.py auto      # Auto-detect (smart)")
        print(f"  python bump_version.py patch     # Bug fixes")
        print(f"  python bump_version.py minor     # New features")
        print(f"  python bump_version.py major     # Breaking changes")

        # 显示智能分析
        analysis = analyze_commits()
        print(f"\n🤖 Smart analysis:")
        print(f"  Suggested: {analysis['type']} ({analysis['reason']})")

        # 显示 git 统计
        diff_count = get_git_diff_count()
        if diff_count > 0:
            print(f"  Commits since last tag: {diff_count}")
        return

    arg = sys.argv[1].lower()
    if arg == "auto":
        result = smart_bump()
    elif arg in ["major", "minor", "patch"]:
        result = smart_bump(force_type=arg)
    else:
        print(f"Invalid: {arg}")
        sys.exit(1)

    old_ver = result["old_ver"]
    new_ver = result["new_ver"]
    version_type = result["type"]
    reason = result["reason"]
    data = result["data"]

    print(f"\n🚀 Version: {old_ver} → {new_ver}")
    print(f"   Type: {VERSION_TYPES[version_type]['emoji']} {version_type}")
    print(f"   Reason: {reason}")

    # 保存新版本
    write_version(data)
    print(f"\n📝 Updated version.json")

    # 更新其他文件
    print(f"\n📄 Updating files:")
    root = Path(__file__).parent.parent.parent
    for rel_path in UPDATE_FILES:
        update_file(root / rel_path, old_ver, new_ver)

    # 生成 changelog
    changelog_entry = generate_changelog(old_ver, new_ver, version_type)
    print(f"\n📒 Changelog entry:")
    print(changelog_entry)

    print(f"\n✅ Done: {new_ver}")

if __name__ == "__main__":
    main()