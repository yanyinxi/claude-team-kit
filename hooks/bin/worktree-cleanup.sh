#!/bin/bash
# worktree-cleanup.sh — Cleanup worktree map after WorktreeRemove
# Usage: Called by Claude Code WorktreeRemove hook

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAP_FILE="${PLUGIN_ROOT}/../.claude/data/worktrees/.worktree-map.json"

# Read hook data from stdin
HOOK_DATA="$(cat)"
[[ -z "$HOOK_DATA" ]] && exit 0

# Try to extract removed worktree path
REMOVED_PATH=$(echo "$HOOK_DATA" | python3 -c "
import json,sys,re
d=json.load(sys.stdin)
msg = d.get('message',{})
content = msg.get('content','')
text = ''
if isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'tool_result':
            t = block.get('content','')
            if isinstance(t, list):
                for x in t:
                    if isinstance(x, dict):
                        text += x.get('text','')
            else:
                text += str(t)
else:
    text = str(content)

# Extract worktree path from git worktree output
m = re.search(r'(\.\./\S*worktree\S*|/.*worktree-\S+)', text)
if m:
    print(m.group(1))
" 2>/dev/null) || REMOVED_PATH=""

if [[ -z "$REMOVED_PATH" ]]; then
    exit 0
fi

if [[ ! -f "$MAP_FILE" ]]; then
    exit 0
fi

# Remove entry from map
python3 -c "
import json,sys
d=json.load(open('${MAP_FILE}'))
path='${REMOVED_PATH}'
removed = [k for k,v in d.items() if v.get('path','') == path]
for k in removed:
    print(f'Removing from map: {k}')
    del d[k]
print(json.dumps(d, indent=2))
" > "${MAP_FILE}.tmp" && mv "${MAP_FILE}.tmp" "$MAP_FILE"

exit 0