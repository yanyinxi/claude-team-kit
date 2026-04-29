#!/usr/bin/env python3
"""
SessionStart Hook — 注入进化系统状态到会话上下文

输出紧凑摘要 (≤200 tokens) 到 stdout，Claude Code 将其注入 system prompt。

注意：进化派发指令由 auto_evolver.py 注入（SessionStart 第一个 hook），
本 hook 只负责仪表盘摘要，避免 evolutionDispatch 键冲突。
"""

import json
import os
import sys
from pathlib import Path


def main():
    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    claude_dir = Path(project_root) / ".claude"
    sys.path.insert(0, str(claude_dir))

    from lib.evolution_dashboard import generate_dashboard_l1
    from lib.token_efficiency import TokenBudget

    # 生成 L1 摘要
    summary = generate_dashboard_l1(project_root)

    # 检查是否有待处理触发器（仅用于摘要展示，派发由 auto_evolver.py 负责）
    pending_alerts = []
    pending_path = claude_dir / "data" / "pending_evolution.json"
    if pending_path.exists():
        try:
            pending = json.loads(pending_path.read_text())
            triggers = pending.get("pending_triggers", [])
            if triggers:
                dims = sorted(set(t.get("dimension", "?") for t in triggers))
                pending_alerts.append(
                    "进化待处理: {}项 ({})".format(len(triggers), ", ".join(dims))
                )
        except (json.JSONDecodeError, OSError):
            pass

    if pending_alerts:
        summary += " | " + " | ".join(pending_alerts)

    est = TokenBudget.estimate(summary)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "compactEvolutionState": summary,
        }
    }
    print(json.dumps(output, ensure_ascii=False))

    print(
        "[load_evolution_state] 进化摘要: {} ({} tokens)".format(summary, est),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
