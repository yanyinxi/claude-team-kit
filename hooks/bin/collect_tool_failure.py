#!/usr/bin/env python3
"""
PostToolUseFailure Hook — 采集工具调用失败数据
这是关键的质量信号，evolution/evolvers 需要它来识别错误模式。

输出: data/tool_failures.jsonl
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

    tool_name = data.get("tool_name", "unknown")
    error_msg = (data.get("error", "") or "")[:200]
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("command", "") or ""
    session_id = data.get("session_id", "unknown")

    record = {
        "type": "tool_failure",
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "tool": tool_name,
        "file_path": file_path[:300],
        "error_summary": error_msg,
    }

    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    data_dir = Path(project_root) / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    fail_file = data_dir / "tool_failures.jsonl"
    with open(fail_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
