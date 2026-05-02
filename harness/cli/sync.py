#!/usr/bin/env python3
"""
kit sync — 从中央配置仓库同步团队共享规则。

用法:
  kit sync --from=https://github.com/team/claude-standards
  kit sync --from=./central-standards

同步内容:
  - rules/*.md → .claude/rules/
  - CLAUDE.md 团队片段 → 合并到项目 CLAUDE.md
  - repo-index.json 更新
"""
import argparse
import json
import os
import sys
from pathlib import Path


def find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def sync_from_local(source: Path, root: Path):
    """从本地目录同步"""
    rules_src = source / "rules"
    rules_dst = root / ".claude" / "rules"

    count = 0
    if rules_src.exists():
        rules_dst.mkdir(parents=True, exist_ok=True)
        for rule_file in rules_src.glob("*.md"):
            dst = rules_dst / rule_file.name
            dst.write_text(rule_file.read_text(encoding="utf-8"), encoding="utf-8")
            count += 1

    print(f"✅ 同步完成: {count} 条规则更新")

    # 同步团队 CLAUDE.md 片段
    team_claude = source / "CLAUDE.md"
    if team_claude.exists():
        snippet = team_claude.read_text(encoding="utf-8")
        snippet_path = root / ".claude" / "CLAUDE_TEAM.md"
        snippet_path.write_text(snippet, encoding="utf-8")
        print(f"✅ 团队 CLAUDE.md 片段已更新 → .claude/CLAUDE_TEAM.md")

    # 更新 repo-index
    index_src = source / "repo-index.json"
    if index_src.exists():
        index_dst = root / ".claude" / "repo-index.json"
        index_dst.write_text(index_src.read_text(encoding="utf-8"))
        print(f"✅ 仓库索引已更新")


def sync_from_git(url: str, root: Path):
    """从 Git 仓库同步"""
    import tempfile
    import subprocess

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, tmp],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"❌ 无法克隆仓库: {result.stderr}")
            sys.exit(1)

        sync_from_local(Path(tmp), root)


def main():
    parser = argparse.ArgumentParser(description="同步团队共享配置")
    parser.add_argument("--from", dest="source", required=True, help="中央配置仓库路径或 URL")
    args = parser.parse_args()

    source = args.source
    root = find_root()

    if source.startswith("http://") or source.startswith("https://") or source.startswith("git@"):
        sync_from_git(source, root)
    else:
        sync_from_local(Path(source).resolve(), root)


if __name__ == "__main__":
    main()
