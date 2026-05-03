#!/usr/bin/env bash
# =============================================================================
# 回滚状态监控脚本 — monitor-rollback.sh
# =============================================================================
# 监控回滚机制状态，定期检查观察期到期的提案。
#
# 用法:
#   ./monitor-rollback.sh status    # 查看回滚系统状态
#   ./monitor-rollback.sh check     # 执行一次回滚检查
#   ./monitor-rollback.sh history   # 查看回滚历史
#   ./monitor-rollback.sh health    # 查看所有提案的健康状态
#   ./monitor-rollback.sh daemon    # 启动持续监控（每 N 分钟检查一次）
#   ./monitor-rollback.sh install   # 安装到 crontab 定时任务
#
# 依赖:
#   - daemon.py run_rollback_check()
#   - rollback.py run_rollback_check()
#   - instinct-record.json (本能记录)
#   - proposal_history.json (提案历史)
# =============================================================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目根目录（支持环境变量或推断）
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EVOLVE_DAEMON_DIR="${PROJECT_ROOT}/harness/evolve-daemon"
DATA_DIR="${PROJECT_ROOT}/.claude/data"
INSTINCT_FILE="${PROJECT_ROOT}/harness/instinct/instinct-record.json"
HISTORY_FILE="${DATA_DIR}/proposal_history.json"

# Python 解释器
PYTHON="${PYTHON:-python3}"

# =============================================================================
# 工具函数
# =============================================================================

log() {
    local level="$1"
    local msg="$2"
    local color="$NC"
    case "$level" in
        info)  color="$BLUE" ;;
        ok)    color="$GREEN" ;;
        warn)  color="$YELLOW" ;;
        error) color="$RED" ;;
    esac
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $msg${NC}"
}

section() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# =============================================================================
# 1. 状态概览
# =============================================================================

