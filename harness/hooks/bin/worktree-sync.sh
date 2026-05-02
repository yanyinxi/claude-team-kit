#!/bin/bash
# worktree-sync.sh — Sync CLAUDE.md and .claude/ context to worktree on WorktreeCreate
# Usage: Called by Claude Code WorktreeCreate hook

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Read hook data from stdin (JSON)
HOOK_DATA="$(cat)"
[[ -z "$HOOK_DATA" ]] && exit 0

WORKTREE_PATH=$(echo "$HOOK_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
# The worktree path is in the message content or tool result
msg = d.get('message',{})
content = msg.get('content','')
if isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'tool_result':
            text = block.get('content', '')
            if isinstance(text, list):
                for t in text:
                    if isinstance(t, dict):
                        text = t.get('text', '')
            # Extract path from git output like "Preparing worktree (new branch) .../worktree-xxx"
            import re
            m = re.search(r'(\S*worktree\S*|\.\./worktree-\S+)', str(text))
            if m:
                print(m.group(1))
                sys.exit(0)
    print('')
else:
    print('')
" 2>/dev/null) || WORKTREE_PATH=""

# If path not found in hook data, look in worktree-map.json
if [[ -z "$WORKTREE_PATH" ]]; then
    MAP_FILE="${PLUGIN_ROOT}/../.claude/data/worktrees/.worktree-map.json"
    if [[ -f "$MAP_FILE" ]]; then
        # Get the most recently created worktree
        WORKTREE_PATH=$(python3 -c "
import json
d=json.load(open('${MAP_FILE}'))
if d:
    newest = max(d.items(), key=lambda x: x[1].get('created',''))
    print(newest[1].get('path',''))
else:
    print('')
" 2>/dev/null) || WORKTREE_PATH=""
    fi
fi

[[ -z "$WORKTREE_PATH" ]] && exit 0
[[ ! -d "$WORKTREE_PATH" ]] && exit 0

log_info() { echo "🔄 worktree-sync: $*" >&2; }

# Sync CLAUDE.md
if [[ -f "${PLUGIN_ROOT}/CLAUDE.md" ]]; then
    cp "${PLUGIN_ROOT}/CLAUDE.md" "${WORKTREE_PATH}/CLAUDE.md"
    log_info "CLAUDE.md synced → ${WORKTREE_PATH}/"
fi

# Sync .claude/ directory
if [[ -d "${PLUGIN_ROOT}/.claude" ]]; then
    mkdir -p "${WORKTREE_PATH}/.claude"
    for item in rules knowledge settings.local.json; do
        if [[ -f "${PLUGIN_ROOT}/.claude/$item" ]]; then
            cp "${PLUGIN_ROOT}/.claude/$item" "${WORKTREE_PATH}/.claude/$item"
            log_info ".claude/$item synced"
        fi
        if [[ -d "${PLUGIN_ROOT}/.claude/$item" ]]; then
            mkdir -p "${WORKTREE_PATH}/.claude/$item"
            cp -r "${PLUGIN_ROOT}/.claude/$item/"* "${WORKTREE_PATH}/.claude/$item/" 2>/dev/null || true
            log_info ".claude/$item/ synced"
        fi
    done
fi

exit 0