#!/bin/bash
# architecture-verify.sh - 架构决策步骤验证

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RULES_FILE="$PROJECT_ROOT/harness/rules/expert-mode.md"

cd "$PROJECT_ROOT" || exit 1

# 检查是否涉及架构相关关键词
trigger_words="架构|设计|重构|架构师|技术决策|决策"
if echo "$CLAUDE_TOOL_INPUT" | grep -qE "$trigger_words"; then
    # 检查是否有决策记录目录
    decision_dir="decision"
    decision_file="decision/adr-001.md"

    # 如果涉及架构但没有决策文件，提示警告
    if [ ! -d "$decision_dir" ] && [ ! -f "$decision_file" ]; then
        # 不阻止，只是提醒
        echo "INFO: Consider documenting architectural decisions in decision/ directory"
    fi
fi

exit 0