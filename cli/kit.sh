#!/usr/bin/env bash
# kit — Claude Team Kit CLI 工具入口
# 用法: kit <command> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

show_help() {
    echo "kit — Claude Team Kit CLI"
    echo ""
    echo "用法: kit <command> [args...]"
    echo ""
    echo "命令:"
    echo "  init       分析项目并生成 CLAUDE.md + .claude/ 配置"
    echo "  sync       从中央配置仓库同步团队共享规则"
    echo "  scan       扫描代码库目录，评估改造量"
    echo "  migrate    执行项目迁移（框架升级等）"
    echo "  status     查看团队插件状态"
    echo "  help       显示此帮助"
    echo ""
    echo "示例:"
    echo "  kit init"
    echo "  kit sync --from=https://github.com/team/claude-standards"
    echo "  kit scan --group=backend-services"
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
    status)
        echo "Claude Team Kit v0.2"
        echo ""
        echo "Agents: $(ls "$SCRIPT_DIR/../agents/" | wc -l | tr -d ' ')"
        echo "Skills: $(ls -d "$SCRIPT_DIR/../skills/"*/ | wc -l | tr -d ' ')"
        echo "Rules:  $(ls "$SCRIPT_DIR/../rules/" | wc -l | tr -d ' ')"
        echo "Hooks:  $(ls "$SCRIPT_DIR/../hooks/bin/" | wc -l | tr -d ' ')"
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
