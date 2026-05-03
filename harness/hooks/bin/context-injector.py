#!/usr/bin/env python3
"""
SessionStart Hook: 注入项目上下文 + 知识推荐。
读取 CLAUDE.md 和当前目录结构，为 AI 提供项目概况。
同时记录会话开始时间到 .claude/data/.session_start，
并调用知识推荐引擎，将推荐结果注入到上下文中。

设计原则:
  - 只读，不改文件（除 .session_start 用于性能追踪）
  - 轻量（< 50ms）
  - 输出精简摘要（< 200 tokens）
"""
import json
import os
import subprocess
import sys
from datetime import datetime
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


def record_session_start(root: Path):
    """记录会话开始时间，用于后续计算 duration"""
    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    session_start_file = data_dir / ".session_start"
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "mode": os.environ.get("CLAUDE_MODE", "solo"),
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
    }

    session_start_file.write_text(json.dumps(session_data, ensure_ascii=False))


def inject_knowledge_recommendations(root: Path):
    """
    调用知识推荐引擎，生成推荐并注入上下文。
    从环境变量读取当前 Skill/Agent 类型，生成针对性推荐。
    """
    recommender_path = root / "harness" / "knowledge" / "knowledge_recommender.py"

    # 从环境变量读取上下文
    skill = os.environ.get("CLAUDE_CURRENT_SKILL", "")
    agent = os.environ.get("CLAUDE_CURRENT_AGENT", "")
    mode = os.environ.get("CLAUDE_MODE", "solo")

    if not recommender_path.exists():
        return ""

    # 调用推荐引擎
    cmd = [sys.executable, str(recommender_path), "recommend"]
    if skill:
        cmd.extend(["--skill", skill])
    if agent:
        cmd.extend(["--agent", agent])
    cmd.extend(["--task", mode])  # 用 mode 作为默认任务上下文

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(root),
        )
        if result.returncode == 0 and result.stdout:
            try:
                data = json.loads(result.stdout)
                recommendations = data.get("recommendations", {})
                merged = recommendations.get("merged", [])

                if not merged:
                    return ""

                # 格式化为 Markdown 上下文
                context_parts = ["\n## Knowledge Recommendations\n"]
                for rec in merged[:5]:
                    type_icon = {
                        "pitfall": "⚠️",
                        "guideline": "📋",
                        "process": "📌",
                        "decision": "🏗️",
                        "model": "📐"
                    }.get(rec.get("type", ""), "📄")
                    context_parts.append(
                        f"- [{type_icon} **{rec['name']}**] "
                        f"_{rec['description'][:90]}_"
                    )
                    if rec.get("content_preview"):
                        preview = rec["content_preview"][:100]
                        context_parts.append(f"  > {preview}")

                return "\n".join(context_parts)
            except json.JSONDecodeError:
                pass
    except (subprocess.TimeoutExpired, OSError):
        pass

    return ""


def main():
    root = find_project_root()

    # 记录会话开始时间
    record_session_start(root)

    claude_md = read_claude_md(root)
    structure_hint = scan_project_structure(root)

    # 调用知识推荐引擎
    knowledge_context = inject_knowledge_recommendations(root)

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

    # 注入知识推荐
    if knowledge_context:
        print(knowledge_context)

    # 写状态到 stderr（不干扰 stdout 输出）
    print(json.dumps(context), file=sys.stderr)


if __name__ == "__main__":
    import json
    main()
