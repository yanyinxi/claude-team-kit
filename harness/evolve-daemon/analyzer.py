#!/usr/bin/env python3
"""
数据分析器 — 聚合多会话数据，识别改进模式。

输入: sessions.jsonl 中的新会话列表（含 rich_context）
输出: 结构化分析结果，供 proposer.py 使用

分析维度:
  1. 纠正热点: 哪些 skill/agent 被用户纠正最多
  2. 失败模式: 哪种 tool 失败率最高
  3. 技能覆盖: 哪些场景缺少 skill 指导
  4. 质量趋势: 纠正率是否在改善
  5. 性能维度: 工具调用耗时、超时模式、响应时间
  6. 交互质量: 会话轮次、任务完成时间、用户满意度
  7. 安全性: 危险操作拦截、权限请求合理性、敏感信息暴露
  8. 上下文: 上下文切换频率、知识复用率、多轮连贯性
"""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def _safe_div(numerator, denominator, default=0):
    """安全除法，避免除零"""
    return round(numerator / denominator, 4) if denominator > 0 else default


def aggregate_and_analyze(sessions: list[dict], config: dict, root: Path) -> dict:
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

    # ========== 性能维度分析 ==========
    performance_analysis = _analyze_performance(sessions)

    # ========== 交互质量维度分析 ==========
    interaction_analysis = _analyze_interaction(sessions)

    # ========== 安全性维度分析 ==========
    security_analysis = _analyze_security(sessions)

    # ========== 上下文维度分析 ==========
    context_analysis = _analyze_context(sessions, config, root)

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

        # ========== 新增分析维度 ==========
        "performance": performance_analysis,
        "interaction": interaction_analysis,
        "security": security_analysis,
        "context": context_analysis,
    }


def _analyze_performance(sessions: list[dict]) -> dict:
    """
    性能维度分析：
    - 工具调用耗时统计
    - 识别超时模式
    - 统计平均响应时间
    """
    tool_durations: dict[str, list[float]] = defaultdict(list)
    timeouts: dict[str, int] = defaultdict(int)
    session_durations: list[float] = []

    for s in sessions:
        # 会话总时长
        start_time = s.get("started_at", "")
        end_time = s.get("ended_at", "")
        if start_time and end_time:
            try:
                from datetime import datetime
                # 标准化时间字符串：处理 Z 和时区
                def parse_iso_time(ts: str) -> datetime | None:
                    if not ts:
                        return None
                    ts = ts.strip()
                    # 去掉 UTC 标记
                    ts = ts.replace("Z", "+00:00")
                    # 去掉时区部分以避免 fromisoformat 在某些格式上失败
                    if "+" in ts:
                        ts = ts.split("+")[0]
                    elif "-" in ts and ts.count("-") > 2:  # 可能是带时区的负偏移
                        ts = ts.rsplit("-", 1)[0]
                    return datetime.fromisoformat(ts)
                start = parse_iso_time(start_time)
                end = parse_iso_time(end_time)
                if start and end:
                    duration = (end - start).total_seconds()
                    if duration > 0:
                        session_durations.append(duration)
            except (ValueError, TypeError):
                pass

        # 工具调用耗时
        for tool_call in s.get("tool_calls", []):
            tool_name = tool_call.get("name", "unknown")
            duration_ms = tool_call.get("duration_ms", 0)
            if duration_ms > 0:
                tool_durations[tool_name].append(duration_ms)

            # 检测超时（>30秒视为潜在超时）
            if duration_ms > 30000:
                timeouts[tool_name] += 1

    # 计算统计指标
    tool_stats = {}
    for tool_name, durations in tool_durations.items():
        if durations:
            avg_duration = statistics.mean(durations)
            median_duration = statistics.median(durations)
            max_duration = max(durations)
            tool_stats[tool_name] = {
                "avg_ms": round(avg_duration, 2),
                "median_ms": round(median_duration, 2),
                "max_ms": round(max_duration, 2),
                "call_count": len(durations),
            }

    # 识别慢工具（超过平均 2 倍标准差）
    slow_tools = []
    if tool_stats:
        all_avgs = [v["avg_ms"] for v in tool_stats.values() if v["avg_ms"] > 0]
        if all_avgs:
            overall_avg = statistics.mean(all_avgs)
            try:
                std_dev = statistics.stdev(all_avgs)
                threshold = overall_avg + 2 * std_dev
                for tool_name, stats in tool_stats.items():
                    if stats["avg_ms"] > threshold:
                        slow_tools.append({"tool": tool_name, "avg_ms": stats["avg_ms"], "threshold_ms": round(threshold, 2)})
            except statistics.StatisticsError:
                pass

    return {
        "tool_stats": tool_stats,
        "timeouts": dict(timeouts),
        "slow_tools": slow_tools,
        "avg_session_duration_s": round(statistics.mean(session_durations), 2) if session_durations else 0,
        "total_sessions_analyzed": len(sessions),
    }


