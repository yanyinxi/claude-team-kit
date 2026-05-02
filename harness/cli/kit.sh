#!/usr/bin/env bash
# kit — Claude Harness Kit CLI 工具入口
# 用法: kit <command> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

show_help() {
    echo "kit — Claude Harness Kit CLI"
    echo ""
    echo "用法: kit <command> [args...]"
    echo ""
    echo "命令:"
    echo "  init       分析项目并生成 CLAUDE.md + .claude/ 配置"
    echo "  sync       从中央配置仓库同步团队共享规则"
    echo "  scan       扫描代码库目录，评估改造量"
    echo "  migrate    执行项目迁移（框架升级等）"
    echo "  gc         知识垃圾回收 — 扫描 .claude/knowledge/ 生成漂移报告"
    echo "  mode       切换执行模式（default|ralph|pipeline）"
    echo "  status     查看 Harness Kit 当前状态（模式/Hooks/Sessions/Instinct）"
    echo "  help       显示此帮助"
    echo ""
    echo "示例:"
    echo "  kit init"
    echo "  kit sync --from=https://github.com/team/claude-standards"
    echo "  kit scan --group=backend-services"
    echo "  kit gc"
    echo "  kit mode ralph"
}

case "${1:-help}" in
    init)
        python3 "$SCRIPT_DIR/init.py" "${@:2}"
        ;;
    sync)
        python3 "$SCRIPT_DIR/sync.py" "${@:2}"
        ;;
    scan)
        python3 "$SCRIPT_DIR/scan.py" "${@:2}"
        ;;
    migrate)
        python3 "$SCRIPT_DIR/migrate.py" "${@:2}"
        ;;
    gc)
        python3 "$SCRIPT_DIR/gc.py" "${@:2}"
        ;;
    mode)
        python3 "$SCRIPT_DIR/mode.py" "${@:2}"
        ;;
    status)
        python3 "$SCRIPT_DIR/status.py"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "未知命令: $1"
        echo "运行 kit help 查看帮助"
        exit 1
        ;;
esac
