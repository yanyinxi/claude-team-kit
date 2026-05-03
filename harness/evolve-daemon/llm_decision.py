#!/usr/bin/env python3
"""
LLM 决策引擎 — 用 LLM 分析会话数据，决定下一步行动。

核心决策:
1. skip — 数据不足以支撑建议
2. propose — 需要生成改进提案
3. auto_apply — 置信度高 + 风险低，直接应用

决策规则:
- 新目标（未在 instinct 中出现）→ 强制提案
- 安全/权限相关 → 强制提案
- 多文件修改 → 强制提案
- 低风险 + 高置信（>= auto_apply_threshold）→ 自动应用
- 其他情况 → 生成提案
"""
import json
import os
from pathlib import Path
from datetime import datetime
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
        "decision": {
            "enabled": True,
            "auto_apply_threshold": 0.8,
            "high_risk_threshold": 0.5,
        },
        "claude_api": {
            "decide_model": "claude-sonnet-4-6",
            "decide_max_tokens": 2048,
            "decide_temperature": 0.2,
        },
        "paths": {
            "data_dir": ".claude/data",
            "proposals_dir": ".claude/proposals",
            "skills_dir": "skills",
            "agents_dir": "agents",
            "rules_dir": "rules",
            "instinct_dir": "instinct",
        },
        "safety": {
            "breaker": {"max_consecutive_rejects": 3, "pause_days": 30},
        },
    }


def load_instinct(root: Path) -> dict:
    """加载 instinct-record.json"""
    instinct_path = root / "harness" / "instinct" / "instinct-record.json"
    if instinct_path.exists():
        try:
            return json.loads(instinct_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"records": []}


def get_existing_targets(instinct: dict) -> set:
    """获取 instinct 中已有的 target 列表"""
    targets = set()
    for record in instinct.get("records", []):
        pattern = record.get("pattern", "")
        if "agent:" in pattern:
            targets.add(pattern.split("agent:")[1].split()[0])
        if "skill:" in pattern:
            targets.add(pattern.split("skill:")[1].split()[0])
    return targets


def is_new_target(target: str, instinct: dict) -> bool:
    """判断是否是新 target（未在 instinct 中出现）"""
    existing = get_existing_targets(instinct)
    return target not in existing


def assess_risk(analysis: dict, config: dict) -> float:
    """
    评估风险等级（0.0 - 1.0）。

    规则:
    - 高风险模式（permission, security, auth）→ 1.0
    - 多文件修改 → 0.8
    - 已有高置信记录 → 0.3
    - 新目标 → 0.6
    """
    risk = 0.3  # 默认风险

    # 检查高风险模式
    hotspots = analysis.get("correction_hotspots", {})
    for target in hotspots.keys():
        target_lower = target.lower()
        for risk_pattern in config.get("decision", {}).get("risk_rules", {}).get("high_risk_patterns", []):
            if risk_pattern in target_lower:
                risk = max(risk, 0.9)

    # 新目标风险增加
    root = find_root()
    instinct = load_instinct(root)
    if hotspots:
        for target in hotspots.keys():
            if is_new_target(target, instinct):
                risk = max(risk, 0.6)

    # 多文件修改风险
    if analysis.get("multi_file_change", False):
        risk = max(risk, 0.8)

    return min(risk, 1.0)