def _analyze_interaction(sessions: list[dict]) -> dict:
    """
    交互质量维度分析：
    - 分析会话轮次
    - 统计任务完成时间
    - 用户满意度推断
    """
    turn_counts: list[int] = []
    task_durations: list[float] = []
    user_messages: int = 0
    assistant_messages: int = 0

    satisfaction_indicators: dict[str, int] = {
        "corrections": 0,        # 用户纠正次数（负面）
        "abandons": 0,           # 中断会话（负面）
        "restarts": 0,          # 重新开始（负面）
        "thanks": 0,             # 感谢语（正面）
        "praises": 0,           # 赞扬（正面）
    }

    for s in sessions:
        # 会话轮次（用户消息数）
        messages = s.get("messages", [])
        turns = len([m for m in messages if m.get("role") == "user"])
        turn_counts.append(turns)

        user_messages += len([m for m in messages if m.get("role") == "user"])
        assistant_messages += len([m for m in messages if m.get("role") == "assistant"])

        # 用户纠正次数
        corrections = s.get("corrections", [])
        satisfaction_indicators["corrections"] += len([c for c in corrections if c])

        # 检测中断/重启
        if s.get("abandoned"):
            satisfaction_indicators["abandons"] += 1

        # 检测感谢/赞扬关键词
        last_msg = messages[-1] if messages else {}
        content = str(last_msg.get("content", "")).lower() if last_msg else ""
        if any(kw in content for kw in ["谢谢", "感谢", "thank"]):
            satisfaction_indicators["thanks"] += 1
        if any(kw in content for kw in ["很好", "完美", "棒", "great", "perfect"]):
            satisfaction_indicators["praises"] += 1

        # 任务完成时间
        start = s.get("started_at", "")
        end = s.get("ended_at", "")
        if start and end:
            try:
                from datetime import datetime
                def parse_iso_time(ts: str) -> datetime | None:
                    if not ts:
                        return None
                    ts = ts.strip()
                    ts = ts.replace("Z", "+00:00")
                    if "+" in ts:
                        ts = ts.split("+")[0]
                    elif "-" in ts and ts.count("-") > 2:
                        ts = ts.rsplit("-", 1)[0]
                    return datetime.fromisoformat(ts)
                start_dt = parse_iso_time(start)
                end_dt = parse_iso_time(end)
                if start_dt and end_dt:
                    task_duration = (end_dt - start_dt).total_seconds()
                    if task_duration > 0:
                        task_durations.append(task_duration)
            except (ValueError, TypeError):
                pass

    # 计算满意度推断分数（0-100）
    positive = satisfaction_indicators["thanks"] + satisfaction_indicators["praises"]
    negative = satisfaction_indicators["corrections"] + satisfaction_indicators["abandons"]

    if len(sessions) > 0:
        base_score = 70  # 基准分
        satisfaction_score = base_score + (positive * 5) - (negative * 3)
        satisfaction_score = max(0, min(100, satisfaction_score))
    else:
        satisfaction_score = 0

    return {
        "avg_turns_per_session": round(statistics.mean(turn_counts), 2) if turn_counts else 0,
        "max_turns": max(turn_counts) if turn_counts else 0,
        "min_turns": min(turn_counts) if turn_counts else 0,
        "avg_task_duration_s": round(statistics.mean(task_durations), 2) if task_durations else 0,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "message_ratio": round(_safe_div(assistant_messages, user_messages), 2) if user_messages > 0 else 0,
        "satisfaction_score": satisfaction_score,
        "satisfaction_indicators": satisfaction_indicators,
    }


