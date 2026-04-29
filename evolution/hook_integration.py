"""
Hook 集成模块 — 已弃用（Deprecated）

此模块曾是 Python 进化引擎的桥接层。
自 evolution-system-design.md v2 方案后，进化改为 Agent 进化器模式：
  - Agent 进化器: agents/skill-evolver.md 等（首选）
  - Python 进化器: evolution/evolvers/（备用，仅供 CLI 手动触发）

当前架构: Stop Hook → session_evolver.py → run_orchestrator() → 持久化决策到 data/pending_evolution.json
下次会话 → load_evolution_state.py 注入上下文 → Claude 主 Agent 调度 Agent 进化器执行

此文件保留以确保向后兼容 evolution/cli.py 的手动调用。
"""

import subprocess
import sys
from pathlib import Path


def trigger_evolution(project_root: str):
    """
    [DEPRECATED] 触发进化检查（Python 引擎）

    此函数调用旧的 Python 进化引擎 (evolution/cli.py run)。
    首选路径是 Agent 进化器 (agents/*-evolver.md)，由 Claude 主 Agent 在会话中调度。

    保留此函数供:
    - 手动 CLI 调试: python3 .claude/evolution/cli.py run
    - 向后兼容
    """
    evolution_cli = Path(project_root) / ".claude" / "evolution" / "cli.py"

    if not evolution_cli.exists():
        print("[Evolution] CLI not found, skipping", file=sys.stderr)
        return

    try:
        # 非阻塞方式触发进化检查
        result = subprocess.run(
            [sys.executable, str(evolution_cli), "run"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30  # 最多30秒
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            if "总计:" in output and "0 项" not in output:
                print(f"[Evolution] {output.split('总计:')[-1].strip()}", file=sys.stderr)

    except subprocess.TimeoutExpired:
        print("[Evolution] Check timeout, will retry next session", file=sys.stderr)
    except Exception as e:
        print(f"[Evolution] Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    # 测试运行
    import os
    project_root = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    trigger_evolution(project_root)
