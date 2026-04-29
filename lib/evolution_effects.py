#!/usr/bin/env python3
"""
进化效果量化 — 进化前后对比 + 效果汇总

用法:
  python3 .claude/lib/evolution_effects.py compare --dimension skill --target karpathy-guidelines
  python3 .claude/lib/evolution_effects.py report   # 所有维度的效果报告
  python3 .claude/lib/evolution_effects.py trend    # 趋势分析
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List


def _find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _load_history(root: Path) -> list:
    """加载进化历史"""
    f = root / ".claude" / "data" / "evolution_history.jsonl"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _load_jsonl(path: Path) -> list:
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


def compare_before_after(dimension: str, target: str, project_root: str = None) -> dict:
    """
    对比目标进化前后的分数变化。
    """
    root = _find_root() if project_root is None else Path(project_root)
    history = _load_history(root)

    # 筛选该目标的进化记录
    target_history = [
        h for h in history
        if h.get("dimension") == dimension and h.get("target_id") == target
    ]

    if not target_history:
        return {"status": "no_data", "message": f"{dimension}/{target} 无进化记录"}

    # 提取分数序列
    scores = []
    for h in sorted(target_history, key=lambda x: x.get("timestamp", "")):
        scores.append({
            "timestamp": h.get("timestamp"),
            "score_before": h.get("score_before", 0),
            "score_after": h.get("score_after", 0),
            "delta": h.get("score_after", 0) - h.get("score_before", 0),
            "success": h.get("success", False),
        })

    first = scores[0]["score_before"]
    last = scores[-1]["score_after"]
    total_delta = last - first
    avg_delta = sum(s["delta"] for s in scores) / len(scores)

    return {
        "dimension": dimension,
        "target": target,
        "total_evolutions": len(scores),
        "initial_score": first,
        "current_score": last,
        "total_improvement": round(total_delta, 2),
        "avg_improvement_per_evolution": round(avg_delta, 2),
        "success_rate": sum(1 for s in scores if s["success"]) / len(scores),
        "scores_timeline": scores,
        "verdict": "improving" if total_delta > 0 else "degrading" if total_delta < 0 else "stable",
    }


def generate_effect_report(project_root: str = None) -> dict:
    """
    生成所有维度的进化效果报告。
    """
    root = _find_root() if project_root is None else Path(project_root)
    history = _load_history(root)

    if not history:
        return {"status": "no_data", "message": "无进化历史"}

    by_dim: Dict[str, list] = {}
    for h in history:
        dim = h.get("dimension", "unknown")
        by_dim.setdefault(dim, []).append(h)

    dimensions = {}
    for dim, records in by_dim.items():
        scores_delta = [
            r.get("score_after", 0) - r.get("score_before", 0)
            for r in records
        ]
        total = len(records)
        success = sum(1 for r in records if r.get("success"))

        dimensions[dim] = {
            "total_evolutions": total,
            "success_count": success,
            "success_rate": round(success / max(total, 1), 2),
            "avg_improvement": round(sum(scores_delta) / max(len(scores_delta), 1), 2),
            "net_improvement": round(sum(scores_delta), 2),
            "last_evolution": max((r.get("timestamp", "") for r in records), default=None),
            "targets": list(set(r.get("target_id", "unknown") for r in records)),
        }

    # 总体统计
    all_deltas = [
        r.get("score_after", 0) - r.get("score_before", 0)
        for r in history
    ]

    return {
        "generated_at": datetime.now().isoformat(),
        "total_evolutions": len(history),
        "overall_net_improvement": round(sum(all_deltas), 2),
        "overall_avg_improvement": round(sum(all_deltas) / max(len(all_deltas), 1), 2),
        "overall_success_rate": round(
            sum(1 for r in history if r.get("success")) / max(len(history), 1), 2
        ),
        "dimensions": dimensions,
        "verdict": "positive" if sum(all_deltas) > 0 else "negative" if sum(all_deltas) < 0 else "neutral",
    }


def generate_trend(project_root: str = None) -> dict:
    """分析进化趋势"""
    root = _find_root() if project_root is None else Path(project_root)
    daily = _load_jsonl(root / ".claude" / "data" / "daily_scores.jsonl")

    if len(daily) < 3:
        return {"status": "insufficient_data", "message": "需要至少 3 天数据"}

    # 计算 7 日移动平均趋势
    trends = {}
    for dim in ["skills", "agents", "rules", "memory"]:
        values = [d.get(dim, 0) for d in daily[-7:]]
        if len(values) >= 2:
            slope = (values[-1] - values[0]) / max(len(values) - 1, 1)
            trends[dim] = {
                "current": values[-1],
                "7d_ago": values[0],
                "slope": round(slope, 2),
                "direction": "up" if slope > 0.5 else "down" if slope < -0.5 else "flat",
            }

    overall_values = [d.get("overall", 0) for d in daily[-7:]]
    overall_slope = (overall_values[-1] - overall_values[0]) / max(len(overall_values) - 1, 1)

    return {
        "generated_at": datetime.now().isoformat(),
        "days_analyzed": len(daily),
        "overall": {
            "current": overall_values[-1],
            "7d_ago": overall_values[0],
            "slope": round(overall_slope, 2),
            "direction": "up" if overall_slope > 0.5 else "down" if overall_slope < -0.5 else "flat",
        },
        "dimensions": trends,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="进化效果量化工具")
    sub = parser.add_subparsers(dest="cmd")

    compare_p = sub.add_parser("compare", help="对比进化前后")
    compare_p.add_argument("--dimension", required=True)
    compare_p.add_argument("--target", required=True)

    sub.add_parser("report", help="完整效果报告")
    sub.add_parser("trend", help="趋势分析")

    args = parser.parse_args()

    if args.cmd == "compare":
        result = compare_before_after(args.dimension, args.target)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == "report":
        result = generate_effect_report()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == "trend":
        result = generate_trend()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
