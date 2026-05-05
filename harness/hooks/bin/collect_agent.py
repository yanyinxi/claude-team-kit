#!/usr/bin/env python3
"""
PostToolUse[Agent] Hook: 记录 Agent 调用。
轻量采集，写入一行 JSONL，耗时 < 1ms。
"""
import json
import os
import sys
from pathlib import Path

# 导入共享工具模块
sys.path.insert(0, str(Path(__file__).parent))
from _session_utils import get_session_id, get_project_root, get_data_dir, write_log_record, get_current_timestamp, load_hook_context


def main():
    root = get_project_root()
    session_id = get_session_id(root)
    hook_data = load_hook_context()

    record = {
        "agent": hook_data.get("agent", hook_data.get("tool_input", {}).get("subagent_type", "unknown")),
        "task": hook_data.get("description", ""),
        "timestamp": get_current_timestamp(),
        "session_id": session_id,
        "success": hook_data.get("success", None),
        "error": hook_data.get("error", ""),
    }

    log_file = get_data_dir(root) / "agent_calls.jsonl"
    write_log_record(record, log_file)

    print(json.dumps({"collected": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"collected": False, "warning": str(e)[:100]}), file=sys.stderr)
        sys.exit(0)