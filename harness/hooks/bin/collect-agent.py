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

    # 尝试获取 session_id（Claude Code 环境变量）
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")

    # 如果为空，尝试从 git 生成确定性 ID
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
                        # 用 git commit + 当前日期生成确定性 session_id
                        from datetime import date
                        today = date.today().isoformat()
                        session_id = f"git-{commit}-{today}"
            except Exception:
                pass

    # 如果还是空的，用项目名 + 时间戳
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
        "agent": hook_data.get("agent", hook_data.get("tool_input", {}).get("subagent_type", "unknown")),
        "task": hook_data.get("description", ""),
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        # 尝试获取执行结果
        "success": hook_data.get("success", None),
        "error": hook_data.get("error", ""),
    }

    log_file = data_dir / "agent_calls.jsonl"
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
