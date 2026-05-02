#!/usr/bin/env python3
"""
evolve_dispatcher.staging.py — 4维度分发器实现（待重命名）
"""
import json
import os
from pathlib import Path
from datetime import datetime


def find_project_root():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def get_dimension(target: str) -> str:
    """
    根据 target 前缀确定维度。

    维度映射:
      agent:xxx → agent
      skill:xxx → skill
      rule:xxx  → rule
      tool:xxx  → instinct
      (其他)    → instinct
    """
    if target.startswith("agent:"):
        return "agent"
    elif target.startswith("skill:"):
        return "skill"
    elif target.startswith("rule:"):
        return "rule"
    elif target.startswith("tool:"):
        return "instinct"
    else:
        return "instinct"


def meets_threshold(dimension: str, count: int) -> bool:
    """
    判断纠正次数是否达到维度阈值。

    维度差异化阈值:
      agent:  >= 3 次
      skill:  >= 3 次
      rule:   >= 5 次（Rules 改动更谨慎）
      instinct: >= 2 次
    """
    thresholds = {
        "agent": 3,
        "skill": 3,
        "rule": 5,
        "instinct": 2,
    }
    return count >= thresholds.get(dimension, 3)


def build_decision(
    dimension: str,
    target: str,
    analysis: dict,
    config: dict,
    root: Path,
) -> dict:
    """
    为指定维度构建进化决策。

    返回:
    {
        "dimension": str,
        "target": str,
        "target_file": str or None,
        "action": "auto_apply" | "propose",
        "suggested_change": str,
        "confidence": float,
        "risk_level": "low" | "medium" | "high",
    }
    """
    # 提取纠正模式信息
    pattern_key = f"{target}:unknown"
    for k, v in analysis.get("correction_patterns", {}).items():
        if k.startswith(f"{target}:"):
            pattern_key = k
            break

    examples = analysis.get("correction_patterns", {}).get(pattern_key, {}).get("examples", [])
    example_summary = ""
    if examples:
        example_summary = "\n".join([f"- {e.get('correction', '')}" for e in examples[:3]])

    # 根据维度生成建议
    if dimension == "agent":
        return _agent_decision(target, pattern_key, example_summary, analysis, config, root)
    elif dimension == "skill":
        return _skill_decision(target, pattern_key, example_summary, analysis, config, root)
    elif dimension == "rule":
        return _rule_decision(target, pattern_key, example_summary, analysis, config, root)
    else:
        return _instinct_decision(target, pattern_key, example_summary, analysis, config, root)


def _agent_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """Agent 维度进化策略"""
    agent_name = target.replace("agent:", "")
    paths = config.get("paths", {})
    agents_dir = root / paths.get("agents_dir", "agents")
    agent_file = agents_dir / f"{agent_name}.md"

    # 低风险模式 → auto_apply
    low_risk = any(k in pattern_key.lower() for k in ["comment", "format", "typo", "docs", "print", "logging"])
    action = "auto_apply" if low_risk else "propose"
    risk_level = "low" if low_risk else "medium"

    # 构建改动建议
    if "print" in pattern_key.lower() or "logging" in pattern_key.lower():
        suggested = "## 注意事项\n- 避免使用 print() 调试，推荐使用 logging 模块\n"
    elif "comment" in pattern_key.lower():
        suggested = "## 注意事项\n- 代码注释需清晰准确，避免误导\n"
    else:
        suggested = f"## 注意事项\n- 根据用户纠正模式补充最佳实践\n示例纠正：\n{examples}\n"

    return {
        "dimension": "agent",
        "target": target,
        "target_file": str(agent_file),
        "action": action,
        "suggested_change": suggested,
        "confidence": 0.6,
        "risk_level": risk_level,
    }


def _skill_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """Skill 维度进化策略"""
    skill_name = target.replace("skill:", "")
    paths = config.get("paths", {})
    skills_dir = root / paths.get("skills_dir", "skills")
    skill_file = skills_dir / skill_name / "SKILL.md"

    return {
        "dimension": "skill",
        "target": target,
        "target_file": str(skill_file),
        "action": "propose",
        "suggested_change": f"## 补充场景\n根据用户纠正补充决策分支：\n{examples}\n",
        "confidence": 0.5,
        "risk_level": "medium",
    }


def _rule_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """Rule 维度进化策略"""
    rule_name = target.replace("rule:", "")
    paths = config.get("paths", {})
    rules_dir = root / paths.get("rules_dir", "rules")
    rule_file = rules_dir / f"{rule_name}.md"

    return {
        "dimension": "rule",
        "target": target,
        "target_file": str(rule_file),
        "action": "propose",
        "suggested_change": f"## 例外情况\n根据用户行为增加例外：\n{examples}\n",
        "confidence": 0.4,
        "risk_level": "high",
    }


def _instinct_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """Instinct 维度进化策略"""
    return {
        "dimension": "instinct",
        "target": target,
        "target_file": None,
        "action": "auto_apply",
        "suggested_change": f"更新失败模式记录: {target}",
        "confidence": 0.7,
        "risk_level": "low",
    }


def dispatch_evolution(analysis: dict, config: dict, root: Path | None = None, sessions: list | None = None) -> list[dict]:
    """
    统一进化信号处理器 — 4维度分发。

    输入: analysis = {
        "correction_hotspots": {"agent:xxx": 5, "skill:xxx": 3, ...},
        "correction_patterns": {...},
        "primary_target": "...",
    }

    输出: decisions[] = [
        {"dimension": "agent|skill|rule|instinct", "target": "xxx", "action": "auto_apply|propose", ...},
    ]
    """
    if root is None:
        root = find_project_root()
    elif isinstance(root, str):
        root = Path(root)

    hotspots = analysis.get("correction_hotspots", {})
    if not hotspots:
        return []

    decisions = []
    seen_dimensions = {}

    for target, count in hotspots.items():
        dimension = get_dimension(target)

        # 同一维度只生成一个决策（取 count 最高的 target）
        if dimension in seen_dimensions:
            if count > hotspots.get(seen_dimensions[dimension], 0):
                seen_dimensions[dimension] = target
        else:
            seen_dimensions[dimension] = target

    # 从 sessions 中提取 instinct_record_ids
    instinct_ids = []
    for s in sessions:
        instinct_ids.extend(s.get("instinct_record_ids", []))
    instinct_ids = list(dict.fromkeys(instinct_ids))  # 去重

    for dimension, target in seen_dimensions.items():
        if not meets_threshold(dimension, hotspots.get(target, 0)):
            continue

        decision = build_decision(dimension, target, analysis, config, root)
        decision["id"] = f"evo-{datetime.now().strftime('%Y%m%d%H%M%S')}-{dimension}"
        decision["linked_instinct_ids"] = instinct_ids
        decisions.append(decision)

    return decisions


def main():
    """CLI 测试入口"""
    root = find_project_root()
    config = {"paths": {"agents_dir": "agents", "skills_dir": "skills", "rules_dir": "rules"}}

    # 模拟分析数据
    analysis = {
        "correction_hotspots": {
            "agent:backend-dev": 5,
            "skill:testing": 3,
            "tool:Bash": 3,
        },
        "correction_patterns": {
            "agent:backend-dev:print_debug": {"count": 5, "examples": [{"correction": "不要用 print，用 logging"}]},
        },
        "primary_target": "agent:backend-dev",
    }

    decisions = dispatch_evolution(analysis, config, root)
    print(json.dumps(decisions, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
