#!/usr/bin/env python3
"""
进化编排器 — Stop Hook → 汇总数据 → 检查触发条件 → 安全门禁 → 调度进化

职责:
  1. 读取所有 data/*.jsonl 的最新统计
  2. 计算各维度指标和触发优先级
  3. 检查安全门禁（熔断器、限流器、数据充分性）
  4. 输出结构化决策到 stdout（Claude Code 读取）
  5. 如果触发条件满足，调用进化引擎

用法（作为 Stop hook 调用）:
  echo '{"session_id":"abc"}' | python3 .claude/lib/evolution_orchestrator.py

用法（CLI）:
  python3 .claude/lib/evolution_orchestrator.py check   # 检查但不执行
  python3 .claude/lib/evolution_orchestrator.py run     # 检查并执行
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


def _find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


# ═══════════════════════════════════════════════════════════════
# 数据聚合
# ═══════════════════════════════════════════════════════════════

def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def aggregate_session_data(project_root: str = None) -> Dict[str, Any]:
    """
    汇总所有 data/*.jsonl 的统计，生成统一的会话摘要。
    """
    root = _find_root() if project_root is None else Path(project_root)
    data_dir = root / ".claude" / "data"

    # Skill 统计
    skill_records = _read_jsonl(data_dir / "skill_usage.jsonl")
    skill_counts: Dict[str, int] = {}
    for r in skill_records:
        skill = r.get("skill", "unknown")
        skill_counts[skill] = skill_counts.get(skill, 0) + 1

    # Agent 统计
    agent_records = _read_jsonl(data_dir / "agent_performance.jsonl")
    agent_data: Dict[str, list] = {}
    for r in agent_records:
        agent = r.get("agent", "unknown")
        agent_data.setdefault(agent, []).append(r)

    # 失败统计
    failure_records = _read_jsonl(data_dir / "tool_failures.jsonl")
    failures_by_tool: Dict[str, int] = {}
    for r in failure_records:
        tool = r.get("tool", "unknown")
        failures_by_tool[tool] = failures_by_tool.get(tool, 0) + 1

    # 违规统计
    violation_records = _read_jsonl(data_dir / "rule_violations.jsonl")
    violations_by_rule: Dict[str, int] = {}
    violations_by_severity: Dict[str, int] = {}
    for r in violation_records:
        rule = r.get("rule", "unknown")
        sev = r.get("severity", "low")
        violations_by_rule[rule] = violations_by_rule.get(rule, 0) + 1
        violations_by_severity[sev] = violations_by_severity.get(sev, 0) + 1

    # 反馈信号
    pending = _read_json(data_dir / "pending_evolution.json")
    pending_signals = pending.get("feedback_signals", [])

    # 熔断器状态
    metrics = _read_json(data_dir / "evolution_metrics.json")
    circuit_breaker = metrics.get("circuit_breaker", {})

    # 进化历史
    history = _read_jsonl(data_dir / "evolution_history.jsonl")
    evo_history = history if isinstance(history, list) else []

    return {
        "skills_used": skill_counts,
        "total_skill_calls": sum(skill_counts.values()),
        "agents_used": list(agent_data.keys()),
        "agent_tasks": {a: len(v) for a, v in agent_data.items()},
        "agent_records": {a: v for a, v in agent_data.items()},
        "total_agent_tasks": sum(len(v) for v in agent_data.values()),
        "total_failures": len(failure_records),
        "failure_records": failure_records,
        "failures_by_tool": failures_by_tool,
        "total_violations": len(violation_records),
        "violations_by_rule": violations_by_rule,
        "violations_by_severity": violations_by_severity,
        "pending_signals": len(pending_signals),
        "signal_types": [s.get("type", "unknown") for s in pending_signals],
        "circuit_breaker_status": circuit_breaker,
        "total_evolutions": len(evo_history),
        "pending_confirmations": sum(1 for h in evo_history if h.get("confirmation_result") is None),
    }


# ═══════════════════════════════════════════════════════════════
# 优先级计算（设计文档 4.2）
# ═══════════════════════════════════════════════════════════════

def _get_trigger_count(project_root: Path, dimension: str, target: str) -> int:
    """获取某维度:目标的历史触发次数（用于优先级升级）。"""
    metrics_file = project_root / ".claude" / "data" / "evolution_metrics.json"
    if not metrics_file.exists():
        return 0
    try:
        metrics = json.loads(metrics_file.read_text())
        trigger_counts = metrics.get("trigger_counts", {})
        key = f"{dimension}:{target}"
        return trigger_counts.get(key, 0)
    except (json.JSONDecodeError, OSError):
        return 0


def _increment_trigger_count(project_root: Path, dimension: str, target: str):
    """递增某维度:目标的触发计数。"""
    metrics_file = project_root / ".claude" / "data" / "evolution_metrics.json"
    try:
        metrics = {}
        if metrics_file.exists():
            metrics = json.loads(metrics_file.read_text())
    except (json.JSONDecodeError, OSError):
        metrics = {}

    metrics.setdefault("trigger_counts", {})
    key = f"{dimension}:{target}"
    metrics["trigger_counts"][key] = metrics["trigger_counts"].get(key, 0) + 1
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))


def compute_priority(dimension: str, metrics: dict) -> float:
    """
    计算进化优先级，返回值 0.0-1.0，> 0.5 触发进化。
    """
    if dimension == "skill":
        call_count = metrics.get("total_calls", 0)
        success_rate = metrics.get("success_rate", 1.0)
        if call_count < 10:
            return 0.0
        return min(1.0, (1 - success_rate) * call_count / 10)

    elif dimension == "agent":
        avg_turns = metrics.get("avg_turns", 10)
        baseline = metrics.get("baseline_turns", 10)
        failure_rate = metrics.get("failure_rate", 0)
        task_count = metrics.get("similar_tasks", 0)
        if task_count < 5:
            return 0.0
        turn_penalty = max(0, (avg_turns - baseline) / baseline)
        failure_penalty = failure_rate / 0.3 if failure_rate > 0.3 else 0
        return min(1.0, turn_penalty * 0.5 + failure_penalty * 0.5)

    elif dimension == "rule":
        violation_count = metrics.get("violation_count", 0)
        if violation_count < 3:
            return 0.0
        return min(1.0, violation_count / 3 * 0.5)

    elif dimension == "memory":
        signal_count = metrics.get("pending_signals", 0)
        if signal_count == 0:
            return 0.0
        return min(1.0, signal_count * 0.5)

    return 0.0


def compute_escalated_priority(base_priority: float, trigger_count: int) -> float:
    """
    计算优先级升级。

    规则（基于历史触发次数）：
    - trigger_count=0（第1次触发）：正常优先级
    - trigger_count=1（第2次触发）：优先级 × 1.3（如果 base > 0）
    - trigger_count>=2（第3次及以上）：强制执行 priority = 1.0（如果 base > 0）

    注意：如果 base_priority 本身就是 0（未达到触发阈值），即使升级也不应触发。

    Args:
        base_priority: 基础优先级（0-1）
        trigger_count: 历史触发次数（从 evolution_metrics.json 读取）

    Returns:
        升级后的优先级
    """
    # 如果基础优先级为 0，不触发进化
    if base_priority <= 0:
        return 0.0

    if trigger_count == 0:
        # 第 1 次触发，正常优先级
        return base_priority
    elif trigger_count == 1:
        # 第 2 次触发，优先级提升 30%
        return min(1.0, base_priority * 1.3)
    else:
        # 第 3 次及以上，强制执行
        return 1.0
    """
    计算进化优先级，返回值 0.0-1.0，> 0.5 触发进化。
    """
    if dimension == "skill":
        call_count = metrics.get("total_calls", 0)
        success_rate = metrics.get("success_rate", 1.0)
        if call_count < 10:
            return 0.0
        return min(1.0, (1 - success_rate) * call_count / 10)

    elif dimension == "agent":
        avg_turns = metrics.get("avg_turns", 10)
        baseline = metrics.get("baseline_turns", 10)
        failure_rate = metrics.get("failure_rate", 0)
        task_count = metrics.get("similar_tasks", 0)
        if task_count < 5:
            return 0.0
        turn_penalty = max(0, (avg_turns - baseline) / baseline)
        failure_penalty = failure_rate / 0.3 if failure_rate > 0.3 else 0
        return min(1.0, turn_penalty * 0.5 + failure_penalty * 0.5)

    elif dimension == "rule":
        violation_count = metrics.get("violation_count", 0)
        if violation_count < 3:
            return 0.0
        return min(1.0, violation_count / 3 * 0.5)

    elif dimension == "memory":
        signal_count = metrics.get("pending_signals", 0)
        if signal_count == 0:
            return 0.0
        return min(1.0, signal_count * 0.5)

    return 0.0


# ═══════════════════════════════════════════════════════════════
# 触发器检查
# ═══════════════════════════════════════════════════════════════

def check_triggers(project_root: str = None) -> dict:
    """
    检查所有维度的触发条件，返回进化建议列表。
    """
    root = _find_root() if project_root is None else Path(project_root)
    data = aggregate_session_data(str(root))

    # 为安全门禁准备
    sys.path.insert(0, str(root / ".claude"))
    from lib.evolution_safety import EvolutionCircuitBreaker, EvolutionRateLimiter

    metrics_path = str(root / ".claude" / "data" / "evolution_metrics.json")
    history_path = str(root / ".claude" / "data" / "evolution_history.jsonl")
    breaker = EvolutionCircuitBreaker(metrics_path)
    limiter = EvolutionRateLimiter(history_path)

    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
    triggers = []

    # ── Skill 触发 ──
    for skill_name, call_count in data["skills_used"].items():
        if breaker.is_open("skill", skill_name):
            continue
        can_evolve, reason = limiter.can_evolve("skill", skill_name, session_id)
        if not can_evolve:
            continue

        # 计算该 skill 的失败率
        skill_failures = sum(
            1 for f in data.get("failure_records", [])
            if f.get("tool") == "Skill"
            and f.get("context", {}).get("skill") == skill_name
        )
        skill_success_rate = 1.0 - (skill_failures / max(call_count, 1))

        priority = compute_priority("skill", {
            "total_calls": call_count,
            "success_rate": round(skill_success_rate, 2),
        })
        # 应用优先级升级机制
        trigger_count = _get_trigger_count(root, "skill", skill_name)
        escalated_priority = compute_escalated_priority(priority, trigger_count)
        if escalated_priority > 0.5:
            triggers.append({
                "dimension": "skill",
                "target": skill_name,
                "reason": f"累计调用 {call_count} 次",
                "priority": round(escalated_priority, 2),
                "base_priority": round(priority, 2),
                "escalation_level": trigger_count + 1,
            })

    # ── Agent 触发 ──
    agents_dir = root / ".claude" / "agents"
    for agent_name, task_count in data["agent_tasks"].items():
        # 跳过 "unknown" 等无对应定义文件的 agent
        agent_file = agents_dir / "{}.md".format(agent_name)
        if not agent_file.exists():
            continue
        if breaker.is_open("agent", agent_name):
            continue
        can_evolve, reason = limiter.can_evolve("agent", agent_name, session_id)
        if not can_evolve:
            continue

        # 从实际数据计算 Agent 指标（非硬编码）
        agent_recs = data.get("agent_records", {}).get(agent_name, [])
        # 估算 avg_turns: 用 task 长度 / 50 作为粗糙代理
        est_turns = [len(r.get("task", "")) / 50 for r in agent_recs]
        avg_turns = sum(est_turns) / len(est_turns) if est_turns else 10
        avg_turns = max(1, round(avg_turns))

        # 从 tool_failures 计算该 agent 的失败率
        agent_failures = sum(
            1 for f in data.get("failure_records", [])
            if f.get("context", {}).get("agent") == agent_name
        )
        failure_rate = agent_failures / max(task_count, 1)

        priority = compute_priority("agent", {
            "similar_tasks": task_count,
            "avg_turns": avg_turns,
            "baseline_turns": 10,
            "failure_rate": round(failure_rate, 2),
        })
        # 应用优先级升级机制
        trigger_count = _get_trigger_count(root, "agent", agent_name)
        escalated_priority = compute_escalated_priority(priority, trigger_count)
        if escalated_priority > 0.5:
            triggers.append({
                "dimension": "agent",
                "target": agent_name,
                "reason": f"累计执行 {task_count} 次, avg_turns={avg_turns}",
                "priority": round(escalated_priority, 2),
                "base_priority": round(priority, 2),
                "escalation_level": trigger_count + 1,
            })

    # ── Rule 触发 ──
    rules_dir = root / ".claude" / "rules"
    for rule_name, count in data["violations_by_rule"].items():
        # 只进化有对应规则文件的规则（跳过内部检查标签如 test-location）
        rule_file = rules_dir / "{}.md".format(rule_name)
        if not rule_file.exists():
            continue
        if breaker.is_open("rule", rule_name):
            continue
        can_evolve, reason = limiter.can_evolve("rule", rule_name, session_id)
        if not can_evolve:
            continue

        priority = compute_priority("rule", {"violation_count": count})
        # 应用优先级升级机制
        trigger_count = _get_trigger_count(root, "rule", rule_name)
        escalated_priority = compute_escalated_priority(priority, trigger_count)
        if escalated_priority > 0.5:
            triggers.append({
                "dimension": "rule",
                "target": rule_name,
                "reason": f"违规 {count} 次",
                "priority": round(escalated_priority, 2),
                "base_priority": round(priority, 2),
                "escalation_level": trigger_count + 1,
            })

    # ── Memory 触发（最高优先级，无升级机制） ──
    if data["pending_signals"] > 0:
        can_evolve, reason = limiter.can_evolve("memory", "global", session_id)
        if can_evolve:
            priority = compute_priority("memory", {"pending_signals": data["pending_signals"]})
            # Memory 不走升级机制（因为用户信号本身就是高优先级）
            if priority > 0.5:
                triggers.append({
                    "dimension": "memory",
                    "target": "pending_signals",
                    "reason": f"{data['pending_signals']} 个待处理信号: {', '.join(data['signal_types'][:3])}",
                    "priority": round(priority, 2),
                })

    # 按优先级排序
    triggers.sort(key=lambda t: -t["priority"])

    return {
        "should_evolve": len(triggers) > 0,
        "session_summary": {
            "skills_used": list(data["skills_used"].keys()),
            "agents_used": data["agents_used"],
            "failures": data["total_failures"],
            "violations": data["total_violations"],
            "pending_signals": data["pending_signals"],
            "total_evolutions": data["total_evolutions"],
            "pending_confirmations": data["pending_confirmations"],
        },
        "triggers": triggers,
        "generated_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# 执行入口
# ═══════════════════════════════════════════════════════════════

def run_orchestrator(project_root: str = None, execute: bool = False) -> dict:
    """
    完整的编排流程: check → safety → persist → notify

    设计原则（来自 evolution-system-design.md）:
    - Stop Hook 无法启动 Agent 工具（会话已结束）
    - 因此 trigger 决策持久化到 data/，待下次会话由 Claude 主 Agent 调度 Agent 进化器
    - Python 进化引擎 (evolution/) 作为备用实现，Agent 进化器 (agents/*-evolver.md) 是首选路径
    """
    decision = check_triggers(project_root)
    root = _find_root() if project_root is None else Path(project_root)

    if not decision["should_evolve"]:
        return decision

    if execute:
        # 将触发决策持久化，供下次会话的 Agent 进化器消费
        data_dir = root / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        pending_path = data_dir / "pending_evolution.json"
        data_dir.mkdir(parents=True, exist_ok=True)

        # fcntl 锁保护的原子 read-modify-write，防止与 detect_feedback.py 冲突
        import fcntl as _fcntl_orch
        with open(pending_path, "a+") as f:
            _fcntl_orch.flock(f.fileno(), _fcntl_orch.LOCK_EX)
            try:
                f.seek(0)
                content = f.read()
                existing = {}
                if content.strip():
                    try:
                        existing = json.loads(content)
                    except (json.JSONDecodeError, OSError):
                        existing = {}

                # 合并本会话的触发决策
                existing_triggers = existing.get("pending_triggers", [])
                for t in decision.get("triggers", []):
                    key = f"{t['dimension']}:{t['target']}"
                    if not any(f"{et.get('dimension')}:{et.get('target')}" == key for et in existing_triggers):
                        existing_triggers.append(t)

                existing["pending_triggers"] = existing_triggers
                existing["last_check"] = datetime.now().isoformat()

                f.seek(0)
                f.truncate()
                f.write(json.dumps(existing, indent=2, ensure_ascii=False))

                # 递增触发计数（用于下次优先级升级）
                for t in decision.get("triggers", []):
                    _increment_trigger_count(root, t["dimension"], t["target"])
            finally:
                _fcntl_orch.flock(f.fileno(), _fcntl_orch.LOCK_UN)

        decision["evolved"] = True
        decision["persisted_to"] = str(pending_path)
    else:
        decision["evolved"] = False

    return decision


# ═══════════════════════════════════════════════════════════════
# Hook 模式 (stdin JSON → stdout JSON)
# ═══════════════════════════════════════════════════════════════

def hook_main():
    """作为 Stop hook 运行：stdin 读取 hook 数据，stdout 输出决策"""
    try:
        raw = sys.stdin.read().strip()
        hook_data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    session_id = hook_data.get("session_id", "unknown")
    os.environ.setdefault("CLAUDE_SESSION_ID", session_id)

    decision = run_orchestrator(execute=True)

    # 输出精简摘要到 stderr
    if decision["should_evolve"]:
        dims = set(t["dimension"] for t in decision["triggers"])
        print(
            f"🎯 进化触发: {len(decision['triggers'])} 项 "
            f"({', '.join(dims)}) "
            f"top={decision['triggers'][0]['dimension']}/{decision['triggers'][0]['target']}",
            file=sys.stderr,
        )
    else:
        print("✅ 无需进化，所有维度在健康范围内", file=sys.stderr)

    # 输出 JSON 决策到 stdout（Claude Code 会读取）
    print(json.dumps(decision, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="进化编排器")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("check", help="检查触发条件（不执行）")
    sub.add_parser("run", help="检查并执行进化")

    args = parser.parse_args()

    if args.cmd == "check":
        decision = check_triggers()
        print(json.dumps(decision, indent=2, ensure_ascii=False))
    elif args.cmd == "run":
        decision = run_orchestrator(execute=True)
        print(json.dumps(decision, indent=2, ensure_ascii=False))
    else:
        # 默认 hook 模式
        hook_main()


if __name__ == "__main__":
    main()
