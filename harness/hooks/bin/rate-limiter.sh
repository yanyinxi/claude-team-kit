#!/bin/bash
# rate-limiter.sh — Claude Code API Rate Limiter (Sliding Window)
# 设计：永远 exit 0，rate limit 超出仅记录到 stderr，不阻断工具调用
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RATE_DIR="${PLUGIN_ROOT}/../.claude/data/rate-limits"
mkdir -p "$RATE_DIR"
STATE_FILE="${RATE_DIR}/state.json"

# ── Rate Limits ────────────────────────────────────────────────────────────────
LIMIT_MIN=30
LIMIT_HR=500
LIMIT_DAY=5000

# ── Helpers ──────────────────────────────────────────────────────────────────

log_warn() { echo "⚠️  rate-limiter: $*" >&2; }

load_state() {
    if [[ -f "$STATE_FILE" ]]; then
        python3 -c "
import json, sys
try:
    with open('${STATE_FILE}') as f:
        print(f.read(), end='')
except Exception:
    print('{\"minute\":[],\"hour\":[],\"day\":[]}', end='')
" 2>/dev/null || echo '{"minute":[],"hour":[],"day":[]}'
    else
        echo '{"minute":[],"hour":[],"day":[]}'
    fi
}

save_state() {
    python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
with open('${STATE_FILE}', 'w') as f:
    json.dump(d, f)
" <<< "$1" 2>/dev/null || true
}

clean_old() {
    python3 -c "
import json, sys, time as _t
now_ms = int(sys.argv[1])
window_min = 60 * 1000
window_hr  = 3600 * 1000
window_day = 86400 * 1000
d = json.loads(sys.stdin.read())
for key, window in [('minute', window_min), ('hour', window_hr), ('day', window_day)]:
    d[key] = [t for t in d.get(key, []) if now_ms - t < window]
print(json.dumps(d), end='')
" "$1" 2>/dev/null || echo '{"minute":[],"hour":[],"day":[]}'
}

# ── Main ──────────────────────────────────────────────────────────────────────

NOW_MS=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null) || NOW_MS=0
STATE=$(load_state)
STATE=$(clean_old "$NOW_MS" <<< "$STATE")

CNT_MIN=$(python3 -c "import json; d=json.loads('${STATE}'); print(len(d.get('minute',[])))" 2>/dev/null) || CNT_MIN=0
CNT_HR=$(python3 -c "import json; d=json.loads('${STATE}'); print(len(d.get('hour',[])))" 2>/dev/null) || CNT_HR=0
CNT_DAY=$(python3 -c "import json; d=json.loads('${STATE}'); print(len(d.get('day',[])))" 2>/dev/null) || CNT_DAY=0

NEW_STATE=$(python3 -c "
import json, sys, time as _t
now = int(_t.time() * 1000)
d = json.loads('${STATE}')
for key in ['minute', 'hour', 'day']:
    d.setdefault(key, []).append(now)
print(json.dumps(d), end='')
" 2>/dev/null) || NEW_STATE="$STATE"

save_state "$NEW_STATE"

(( CNT_MIN >= LIMIT_MIN )) && log_warn "Minute limit: $CNT_MIN/$LIMIT_MIN"
(( CNT_HR  >= LIMIT_HR  )) && log_warn "Hour limit: $CNT_HR/$LIMIT_HR"
(( CNT_DAY >= LIMIT_DAY )) && log_warn "Day limit: $CNT_DAY/$LIMIT_DAY"

exit 0
