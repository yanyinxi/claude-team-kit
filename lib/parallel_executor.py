#!/usr/bin/env python3
"""
并行策略对比沙箱 — 模拟多 Agent 并行执行，对比各策略变体效果

职责:
  1. 接受多个策略变体作为输入
  2. 模拟各变体的并行执行过程
  3. 基于质量/速度/协作三维度评分
  4. 输出最佳策略变体

当前实现: 模拟执行（`_simulate_execution()`），用于策略预评估。
真实并行执行依赖 Claude Code 的 Agent 工具原生并发能力。

用法:
  python3 .claude/lib/parallel_executor.py                    # 默认对比所有变体
  python3 .claude/lib/parallel_executor.py --strategy hybrid  # 模拟特定策略
"""
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


# ═══════════════════════════════════════════════════════════════
# 模拟执行引擎
# ═══════════════════════════════════════════════════════════════

def _simulate_execution(variant: dict, task_complexity: int) -> dict:
    """
    模拟一个策略变体的并行执行过程。

    模拟模型:
      - 并行度越高，总时间越短（Amdahl 定律修正）
      - 但并行度越高，协调开销越大
      - 质量取决于：是否包含 code-reviewer、有测试覆盖
    """
    parallelism = variant.get("parallelism", 1)
    agents = variant.get("agents", {})
    agent_count = sum(agents.values()) if agents else parallelism

    # 时间模拟: 基础任务时间 * 并行效率
    base_time = task_complexity * 15  # 每个复杂度单位 15 分钟
    # Amdahl: 80% 可并行 + 20% 串行
    parallel_fraction = 0.8
    serial_fraction = 0.2
    coordination_overhead = math.log2(max(agent_count, 1)) * 2
    simulated_time = base_time * (
        serial_fraction +
        parallel_fraction / max(agent_count, 1) * (1 + coordination_overhead / 10)
    )

    # 质量模拟: 基于 Agent 角色组合
    has_reviewer = "code-reviewer" in agents
    has_tester = "test" in agents
    has_fe_be = "frontend-developer" in agents and "backend-developer" in agents

    quality_base = 60
    if has_reviewer:
        quality_base += 15
    if has_tester:
        quality_base += 10
    if has_fe_be:
        quality_base += 10  # 前后端协作加分
    # 并行度过高反而降低质量（沟通成本）
    quality = quality_base - max(0, (agent_count - 4) * 3)
    quality = max(20, min(100, quality))

    # 协作效果: 基于角色多样性
    unique_roles = len(set(agents.keys())) if agents else 1
    collaboration = min(100, unique_roles * 25 + 25)

    # 综合评分
    time_score = max(0, 100 - simulated_time / base_time * 50)
    overall = round(time_score * 0.3 + quality * 0.4 + collaboration * 0.3, 1)

    return {
        "simulated_time_min": round(simulated_time, 1),
        "time_score": round(time_score, 1),
        "quality_score": quality,
        "collaboration_score": collaboration,
        "overall_score": overall,
        "agent_count": agent_count,
        "has_reviewer": has_reviewer,
        "has_tester": has_tester,
        "has_fe_be_collab": has_fe_be,
    }


# ═══════════════════════════════════════════════════════════════
# 策略加载
# ═══════════════════════════════════════════════════════════════

