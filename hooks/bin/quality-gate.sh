#!/bin/bash
set -euo pipefail
# 质量门禁：验证代码和配置文件
# Claude Code PostToolUse Hook - 从 stdin 读取 JSON 输入

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# 从 stdin 读取 JSON
INPUT=$(cat)

# 提取工具名和文件路径
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

block_post() {
    local reason="$1"
    echo -e "$reason" >&2
    exit 2
}

# ── JSON 文件格式验证 ──
if [[ "$FILE_PATH" =~ \.json$ ]]; then
    if ! python3 -m json.tool "$FILE_PATH" > /dev/null 2>&1; then
        block_post "❌ JSON 格式错误：$FILE_PATH\n请检查是否有语法错误（多余逗号、非法注释等）"
    fi
fi

# ── project_standards.md 验证 ──
if [[ "$FILE_PATH" == *"project_standards.md"* ]]; then
    VERIFY_SCRIPT="$PROJECT_DIR/.claude/tests/test_parallelism_protocol.py"
    if [[ -f "$VERIFY_SCRIPT" ]]; then
        echo "ℹ️ project_standards.md 已变更，建议运行验证测试"
    fi
fi

# ── Agent 文件格式验证（警告不阻断）──
if [[ "$FILE_PATH" == *"agents/"* ]] && [[ "$FILE_PATH" =~ \.md$ ]]; then
    grep -q "^description:" "$FILE_PATH" 2>/dev/null || echo "⚠️ Agent 文件缺少 description 字段：$FILE_PATH"
    grep -q "^tools:" "$FILE_PATH" 2>/dev/null || echo "⚠️ Agent 文件缺少 tools 字段：$FILE_PATH"
fi

# ── Skill 文件格式验证（警告不阻断）──
if [[ "$FILE_PATH" == *"skills/"* ]] && [[ "$FILE_PATH" =~ \.md$ ]]; then
    grep -q "^---" "$FILE_PATH" 2>/dev/null || echo "⚠️ Skill 文件缺少 frontmatter：$FILE_PATH"
fi

# ── Python 语法检查 ──
if [[ "$FILE_PATH" =~ \.py$ ]] && [[ -f "$FILE_PATH" ]]; then
    if ! python3 -m py_compile "$FILE_PATH" 2>/dev/null; then
        block_post "❌ Python 语法错误：$FILE_PATH"
    fi
fi

exit 0
