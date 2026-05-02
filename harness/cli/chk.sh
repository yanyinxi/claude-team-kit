#!/usr/bin/env bash
# chk — Claude Harness Kit 统一入口
# 用法: chk <mode> [args...]
# 支持模式: init solo auto team ultra pipeline ralph ccg help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

show_help() {
    cat <<'EOF'
chk — Claude Harness Kit 统一入口

用法: chk <mode> [args...]

执行模式:
  init       分析当前项目，生成 CLAUDE.md + .claude/ 配置
  solo       Solo 模式 — 直接对话，不用 Agent
  auto       Autopilot 模式 — 全自动端到端，快速修复 Bug
  team       Team 模式 — 默认模式，5 阶段流程（功能开发）
  ultra      Ultrawork 模式 — 极限并行，3-5 个 Agent 同时工作
  pipeline   Pipeline 模式 — 严格阶段顺序，上一步输出喂下一步
  ralph      Ralph 模式 — TDD 强制，不通过不停止
  ccg        CCG 模式 — Claude + Codex + Gemini 三方审查

其他:
  status     查看 Harness Kit 当前状态
  gc         知识垃圾回收
  mode       查看/切换执行模式
  help       显示此帮助

场景选择指南:
  简单问答              → chk solo
  快速修复 Bug          → chk auto
  日常功能开发          → chk team        （默认）
  批量代码改造          → chk ultra
  数据库迁移            → chk pipeline
  支付/安全关键代码     → chk ralph
  关键架构决策          → chk ccg
  新项目初始化          → chk init

在 Claude Code 中直接使用斜杠命令:
  /chk-init  /chk-solo  /chk-auto  /chk-team  /chk-ultra
  /chk-pipeline  /chk-ralph  /chk-ccg  /chk-status  /chk-gc

示例:
  chk init                        # 初始化当前目录
  chk init /path/to/project       # 初始化指定目录
  chk team                        # 进入 Team 开发模式
  chk ralph                       # 进入 Ralph TDD 模式
EOF
}

# 路由
case "${1:-}" in
    init)
        shift
        # 支持 chk init --target=/path/to/project
        python3 "$SCRIPT_DIR/init.py" "$@"
        ;;
    solo|auto|team|ultra|pipeline|ralph|ccg)
        MODE="$1"
        shift
        python3 "$SCRIPT_DIR/mode.py" "$MODE" "$@"
        ;;
    status)
        python3 "$SCRIPT_DIR/status.py" "$@"
        ;;
    gc)
        python3 "$SCRIPT_DIR/gc.py" "$@"
        ;;
    mode)
        if [ -n "${2:-}" ]; then
            python3 "$SCRIPT_DIR/mode.py" "$2"
        else
            python3 "$SCRIPT_DIR/mode.py"
        fi
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo "未知命令: $1"
        echo "运行 chk help 查看帮助"
        exit 1
        ;;
esac
