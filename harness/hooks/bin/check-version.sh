#!/bin/bash
# 版本一致性检查钩子
# 自动检查所有文件的 version 字段是否与 harness/_core/version.json 一致

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🔍 检查版本一致性..."

cd "$ROOT_DIR"

# 运行版本检查
python3 "$SCRIPT_DIR/version-consistency-check.py"
exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo ""
    echo "❌ 版本检查失败！请先运行: python harness/_core/bump_version.py auto"
    echo ""
    read -p "是否立即修复版本? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python3 harness/_core/bump_version.py auto
        if [ $? -eq 0 ]; then
            echo ""
            echo "✅ 版本已修复，请重新 commit"
            exit 1
        fi
    fi
    echo "❌ Commit 被取消"
    exit 1
fi

echo "✅ 版本检查通过"