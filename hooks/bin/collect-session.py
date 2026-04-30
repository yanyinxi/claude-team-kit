#!/usr/bin/env python3
"""
Stop Hook: 聚合本轮会话摘要，触成语义提取。

阶段 1: 元数据收集（< 10ms）
  读取本轮所有临时 jsonl → 构建会话摘要行 → 写入 sessions.jsonl

阶段 2: 触发 extract_semantics.py（异步 2-3s，不阻塞）
  如果检测到用户纠正，异步触发语义提取

设计原则:
  - Hook 只采集元数据，不做 AI 调用
  - 非阻塞：写入一行 JSONL 后立即返回
  - 语义提取异步触发，失败不影响主流程
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def find_project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def build_session_summary() -> dict:
    """从环境变量和 stdin 构建会话摘要"""
    # 从 stdin 读取 hook 传递的数据（如果有）
    try:
        raw = sys.stdin.read().strip()
        hook_data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    session_id = hook_data.get("session_id", os.environ.get("CLAUDE_SESSION_ID", "unknown"))
    mode = os.environ.get("CLAUDE_MODE", "solo")

    return {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "duration_minutes": hook_data.get("duration_minutes", 0),
        "agents_used": hook_data.get("agents_used", []),
        "skills_used": hook_data.get("skills_used", []),
        "tool_failures": hook_data.get("tool_failures", 0),
        "git_files_changed": hook_data.get("git_files_changed", 0),
        "corrections": [],
        "rich_context": {},
    }


def append_session(root: Path, session: dict) -> int:
    """追加一行到 sessions.jsonl，返回写入的字节位置"""
    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    log_file = data_dir / "sessions.jsonl"

    line = json.dumps(session, ensure_ascii=False) + "\n"
    with open(log_file, "a") as f:
        f.write(line)

    return 0


def trigger_semantic_extraction(root: Path):
    """异步触发语义提取（仅当有用户纠正时）"""
    daemon_dir = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", root)) / "hooks" / "bin"
    extract_script = daemon_dir / "extract_semantics.py"
    if not extract_script.exists():
        return False

    import subprocess
    subprocess.Popen(
        [sys.executable, str(extract_script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def main():
    root = find_project_root()

    session = build_session_summary()
    append_session(root, session)

    has_corrections = bool(os.environ.get("CLAUDE_HAS_CORRECTIONS"))
    extraction_triggered = False
    if has_corrections:
        extraction_triggered = trigger_semantic_extraction(root)

    result = {
        "collected": True,
        "session_id": session["session_id"],
        "extraction_triggered": extraction_triggered,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