def _load_variants() -> dict:
    variants_file = (
        Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
        / ".claude" / "data" / "strategy_variants.json"
    )
    if variants_file.exists():
        try:
            return json.loads(variants_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # 默认变体
    return {
        "sequential": {
            "name": "顺序执行",
            "parallelism": 1,
            "agents": {"backend-developer": 1},
        },
        "granular": {
            "name": "细粒度分解",
            "parallelism": 3,
            "agents": {"backend-developer": 1, "frontend-developer": 1, "code-reviewer": 1},
        },
        "hybrid": {
            "name": "混合策略",
            "parallelism": 3,
            "agents": {"backend-developer": 1, "frontend-developer": 1, "test": 1},
        },
        "parallel_high": {
            "name": "高并行度",
            "parallelism": 5,
            "agents": {
                "backend-developer": 2,
                "frontend-developer": 2,
                "code-reviewer": 1,
            },
        },
    }


# ═══════════════════════════════════════════════════════════════
# 对比执行
# ═══════════════════════════════════════════════════════════════

def compare_strategies(task_complexity: int = 5, task_domain: str = "fullstack") -> dict:
    """对比所有策略变体，返回排名和最佳策略"""
    variants = _load_variants()
    results = {}

    for key, variant in variants.items():
        if key.startswith("_"):
            continue
        if not isinstance(variant, dict):
            continue
        result = _simulate_execution(variant, task_complexity)
        result["strategy_name"] = variant.get("name", key)
        result["parallelism"] = variant.get("parallelism", 1)
        results[key] = result

    # 按综合分排序
    ranked = sorted(results.items(), key=lambda x: x[1]["overall_score"], reverse=True)

    return {
        "task": {
            "complexity": task_complexity,
            "domain": task_domain,
        },
        "variants": results,
        "ranking": [{"rank": i + 1, "strategy": k, "score": v["overall_score"]}
                     for i, (k, v) in enumerate(ranked)],
        "best_variant": ranked[0][0],
        "best_score": ranked[0][1]["overall_score"],
        "simulated_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="并行策略对比沙箱")
    parser.add_argument("--strategy", default=None, help="模拟特定策略")
    parser.add_argument("--complexity", type=int, default=5, help="任务复杂度 (1-10)")
    parser.add_argument("--domain", default="fullstack", help="任务领域")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    variants = _load_variants()

    if args.strategy:
        variant = variants.get(args.strategy)
        if not variant:
            print(f"❌ 未知策略: {args.strategy}")
            print(f"可用: {list(variants.keys())}")
            sys.exit(1)
        result = _simulate_execution(variant, args.complexity)
        result["strategy_name"] = variant.get("name", args.strategy)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_single_result(args.strategy, result)
    else:
        comparison = compare_strategies(args.complexity, args.domain)
        if args.json:
            print(json.dumps(comparison, indent=2, ensure_ascii=False))
        else:
            _print_comparison(comparison)


def _print_single_result(strategy: str, result: dict):
    print(f"🧪 模拟执行: {result['strategy_name']} ({strategy})")
    print(f"   并行 Agent 数: {result['agent_count']}")
    print(f"   预估时间: {result['simulated_time_min']} 分钟")
    print(f"   质量分: {result['quality_score']}/100")
    print(f"   协作分: {result['collaboration_score']}/100")
    print(f"   综合分: {result['overall_score']}/100")
    print(f"   审查覆盖: {'✅' if result['has_reviewer'] else '❌'}")
    print(f"   测试覆盖: {'✅' if result['has_tester'] else '❌'}")
    print(f"   前后端协作: {'✅' if result['has_fe_be_collab'] else '❌'}")


def _print_comparison(comparison: dict):
    task = comparison["task"]
    print(f"🧪 策略对比 — 复杂度 {task['complexity']}/10, 领域 {task['domain']}")
    print()
    print(f"{'排名':<6} {'策略':<16} {'综合分':<8} {'时间(分)':<10} {'质量':<6} {'协作':<6}")
    print("-" * 56)

    for item in comparison["ranking"]:
        key = item["strategy"]
        v = comparison["variants"][key]
        print(f"{item['rank']:<6} {key:<16} {v['overall_score']:<8.1f} "
              f"{v['simulated_time_min']:<10.1f} {v['quality_score']:<6} {v['collaboration_score']:<6}")

    print()
    best = comparison["best_variant"]
    print(f"🏆 最佳策略: {best} ({comparison['variants'][best]['strategy_name']}) "
          f"— 综合分 {comparison['best_score']:.1f}/100")


if __name__ == "__main__":
    main()
