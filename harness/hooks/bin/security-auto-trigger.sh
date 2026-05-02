#!/bin/bash
# security-auto-trigger.sh — PostToolUse Hook: 敏感文件修改时自动触发安全审查提示
# 设计：永远 exit 0，提示不阻断
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRIGGER_LOG="${PLUGIN_ROOT}/.claude/security/.auto-trigger-log.json"

SECURITY_PATTERNS=(
    "auth" "security" "jwt" "token" "crypto"
    "password" "credential" "oauth" "permission"
    "role" "payment" "billing"
)

SESSION_TRIGGER_LOG="${PLUGIN_ROOT}/.claude/security/.session-triggers-$$.json"

HOOK_DATA=$(cat 2>/dev/null) || HOOK_DATA=""
[[ -z "$HOOK_DATA" ]] && exit 0

TOOL_NAME=$(echo "$HOOK_DATA" | python3 -c "
import sys, json
d = json.load(sys.stdin)
msg = d.get('message', {})
print(msg.get('name', ''))
" 2>/dev/null) || { exit 0; }

FILE_PATH=$(echo "$HOOK_DATA" | python3 -c "
import sys, json
d = json.load(sys.stdin)
msg = d.get('message', {})
content = msg.get('content', '')
if isinstance(content, list):
    for b in content:
        if isinstance(b, dict) and b.get('type') == 'input':
            for inp in b.get('inputs', []):
                if inp.get('name') == 'file_path':
                    print(inp.get('file_path', ''), end='')
" 2>/dev/null) || { exit 0; }

[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0
[[ -z "$FILE_PATH" ]] && exit 0

MATCHED=""
for pattern in "${SECURITY_PATTERNS[@]}"; do
    if echo "$FILE_PATH" | grep -qi "$pattern"; then
        MATCHED="$pattern"
        break
    fi
done

[[ -z "$MATCHED" ]] && exit 0

SESSION_ID=$(echo "$HOOK_DATA" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('sessionId', 'unknown'))
" 2>/dev/null) || SESSION_ID="unknown"

KEY="${SESSION_ID}:${FILE_PATH}"

STATE_DIR="${PLUGIN_ROOT}/.claude/security"
mkdir -p "$STATE_DIR"
TRACK_FILE="${STATE_DIR}/session-triggers.jsonl"

[[ -f "$TRACK_FILE" ]] && grep -q "\"$KEY\"" "$TRACK_FILE" 2>/dev/null && exit 0

echo "{\"key\":\"${KEY}\",\"pattern\":\"${MATCHED}\",\"file\":\"${FILE_PATH}\",\"session\":\"${SESSION_ID}\"}" \
    >> "$TRACK_FILE" 2>/dev/null || true

echo "🔒 Security Auto-Trigger:" >&2
echo "  File modified: $FILE_PATH" >&2
echo "  Matched pattern: $MATCHED" >&2
echo "" >&2
echo "  → Consider running /security-review or invoking the security-audit skill" >&2
echo "  → This suggestion was auto-triggered by security-auto-trigger hook" >&2

exit 0
