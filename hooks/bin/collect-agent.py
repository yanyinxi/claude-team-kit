#!/usr/bin/env python3
"""
PostToolUse[Agent] Hook: 记录 Agent 调用。
轻量采集，写入一行 JSONL，耗时 < 1ms。
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime


def main():
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        hook_data = json.loads(sys.stdin.read().strip()) if sys.stdin.read().strip() else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    record = {
        "agent": hook_data.get("agent", hook_data.get("tool_input", {}).get("subagent_type", "unknown")),
        "task": hook_data.get("description", ""),
        "timestamp": datetime.now().isoformat(),
        "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
    }

    log_file = data_dir / "agent_calls.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps({"collected": True}))


if __name__ == "__main__":
    main()