def call_claude_api(
    system_prompt: str,
    user_message: str,
    config: dict
) -> Optional[dict]:
    """调用 Claude API"""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY 未设置，无法调用 LLM 决策引擎。\n"
            "请先配置 API Key：\n"
            "  1. 复制 .env.example 为 .env\n"
            "  2. 填入 ANTHROPIC_API_KEY=your_key\n"
            "  3. 或在终端执行: export ANTHROPIC_API_KEY=your_key\n"
            "获取 API Key: https://console.anthropic.com/settings/keys"
        )

    api_config = config.get("claude_api", {})

    try:
        # 优先使用 SDK
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=api_config.get("decide_model", "claude-sonnet-4-6"),
            max_tokens=api_config.get("decide_max_tokens", 2048),
            temperature=api_config.get("decide_temperature", 0.2),
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content = block.text
                break

    except ImportError:
        # 降级为 urllib
        try:
            import urllib.request

            body = json.dumps({
                "model": api_config.get("decide_model", "claude-sonnet-4-6"),
                "max_tokens": api_config.get("decide_max_tokens", 2048),
                "temperature": api_config.get("decide_temperature", 0.2),
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                content = result["content"][0]["text"]

        except Exception:
            return None

    # 解析 LLM 返回
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"action": "propose", "reason": "Invalid JSON from LLM", "confidence": 0.5}


def decide_action(sessions: list[dict], analysis: dict, config: Optional[dict] = None) -> dict:
    """
    LLM 决策主函数。

    返回:
    {
        "action": "auto_apply" | "propose" | "skip",
        "reason": str,
        "target_file": str | None,
        "suggested_change": str | None,
        "risk_level": "low" | "medium" | "high",
        "confidence": float,
        "id": str,
    }
    """
    if config is None:
        config = _default_config()

    if not config.get("decision", {}).get("enabled", True):
        return {"action": "skip", "reason": "LLM decision disabled", "confidence": 0}

    # 规则保护：检查熔断器
    if _check_circuit_breaker(config):
        return {"action": "skip", "reason": "Circuit breaker triggered", "confidence": 0}

    # 检查是否需要干预
    hotspots = analysis.get("correction_hotspots", {})
    if not hotspots:
        return {"action": "skip", "reason": "No correction hotspots", "confidence": 0}

    # 规则保护：安全相关 → 强制提案
    risk_score = assess_risk(analysis, config)
    if risk_score >= 0.9:
        return {
            "action": "propose",
            "reason": "High risk (security/permission related)",
            "risk_level": "high",
            "confidence": 0.5,
            "id": f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }

    # 构建分析 prompt
    system_prompt = """你是 AI 工程规范进化助手。分析使用数据，判断是否需要改进 Agent/Skill/Rule 定义。

决策选项：
1. auto_apply: 置信度极高，风险极低，可以自动应用
2. propose: 需要人工 Review，生成提案
3. skip: 数据不足以支撑建议

决策规则：
- 低风险（comment/format/typo/docs） + 高置信（>= 0.8）→ auto_apply
- 新目标、未验证的改动 → propose
- 高风险（安全/权限/新目标/多文件）→ propose
- 数据不足以支撑明确建议 → skip

输出格式（JSON）：
{
  "action": "auto_apply" | "propose" | "skip",
  "reason": "决策理由",
  "confidence": 0.0-1.0,
  "target_file": "agents/xxx.md 或 skills/xxx/SKILL.md",
  "suggested_change": "具体改动内容（如果是 auto_apply）",
  "risk_level": "low" | "medium" | "high"
}
"""

    # 提取关键数据
    correction_data = []
    for s in sessions[-20:]:  # 最近 20 个会话
        corrections = s.get("corrections", [])
        for c in corrections[:3]:  # 每个会话最多 3 条
            correction_data.append({
                "session": s.get("session_id", ""),
                "target": c.get("target", ""),
                "context": c.get("context", ""),
                "correction": c.get("user_correction", ""),
            })

    # 也从失败数据中提取
    failure_data = []
    for s in sessions[-10:]:
        failure_types = s.get("failure_types", {})
        for error_type, count in failure_types.items():
            if count >= 2:
                failure_data.append({
                    "session": s.get("session_id", ""),
                    "error_type": error_type,
                    "count": count,
                })

    user_message = json.dumps({
        "hotspots": hotspots,
        "corrections": correction_data[:10],
        "failures": failure_data[:10],
        "total_sessions": len(sessions),
        "primary_target": analysis.get("primary_target", ""),
    }, ensure_ascii=False)

    # 调用 LLM
    try:
        llm_result = call_claude_api(system_prompt, user_message, config)
    except EnvironmentError as e:
        # 网络/IO 错误不应该中断主流程，返回保守决策
        logger.warning(f"LLM 调用失败（EnvironmentError）: {e}")
        return {
            "action": "propose",
            "reason": f"LLM 调用失败: {e}，使用保守决策",
            "confidence": 0.3,
            "risk_level": "high",
            "id": f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }

    # 风险检查
    risk_level = llm_result.get("risk_level", "medium")
    if risk_level == "high" or risk_score >= config.get("decision", {}).get("high_risk_threshold", 0.5):
        return {
            "action": "propose",
            "reason": llm_result.get("reason", "Risk level is high"),
            "confidence": llm_result.get("confidence", 0.5),
            "risk_level": "high",
            "id": f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }

    # 自动应用检查
    confidence = llm_result.get("confidence", 0)
    auto_threshold = config.get("decision", {}).get("auto_apply_threshold", 0.8)
    if llm_result.get("action") == "auto_apply" and confidence >= auto_threshold and risk_level == "low":
        return {
            "action": "auto_apply",
            "reason": llm_result.get("reason", "Low risk + high confidence"),
            "confidence": confidence,
            "target_file": llm_result.get("target_file"),
            "suggested_change": llm_result.get("suggested_change"),
            "risk_level": "low",
            "id": f"auto-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }

    # 默认生成提案
    return {
        "action": "propose",
        "reason": llm_result.get("reason", "Default to proposal"),
        "confidence": llm_result.get("confidence", 0.5),
        "risk_level": risk_level,
        "id": f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    }


def _rule_based_decision(analysis: dict, config: dict) -> dict:
    """规则引擎降级决策"""

    hotspots = analysis.get("correction_hotspots", {})

    # 无热点 → skip
    if not hotspots:
        return {"action": "skip", "reason": "No hotspots", "confidence": 0}

    # 检查是否满足自动应用条件
    primary_target = analysis.get("primary_target", "")
    root = find_root()
    instinct = load_instinct(root)

    # 新目标 → 强制提案
    if is_new_target(primary_target, instinct):
        return {
            "action": "propose",
            "reason": f"New target: {primary_target}",
            "confidence": 0.5,
            "risk_level": "medium",
            "id": f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }

    # 有高置信记录 → 可以自动应用
    for record in instinct.get("records", []):
        if primary_target in record.get("pattern", ""):
            if record.get("confidence", 0) >= 0.8:
                return {
                    "action": "auto_apply",
                    "reason": f"High confidence record exists for {primary_target}",
                    "confidence": record.get("confidence", 0.8),
                    "risk_level": "low",
                    "id": f"auto-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                }

    # 默认 → 提案
    return {
        "action": "propose",
        "reason": f"Target {primary_target} has {hotspots.get(primary_target, 0)} corrections",
        "confidence": 0.5,
        "risk_level": "medium",
        "id": f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    }


def _check_circuit_breaker(config: dict) -> bool:
    """检查熔断器状态"""
    # TODO: 实现熔断器检查
    # 检查最近回滚次数，超过阈值暂停
    return False


def get_decision_stats(history_file: Path) -> dict:
    """获取决策统计"""
    if not history_file.exists():
        return {"total": 0, "auto_apply": 0, "propose": 0, "skip": 0}

    try:
        history = json.loads(history_file.read_text())
        total = len(history)
        auto_apply = sum(1 for h in history if h.get("action") == "auto_apply")
        propose = sum(1 for h in history if h.get("action") == "propose")
        skip = sum(1 for h in history if h.get("action") == "skip")

        return {
            "total": total,
            "auto_apply": auto_apply,
            "propose": propose,
            "skip": skip,
            "auto_apply_rate": round(auto_apply / max(total, 1), 2),
        }
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "auto_apply": 0, "propose": 0, "skip": 0}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LLM 决策引擎")
    parser.add_argument("action", choices=["decide", "stats"])
    parser.add_argument("--sessions", help="sessions.jsonl 路径")

    args = parser.parse_args()

    if args.action == "decide":
        # 读取最近的 sessions
        root = find_root()
        data_dir = root / ".claude" / "data"
        sessions_file = data_dir / "sessions.jsonl"

        sessions = []
        if sessions_file.exists():
            for line in sessions_file.read_text().splitlines():
                if line.strip():
                    try:
                        sessions.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # 模拟 analysis（实际应该从 analyzer 获取）
        from analyzer import aggregate_and_analyze
        config = load_config()
        analysis = aggregate_and_analyze(sessions, config, root)

        # 做决策
        decision = decide_action(sessions, analysis, config)
        print(json.dumps(decision, indent=2, ensure_ascii=False))

    elif args.action == "stats":
        root = find_root()
        history_file = root / ".claude" / "data" / "decision_history.json"
        stats = get_decision_stats(history_file)
        print(json.dumps(stats, indent=2))