#!/usr/bin/env python3
"""
自动回滚模块 — 观察期验证效果，自动回滚恶化的改动。

借鉴 CI/CD 的 AI-Powered Verification + Auto-Rollback 模式：
提案应用后进入观察期，指标恶化时自动回滚。

工作流程:
1. 定期检查所有应用的提案
2. 收集观察期内的指标
3. 与基线对比，决定是否回滚
4. 执行回滚并通知
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def load_config():
    """加载配置"""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        return _default_config()
    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    except ImportError:
        return _default_config()


def _default_config():
    return {
        "observation": {
            "days": 7,
            "check_interval_hours": 24,
        },
        "observation": {
            "days": 7,
            "check_interval_hours": 24,
        },
        "safety": {
            "breaker": {
                "max_consecutive_rejects": 3,
                "pause_days": 30,
                "max_rollbacks_per_week": 5,
            },
        },
        "paths": {
            "data_dir": ".claude/data",
        },
    }


def load_proposal_history(history_file: Path) -> list:
    """加载提案历史"""
    if not history_file.exists():
        return []
    try:
        return json.loads(history_file.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_proposal_history(history_file: Path, history: list):
    """保存提案历史"""
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def collect_metrics(root, proposal_id: str = "", observation_days: int = 7) -> dict:
    if isinstance(root, str):
        root = Path(root)
    """
    收集观察期内的指标。

    返回:
    {
        "task_success_rate": float,
        "failure_rate": float,
        "correction_rate": float,
        "sample_size": int,
    }
    """
    sessions_file = root / ".claude" / "data" / "sessions.jsonl"

    metrics = {
        "task_success_rate": 1.0,
        "failure_rate": 0.0,
        "correction_rate": 0.0,
        "sample_size": 0,
    }

    if not sessions_file.exists():
        return metrics

    # 收集观察期内的会话
    cutoff = (datetime.now() - timedelta(days=observation_days)).isoformat()
    sessions = []

    try:
        for line in sessions_file.read_text().splitlines():
            if not line.strip():
                continue
            try:
                session = json.loads(line)
                if session.get("timestamp", "") >= cutoff:
                    sessions.append(session)
            except json.JSONDecodeError:
                continue
    except OSError:
        return metrics

    if not sessions:
        return metrics

    total = len(sessions)

    # 计算指标
    total_failures = sum(s.get("tool_failures", 0) for s in sessions)
    total_corrections = sum(len(s.get("corrections", [])) for s in sessions)

    # 成功率：无失败 = 成功
    success_count = sum(1 for s in sessions if s.get("tool_failures", 0) == 0)
    failure_count = sum(1 for s in sessions if s.get("tool_failures", 0) > 0)

    metrics["task_success_rate"] = round(success_count / max(total, 1), 2)
    metrics["failure_rate"] = round(failure_count / max(total, 1), 2)
    metrics["correction_rate"] = round(total_corrections / max(total, 1), 2)
    metrics["sample_size"] = total

    return metrics


def evaluate_proposal(proposal: dict, metrics: dict, baseline: dict, config: dict = None) -> str:
    """
    评估是否应该保留或回滚。

    返回: "keep" | "rollback" | "observe"
    """
    triggers = []

    # 从配置读取阈值
    obs_config = (config or {}).get("observation", {})
    min_success_rate = obs_config.get("metrics", {}).get("min_success_rate", 0.8)
    max_correction_rate = obs_config.get("metrics", {}).get("max_correction_rate", 0.2)
    max_failure_delta = obs_config.get("metrics", {}).get("max_failure_rate_delta", 0.1)

    # 检查成功率
    baseline_success = baseline.get("task_success_rate", 1.0)
    current_success = metrics.get("task_success_rate", 1.0)
    if current_success < min_success_rate:
        triggers.append(f"成功率 {current_success:.0%} < 阈值 {min_success_rate:.0%}")
    elif baseline_success > 0 and current_success < baseline_success * (1 - max_failure_delta):
        delta = (baseline_success - current_success) / baseline_success
        triggers.append(f"成功率下降 {delta:.0%}")

    # 检查纠正率
    baseline_correction = baseline.get("correction_rate", 0)
    current_correction = metrics.get("correction_rate", 0)
    if baseline_correction > 0 and current_correction > baseline_correction * 1.20:
        triggers.append(f"纠正率上升 {((current_correction - baseline_correction) / baseline_correction * 100):.0f}%")

    # 如果原纠正率为 0，现在有纠正 = 恶化
    if baseline_correction == 0 and current_correction > 0.1:
        triggers.append(f"新增纠正率 {current_correction:.0%}")

    # 检查样本量（需要足够的数据才有统计意义）
    if metrics.get("sample_size", 0) < 5:
        return "observe"  # 样本太少，继续观察

    # 决策
    if triggers:
        return "rollback"

    # 所有指标稳定
    if metrics.get("sample_size", 0) >= 10:
        return "keep"

    return "observe"


def check_circuit_breaker(history: list, config: dict) -> tuple[bool, str]:
    """
    检查熔断器状态。

    返回: (is_triggered, reason)
    """
    breaker_config = config.get("safety", {}).get("breaker", {})
    max_rollbacks_per_week = breaker_config.get("max_rollbacks_per_week", 5)
    pause_days = breaker_config.get("pause_days", 30)

    # 统计最近一周的回滚次数
    week_ago = datetime.now() - timedelta(days=7)
    recent_rollbacks = [
        p for p in history
        if p.get("status") == "rolled_back"
        and datetime.fromisoformat(p.get("rolled_back_at", "2000-01-01")) >= week_ago
    ]

    if len(recent_rollbacks) >= max_rollbacks_per_week:
        return True, f"{len(recent_rollbacks)} rollbacks in 7 days, exceeding limit {max_rollbacks_per_week}"

    # 检查是否处于暂停期
    pause_cutoff = datetime.now() - timedelta(days=pause_days)
    for p in history:
        if p.get("status") == "paused":
            paused_at = datetime.fromisoformat(p.get("paused_at", "2000-01-01"))
            if paused_at >= pause_cutoff:
                return True, f"System paused until {p.get('resume_at', 'unknown')}"

    return False, ""


def execute_rollback(proposal: dict, root: Path, config: dict) -> bool:
    """执行回滚"""
    try:
        from apply_change import rollback_proposal

        proposal_id = proposal.get("id", "")
        reason = f"Metrics degraded: {proposal.get('rollback_triggers', [])}"

        return rollback_proposal(proposal_id, root, reason)

    except Exception as e:
        print(f"Failed to execute rollback: {e}")
        return False


def consolidate_proposal(proposal: dict, root: Path):
    """固化提案"""
    try:
        from apply_change import consolidate_proposal as do_consolidate
        do_consolidate(proposal.get("id", ""), root)
    except Exception as e:
        print(f"Failed to consolidate: {e}")


def run_rollback_check(root: Optional[Path] = None, config: Optional[dict] = None) -> dict:
    """
    检查所有提案，执行回滚或固化。

    返回检查结果。
    """
    if root is None:
        root = find_root()

    if config is None:
        config = load_config()

    history_file = root / ".claude" / "data" / "proposal_history.json"
    history = load_proposal_history(history_file)

    # 检查熔断器
    is_paused, pause_reason = check_circuit_breaker(history, config)
    if is_paused:
        return {
            "status": "paused",
            "reason": pause_reason,
            "checked": 0,
            "rolled_back": 0,
            "consolidated": 0,
        }

    observation_days = config.get("observation", {}).get("days", 7)
    now = datetime.now()

    stats = {"checked": 0, "rolled_back": 0, "consolidated": 0, "observed": 0}

    for proposal in history:
        if proposal.get("status") != "applied":
            continue

        stats["checked"] += 1

        # 检查是否到期
        observation_end = datetime.fromisoformat(proposal.get("observation_end", now.isoformat()))
        if now < observation_end:
            continue  # 还在观察期内

        # 收集指标
        metrics = collect_metrics(root, proposal.get("id", ""), observation_days)
        baseline = proposal.get("baseline_metrics", {})

        # 评估
        decision = evaluate_proposal(proposal, metrics, baseline, config)

        # 记录触发条件
        proposal["rollback_triggers"] = []

        if decision == "rollback":
            # 执行回滚
            success = execute_rollback(proposal, root, config)
            if success:
                stats["rolled_back"] += 1
                proposal["rollback_triggers"] = proposal.get("rollback_triggers", [])

        elif decision == "keep":
            # 固化
            consolidate_proposal(proposal, root)
            _promote_instinct_on_observation(proposal, root)
            stats["consolidated"] += 1

        else:
            stats["observed"] += 1

    # 保存历史
    save_proposal_history(history_file, history)

    # 检查熔断器（更新状态）
    is_paused, pause_reason = check_circuit_breaker(history, config)
    if is_paused:
        # 暂停系统
        for p in history:
            if p.get("status") == "applied":
                p["status"] = "paused"
                p["paused_at"] = now.isoformat()
                p["pause_reason"] = pause_reason
                p["resume_at"] = (now + timedelta(days=30)).isoformat()
        save_proposal_history(history_file, history)

    return {
        "status": "completed",
        "checked": stats["checked"],
        "rolled_back": stats["rolled_back"],
        "consolidated": stats["consolidated"],
        "observed": stats["observed"],
        "message": f"Checked {stats['checked']}, rolled back {stats['rolled_back']}, consolidated {stats['consolidated']}",
    }


def get_proposal_health(proposal_id: str, root: Path, config: dict) -> dict:
    """获取单个提案的健康状态"""
    history_file = root / ".claude" / "data" / "proposal_history.json"
    history = load_proposal_history(history_file)

    proposal = None
    for p in history:
        if p.get("id") == proposal_id:
            proposal = p
            break

    if not proposal:
        return {"status": "not_found"}

    observation_days = config.get("observation", {}).get("days", 7)
    metrics = collect_metrics(root, proposal_id, observation_days)
    baseline = proposal.get("baseline_metrics", {})
    decision = evaluate_proposal(proposal, metrics, baseline, config)

    return {
        "id": proposal_id,
        "status": proposal.get("status", "unknown"),
        "decision": decision,
        "metrics": metrics,
        "baseline": baseline,
        "observation_end": proposal.get("observation_end"),
        "days_remaining": max(0, (datetime.fromisoformat(proposal.get("observation_end", datetime.now().isoformat())) - datetime.now()).days),
    }



def _promote_instinct_on_observation(proposal: dict, root: Path):
    """
    观察期通过后：增强 instinct 置信度 + 关联 target_file。
    """
    try:
        from instinct_updater import promote_confidence, find_instinct_by_target
        target_file = proposal.get("target_file")
        linked_id = proposal.get("linked_instinct_id")
        if linked_id:
            promote_confidence(linked_id, delta=0.1, root=root)
        elif target_file:
            records = find_instinct_by_target(target_file, root)
            if records:
                promote_confidence(records[0].get("id"), delta=0.1, root=root)
    except Exception:
        pass

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="自动回滚模块")
    parser.add_argument("action", choices=["check", "health", "stats"])
    parser.add_argument("--id", help="提案 ID")

    args = parser.parse_args()

    root = find_root()
    config = load_config()

    if args.action == "check":
        result = run_rollback_check(root, config)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.action == "health":
        if not args.id:
            print("Error: --id required for health")
            sys.exit(1)
        health = get_proposal_health(args.id, root, config)
        print(json.dumps(health, indent=2, ensure_ascii=False))

    elif args.action == "stats":
        history_file = root / ".claude" / "data" / "proposal_history.json"
        history = load_proposal_history(history_file)

        total = len(history)
        applied = sum(1 for p in history if p.get("status") == "applied")
        rolled_back = sum(1 for p in history if p.get("status") == "rolled_back")
        consolidated = sum(1 for p in history if p.get("status") == "consolidated")

        print(json.dumps({
            "total": total,
            "applied": applied,
            "rolled_back": rolled_back,
            "consolidated": consolidated,
            "rollback_rate": round(rolled_back / max(applied, 1), 2),
        }, indent=2))