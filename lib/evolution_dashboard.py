#!/usr/bin/env python3
"""
进化仪表盘 — 一站式查看进化健康度

三层输出:
  L1 (200 tokens): SessionStart 注入摘要
  L2 (1000 tokens): --summary 模式
  L3 (5000 tokens): --full 模式
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
from pathlib import Path as _Path
_lib_dir = _Path(__file__).parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

from token_efficiency import TokenBudget
from evolution_scoring import compute_all_scores, load_daily_scores, collect_all_metrics


def generate_dashboard_l1(project_root: str = ".") -> str:
    """
    L1 紧凑摘要 (≤200 tokens)，用于 SessionStart 注入。
    纯文本格式，无 JSON 开销。
    无数据维度显示 N/A 而非 0/F。
    """
    scores = compute_all_scores(project_root)
    dims = scores["dimension_scores"]
    overall = scores["overall_score"]
    grade = scores["overall_grade"]

    def _fmt_dim(s: float) -> str:
        if s < 0:
            return "N/A"
        g = "A" if s >= 80 else "B" if s >= 65 else "C" if s >= 50 else "D" if s >= 35 else "F"
        return f"{s:.0f}/{g}"

    parts = []
    dim_order = ["skills", "agents", "rules", "memory"]
    dim_names = {"skills": "Skill", "agents": "Agent", "rules": "Rule", "memory": "Memory"}

    for d in dim_order:
        s = dims.get(d, -1)
        parts.append(f"{dim_names[d]}:{_fmt_dim(s)}")

    overall_str = f"{overall:.0f}/{grade}" if overall >= 0 else "N/A"
    summary = f"[Evo {overall_str}] " + " | ".join(parts)

    # 严格控制在 L1 预算内
    if len(summary) > 250:
        summary = summary[:247] + "..."

    return summary


def generate_dashboard_l2(project_root: str = ".") -> str:
    """
    L2 摘要格式 (≤1000 tokens)，包含各维度详细 breakdown。
    """
    scores = compute_all_scores(project_root)
    daily = load_daily_scores(project_root)
    metrics = collect_all_metrics(project_root)

    lines = []
    lines.append("=" * 50)
    lines.append(f"📊 进化仪表盘 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 50)

    overall = scores["overall_score"]
    grade = scores["overall_grade"]
    trend_symbol = _compute_overall_trend(daily)
    overall_str = f"{overall:.1f}/100" if overall >= 0 else "N/A (无数据)"
    lines.append(f"\n🏆 总分: {overall_str} | 等级: {grade} | 趋势: {trend_symbol}")

    dim_order = ["skills", "agents", "rules", "memory"]
    dim_names = {"skills": "Skill", "agents": "Agent", "rules": "Rule", "memory": "Memory"}

    lines.append(f"\n{'维度':<10} {'分数':>6} {'等级':>4} {'趋势':>10}")
    lines.append("-" * 35)

    for d in dim_order:
        s = scores["dimension_scores"].get(d, -1)
        g = _grade(s)
        s_str = f"{s:>6.1f}" if s >= 0 else f"{'N/A':>6}"
        t_detail = scores.get("details", {}).get(d, {})
        trend = ""
        if d == "memory":
            trend = t_detail.get("_overall", {}).get("trend", "➡️")
        elif t_detail:
            trends = [v.get("trend", "➡️") for v in t_detail.values()]
            trend = "📈" if "📈" in "".join(trends) else "📉" if "📉" in "".join(trends) else "➡️"
        lines.append(f"{dim_names[d]:<10} {s_str} {g:>4} {trend:>10}")

    # 各维度细节
    lines.append(f"\n{'─' * 50}")
    metrics_section = _build_metrics_section(metrics)
    lines.append(metrics_section)

    lines.append(f"\n📈 最近 7 日趋势:")
    if daily:
        for d in daily[-7:]:
            lines.append(f"   {d['date']} → 总分:{d['overall']:.0f} S:{d.get('skills',0):.0f} A:{d.get('agents',0):.0f} R:{d.get('rules',0):.0f} M:{d.get('memory',0):.0f}")
    else:
        lines.append("   (无历史数据)")

    result = "\n".join(lines)
    if TokenBudget.estimate(result) > 1000:
        result = TokenBudget.truncate(result, 1000)
    return result


def generate_dashboard_l3(project_root: str = ".") -> dict:
    """
    L3 详细数据 (≤5000 tokens)，完整 JSON 结构。
    """
    scores = compute_all_scores(project_root)
    daily = load_daily_scores(project_root)
    metrics = collect_all_metrics(project_root)

    history = _load_evolution_history(project_root)
    total_evos = len(history)
    days_tracked = len(daily)

    summary_text = _generate_summary_text(scores)

    return {
        "dashboard": {
            "generated_at": datetime.now().isoformat(),
            "overall_score": scores["overall_score"],
            "overall_grade": scores["overall_grade"],
            "total_evolutions": total_evos,
            "days_tracked": days_tracked,
            "summary": summary_text,
        },
        "dimensions": {
            "skills": _build_dimension_block("skills", scores, metrics),
            "agents": _build_dimension_block("agents", scores, metrics),
            "rules": _build_dimension_block("rules", scores, metrics),
            "memory": _build_dimension_block("memory", scores, metrics),
        },
        "daily_scores": daily[-14:],
    }


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def _grade(s: float) -> str:
    if s < 0: return "N/A"
    if s >= 80: return "A"
    if s >= 65: return "B"
    if s >= 50: return "C"
    if s >= 35: return "D"
    return "F"


def _compute_overall_trend(daily_scores: list) -> str:
    if len(daily_scores) < 2:
        return "➡️ 持平"
    recent = daily_scores[-2:]
    curr = recent[-1].get("overall", -1)
    prev = recent[0].get("overall", -1)
    if curr < 0 or prev < 0:
        return "N/A"
    if curr > prev + 3:
        return "📈 上升"
    elif curr < prev - 3:
        return "📉 下降"
    return "➡️ 持平"


def _build_metrics_section(metrics: dict) -> str:
    lines = ["📋 数据概览:"]
    dim_labels = {"skills": "Skill 调用", "agents": "Agent 任务", "rules": "违规记录", "memory": "记忆文件"}
    for dim, label in dim_labels.items():
        if dim == "memory":
            lines.append(f"   {label}: {metrics[dim].get('total_files', 0)} 文件")
        else:
            total = sum(len(v) if isinstance(v, (list, dict)) else 0 for v in metrics.get(dim, {}).values())
            lines.append(f"   {label}: {total} 条记录")
    return "\n".join(lines)


def _build_dimension_block(dim: str, scores: dict, metrics: dict) -> dict:
    dim_scores = scores["dimension_scores"]
    details = scores.get("details", {}).get(dim, {})
    dim_metrics = metrics.get(dim, {})

    dim_score = dim_scores.get(dim, -1)
    block = {
        "score": dim_score,
        "grade": _grade(dim_score),
        "targets": {},
    }

    if dim == "memory":
        block["trend"] = details.get("_overall", {}).get("trend", "➡️")
        block["targets"] = {
            "total_files": dim_metrics.get("total_files", 0),
            "pending_signals": dim_metrics.get("signals_last_7d", 0),
        }
    else:
        for target, t_score in details.items():
            t_metric = dim_metrics.get(target, {})
            block["targets"][target] = {
                "score": t_score.get("total", 0),
                "grade": _grade(t_score.get("total", 0)),
            }
            # 附加指标
            for k in ("total_calls", "total_tasks", "total_violations", "success_rate", "avg_turns"):
                if k in t_metric:
                    block["targets"][target][k] = t_metric[k]
            for k in ("total_calls", "total_tasks", "total_violations", "success_rate", "avg_turns"):
                if k in t_score:
                    block["targets"][target][k] = t_score[k]

    return block


def _load_evolution_history(project_root: str) -> list:
    p = Path(project_root) / ".claude" / "data" / "evolution_history.jsonl"
    if not p.exists():
        return []
    records = []
    try:
        for line in p.read_text().strip().splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        return []
    return records


def _generate_summary_text(scores: dict) -> str:
    dims = scores["dimension_scores"]
    highest = max(dims.items(), key=lambda x: x[1])
    lowest = min(dims.items(), key=lambda x: x[1])

    parts = []
    if highest[1] >= 80:
        parts.append(f"{highest[0]} 维度表现优秀 ({highest[1]:.0f}分)")
    if lowest[1] < 50:
        parts.append(f"{lowest[0]} 维度需关注 ({lowest[1]:.0f}分)")

    if not parts:
        parts.append("系统整体健康")
    return "，".join(parts)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="进化仪表盘")
    parser.add_argument("--mode", choices=["l1", "l2", "l3"], default="l2",
                        help="输出模式: l1=紧凑(200t), l2=摘要(1000t), l3=完整(5000t)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    if args.mode == "l1":
        summary = generate_dashboard_l1(project_root)
        print(summary)
        print(f"\n# Token 估算: {TokenBudget.estimate(summary)}", file=sys.stderr)
    elif args.mode == "l2":
        if args.json:
            scores = compute_all_scores(project_root)
            print(json.dumps({"summary": scores}, indent=2, ensure_ascii=False))
        else:
            print(generate_dashboard_l2(project_root))
    elif args.mode == "l3":
        data = generate_dashboard_l3(project_root)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        est = TokenBudget.estimate(json.dumps(data, ensure_ascii=False))
        print(f"\n# Token 估算: {est}", file=sys.stderr)


if __name__ == "__main__":
    main()
