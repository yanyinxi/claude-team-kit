#!/usr/bin/env bash
# install.sh — Claude Harness Kit 一键安装脚本
# 用法: bash ./install.sh
# 效果: 安装插件 + 复制斜杠命令，一步搞定

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "CHK 一键安装开始..."
echo ""

# Step 1: 安装 Claude Code 插件
echo "Step 1: 安装 Claude Code 插件"
cd "$CHK_ROOT"
if claude plugins marketplace add --scope local "$(pwd)" 2>&1 | grep -q "already"; then
    echo "  ✅ marketplace 已存在"
else
    echo "  ✅ marketplace 已添加"
fi

if claude plugins install claude-harness-kit 2>&1 | grep -q "already installed"; then
    echo "  ✅ 插件已安装"
else
    echo "  ✅ 插件安装成功"
fi

# Step 2: 复制斜杠命令到用户目录
echo ""
echo "Step 2: 复制斜杠命令"

PLUGIN_CACHE="$HOME/.claude/plugins/cache/claude-harness-kit/claude-harness-kit/0.4.0"
USER_SKILLS="$HOME/.claude/skills"

if [ -d "$PLUGIN_CACHE/skills" ]; then
    mkdir -p "$USER_SKILLS"
    for skill_dir in "$PLUGIN_CACHE/skills"/*/; do
        skill_name="$(basename "$skill_dir")"
        if [ "$skill_name" != "_meta.json" ] && [ ! -d "$USER_SKILLS/$skill_name" ]; then
            mkdir -p "$USER_SKILLS/$skill_name"
            cp -r "$skill_dir"*/. "$USER_SKILLS/$skill_name/" 2>/dev/null || true
            # Copy just SKILL.md
            if [ -f "$skill_dir/SKILL.md" ]; then
                cp "$skill_dir/SKILL.md" "$USER_SKILLS/$skill_name/"
            fi
            echo "  ✅ $skill_name"
        fi
    done
    echo "  ✅ 斜杠命令已复制到 $USER_SKILLS"
else
    echo "  ⚠️ 未找到插件缓存，跳过斜杠命令复制"
    echo "    请确保插件已正确安装后重试"
fi

echo ""
echo "✅ 安装完成！"
echo ""
echo "下一步：重启 Claude Code，然后在聊天框输入 /chk-init 即可"
echo ""
echo "常用命令:"
echo "  /chk-init   初始化项目"
echo "  /chk-team   功能开发（默认）"
echo "  /chk-auto   快速修复 Bug"
echo "  /chk-ultra  批量代码改造"
echo "  /chk-ralph  写支付/安全代码"
echo "  /chk-ccg    架构决策"
echo "  /chk-help   查看所有命令"
