#!/bin/bash
# git-commit-check.sh - 检查 Git 提交规范

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RULES_FILE="$PROJECT_ROOT/harness/rules/general.md"

cd "$PROJECT_ROOT" || exit 1

# 从 general.md 提取有效类型
VALID_TYPES="feat|fix|docs|refactor|test|chore"

# 检查 git commit 命令
if [ "$CLAUDE_TOOL_NAME" = "Bash" ]; then
    cmd="$CLAUDE_TOOL_INPUT"
    if echo "$cmd" | grep -qE "git commit"; then
        # 提取提交信息
        msg=$(echo "$cmd" | grep -oE "'[^']*'|\"[^\"]*\"" | head -1 | tr -d "'\"")

        if [ -n "$msg" ]; then
            # 检查是否匹配规范格式
            if ! echo "$msg" | grep -qE "^($VALID_TYPES)(\([^)]*\))?: .+"; then
                echo "WARN: Commit message should follow format: type(scope): description"
                echo "Valid types: feat, fix, docs, refactor, test, chore"
            fi
        fi
    fi
fi

exit 0