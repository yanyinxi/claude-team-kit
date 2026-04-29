#!/usr/bin/env python3
"""
PostToolUse[Skill] Hook — 采集 Skill 调用数据
需要验证 matcher: "Skill" 是否能匹配到 Claude Code 的 Skill 工具调用。

输出: data/skill_usage.jsonl
"""
import fcntl, json, os, sys
from datetime import datetime
from pathlib import Path


def main():
    try:
        raw = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        data = {}

    tool_input = data.get("tool_input", {})
    skill_name = tool_input.get("skill", "")

    if not skill_name:
        return

    session_id = data.get("session_id", "unknown")

    record = {
        "type": "skill_invoked",
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "skill": skill_name,
    }

    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    data_dir = Path(project_root) / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    usage_file = data_dir / "skill_usage.jsonl"
    with open(usage_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
