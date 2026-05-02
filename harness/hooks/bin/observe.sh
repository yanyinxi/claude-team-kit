#!/bin/bash
# observe.sh — Hook 观测事件采集器（shell wrapper）
# 职责：调用 observe.py，永远 exit 0，零阻塞主流程
#
# 设计原则：
#   1. 永远 exit 0 — 即使 Python 崩溃也不影响 Claude Code 工作流
#   2. 所有异常在 Python 内部捕获，shell 层不抛任何错误
#   3. trap 确保任何退出路径都返回 0

set +e  # 关闭 errexit，防止任何命令失败导致 shell 退出
         # Python 层已有完善的异常处理，shell 层无需再防护

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_SCRIPT="${PLUGIN_ROOT}/hooks/bin/observe.py"

# 无论如何都返回 0
trap 'exit 0' EXIT INT TERM HUP

if [[ -x "$PYTHON_SCRIPT" ]]; then
    python3 "$PYTHON_SCRIPT" </dev/stdin
else
    python3 -c "
import sys, json
try:
    data = sys.stdin.read()
    if data.strip():
        pass  # 解析已移至 observe.py，静默跳过
except Exception:
    pass
"
fi

# 确保 exit 0（即使 Python 返回非零）
exit 0
