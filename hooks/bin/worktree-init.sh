#!/bin/bash
# worktree-init.sh — PreToolUse Bash hook: auto-creates worktree for isolation sessions
# Usage: Called by Claude Code PreToolUse hook when Bash is invoked
# Env: HOOK_DATA JSON on stdin containing message details

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_STATE_DIR="${PLUGIN_ROOT}/../.claude/data/worktrees/sessions"
MAP_FILE="${PLUGIN_ROOT}/../.claude/data/worktrees/.worktree-map.json"

mkdir -p "$SESSION_STATE_DIR"

# Read hook data from stdin
HOOK_DATA="$(cat)"
[[ -z "$HOOK_DATA" ]] && exit 0

# Only trigger on Bash tool
TOOL_NAME=$(echo "$HOOK_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('message',{}).get('name',''))
" 2>/dev/null) || exit 0

[[ "$TOOL_NAME" != "Bash" ]] && exit 0

SESSION_ID=$(echo "$HOOK_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('sessionId','default'))
" 2>/dev/null) || SESSION_ID="default"

SESSION_STATE="${SESSION_STATE_DIR}/${SESSION_ID}.json"

# If session already has a worktree, nothing to do
if [[ -f "$SESSION_STATE" ]]; then
  exit 0
fi

# Check if this session requests worktree isolation via .chk-worktree-isolation marker
WORKTREE_REQUESTED=false
if [[ -f "${PLUGIN_ROOT}/../.claude/data/worktrees/.isolation-request" ]]; then
  WORKTREE_REQUESTED=true
fi

if [[ "$WORKTREE_REQUESTED" == "false" ]]; then
  exit 0
fi

# Create session state indicating worktree isolation is needed
# The actual worktree will be created by worktree-manager.sh create
WT_NAME="session-${SESSION_ID}"
mkdir -p "${PLUGIN_ROOT}/../.claude/data/worktrees"

# Create worktree via worktree-manager.sh if not already created
"${PLUGIN_ROOT}/hooks/bin/worktree-manager.sh" create "$WT_NAME" "isolation-session" >/dev/null 2>&1 || true

WT_PATH=$(cat "${MAP_FILE}" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
name='session-${SESSION_ID}'
print(d.get(name,{}).get('path','') if name in d else '')
" 2>/dev/null) || WT_PATH=""

if [[ -n "$WT_PATH" ]]; then
  echo "{\"sessionId\":\"$SESSION_ID\",\"path\":\"$WT_PATH\",\"isolation\":\"worktree\"}" > "$SESSION_STATE"
fi

exit 0