#!/usr/bin/env bash
# install.sh — 将 chk 命令安装到系统 PATH
# 用法: bash cli/install.sh
# 效果: 在 ~/.zshrc 中写入 chk bash function，支持 chk <cmd> 全局调用

set -euo pipefail

INSTALL_SCRIPT=$(cat <<'EOF'
# ── Claude Harness Kit (/chk) ──
# 安装时间: INSTALL_TIMESTAMP
# 使用: chk <init|solo|auto|team|ultra|pipeline|ralph|ccg|status|gc|mode|help>
chk() {
    local CHK_CLI="/Users/yanyinxi/工作/code/github/claude-harness-kit/cli"
    case "${1:-}" in
        init|solo|auto|team|ultra|pipeline|ralph|ccg|status|gc|mode|help)
            bash "$CHK_CLI/chk.sh" "$@"
            ;;
        *)
            echo "用法: chk <mode> [args...]"
            echo "  chk help  查看所有命令"
            return 1
            ;;
    esac
}
EOF
)

# 动态插入时间戳
INSTALL_SCRIPT="${INSTALL_SCRIPT/INSTALL_TIMESTAMP/$(date '+%Y-%m-%d %H:%M')}"

# 检测 shell 配置
SHELL_RC="$HOME/.zshrc"
if [ ! -f "$SHELL_RC" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

# 检查是否已安装
if grep -q "Claude Harness Kit.*chk" "$SHELL_RC" 2>/dev/null; then
    echo "✅ /chk 已安装，无需重复安装"
    echo "   配置文件: $SHELL_RC"
    echo "   如需重新安装，先手动删除 $SHELL_RC 中的 chk 相关行"
    exit 0
fi

# 追加到 shell 配置
{
    echo ""
    echo "$INSTALL_SCRIPT"
} >> "$SHELL_RC"

echo "✅ /chk 安装成功"
echo ""
echo "立即生效: source $SHELL_RC"
echo "使用方式: chk help"
echo ""
echo "之后在任何终端窗口中，直接使用 chk 命令即可"
echo ""
echo "卸载方式: 编辑 $SHELL_RC，删除 \"# ── Claude Harness Kit\" 相关行"