cmd_status() {
    section "回滚系统状态概览"

    # 1.1 提案历史统计
    log "info" "提案历史: ${HISTORY_FILE}"
    if [[ -f "$HISTORY_FILE" ]]; then
        local total=$(python3 -c "import json; h=json.load(open('$HISTORY_FILE')); print(len(h))" 2>/dev/null || echo "0")
        local applied=$(python3 -c "import json; h=json.load(open('$HISTORY_FILE')); print(sum(1 for p in h if p.get('status')=='applied'))" 2>/dev/null || echo "0")
        local rolled_back=$(python3 -c "import json; h=json.load(open('$HISTORY_FILE')); print(sum(1 for p in h if p.get('status')=='rolled_back'))" 2>/dev/null || echo "0")
        local consolidated=$(python3 -c "import json; h=json.load(open('$HISTORY_FILE')); print(sum(1 for p in h if p.get('status')=='consolidated'))" 2>/dev/null || echo "0")
        local paused=$(python3 -c "import json; h=json.load(open('$HISTORY_FILE')); print(sum(1 for p in h if p.get('status')=='paused'))" 2>/dev/null || echo "0")

        echo ""
        echo -e "  总提案数:     ${BLUE}${total}${NC}"
        echo -e "  观察中:       ${YELLOW}${applied}${NC}"
        echo -e "  已固化:       ${GREEN}${consolidated}${NC}"
        echo -e "  已回滚:       ${RED}${rolled_back}${NC}"
        echo -e "  系统暂停:     ${RED}${paused}${NC}"

        if (( total > 0 )); then
            local rollback_rate
            rollback_rate=$(python3 -c "print(round(${rolled_back}/${total}*100, 1))" 2>/dev/null || echo "N/A")
            echo -e "  回滚率:       ${BLUE}${rollback_rate}%${NC}"
        fi
    else
        log "warn" "提案历史文件不存在: ${HISTORY_FILE}"
    fi

    # 1.2 回滚记录（instinct）
    echo ""
    log "info" "本能记录中的回滚事件:"
    if [[ -f "$INSTINCT_FILE" ]]; then
        local rb_count
        rb_count=$(python3 -c "import json; d=json.load(open('$INSTINCT_FILE')); print(sum(1 for r in d.get('records',[]) if r.get('source')=='rollback-event'))" 2>/dev/null || echo "0")
        echo -e "  回滚记录数: ${RED}${rb_count}${NC}"

        # 最近 3 条回滚记录
        python3 -c "
import json, sys
from datetime import datetime
try:
    d = json.load(open('$INSTINCT_FILE'))
    records = [r for r in d.get('records', []) if r.get('source') == 'rollback-event']
    records = sorted(records, key=lambda r: r.get('created_at', ''), reverse=True)[:3]
    for r in records:
        ts = r.get('created_at', 'unknown')[:19]
        conf = r.get('confidence', 0)
        pattern = r.get('pattern', 'unknown')[:40]
        print(f'    {ts} | conf={conf:.2f} | {pattern}')
except Exception as e:
    print(f'    Error: {e}')
" 2>/dev/null || true
    else
        log "warn" "本能记录文件不存在: ${INSTINCT_FILE}"
    fi

    # 1.3 观察期即将到期的提案
    echo ""
    log "info" "观察期即将到期的提案（7天内）:"
    if [[ -f "$HISTORY_FILE" ]]; then
        python3 -c "
import json, sys
from datetime import datetime, timedelta
try:
    now = datetime.now()
    d7 = (now + timedelta(days=7)).isoformat()
    h = json.load(open('$HISTORY_FILE'))
    urgent = [p for p in h if p.get('status') == 'applied' and p.get('observation_end', '') < d7]
    if urgent:
        for p in urgent:
            end = p.get('observation_end', 'unknown')[:19]
            target = p.get('target_file', 'unknown')[:30]
            print(f'    {end} | {target}')
    else:
        print('    无')
except Exception as e:
    print(f'    Error: {e}')
" 2>/dev/null || log "warn" "无法解析提案历史"
    fi

    # 1.4 配置检查
    echo ""
    log "info" "回滚配置:"
    if [[ -f "${EVOLVE_DAEMON_DIR}/config.yaml" ]]; then
        python3 -c "
import yaml, sys
try:
    with open('${EVOLVE_DAEMON_DIR}/config.yaml') as f:
        c = yaml.safe_load(f)
    obs = c.get('observation', {})
    rb = c.get('rollback', {})
    print(f'  观察期天数:       {obs.get(\"days\", \"N/A\")} 天')
    print(f'  检查间隔:         {obs.get(\"check_interval_hours\", \"N/A\")} 小时')
    print(f'  自动回滚:         {rb.get(\"auto_enabled\", \"N/A\")}')
    print(f'  回滚前观察:       {rb.get(\"observe_before_rollback_hours\", \"N/A\")} 小时')
    min_sr = obs.get('metrics', {}).get('min_success_rate', 0.8)
    print(f'  最低成功率阈值:   {min_sr:.0%}')
    max_cr = obs.get('metrics', {}).get('max_correction_rate', 0.2)
    print(f'  最高纠正率阈值:   {max_cr:.0%}')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null || log "warn" "无法解析配置文件"
    fi
}

# =============================================================================
# 2. 执行回滚检查
# =============================================================================

cmd_check() {
    section "执行回滚检查"

    log "info" "调用 daemon.py rollback-check..."
    cd "$PROJECT_ROOT"
    "$PYTHON" -m harness.evolve_daemon.daemon rollback-check 2>/dev/null || \
    "$PYTHON" "${EVOLVE_DAEMON_DIR}/daemon.py" rollback-check

    local exit_code=$?

    if (( exit_code == 0 )); then
        log "ok" "回滚检查完成"
    else
        log "error" "回滚检查失败 (exit=${exit_code})"
    fi

    return $exit_code
}

# =============================================================================
# 3. 回滚历史
# =============================================================================

