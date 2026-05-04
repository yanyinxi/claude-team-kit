#!/usr/bin/env python3
"""
PostToolUseFailure Hook: 记录工具调用失败。
轻量采集，写入一行 JSONL，耗时 < 1ms。
"""
import json
import os
import sys
from pathlib import Path

# 导入共享工具模块
sys.path.insert(0, str(Path(__file__).parent))
from _session_utils import get_session_id, get_project_root, get_data_dir, write_log_record, get_current_timestamp


def classify_error_type(error: str) -> str:
    """分类错误类型"""
    error_lower = error.lower()
    if "permission" in error_lower or "denied" in error_lower:
        return "permission_error"
    if "not found" in error_lower or "no such" in error_lower:
        return "not_found_error"
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout_error"
    if "syntax" in error_lower or "parse" in error_lower:
        return "syntax_error"
    if "connection" in error_lower or "network" in error_lower:
        return "network_error"
    return "unknown_error"


def main():
    root = get_project_root()
    session_id = get_session_id(root)

    raw = sys.stdin.read().strip()
    try:
        hook_data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    record = {
        "tool": hook_data.get("tool_name", "unknown"),
        "tool_input": str(hook_data.get("tool_input", ""))[:200],
        "error": str(hook_data.get("error", ""))[:200],
        "error_type": classify_error_type(hook_data.get("error", "")),
        "timestamp": get_current_timestamp(),
        "session_id": session_id,
    }

    log_file = get_data_dir(root) / "failures.jsonl"
    write_log_record(record, log_file)

    print(json.dumps({"collected": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"collected": False, "warning": str(e)[:100]}), file=sys.stderr)
        sys.exit(0)