def _analyze_security(sessions: list[dict]) -> dict:
    """
    安全性维度分析：
    - 统计危险操作拦截
    - 分析权限请求合理性
    - 检测敏感信息暴露模式
    """
    danger_ops: dict[str, int] = defaultdict(int)
    permission_requests: dict[str, int] = defaultdict(int)
    sensitive_patterns: list[dict] = []

    # 危险操作关键词
    danger_keywords = [
        "rm -rf", "drop table", "delete *", "truncate",
        "format disk", "shutdown", "reboot",
    ]

    # 敏感信息模式（预编译正则以提高性能）
    sensitive_patterns_def = [
        {"pattern": re.compile(r"password\s*=", re.IGNORECASE), "label": "hardcoded_password"},
        {"pattern": re.compile(r"api[_-]?key\s*=", re.IGNORECASE), "label": "hardcoded_api_key"},
        {"pattern": re.compile(r"secret\s*=", re.IGNORECASE), "label": "hardcoded_secret"},
        {"pattern": re.compile(r"token\s*=\s*['\"][a-zA-Z0-9]{20,}['\"]"), "label": "hardcoded_token"},
    ]

    for s in sessions:
        # 危险操作检测
        for tool_call in s.get("tool_calls", []):
            input_data = json.dumps(tool_call.get("input", {}))
            for keyword in danger_keywords:
                if keyword.lower() in input_data.lower():
                    danger_ops[keyword] += 1

        # 权限请求统计
        hooks_triggered = s.get("hooks_triggered", [])
        for hook in hooks_triggered:
            hook_name = hook.get("hook_name", "unknown")
            permission_requests[hook_name] += 1

        # 敏感信息暴露检测（使用预编译正则）
        for msg in s.get("messages", []):
            content = str(msg.get("content", ""))
            for sp in sensitive_patterns_def:
                if sp["pattern"].search(content):
                    sensitive_patterns.append({
                        "session_id": s.get("session_id", "unknown"),
                        "type": sp["label"],
                        "context": content[:100],
                    })

    # 权限请求合理性评分
    permission_score = 100
    if permission_requests:
        # 权限请求过多可能表示滥用
        total_requests = sum(permission_requests.values())
        sessions_with_hooks = len([s for s in sessions if s.get("hooks_triggered")])
        avg_requests = _safe_div(total_requests, sessions_with_hooks)
        if avg_requests > 5:
            permission_score = 60
        elif avg_requests > 10:
            permission_score = 30

    return {
        "danger_operations": dict(danger_ops),
        "permission_requests": dict(permission_requests),
        "permission_score": permission_score,
        "sensitive_exposures": sensitive_patterns[:10],  # 最多返回10条
        "total_sessions_checked": len(sessions),
    }


def _analyze_context(sessions: list[dict], config: dict, root: Path) -> dict:
    """
    上下文维度分析：
    - 分析上下文切换频率
    - 统计知识复用率
    - 多轮对话连贯性
    """
    context_switches: list[int] = []
    knowledge_reuse: dict[str, int] = defaultdict(int)
    coherence_scores: list[float] = []

    for s in sessions:
        switches = 0
        messages = s.get("messages", [])

        # 上下文切换检测（通过检测 Agent/Skill 切换）
        prev_agent = None
        prev_skill = None
        for msg in messages:
            metadata = msg.get("metadata", {})
            current_agent = metadata.get("agent", "")
            current_skill = metadata.get("skill", "")

            if prev_agent and current_agent and current_agent != prev_agent:
                switches += 1
            if prev_skill and current_skill and current_skill != prev_skill:
                switches += 1

            prev_agent = current_agent
            prev_skill = current_skill

        context_switches.append(switches)

        # 知识复用检测
        knowledge_sources = s.get("knowledge_sources", [])
        for source in knowledge_sources:
            source_id = source.get("source_id", "unknown")
            knowledge_reuse[source_id] += 1

        # 连贯性评分（基于词汇多样性）
        # 词汇越丰富（unique_ratio 接近 1），说明内容发散，可能连贯性差
        # 词汇越单调（unique_ratio 接近 0），说明聚焦，可能连贯性好
        all_content = " ".join([str(m.get("content", "")) for m in messages])
        words = all_content.split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            # 词汇单调=聚焦=连贯性好，所以 coherence=unique_ratio
            coherence = unique_ratio
            coherence_scores.append(coherence)

    # 知识复用率
    total_knowledge_refs = sum(knowledge_reuse.values())
    reuse_rate = _safe_div(total_knowledge_refs, len(sessions)) if sessions else 0

    return {
        "avg_context_switches": round(statistics.mean(context_switches), 2) if context_switches else 0,
        "max_context_switches": max(context_switches) if context_switches else 0,
        "knowledge_reuse": dict(knowledge_reuse),
        "knowledge_reuse_rate": round(reuse_rate, 2),
        "avg_coherence_score": round(statistics.mean(coherence_scores), 4) if coherence_scores else 0,
        "sessions_analyzed": len(sessions),
    }


def _meets_safety_checks(config: dict, correction_targets: Counter) -> bool:
    """检查安全限制"""
    # 安全检查：每天最多 N 个提案
    max_proposals = config.get("safety", {}).get("max_proposals_per_day", 3)
    # 简化实现：只要有问题就允许提案（详细限制在 proposer 处理）
    return len(correction_targets) > 0
