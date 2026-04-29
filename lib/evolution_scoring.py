#!/usr/bin/env python3
"""
进化评分引擎 — 每个维度 0-100 健康度评分

公式: 基础分(40) + 活跃度(20) + 效果分(25) + 质量分(15)
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional


class EvolutionScorer:
    """进化评分引擎"""

    @staticmethod
    def score_skill(skill_name: str, metrics: dict) -> dict:
        base = min(40, metrics.get("total_calls", 0) * 4)
        activity = min(20, metrics.get("calls_last_7d", 0) * 6)
        effect = 0 if metrics.get("circuit_open") else min(25, metrics.get("success_rate", 0) * 25)
        quality = (
            (5 if not metrics.get("corrupted_rows") else 0) +
            (5 if metrics.get("evolution_frequency", 0) <= 1 else 2) +
            (5 if not metrics.get("anomaly_detected") else 0)
        )
        total = base + activity + effect + quality
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": EvolutionScorer._trend(metrics),
        }

    @staticmethod
    def score_agent(agent_name: str, metrics: dict) -> dict:
        base = min(40, metrics.get("total_tasks", 0) * 8)
        activity = min(20, metrics.get("tasks_last_7d", 0) * 4)
        avg_turns = metrics.get("avg_turns", 15)
        baseline = metrics.get("baseline_turns", 15)
        turn_ratio = baseline / max(avg_turns, 1)
        effect = 0 if metrics.get("circuit_open") else min(25, turn_ratio * 20)
        quality = 15 if not metrics.get("anomaly_detected") else 5
        total = base + activity + effect + quality
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": EvolutionScorer._trend(metrics),
        }

    @staticmethod
    def score_rule(rule_name: str, metrics: dict) -> dict:
        violations = metrics.get("total_violations", 0)
        base = max(0, 40 - violations * 5)
        activity = 20 if metrics.get("last_violation_7d") else 10
        effect = 0 if metrics.get("circuit_open") else min(25, 25 - violations * 3)
        quality = 15 if not metrics.get("corrupted_rows") else 5
        total = base + activity + effect + quality
        prev_v = metrics.get("prev_violations", violations)
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": "📈" if violations <= prev_v else "📉",
        }

    @staticmethod
    def score_memory(metrics: dict) -> dict:
        file_count = metrics.get("total_files", 0)
        base = min(40, file_count * 10)
        activity = 20 if metrics.get("signals_last_7d", 0) > 0 else 10
        effect = min(25, file_count * 5)
        quality = 15
        total = base + activity + effect + quality
        prev = metrics.get("prev_file_count", file_count)
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": "📈" if file_count >= prev else "➡️",
        }

    @staticmethod
    def _grade(score: float) -> str:
        if score < 0: return "N/A"
        if score >= 80: return "A"
        if score >= 65: return "B"
        if score >= 50: return "C"
        if score >= 35: return "D"
        return "F"

    @staticmethod
    def _trend(metrics: dict) -> str:
        prev = metrics.get("prev_score", metrics.get("total", 0))
        curr = metrics.get("total", 0)
        if curr > prev + 3: return "📈 上升"
        if curr < prev - 3: return "📉 下降"
        return "➡️ 持平"


# ═══════════════════════════════════════════════════════════════
# 指标采集器 — 从 data/ 目录读取实际数据计算评分输入
# ═══════════════════════════════════════════════════════════════

def _count_jsonl(file_path: str) -> int:
    p = Path(file_path)
    if not p.exists():
        return 0
    return sum(1 for _ in open(p, encoding="utf-8") if _.strip())


def _count_jsonl_last_7d(file_path: str) -> int:
    p = Path(file_path)
    if not p.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=7)
    count = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                ts = r.get("timestamp", "")
                if ts and datetime.fromisoformat(ts[:19]) > cutoff:
                    count += 1
            except (json.JSONDecodeError, ValueError):
                continue
    return count


def _read_jsonl(file_path: str) -> list:
    p = Path(file_path)
    if not p.exists():
        return []
    records = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def collect_skill_metrics(data_dir: str) -> Dict[str, dict]:
    """从 skill_usage.jsonl 采集各 Skill 的评分指标"""
    dp = Path(data_dir)
    records = _read_jsonl(str(dp / "skill_usage.jsonl"))

    by_skill: Dict[str, list] = {}
    for r in records:
        skill = r.get("skill", "unknown")
        by_skill.setdefault(skill, []).append(r)

    result = {}
    for skill, recs in by_skill.items():
        total = len(recs)
        last_7d = sum(1 for r in recs
                      if r.get("timestamp", "") and
                      datetime.fromisoformat(r["timestamp"][:19]) > datetime.now() - timedelta(days=7))

        failures = _read_jsonl(str(dp / "tool_failures.jsonl"))
        skill_fails = sum(1 for f in failures if f.get("tool") == "Skill")

        success_rate = 1.0 - (skill_fails / max(total, 1))
        corrupted = 1 if any(not r.get("type") for r in recs) else 0

        result[skill] = {
            "total_calls": total,
            "calls_last_7d": last_7d,
            "success_rate": round(success_rate, 2),
            "circuit_open": False,
            "corrupted_rows": corrupted,
            "evolution_frequency": 0,
            "anomaly_detected": False,
        }

    return result


def collect_agent_metrics(data_dir: str) -> Dict[str, dict]:
    """从 agent_performance.jsonl 采集各 Agent 的评分指标"""
    dp = Path(data_dir)
    records = _read_jsonl(str(dp / "agent_performance.jsonl"))

    by_agent: Dict[str, list] = {}
    for r in records:
        agent = r.get("agent", "unknown")
        by_agent.setdefault(agent, []).append(r)

    result = {}
    for agent, recs in by_agent.items():
        total = len(recs)
        last_7d = sum(1 for r in recs
                      if r.get("timestamp", "") and
                      datetime.fromisoformat(r["timestamp"][:19]) > datetime.now() - timedelta(days=7))

        # 估算 avg_turns: agent 执行没有 turns 字段，用 task 长度 / 50 作为粗糙估计
        avg_turns = sum(len(r.get("task", "")) / 50 for r in recs) / max(total, 1)
        avg_turns = max(1, round(avg_turns))

        result[agent] = {
            "total_tasks": total,
            "tasks_last_7d": last_7d,
            "avg_turns": avg_turns,
            "baseline_turns": 15,
            "circuit_open": False,
            "anomaly_detected": False,
        }

    return result


def collect_rule_metrics(data_dir: str) -> Dict[str, dict]:
    """从 rule_violations.jsonl 采集各规则的评分指标"""
    dp = Path(data_dir)
    records = _read_jsonl(str(dp / "rule_violations.jsonl"))

    by_rule: Dict[str, list] = {}
    for r in records:
        rule = r.get("rule", "unknown")
        by_rule.setdefault(rule, []).append(r)

    result = {}
    for rule, recs in by_rule.items():
        total = len(recs)
        last_violation_7d = any(
            r.get("timestamp", "") and
            datetime.fromisoformat(r["timestamp"][:19]) > datetime.now() - timedelta(days=7)
            for r in recs
        )

        result[rule] = {
            "total_violations": total,
            "last_violation_7d": last_violation_7d,
            "prev_violations": total,
            "circuit_open": False,
            "corrupted_rows": 0,
        }

    return result


def collect_memory_metrics(data_dir: str, memory_dir: str = None) -> dict:
    """从 memory/ 目录采集 Memory 维度评分指标"""
    dp = Path(data_dir)
    mp = Path(memory_dir) if memory_dir else dp.parent / "memory"

    files = list(mp.glob("*.md")) if mp.exists() else []
    total_files = len(files)

    pending_file = dp / "pending_evolution.json"
    signals_last_7d = 0
    if pending_file.exists():
        try:
            pending = json.loads(pending_file.read_text())
            feedback = pending.get("feedback_signals", [])
            cutoff = datetime.now() - timedelta(days=7)
            signals_last_7d = sum(
                1 for s in feedback
                if s.get("timestamp", "") and
                datetime.fromisoformat(s["timestamp"][:19]) > cutoff
            )
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    return {
        "total_files": total_files,
        "prev_file_count": total_files,
        "signals_last_7d": signals_last_7d,
    }


def collect_all_metrics(project_root: str = ".") -> dict:
    """采集所有维度的评分指标"""
    root = Path(project_root)
    data_dir = root / ".claude" / "data"

    return {
        "skills": collect_skill_metrics(str(data_dir)),
        "agents": collect_agent_metrics(str(data_dir)),
        "rules": collect_rule_metrics(str(data_dir)),
        "memory": collect_memory_metrics(str(data_dir), str(root / ".claude" / "memory")),
    }


def compute_all_scores(project_root: str = ".") -> dict:
    """计算所有维度的完整评分"""
    metrics = collect_all_metrics(project_root)
    scorer = EvolutionScorer()

    dim_scores = {}

    for skill, m in metrics["skills"].items():
        dim_scores.setdefault("skills", {})[skill] = scorer.score_skill(skill, m)

    for agent, m in metrics["agents"].items():
        dim_scores.setdefault("agents", {})[agent] = scorer.score_agent(agent, m)

    for rule, m in metrics["rules"].items():
        dim_scores.setdefault("rules", {})[rule] = scorer.score_rule(rule, m)

    dim_scores["memory"] = {
        "_overall": scorer.score_memory(metrics["memory"])
    }

    # 计算各维度平均分（无数据时返回 -1 哨兵值表示 N/A）
    dimension_averages = {}
    for dim, targets in dim_scores.items():
        if dim == "memory":
            dimension_averages[dim] = targets["_overall"]["total"]
        else:
            scores = [t["total"] for t in targets.values()]
            dimension_averages[dim] = round(sum(scores) / len(scores), 1) if scores else -1

    # 整体分只计算有数据的维度
    valid_scores = [s for s in dimension_averages.values() if s >= 0]
    overall = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else -1

    return {
        "overall_score": overall,
        "overall_grade": EvolutionScorer._grade(overall),
        "dimension_scores": dimension_averages,
        "details": dim_scores,
        "generated_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# 趋势存储 — 用于计算 daily_scores
# ═══════════════════════════════════════════════════════════════

def save_daily_score(project_root: str = "."):
    """保存今日评分到 daily_scores.jsonl（fcntl 锁保护）"""
    scores = compute_all_scores(project_root)
    root = Path(project_root)
    daily_file = root / ".claude" / "data" / "daily_scores.jsonl"
    daily_file.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "overall": scores["overall_score"],
        "skills": scores["dimension_scores"].get("skills", -1),
        "agents": scores["dimension_scores"].get("agents", -1),
        "rules": scores["dimension_scores"].get("rules", -1),
        "memory": scores["dimension_scores"].get("memory", -1),
    }

    import fcntl as _fcntl
    with open(daily_file, "a+") as f:
        _fcntl.flock(f.fileno(), _fcntl.LOCK_EX)
        try:
            f.seek(0)
            existing = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    if r.get("date") != record["date"]:
                        existing.append(r)
                except json.JSONDecodeError:
                    continue

            existing.append(record)
            f.seek(0)
            f.truncate()
            for r in existing:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        finally:
            _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)

    return record


def load_daily_scores(project_root: str = ".") -> list:
    daily_file = Path(project_root) / ".claude" / "data" / "daily_scores.jsonl"
    if not daily_file.exists():
        return []
    scores = []
    with open(daily_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    scores.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return sorted(scores, key=lambda r: r.get("date", ""))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        record = save_daily_score()
        print(json.dumps(record, indent=2, ensure_ascii=False))
    else:
        scores = compute_all_scores()
        print(json.dumps(scores, indent=2, ensure_ascii=False))
