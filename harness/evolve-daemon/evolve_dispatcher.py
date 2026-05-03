#!/usr/bin/env python3
"""
进化分发器 — 8维度分析决策引擎

4个核心维度:
  agent  - Agent 行为优化
  skill  - Skill 决策完善
  rule   - 团队规则调整
  instinct - 本能记录更新

4个扩展维度:
  performance - 性能分析与优化
  interaction - 交互质量提升
  security    - 安全风险管控
  context     - 上下文管理优化
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

    核心维度:
      agent:xxx → agent
      skill:xxx → skill
      rule:xxx  → rule
      tool:xxx  → instinct

    扩展维度（performance/interaction/security/context 前缀）:
      perf:xxx  → performance
      interact:xxx → interaction
      sec:xxx   → security
      ctx:xxx   → context

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
    elif target.startswith("perf:"):
        return "performance"
    elif target.startswith("interact:"):
        return "interaction"
    elif target.startswith("sec:"):
        return "security"
    elif target.startswith("ctx:"):
        return "context"
    else:
        return "instinct"


def meets_threshold(dimension: str, count: int) -> bool:
    """
    判断纠正次数是否达到维度阈值。

    维度差异化阈值:
      agent:       >= 3 次
      skill:       >= 3 次
      rule:        >= 5 次（Rules 改动更谨慎）
      instinct:    >= 2 次
      performance: >= 4 次（性能问题需谨慎）
      interaction: >= 4 次（交互问题积累后处理）
      security:    >= 2 次（安全问题立即关注）
      context:     >= 3 次
    """
    thresholds = {
        "agent": 3,
        "skill": 3,
        "rule": 5,
        "instinct": 2,
        "performance": 4,
        "interaction": 4,
        "security": 2,
        "context": 3,
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
    elif dimension == "performance":
        return _performance_decision(target, pattern_key, example_summary, analysis, config, root)
    elif dimension == "interaction":
        return _interaction_decision(target, pattern_key, example_summary, analysis, config, root)
    elif dimension == "security":
        return _security_decision(target, pattern_key, example_summary, analysis, config, root)
    elif dimension == "context":
        return _context_decision(target, pattern_key, example_summary, analysis, config, root)
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


def _performance_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """
    性能维度进化策略

    分析内容:
    - 工具调用耗时
    - 超时模式识别
    - 慢工具优化建议
    """
    perf_data = analysis.get("performance", {})
    tool_stats = perf_data.get("tool_stats", {})
    slow_tools = perf_data.get("slow_tools", [])

    perf_name = target.replace("perf:", "")
    related_slow = [t for t in slow_tools if perf_name in t.get("tool", "")]

    # 构建性能优化建议
    if related_slow:
        slow_info = related_slow[0]
        suggested = (
            f"## 性能优化建议\n"
            f"- 工具 {slow_info['tool']} 平均耗时 {slow_info['avg_ms']:.0f}ms，超过阈值 {slow_info['threshold_ms']:.0f}ms\n"
            f"- 建议：检查是否有不必要的操作或优化算法复杂度\n"
            f"- 考虑添加缓存或批量处理"
        )
        confidence = 0.75
        risk_level = "medium"
    else:
        suggested = f"## 性能优化\n基于分析数据优化工具性能\n{examples}\n"
        confidence = 0.6
        risk_level = "low"

    # 性能问题通常是自动修复
    action = "auto_apply" if risk_level == "low" else "propose"

    return {
        "dimension": "performance",
        "target": target,
        "target_file": None,
        "action": action,
        "suggested_change": suggested,
        "confidence": confidence,
        "risk_level": risk_level,
    }


def _interaction_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """
    交互质量维度进化策略

    分析内容:
    - 会话轮次
    - 任务完成时间
    - 用户满意度推断
    """
    interaction_data = analysis.get("interaction", {})
    satisfaction_score = interaction_data.get("satisfaction_score", 70)
    avg_turns = interaction_data.get("avg_turns_per_session", 0)

    # 满意度低于60或平均轮次过高都需要优化
    needs_intervention = satisfaction_score < 60 or avg_turns > 20

    interaction_name = target.replace("interact:", "")

    if needs_intervention:
        suggestions = []
        if satisfaction_score < 60:
            suggestions.append(f"- 当前满意度评分 {satisfaction_score}，低于阈值")
        if avg_turns > 20:
            suggestions.append(f"- 平均会话轮次 {avg_turns} 过高，可能存在沟通效率问题")

        suggested = (
            f"## 交互质量优化建议\n" + "\n".join(suggestions) + f"\n"
            f"- 考虑增加主动确认步骤\n"
            f"- 优化输出格式，减少不必要的冗余"
        )
        confidence = 0.65
        risk_level = "medium"
    else:
        suggested = f"## 交互优化\n交互质量整体良好，仅需小幅改进\n{examples}\n"
        confidence = 0.7
        risk_level = "low"

    return {
        "dimension": "interaction",
        "target": target,
        "target_file": None,
        "action": "propose",
        "suggested_change": suggested,
        "confidence": confidence,
        "risk_level": risk_level,
    }


def _security_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """
    安全性维度进化策略

    分析内容:
    - 危险操作拦截
    - 权限请求合理性
    - 敏感信息暴露检测
    """
    security_data = analysis.get("security", {})
    danger_ops = security_data.get("danger_operations", {})
    permission_score = security_data.get("permission_score", 100)
    sensitive_exposures = security_data.get("sensitive_exposures", [])

    sec_name = target.replace("sec:", "")

    # 安全问题风险等级较高
    if danger_ops or permission_score < 60 or len(sensitive_exposures) > 0:
        suggestions = []
        if danger_ops:
            suggestions.append(f"- 检测到危险操作: {list(danger_ops.keys())}")
        if permission_score < 60:
            suggestions.append(f"- 权限请求评分 {permission_score}，可能存在权限滥用")
        if sensitive_exposures:
            suggestions.append(f"- 检测到 {len(sensitive_exposures)} 处敏感信息暴露风险")

        suggested = (
            f"## 安全风险处理建议\n" + "\n".join(suggestions) + f"\n"
            f"- 建议添加安全检查 Hook\n"
            f"- 考虑在 Agent 指令中增加安全提醒"
        )
        confidence = 0.8
        risk_level = "high"
    else:
        suggested = f"## 安全优化\n安全状况良好\n{examples}\n"
        confidence = 0.7
        risk_level = "low"

    return {
        "dimension": "security",
        "target": target,
        "target_file": None,
        "action": "propose",
        "suggested_change": suggested,
        "confidence": confidence,
        "risk_level": risk_level,
    }


def _context_decision(target: str, pattern_key: str, examples: str, analysis: dict, config: dict, root: Path) -> dict:
    """
    上下文维度进化策略

    分析内容:
    - 上下文切换频率
    - 知识复用率
    - 多轮对话连贯性
    """
    context_data = analysis.get("context", {})
    avg_switches = context_data.get("avg_context_switches", 0)
    reuse_rate = context_data.get("knowledge_reuse_rate", 0)
    coherence_score = context_data.get("avg_coherence_score", 0)

    ctx_name = target.replace("ctx:", "")

    # 上下文切换过多或连贯性差需要优化
    needs_intervention = avg_switches > 5 or coherence_score < 0.3

    if needs_intervention:
        suggestions = []
        if avg_switches > 5:
            suggestions.append(f"- 平均上下文切换 {avg_switches} 次/会话，频率较高")
        if coherence_score < 0.3:
            suggestions.append(f"- 连贯性评分 {coherence_score:.2f} 较低，可能存在话题跳跃")

        suggested = (
            f"## 上下文管理优化建议\n" + "\n".join(suggestions) + f"\n"
            f"- 建议在 Agent 中增加上下文保持策略\n"
            f"- 考虑增加知识复用机制"
        )
        confidence = 0.6
        risk_level = "medium"
    else:
        suggested = f"## 上下文优化\n上下文管理良好，知识复用率 {reuse_rate}\n{examples}\n"
        confidence = 0.7
        risk_level = "low"

    return {
        "dimension": "context",
        "target": target,
        "target_file": None,
        "action": "propose",
        "suggested_change": suggested,
        "confidence": confidence,
        "risk_level": risk_level,
    }


def dispatch_evolution(analysis: dict, config: dict, root: Path | None = None, sessions: list | None = None) -> list[dict]:
    """
    统一进化信号处理器 — 8维度分发。

    4个核心维度: agent, skill, rule, instinct
    4个扩展维度: performance, interaction, security, context

    输入: analysis = {
        "correction_hotspots": {"agent:xxx": 5, "skill:xxx": 3, ...},
        "correction_patterns": {...},
        "primary_target": "...",
        "performance": {...},
        "interaction": {...},
        "security": {...},
        "context": {...},
    }

    输出: decisions[] = [
        {"dimension": "agent|skill|rule|instinct|performance|interaction|security|context",
         "target": "xxx", "action": "auto_apply|propose", ...},
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

    # ========== 处理扩展维度（performance/interaction/security/context）==========
    decisions.extend(_dispatch_extended_dimensions(analysis, instinct_ids))

    return decisions


def _dispatch_extended_dimensions(analysis: dict, instinct_ids: list) -> list[dict]:
    """
    处理4个扩展维度的进化决策

    这些维度不依赖于 correction_hotspots，而是直接分析其数据
    """
    decisions = []
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

    # 1. 性能维度
    perf_data = analysis.get("performance", {})
    slow_tools = perf_data.get("slow_tools", [])
    timeouts = perf_data.get("timeouts", {})
    if slow_tools or timeouts:
        target = f"perf:tool_performance"
        if meets_threshold("performance", len(slow_tools) + len(timeouts)):
            decision = build_decision("performance", target, analysis, {}, Path("."))
            decision["id"] = f"evo-{timestamp}-performance"
            decision["linked_instinct_ids"] = instinct_ids
            decision["details"] = {
                "slow_tools": slow_tools,
                "timeouts": timeouts,
            }
            decisions.append(decision)

    # 2. 交互质量维度
    interaction_data = analysis.get("interaction", {})
    satisfaction = interaction_data.get("satisfaction_score", 70)
    avg_turns = interaction_data.get("avg_turns_per_session", 0)
    if satisfaction < 60 or avg_turns > 20:
        target = f"interact:session_quality"
        if meets_threshold("interaction", 1):
            decision = build_decision("interaction", target, analysis, {}, Path("."))
            decision["id"] = f"evo-{timestamp}-interaction"
            decision["linked_instinct_ids"] = instinct_ids
            decision["details"] = {
                "satisfaction_score": satisfaction,
                "avg_turns": avg_turns,
            }
            decisions.append(decision)

    # 3. 安全性维度
    security_data = analysis.get("security", {})
    danger_ops = security_data.get("danger_operations", {})
    permission_score = security_data.get("permission_score", 100)
    sensitive_exposures = security_data.get("sensitive_exposures", [])
    if danger_ops or permission_score < 60 or len(sensitive_exposures) > 0:
        target = f"sec:security_risks"
        if meets_threshold("security", len(danger_ops) + len(sensitive_exposures) + (1 if permission_score < 60 else 0)):
            decision = build_decision("security", target, analysis, {}, Path("."))
            decision["id"] = f"evo-{timestamp}-security"
            decision["linked_instinct_ids"] = instinct_ids
            decision["details"] = {
                "danger_operations": danger_ops,
                "permission_score": permission_score,
                "exposure_count": len(sensitive_exposures),
            }
            decisions.append(decision)

    # 4. 上下文维度
    context_data = analysis.get("context", {})
    avg_switches = context_data.get("avg_context_switches", 0)
    coherence = context_data.get("avg_coherence_score", 0)
    if avg_switches > 5 or coherence < 0.3:
        target = f"ctx:context_management"
        if meets_threshold("context", 1):
            decision = build_decision("context", target, analysis, {}, Path("."))
            decision["id"] = f"evo-{timestamp}-context"
            decision["linked_instinct_ids"] = instinct_ids
            decision["details"] = {
                "avg_switches": avg_switches,
                "coherence_score": coherence,
            }
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
