#!/usr/bin/env python3
"""
SessionStart Hook: 注入项目上下文。
读取 CLAUDE.md 和当前目录结构，为 AI 提供项目概况。

设计原则:
  - 只读，不改文件
  - 轻量（< 50ms）
  - 输出精简摘要（< 200 tokens）
"""
import os
import sys
from pathlib import Path


def find_project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def read_claude_md(root: Path) -> str:
    """读取项目 CLAUDE.md，提取关键信息"""
    candidates = [
        root / "CLAUDE.md",
        root / ".claude" / "CLAUDE.md",
    ]
    for p in candidates:
        if p.exists():
            content = p.read_text(encoding="utf-8")
            # 只取前 50 行（包含项目概述和技术栈）
            lines = content.strip().split("\n")[:50]
            return "\n".join(lines)
    return ""


def scan_project_structure(root: Path) -> str:
    """快速扫描项目结构，生成精简目录树"""
    entries = []
    ignore = {".git", "node_modules", "__pycache__", ".idea", "dist", "build", "target"}

    try:
        items = sorted(root.iterdir())
        for item in items:
            if item.name.startswith(".") and item.name != ".claude":
                continue
            if item.name in ignore:
                continue
            if item.is_dir():
                sub_items = sorted(item.iterdir())[:5]
                sub = ", ".join(i.name for i in sub_items)
                entries.append(f"  {item.name}/ ({sub}...)")
            elif item.name.endswith((".json", ".xml", ".yml", ".yaml", ".toml")):
                entries.append(f"  {item.name}")
    except PermissionError:
        pass

    return "\n".join(entries[:20]) if entries else ""


def main():
    root = find_project_root()

    claude_md = read_claude_md(root)
    structure_hint = scan_project_structure(root)

    context = {
        "project_root": str(root),
        "has_claude_md": bool(claude_md),
        "structure_hint": structure_hint,
    }

    if not claude_md:
        print(json.dumps({"warning": "No CLAUDE.md found. Run `kit init` to generate one."}))
        return

    # 输出精简摘要到 stdout（Claude Code 会注入到 system prompt）
    print(f"# Project Context (auto-injected)\n")
    print(f"## Project Overview\n{claude_md[:800]}\n")
    if structure_hint:
        print(f"## Structure\n```\n{structure_hint}\n```")

    # 写状态到 stderr（不干扰 stdout 输出）
    print(json.dumps(context), file=sys.stderr)


if __name__ == "__main__":
    import json
    main()