cmd_history() {
    section "回滚历史"

    if [[ ! -f "$HISTORY_FILE" ]]; then
        log "warn" "提案历史文件不存在: ${HISTORY_FILE}"
        return 1
    fi

    python3 -c "
import json, sys
from datetime import datetime

h = json.load(open('$HISTORY_FILE'))

# 回滚记录
rolled = [p for p in h if p.get('status') == 'rolled_back']
rolled = sorted(rolled, key=lambda p: p.get('rolled_back_at', ''), reverse=True)

print(f'\n  共 {len(rolled)} 条回滚记录:\n')
print(f'  {\"时间\":<20} {\"ID\":<16} {\"目标文件\":<35} {\"原因\"}')
print(f'  {\"-\"*20} {\"-\"*16} {\"-\"*35} {\"-\"*30}')

for p in rolled[:20]:
    ts = p.get('rolled_back_at', 'unknown')[:19]
    pid = p.get('id', 'unknown')[:14]
    target = p.get('target_file', 'unknown')[:33]
    reason = (p.get('rollback_reason', '') or p.get('reason', ''))[:28]
    print(f'  {ts:<20} {pid:<16} {target:<35} {reason}')

# 固化的记录
consolidated = [p for p in h if p.get('status') == 'consolidated']
print(f'\n  共 {len(consolidated)} 条固化记录:\n')
print(f'  {\"时间\":<20} {\"ID\":<16} {\"目标文件\":<35} {\"应用时间\"}')
print(f'  {\"-\"*20} {\"-\"*16} {\"-\"*35} {\"-\"*20}')
for p in consolidated[-10:]:
    ts = p.get('consolidated_at', 'unknown')[:19]
    pid = p.get('id', 'unknown')[:14]
    target = p.get('target_file', 'unknown')[:33]
    applied = p.get('applied_at', 'unknown')[:19]
    print(f'  {ts:<20} {pid:<16} {target:<35} {applied}')
" 2>/dev/null || log "error" "无法解析提案历史"
}

# =============================================================================
# 4. 健康状态
# =============================================================================

cmd_health() {
    section "提案健康状态"

    if [[ ! -f "$HISTORY_FILE" ]]; then
        log "warn" "提案历史文件不存在: ${HISTORY_FILE}"
        return 1
    fi

    python3 << 'PYEOF'
import json, sys
from datetime import datetime, timedelta

try:
    h = json.load(open(""" + f"'{HISTORY_FILE}'" + """))
    now = datetime.now()
    applied = [p for p in h if p.get("status") == "applied"]

    if not applied:
        print("\n  当前无观察中的提案\n")
        sys.exit(0)

    print(f"\n  当前有 {len(applied)} 个提案处于观察期:\n")
    print(f"  {'ID':<16} {'目标':<30} {'观察结束':<20} {'剩余':<8} {'状态'}")
    print(f"  {'-'*16} {'-'*30} {'-'*20} {'-'*8} {'-'*10}")

    for p in sorted(applied, key=lambda x: x.get("observation_end", "")):
        pid = p.get("id", "unknown")[:14]
        target = p.get("target_file", "unknown")[:28]
        end_str = p.get("observation_end", "unknown")[:19]
        try:
            end_dt = datetime.fromisoformat(p.get("observation_end", datetime.now().isoformat()))
            days_left = (end_dt - now).days
            if days_left < 0:
                remaining = f"已到期{abs(days_left)}天"
                status = "待检查"
            elif days_left == 0:
                remaining = "<1天"
                status = "即将到期"
            else:
                remaining = f"{days_left}天"
                status = "观察中"
        except Exception:
            remaining = "?"
            status = "未知"

        color_flag = ""
        if "待检查" in status or "到期" in status:
            color_flag = " [需处理]"
        print(f"  {pid:<16} {target:<30} {end_str:<20} {remaining:<8} {status}{color_flag}")

    # 显示最近的回滚和固化
    rb = [p for p in h if p.get("status") == "rolled_back"][-5:]
    if rb:
        print(f"\n  最近回滚 ({len(rb)} 条):")
        for p in rb:
            ts = p.get("rolled_back_at", "unknown")[:19]
            pid = p.get("id", "unknown")[:14]
            target = p.get("target_file", "unknown")[:28]
            print(f"    {ts} | {pid} | {target}")

except Exception as e:
    print(f"  Error: {e}")
PYEOF
}

# =============================================================================
# 5. 持续监控模式
# =============================================================================

cmd_daemon() {
    local interval="${1:-60}"  # 默认 60 分钟

    section "启动持续监控模式"
    log "info" "监控间隔: ${interval} 分钟"
    log "info" "每 ${interval} 分钟检查一次回滚状态"
    log "info" "按 Ctrl+C 停止"
    echo ""

    # 安装信号处理
    trap 'log "info" "停止监控..."; exit 0' INT TERM

    while true; do
        local ts
        ts=$(date '+%Y-%m-%d %H:%M:%S')
        echo -e "${BLUE}[${ts}]${NC} 检查回滚状态..."

        # 执行检查
        "$0" check > /dev/null 2>&1 || true

        # 短暂显示状态
        "$0" status | head -20

        echo ""
        log "info" "下次检查在 ${interval} 分钟后..."
        sleep "${interval}m"
    done
}

