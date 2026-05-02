#!/usr/bin/env python3
"""
PostToolUseFailure Hook: 记录工具调用失败。
轻量采集，写入一行 JSONL，耗时 < 1ms。
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime


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
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    # 尝试获取 session_id
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")

    if not session_id or session_id == "unknown":
        git_dir = root / ".git"
        if git_dir.exists():
            try:
                import subprocess
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=root, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    commit = result.stdout.strip()
                    if commit:
                        from datetime import date
                        today = date.today().isoformat()
                        session_id = f"git-{commit}-{today}"
            except Exception:
                pass

    if not session_id or session_id == "unknown":
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"{root.name}-{ts}"

    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

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
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
    }

    log_file = data_dir / "failures.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps({"collected": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys, json
        print(json.dumps({"collected": False, "warning": str(e)[:100]}), file=sys.stderr)
        sys.exit(0)