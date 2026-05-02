#!/bin/bash
# tdd-check.sh — PreToolUse Hook: TDD 阻断检查，实现文件写入前必须存在对应测试文件
# 设计：永远 exit 0（Hook 失败不阻断），TDD 违规通过 hookSpecificOutput 阻断
set -uo pipefail

INPUT=$(cat 2>/dev/null) || INPUT=""
[[ -z "$INPUT" ]] && exit 0

TOOL_NAME=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_name', ''))
" 2>/dev/null) || { exit 0; }

FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null) || { exit 0; }

if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    exit 0
fi
[[ -z "$FILE_PATH" ]] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# 判断是否为实现代码
_is_impl() {
    local f="$1"
    [[ "$f" =~ \.json$ ]] && return 1
    [[ "$f" =~ \.ya?ml$ ]] && return 1
    [[ "$f" =~ \.md$ ]] && return 1
    [[ "$f" =~ \.txt$ ]] && return 1
    [[ "$f" =~ \.csv$ ]] && return 1
    [[ "$f" =~ \.css$ ]] && return 1
    [[ "$f" =~ \.html$ ]] && return 1
    [[ "$f" =~ \.svg$ ]] && return 1
    [[ "$f" =~ /docs/ ]] && return 1
    [[ "$f" =~ /README ]] && return 1
    [[ "$f" =~ \.test\. ]] && return 1
    [[ "$f" =~ \.spec\. ]] && return 1
    [[ "$f" =~ /test/ ]] && return 1
    [[ "$f" =~ /__tests__/ ]] && return 1
    [[ "$f" =~ /spec/ ]] && return 1
    [[ "$f" =~ \.(java|ts|tsx|js|jsx|py|go|rs|rb|php|swift|kt|scala|cs|c|cpp|h)$ ]] && return 0
    return 1
}

_is_impl "$FILE_PATH" || exit 0

WHITELIST_DIRS=("migrations/" "db/migrate/" "generated/" "proto/" "vendor/" "third_party/")
for d in "${WHITELIST_DIRS[@]}"; do
    [[ "$FILE_PATH" == *"$d"* ]] && exit 0
done

block() {
    local reason="$1"
    python3 -c "
import json, sys
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': sys.argv[1]
    }
}, ensure_ascii=False))
" "$reason"
    exit 2
}

IMP_FILE="$FILE_PATH"
BASENAME=$(basename "$IMP_FILE")
NAME="${BASENAME%.*}"

CANDIDATES=()
CANDIDATES+=("$(dirname "$IMP_FILE")/$NAME.test.${BASENAME##*.}")
CANDIDATES+=("$(dirname "$IMP_FILE")/$NAME.spec.${BASENAME##*.}")
CANDIDATES+=("$(dirname "$IMP_FILE")/${NAME}_test.${BASENAME##*.}")
CANDIDATES+=("$(dirname "$IMP_FILE")/${NAME}_spec.${BASENAME##*.}")

if [[ "$IMP_FILE" == *"/main/"* ]]; then
    TEST_DIR="${IMP_FILE/main\//test/}"
    TEST_DIR="${TEST_DIR%/*}"
    CANDIDATES+=("$TEST_DIR/${NAME}Test.${BASENAME##*.}")
fi

PROJECT_REL="${IMP_FILE#./}"
CANDIDATES+=("__tests__/${NAME}.test.${BASENAME##*.}")
CANDIDATES+=("__tests__/${NAME}_test.${BASENAME##*.}")
CANDIDATES+=("tests/${NAME}_test.${BASENAME##*.}")
CANDIDATES+=("tests/${NAME}.test.${BASENAME##*.}")

for candidate in "${CANDIDATES[@]}"; do
    [[ -f "$candidate" ]] && exit 0
done

# git staged check — 失败不阻断
if git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    STAGED=$(git -C "$PROJECT_DIR" diff --cached --name-only 2>/dev/null) || STAGED=""
    for f in $STAGED; do
        if [[ "$f" =~ \.test\. ]] || [[ "$f" =~ \.spec\. ]] || [[ "$f" =~ /test/ ]]; then
            exit 0
        fi
    done
fi

block "测试先行: 实现文件 \"${FILE_PATH}\" 没有对应的测试文件。\n请先创建测试文件（如 ${CANDIDATES[0]} 或 ${CANDIDATES[1]}），确保测试失败后，再编写实现代码。\n\nTDD 流程: RED（写失败测试）→ GREEN（让测试通过）→ REFACTOR（优化结构）"