# =============================================================================
# 6. 安装到 crontab
# =============================================================================

cmd_install() {
    section "安装到 crontab 定时任务"

    local interval="${1:-360}"  # 默认 6 小时

    local cron_entry="0 */$((interval / 60)) * * * cd $PROJECT_ROOT && $PYTHON $EVOLVE_DAEMON_DIR/daemon.py rollback-check >> $DATA_DIR/logs/rollback-check.log 2>&1"

    echo ""
    echo "将添加以下 crontab 条目:"
    echo "  $cron_entry"
    echo ""
    read -p "确认安装? (y/N) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # 确保日志目录存在
        mkdir -p "$DATA_DIR/logs"

        # 添加到 crontab
        (crontab -l 2>/dev/null | grep -v "rollback-check"; echo "$cron_entry") | crontab -
        log "ok" "已安装 crontab 定时任务 (每 ${interval} 分钟)"

        # 显示当前 crontab
        echo ""
        echo "当前 crontab:"
        crontab -l | grep rollback-check || true
    else
        log "info" "已取消"
    fi
}

# =============================================================================
# 7. 仪表盘
# =============================================================================

cmd_dashboard() {
    section "回滚系统仪表盘"

    echo ""

    # 关键指标
    if [[ -f "$HISTORY_FILE" ]]; then
        python3 << PYEOF
import json
from datetime import datetime, timedelta

h = json.load(open('$HISTORY_FILE'))
total = len(h)
applied = sum(1 for p in h if p.get('status') == 'applied')
rolled = sum(1 for p in h if p.get('status') == 'rolled_back')
cons = sum(1 for p in h if p.get('status') == 'consolidated')

now = datetime.now()
d7 = (now + timedelta(days=7)).isoformat()
urgent = [p for p in h if p.get('status') == 'applied' and p.get('observation_end', '') < d7]

rate = round(rolled / total * 100, 1) if total > 0 else 0
health = "HEALTHY" if rate < 20 else "WARNING" if rate < 40 else "CRITICAL"

print(f"  回滚率:     {rate}%  (目标 < 20%)")
print(f"  系统状态:   {health}")
print(f"  观察中:     {applied}")
print(f"  已固化:     {cons}")
print(f"  待处理:     {len(urgent)} (7天内到期)")
PYEOF
    fi

    echo ""
    echo "  最新 5 条记录:"
    if [[ -f "$HISTORY_FILE" ]]; then
        python3 -c "
import json
h = json.load(open('$HISTORY_FILE'))
for p in h[-5:]:
    status_icon = {'applied': '⏳', 'consolidated': '✅', 'rolled_back': '🔄', 'paused': '⏸'}.get(p.get('status'), '❓')
    ts = p.get('applied_at', 'unknown')[:10]
    target = p.get('target_file', 'unknown')[:25]
    print(f'    {status_icon} {p[\"status\"]:<14} {ts}  {target}')
" 2>/dev/null || true
    fi

    echo ""
}

# =============================================================================
# 主入口
# =============================================================================

main() {
    local cmd="${1:-dashboard}"

    case "$cmd" in
        status|dashboard)
            cmd_status
            ;;
        check)
            cmd_check
            ;;
        history)
            cmd_history
            ;;
        health)
            cmd_health
            ;;
        daemon|monitor)
            local interval="${2:-60}"
            cmd_daemon "$interval"
            ;;
        install)
            local interval="${2:-360}"
            cmd_install "$interval"
            ;;
        help|--help|-h)
            echo "回滚状态监控脚本"
            echo ""
            echo "用法: $0 <command> [options]"
            echo ""
            echo "命令:"
            echo "  status    查看回滚系统状态概览"
            echo "  check     执行一次回滚检查"
            echo "  history   查看回滚历史"
            echo "  health    查看所有提案的健康状态"
            echo "  daemon    启动持续监控模式"
            echo "  install   安装到 crontab 定时任务"
            echo "  dashboard 仪表盘视图"
            echo ""
            echo "示例:"
            echo "  $0 status           # 查看状态"
            echo "  $0 check            # 执行检查"
            echo "  $0 daemon 30        # 每 30 分钟监控一次"
            echo "  $0 install 360      # 安装为 6 小时定时任务"
            ;;
        *)
            log "error" "未知命令: $cmd"
            echo "运行 '$0 help' 查看帮助"
            exit 1
            ;;
    esac
}

main "$@"