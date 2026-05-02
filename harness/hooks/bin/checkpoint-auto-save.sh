#!/bin/bash
# checkpoint-auto-save.sh — PreToolUse Hook: 检测 /compact 并自动保存 checkpoint
# 设计：永远 exit 0，checkpoint 保存失败不阻断工具调用
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOOK_DATA=$(cat 2>/dev/null) || HOOK_DATA=""
[[ -z "$HOOK_DATA" ]] && exit 0

CONTENT=$(echo "$HOOK_DATA" | python3 -c "
import json, sys
d = json.load(sys.stdin)
msg = d.get('message', {})
content = msg.get('content', '')
if isinstance(content, list):
    for b in content:
        if isinstance(b, dict):
            t = b.get('text', '')
            if t:
                print(t, end='')
elif isinstance(content, str):
    print(content, end='')
" 2>/dev/null) || { exit 0; }

if ! echo "$CONTENT" | grep -qi '/compact\|/checkpoint\s*save'; then
    exit 0
fi

CHECKPOINT_DIR="${PLUGIN_ROOT}/.claude/checkpoints"
mkdir -p "$CHECKPOINT_DIR"

TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)

SESSION_ID=$(echo "$HOOK_DATA" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('sessionId', 'default'))
" 2>/dev/null) || SESSION_ID="default"

SESSION_STATE="${CHECKPOINT_DIR}/.auto-save-${SESSION_ID}.json"

echo "$HOOK_DATA" | python3 -c "
import json, sys, datetime
d = json.load(sys.stdin)
ts = datetime.datetime.utcnow().isoformat() + 'Z'
session = d.get('sessionId', 'unknown')
msg = d.get('message', {})
content = msg.get('content', '')
text = ''
if isinstance(content, list):
    for b in content:
        if isinstance(b, dict):
            text += b.get('text', '') + ' '
elif isinstance(content, str):
    text = content
data = {
    'timestamp': ts,
    'session_id': session,
    'checkpoint_name': 'auto-\${ts[:10]}',
    'message_preview': text[:200],
    'auto_saved': True
}
path = '${SESSION_STATE}'
with open(path, 'w') as f:
    json.dump(data, f, ensure_ascii=False)
" 2>/dev/null || { exit 0; }

echo "Auto-checkpoint saved to ${SESSION_STATE}" >&2
exit 0
