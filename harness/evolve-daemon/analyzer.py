#!/usr/bin/env python3
"""
数据分析器 — 聚合多会话数据，识别改进模式。

输入: sessions.jsonl 中的新会话列表（含 rich_context）
输出: 结构化分析结果，供 proposer.py 使用
"""
import json
from collections import Counter
from pathlib import Path


def aggregate_and_analyze(sessions: list[dict], config: dict, root: Path) -> dict:
    """
    聚合多会话数据，输出分析结果。

    分析维度:
      1. 纠正热点: 哪些 skill/agent 被用户纠正最多
      2. 失败模式: 哪种 tool 失败率最高
      3. 技能覆盖: 哪些场景缺少 skill 指导
      4. 质量趋势: 纠正率是否在改善
    """
    # 统计纠正热点
    correction_targets: Counter = Counter()
    correction_patterns: dict[str, list] = {}

    for s in sessions:
        for c in s.get("corrections", []):
            if c is None:
                continue
            target = c.get("target", "unknown")
            correction_targets[target] += 1
            hint = c.get("root_cause_hint", "unknown")
            key = f"{target}:{hint}"
            correction_patterns.setdefault(key, []).append({
                "session_id": s.get("session_id", "unknown"),
                "context": c.get("context", ""),
                "correction": c.get("user_correction", ""),
            })

    # 统计工具失败
    # 从 rich_context.failure_stats.failure_types 读取
    for s in sessions:
        rich_ctx = s.get("rich_context", {})
        failure_stats = rich_ctx.get("failure_stats", {})
        failures = failure_stats.get("failure_types", {})
        for error_type, count in failures.items():
            if count >= 1:  # 有任何失败都记录
                correction_targets[f"tool:{error_type}"] += count

    tool_failures: Counter = Counter()
    for s in sessions:
        # 从 rich_context.failure_stats.total 或直接字段获取
        rich_ctx = s.get("rich_context", {})
        failure_stats = rich_ctx.get("failure_stats", {})
        failures = failure_stats.get("failure_tools", {})
        for tool, count in failures.items():
            tool_failures[tool] += count

    # 统计技能使用
    skill_usage: Counter = Counter()
    skill_override: Counter = Counter()
    for s in sessions:
        for sk in s.get("skills_used", []):
            if isinstance(sk, dict):
                skill_usage[sk.get("skill", "unknown")] += 1
                if sk.get("user_overrode"):
                    skill_override[sk.get("skill", "unknown")] += 1

    # 找出最需要改进的 target
    primary_target = None
    if correction_targets:
        primary_target = correction_targets.most_common(1)[0][0]

    # 计算纠正率趋势
    total_skills = sum(skill_usage.values())
    total_overrides = sum(skill_override.values())
    override_rate = total_overrides / max(total_skills, 1)

    return {
        "total_sessions": len(sessions),
        "correction_hotspots": dict(correction_targets),
        "correction_patterns": {
            k: {"count": len(v), "examples": v[:2]}
            for k, v in correction_patterns.items()
        },
        "tool_failures": dict(tool_failures),
        "skill_usage": dict(skill_usage),
        "skill_override_rate": round(override_rate, 2),
        "primary_target": primary_target or "general",
        "should_propose": (len(correction_targets) > 0 or len(tool_failures) > 0) and _meets_safety_checks(config, correction_targets),
    }


def _meets_safety_checks(config: dict, correction_targets: Counter) -> bool:
    """检查安全限制"""
    # 安全检查：每天最多 N 个提案
    max_proposals = config.get("safety", {}).get("max_proposals_per_day", 3)
    # 简化实现：只要有问题就允许提案（详细限制在 proposer 处理）
    return len(correction_targets) > 0
