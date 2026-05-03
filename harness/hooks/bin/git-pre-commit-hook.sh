#!/bin/bash
# Git pre-commit 钩子 - 版本一致性检查
# 复制到 .git/hooks/pre-commit 并添加执行权限即可启用

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 运行版本检查
cd "$ROOT_DIR"
python3 harness/hooks/bin/version-consistency-check.py
exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo ""
    echo "❌ 版本检查失败！请先修复版本不一致问题"
    echo "💡 运行以下命令修复："
    echo "   python3 harness/_core/bump_version.py auto"
    exit 1
fi

echo "✅ 版本检查通过"