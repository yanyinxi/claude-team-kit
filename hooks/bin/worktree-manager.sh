#!/bin/bash
# worktree-manager.sh — Claude Harness Kit Worktree Lifecycle Manager
# Usage: worktree-manager.sh <create|enter|cleanup|list|delete> [name]

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKTREE_BASE="${PLUGIN_ROOT}/../.claude/data/worktrees"
MAP_FILE="${PLUGIN_ROOT}/../.claude/data/worktrees/.worktree-map.json"

mkdir -p "$WORKTREE_BASE"

# ── Helpers ────────────────────────────────────────────────────────────────────

log_info()  { echo "ℹ️  $*" >&2; }
log_ok()    { echo "✅ $*" >&2; }
log_warn()  { echo "⚠️  $*" >&2; }
log_error() { echo "❌ $*" >&2; }

init_map() {
  if [[ ! -f "$MAP_FILE" ]]; then
    echo '{}' > "$MAP_FILE"
  fi
}

read_map() { cat "$MAP_FILE" 2>/dev/null || echo '{}'; }

write_map() {
  local tmp; tmp=$(mktemp)
  cat > "$tmp"
  mv "$tmp" "$MAP_FILE"
  chmod 600 "$MAP_FILE"
}

get_main_branch() {
  git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "master"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_create() {
  local name="${1:-}" agent_name="${2:-}"
  init_map

  if [[ -z "$name" ]]; then
    name="wt-$(date +%Y%m%d-%H%M%S)"
  fi

  local wt_path="${WORKTREE_BASE}/${name}"

  if [[ -d "$wt_path" ]]; then
    log_error "Worktree already exists: $name"
    exit 1
  fi

  local branch="worktree/${name}"
  local main_branch
  main_branch=$(get_main_branch)

  log_info "Creating worktree '$name' from '$main_branch'..."

  if ! git worktree add -b "$branch" "$wt_path" 2>/dev/null; then
    log_error "git worktree add failed. Is this a git repository?"
    exit 1
  fi

  # Sync CLAUDE.md and .claude/ directory
  sync_context_to_worktree "$wt_path"

  # Record in map
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local map
  map=$(read_map)
  local entry
  entry=$(printf '{"path":"%s","branch":"%s","agent":"%s","created":"%s","status":"active"}' \
    "$wt_path" "$branch" "${agent_name:-system}" "$ts")
  local new_map
  new_map=$(echo "$map" | python3 -c "
import json,sys
d=json.load(sys.stdin)
d['$name']=json.loads('$entry')
print(json.dumps(d,indent=2))
" 2>/dev/null || echo "$map")
  echo "$new_map" | write_map

  log_ok "Worktree created: $name → $wt_path (branch: $branch)"
  echo "$wt_path"
}

sync_context_to_worktree() {
  local wt_path="$1"

  # Sync CLAUDE.md
  if [[ -f "${PLUGIN_ROOT}/CLAUDE.md" ]]; then
    cp "${PLUGIN_ROOT}/CLAUDE.md" "${wt_path}/CLAUDE.md"
    log_info "Synced CLAUDE.md"
  fi

  # Sync .claude/ directory
  if [[ -d "${PLUGIN_ROOT}/.claude" ]]; then
    mkdir -p "${wt_path}/.claude"
    # Sync non-machine-specific files
    for f in rules knowledge settings.local.json; do
      if [[ -f "${PLUGIN_ROOT}/.claude/$f" ]]; then
        cp "${PLUGIN_ROOT}/.claude/$f" "${wt_path}/.claude/$f"
      fi
      if [[ -d "${PLUGIN_ROOT}/.claude/$f" ]]; then
        mkdir -p "${wt_path}/.claude/$f"
        cp -r "${PLUGIN_ROOT}/.claude/$f/"* "${wt_path}/.claude/$f/" 2>/dev/null || true
      fi
    done
    log_info "Synced .claude/ context"
  fi
}

cmd_enter() {
  local name="$1"
  init_map

  local wt_path
  wt_path=$(echo "$(read_map)" | python3 -c "
import json,sys
d=json.load(sys.stdin)
name='$name'
if name not in d:
    print('')
    sys.exit(1)
print(d[name].get('path',''))
" 2>/dev/null) || true

  if [[ -z "$wt_path" || ! -d "$wt_path" ]]; then
    log_error "Worktree not found: $name"
    exit 1
  fi

  log_ok "Worktree path: $wt_path"
  echo "$wt_path"
}

cmd_cleanup() {
  init_map

  local expired
  expired=$(echo "$(read_map)" | python3 -c "
import json,sys,json as m,datetime
d=json.load(sys.stdin)
now=datetime.datetime.utcnow()
cutoff=datetime.timedelta(days=7)
expired=[]
for k,v in d.items():
    try:
        created=datetime.datetime.fromisoformat(v['created'].replace('Z','+00:00'))
        if (now-created.replace(tzinfo=now.tzinfo))>cutoff and v.get('status')=='active':
            expired.append(k)
    except:
        pass
print(json.dumps(expired))
" 2>/dev/null) || echo "[]"

  if [[ "$expired" == "[]" ]]; then
    log_ok "No expired worktrees to clean up"
    return 0
  fi

  log_info "Expired worktrees: $expired"
  for wt_name in $(echo "$expired" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
    cmd_delete "$wt_name"
  done
}

cmd_delete() {
  local name="$1"
  init_map

  local wt_path
  wt_path=$(echo "$(read_map)" | python3 -c "
import json,sys
d=json.load(sys.stdin)
name='$name'
if name not in d:
    sys.exit(1)
print(d[name].get('path',''))
" 2>/dev/null) || true

  if [[ -z "$wt_path" || ! -d "$wt_path" ]]; then
    log_error "Worktree not found or already removed: $name"
    # Still clean up map entry
    local map
    map=$(read_map)
    echo "$map" | python3 -c "
import json,sys
d=json.load(sys.stdin)
d.pop('$name', None)
print(json.dumps(d,indent=2))
" | write_map
    return 1
  fi

  # Remove worktree
  log_info "Removing worktree: $name at $wt_path"
  git worktree remove "$wt_path" 2>/dev/null || git worktree remove --force "$wt_path" 2>/dev/null || true

  # Remove from map
  local map
  map=$(read_map)
  echo "$map" | python3 -c "
import json,sys
d=json.load(sys.stdin)
d.pop('$name', None)
print(json.dumps(d,indent=2))
" | write_map

  log_ok "Worktree removed: $name"
}

cmd_list() {
  init_map

  local map
  map=$(read_map)

  if [[ "$map" == "{}" ]]; then
    log_info "No worktrees managed by CHK"
    return 0
  fi

  echo "CHK-managed Worktrees:"
  echo "$map" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if not d:
    print('  (none)')
for name, info in sorted(d.items()):
    status = info.get('status','?')
    agent = info.get('agent','?')
    path = info.get('path','')
    branch = info.get('branch','')
    print(f'  [{status}] {name}')
    print(f'    path: {path}')
    print(f'    branch: {branch}')
    print(f'    agent: {agent}')
"
}

# ── Main ──────────────────────────────────────────────────────────────────────

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  create)    cmd_create "$@" ;;
  enter)     cmd_enter "$@" ;;
  cleanup)   cmd_cleanup ;;
  list)      cmd_list ;;
  delete)    [[ $# -ge 1 ]] || { log_error "Usage: worktree-manager.sh delete <name>"; exit 1; }; cmd_delete "$1" ;;
  *)
    echo "Usage: worktree-manager.sh <create|enter|cleanup|list|delete> [args]"
    echo ""
    echo "Commands:"
    echo "  create [name] [agent]  — Create a new worktree"
    echo "  enter <name>           — Get worktree path"
    echo "  cleanup                — Remove worktrees inactive >7 days"
    echo "  list                   — List all managed worktrees"
    echo "  delete <name>          — Force-remove a worktree"
    exit 1
    ;;
esac