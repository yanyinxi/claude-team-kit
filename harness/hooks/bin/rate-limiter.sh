#!/bin/bash
# rate-limiter.sh — Claude Code API Rate Limiter (Sliding Window)
# 设计：永远 exit 0，rate limit 超出仅记录到 stderr，不阻断工具调用
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RATE_DIR="${PLUGIN_ROOT}/../../.claude/data/rate-limits"
mkdir -p "$RATE_DIR"
STATE_FILE="${RATE_DIR}/state.json"

# ── Rate Limits ────────────────────────────────────────────────────────────────
LIMIT_MIN=30
LIMIT_HR=500
LIMIT_DAY=5000

# ── Helpers ──────────────────────────────────────────────────────────────────

log_warn() { echo "⚠️  rate-limiter: $*" >&2; }

# ── Safe JSON validate ────────────────────────────────────────────────────────
is_valid_json() {
    python3 -c "import json, sys; json.load(sys.stdin)" <<< "$1" &>/dev/null
}

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

# clean_old: 第一行 stdin=JSON, 后续行 stdin+argv 混用导致冲突
# 统一改为全部从 stdin 读取：timestamp\nJSON
clean_old() {
    python3 << 'PYEOF'
import json, sys
try:
    first = sys.stdin.readline().strip()
    now_ms = int(first) if first else 0
    d = json.loads(sys.stdin.read())
    for key, window in [('minute', 60*1000), ('hour', 3600*1000), ('day', 86400*1000)]:
        d[key] = [t for t in d.get(key, []) if now_ms - t < window]
    print(json.dumps(d), end='')
except Exception:
    print('{"minute":[],"hour":[],"day":[]}', end='')
PYEOF
}

# 统一计数函数：key 作为第一行写入 stdin，Python 读取后输出计数
count_from_state() {
    python3 << 'PYEOF'
import json, sys
try:
    key = sys.stdin.readline().strip()
    d = json.loads(sys.stdin.read())
    print(len(d.get(key, [])))
except Exception:
    print(0)
PYEOF
}

# 生成新状态：追加时间戳到 minute/hour/day 三个窗口
build_new_state() {
    python3 << 'PYEOF'
import json, sys, time as _t
try:
    d = json.loads(sys.stdin.read())
    now = int(_t.time() * 1000)
    for key in ['minute', 'hour', 'day']:
        d.setdefault(key, []).append(now)
    print(json.dumps(d), end='')
except Exception:
    print('{"minute":[],"hour":[],"day":[]}', end='')
PYEOF
}

# ── Main ──────────────────────────────────────────────────────────────────────

NOW_MS=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null) || NOW_MS=0

# 加载状态并清理过期记录（timestamp 作为首行传入 stdin）
STATE=$(load_state)
STATE=$(echo "$NOW_MS" | clean_old <<< "$STATE")

# 验证清理后的状态是否为有效 JSON，无效则使用默认空状态
if ! is_valid_json "$STATE"; then
    log_warn "Invalid state JSON, using empty state"
    STATE='{"minute":[],"hour":[],"day":[]}'
fi

# 提取三个窗口的计数（key 作为首行传入 stdin）
CNT_MIN=$(echo "minute"  | count_from_state <<< "$STATE")
CNT_HR=$(echo "hour"    | count_from_state <<< "$STATE")
CNT_DAY=$(echo "day"    | count_from_state <<< "$STATE")

# 生成新状态（追加当前时间戳）
NEW_STATE=$(echo "$STATE" | build_new_state)

# 保存新状态
save_state "$NEW_STATE"

# ── 预防性警告 (80% 阈值) ───────────────────────────────────────────────────
WARN_MIN=$((LIMIT_MIN * 80 / 100))
WARN_HR=$((LIMIT_HR * 80 / 100))
WARN_DAY=$((LIMIT_DAY * 80 / 100))

(( CNT_MIN >= WARN_MIN && CNT_MIN < LIMIT_MIN )) && log_warn "Minute warning: $CNT_MIN/$LIMIT_MIN (80%)"
(( CNT_HR  >= WARN_HR  && CNT_HR  < LIMIT_HR  )) && log_warn "Hour warning: $CNT_HR/$LIMIT_HR (80%)"
(( CNT_DAY >= WARN_DAY && CNT_DAY < LIMIT_DAY )) && log_warn "Day warning: $CNT_DAY/$LIMIT_DAY (80%)"

# 超限警告
(( CNT_MIN >= LIMIT_MIN )) && log_warn "Minute limit EXCEEDED: $CNT_MIN/$LIMIT_MIN"
(( CNT_HR  >= LIMIT_HR  )) && log_warn "Hour limit EXCEEDED: $CNT_HR/$LIMIT_HR"
(( CNT_DAY >= LIMIT_DAY )) && log_warn "Day limit EXCEEDED: $CNT_DAY/$LIMIT_DAY"

exit 0