#!/usr/bin/env python3
"""
PostToolUse[Agent] Hook — 采集 Agent 启动数据
这是唯一能可靠获取 subagent_type 的 Hook 事件。
SubagentStop 不提供 subagent_type（平台已知限制），因此不用它。

输出: data/agent_performance.jsonl
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
    agent_name = tool_input.get("subagent_type", "unknown")

    session_id = data.get("session_id", "unknown")
    description = (tool_input.get("description", "") or "")[:200]
    prompt = (tool_input.get("prompt", "") or "")[:200]

    record = {
        "type": "agent_launch",
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "agent": agent_name,
        "task": description,
        "prompt_preview": prompt,
    }
    if agent_name == "unknown":
        record["note"] = "platform_bug_subagent_type_missing"

    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    data_dir = Path(project_root) / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    perf_file = data_dir / "agent_performance.jsonl"
    with open(perf_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # 用户可见进度输出：Agent 启动时 stderr 消息会出现在界面
    note = " (⚠️ 类型未知)" if agent_name == "unknown" else ""
    print(f"📤 Agent 启动: {agent_name}{note} — {description[:80]}", file=sys.stderr)


if __name__ == "__main__":
    main()
