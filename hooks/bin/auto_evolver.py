#!/usr/bin/env python3
"""
SessionStart Hook — Evolution Dispatch Injector + Hard Fallback

读取 pending_evolution.json 中的待处理触发器。

主路径（Agent evolver）：
  构建精确的 Agent 派发指令注入到会话上下文，由 LLM 驱动的 Agent evolver
  分析并重写目标文件。这是智能进化路径。

硬回退（Python engine）：
  如果同一 trigger 连续 2 次被派发但未被 Agent evolver 处理（即
  consecutive_missed >= 2），回退到 Python EvolutionEngine.force_evolve()。
  确保系统在任何情况下都有最低限度的进化产出。

安全机制：
  - 熔断器检查（连续 2 次退化 → 阻止）
  - 限流器检查（24h/48h 冷却，每会话最多 3 次）
  - 目标文件存在性检查
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def main():
    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    claude_dir = Path(project_root) / ".claude"
    sys.path.insert(0, str(claude_dir))

    pending_path = claude_dir / "data" / "pending_evolution.json"

    dispatch_entries = []
    fallback_results = []
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # ── 读取待处理触发器 ──
    if pending_path.exists():
        try:
            pending = json.loads(pending_path.read_text())
            triggers = pending.get("pending_triggers", [])
        except (json.JSONDecodeError, OSError):
            pending = {}
            triggers = []
    else:
        pending = {}
        triggers = []

    # ── 更新 consecutive_missed 计数 ──
    triggers_updated = False
    for t in triggers:
        last_disp = t.get("last_dispatched_session", "")
        if last_disp and last_disp != session_id:
            # 上次派发了但本次仍在 → LLM 未处理
            t["consecutive_missed"] = t.get("consecutive_missed", 0) + 1
            triggers_updated = True
        elif not last_disp:
            t["consecutive_missed"] = 0

    if triggers_updated:
        _save_pending(pending_path, pending)
        print(
            "[auto_evolver] 检测到 {} 个未处理的派发，已更新 consecutive_missed".format(
                sum(1 for t in triggers if t.get("consecutive_missed", 0) > 0)
            ),
            file=sys.stderr,
        )

    if not triggers:
        # ── 输出空的 hookSpecificOutput ──
        output = {"hookSpecificOutput": {"hookEventName": "SessionStart"}}
        print(json.dumps(output, ensure_ascii=False))
        print("[auto_evolver] 无待派发触发器", file=sys.stderr)
        return

    triggers.sort(key=lambda t: -t.get("priority", 0))

    # ── 安全门禁 ──
    sys.path.insert(0, str(claude_dir / "lib"))
    try:
        from evolution_safety import EvolutionCircuitBreaker, EvolutionRateLimiter
    except ImportError:
        EvolutionCircuitBreaker = None
        EvolutionRateLimiter = None

    metrics_path = str(claude_dir / "data" / "evolution_metrics.json")
    history_path = str(claude_dir / "data" / "evolution_history.jsonl")
    breaker = EvolutionCircuitBreaker(metrics_path) if EvolutionCircuitBreaker else None
    limiter = EvolutionRateLimiter(history_path) if EvolutionRateLimiter else None

    evolver_map = {
        "skill": "skill-evolver",
        "agent": "agent-evolver",
        "rule": "rule-evolver",
        "memory": "memory-evolver",
    }

    # ── 初始化 Python 回退引擎 ──
    python_engine = None

    def _get_python_engine():
        nonlocal python_engine
        if python_engine is None:
            try:
                from evolution.config import EvolutionConfig
                from evolution.engine import EvolutionEngine
                config = EvolutionConfig()
                config.project_root = Path(project_root)
                python_engine = EvolutionEngine(config)
            except ImportError:
                python_engine = False  # 标记为不可用
        return python_engine if python_engine is not False else None

    for trigger in triggers[:3]:
        dim = trigger["dimension"]
        target = trigger["target"]
        priority = trigger.get("priority", 0)
        reason = trigger.get("reason", "")
        consecutive_missed = trigger.get("consecutive_missed", 0)

        # 安全门禁
        if breaker and breaker.is_open(dim, target):
            print("[auto_evolver] 熔断 {}/{}，跳过".format(dim, target), file=sys.stderr)
            continue

        if limiter:
            can_evolve, limit_reason = limiter.can_evolve(dim, target, session_id)
            if not can_evolve:
                print("[auto_evolver] 限流 {}/{}: {}".format(dim, target, limit_reason), file=sys.stderr)
                continue

        evolver = evolver_map.get(dim)
        if not evolver:
            print("[auto_evolver] 未知维度 {}，跳过".format(dim), file=sys.stderr)
            continue

        # 目标文件存在性检查（memory 维度创建新文件，跳过检查）
        if dim != "memory":
            target_path = _resolve_target_path(claude_dir, dim, target)
            if target_path and not target_path.exists():
                print("[auto_evolver] 目标不存在 {}，跳过".format(target_path), file=sys.stderr)
                continue

        # ── 硬回退判断 ──
        # 超过 5 次连续未处理 → 放弃（避免无限循环）
        if consecutive_missed >= 5:
            print(
                "[auto_evolver] ABANDON {}/{} 连续 {} 次未处理，放弃".format(
                    dim, target, consecutive_missed
                ),
                file=sys.stderr,
            )
            _remove_trigger(pending_path, dim, target)
            continue

        if consecutive_missed >= 2:
            print(
                "[auto_evolver] {} {}/{} 连续 {} 次未处理，回退到 Python 引擎".format(
                    "HARD FALLBACK" if consecutive_missed >= 3 else "fallback",
                    dim, target, consecutive_missed
                ),
                file=sys.stderr,
            )
            engine = _get_python_engine()
            if engine:
                try:
                    result = engine.force_evolve(dim, target)
                    if result and result.success:
                        _write_history(claude_dir, dim, target, result, session_id)
                        fallback_results.append({
                            "dimension": dim,
                            "target": target,
                            "success": True,
                            "changes": result.changes_made,
                            "score_before": result.score_before,
                            "score_after": result.score_after,
                            "path": "python_fallback",
                        })
                        # 回退成功后从 pending_triggers 移除
                        _remove_trigger(pending_path, dim, target)
                        if breaker:
                            breaker.record_result(dim, target,
                                result.score_after > result.score_before)
                    else:
                        fallback_results.append({
                            "dimension": dim, "target": target,
                            "success": False,
                            "path": "python_fallback",
                            "error": "force_evolve returned None or failed" if result else "force_evolve returned None",
                        })
                except Exception as exc:
                    print("[auto_evolver] Python 回退失败 {}/{}: {}".format(
                        dim, target, exc), file=sys.stderr)
                    fallback_results.append({
                        "dimension": dim, "target": target,
                        "success": False,
                        "path": "python_fallback",
                        "error": str(exc),
                    })
            else:
                print("[auto_evolver] Python 引擎不可用，仍然派发 Agent", file=sys.stderr)
                # 回退引擎不可用，标记为紧急派发
                entry = _build_dispatch_entry(dim, target, priority, reason, evolver, consecutive_missed, urgent=True)
                dispatch_entries.append(entry)
            continue

        # ── 主路径：Agent evolver 派发 ──
        entry = _build_dispatch_entry(dim, target, priority, reason, evolver, consecutive_missed, urgent=False)
        dispatch_entries.append(entry)

    # ── 标记已派发的 trigger ──
    if dispatch_entries:
        for d in dispatch_entries:
            _mark_dispatched(pending_path, d["dimension"], d["target"], session_id)

    # ── 输出 hookSpecificOutput ──
    output = {"hookSpecificOutput": {"hookEventName": "SessionStart"}}

    if dispatch_entries:
        output["hookSpecificOutput"]["evolutionDispatch"] = dispatch_entries
        output["hookSpecificOutput"]["evolutionMandate"] = _build_mandate(dispatch_entries, fallback_results)

    if fallback_results:
        output["hookSpecificOutput"]["evolutionFallback"] = fallback_results

    print(json.dumps(output, ensure_ascii=False))

    # stderr 日志
    if dispatch_entries:
        dims = sorted(set(d["dimension"] for d in dispatch_entries))
        prio_parts = []
        for d in dispatch_entries:
            prio_parts.append("{}/{}={:.2f}".format(d["dimension"], d["target"], d["priority"]))
        print(
            "[auto_evolver] Agent 派发: {} 项 ({}) | 优先级: {}".format(
                len(dispatch_entries), ", ".join(dims), prio_parts
            ),
            file=sys.stderr,
        )
    if fallback_results:
        ok = sum(1 for r in fallback_results if r["success"])
        print(
            "[auto_evolver] Python 回退完成: {}/{} 成功".format(ok, len(fallback_results)),
            file=sys.stderr,
        )
    if not dispatch_entries and not fallback_results:
        print("[auto_evolver] 无待派发触发器（全部被安全门禁阻止）", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _resolve_target_path(claude_dir: Path, dim: str, target: str) -> Optional[Path]:
    """将 dimension/target 解析为目标文件路径。"""
    mapping = {
        "agent": claude_dir / "agents" / "{}.md".format(target),
        "rule": claude_dir / "rules" / "{}.md".format(target),
        "skill": claude_dir / "skills" / target / "SKILL.md",
        "memory": claude_dir / "memory" / "{}.md".format(target),
    }
    return mapping.get(dim)


def _build_dispatch_entry(dim: str, target: str, priority: float, reason: str,
                          evolver: str, consecutive_missed: int, urgent: bool = False) -> dict:
    """构建单个派发条目。"""
    prefix = "URGENT " if urgent else ""
    prompt = _build_evolver_prompt(dim, target, reason, priority)
    return {
        "dimension": dim,
        "target": target,
        "priority": priority,
        "reason": reason,
        "evolver": evolver,
        "consecutive_missed": consecutive_missed,
        "urgent": urgent,
        "agent_call": {
            "subagent_type": evolver,
            "description": "{}进化 {}/{}".format(prefix, dim, target),
            "prompt": prompt,
            "run_in_background": True,
        },
    }


# 统一的进化历史记录 schema（所有 evolver 必须遵循）
_HISTORY_SCHEMA = (
    'timestamp: ISO8601, session_id: str, dimension: str, target: str, '
    'source: agent, success: bool, score_before: null, score_after: null, '
    'changes: [具体改动], summary: 人类可读摘要'
)


def _build_evolver_prompt(dim: str, target: str, reason: str, priority: float) -> str:
    """为 Agent evolver 构建详细的分析+修改+清理提示词。"""
    history_instruction = (
        '\n5. 追加进化记录到 .claude/data/evolution_history.jsonl（JSONL 一行）\n'
        '   统一 schema: {schema}\n'
        '   示例: {{{{ "timestamp": "2026-04-28T12:00:00Z", "session_id": "..."'
        '"dimension": "{dim}", "target": "{target}", '
        '"source": "agent", "success": true, '
        '"score_before": null, "score_after": null, '
        '"changes": ["改动1"], "summary": "摘要" }}}}\n'
    ).format(schema=_HISTORY_SCHEMA, dim=dim, target=target)

    clear_trigger_code = (
        "\n\n"
        "清理步骤（必须执行）:\n"
        '7. 从 .claude/data/pending_evolution.json 中移除本 trigger:\n'
        "   - 读取 pending_evolution.json\n"
        '   - 从 pending_triggers 数组中移除 dimension="{dim}" 且 target="{target}" 的条目\n'
        "   - 保留 feedback_signals 和其他 trigger 不变\n"
        "   - 写回文件\n"
    ).format(dim=dim, target=target)

    base_prompts = {
        "agent": (
            "对 Agent '{target}' 执行进化优化。\n"
            "触发原因: {reason} (优先级: {priority:.2f})\n\n"
            "工作步骤:\n"
            "1. 读取 .claude/agents/{target}.md 当前内容\n"
            "2. 读取 .claude/data/agent_performance.jsonl 分析该 agent 的执行数据\n"
            "3. 识别: 常见失败模式、被拒绝的工具调用、效率低下的模式、任务完成率\n"
            "4. 重写 agent 定义文件以修复发现的问题，优化提示词结构\n"
            + history_instruction +
            "\n6. 报告: 发现了什么问题、改了什么、预期效果"
        ),
        "rule": (
            "对规则 '{target}' 执行进化优化。\n"
            "触发原因: {reason} (优先级: {priority:.2f})\n\n"
            "工作步骤:\n"
            "1. 读取 .claude/rules/{target}.md 当前内容\n"
            "2. 读取 .claude/logs/sessions.jsonl 分析规则违规数据\n"
            "3. 识别: 规则不清晰/太严格/过时/用户不知道等问题\n"
            "4. 按决策树执行修改: 不清晰->补充示例, 太严格->增加例外条件, 过时->更新技术栈引用\n"
            + history_instruction +
            "\n6. 报告: 发现了什么问题、改了什么、预期效果"
        ),
        "skill": (
            "对技能 '{target}' 执行进化优化。\n"
            "触发原因: {reason} (优先级: {priority:.2f})\n\n"
            "工作步骤:\n"
            "1. 读取 .claude/skills/{target}/SKILL.md 当前内容\n"
            "2. 读取 .claude/data/skill_usage.jsonl 分析使用数据\n"
            "3. 识别: description 精准度、触发词覆盖、步骤有效性、工具权限配置\n"
            "4. 按风险等级修改: 低风险(description)->中风险(触发词)->高风险(body步骤)->工具权限\n"
            + history_instruction +
            "\n6. 报告: 发现了什么问题、改了什么、预期效果"
        ),
        "memory": (
            "对记忆信号 '{target}' 执行进化优化。\n"
            "触发原因: {reason} (优先级: {priority:.2f})\n\n"
            "工作步骤:\n"
            "1. 读取 .claude/data/pending_evolution.json 中的 feedback_signals\n"
            "2. 分类信号类型: user/feedback/project/reference，过滤噪音信号\n"
            "3. 为每个有意义的信号生成或更新 memory 文件 (写入 .claude/memory/)\n"
            "4. 更新 .claude/memory/MEMORY.md 索引（只添加新条目，不删除已有条目）\n"
            + history_instruction +
            "\n6. 报告: 创建/更新了哪些记忆、为什么、预期用途"
        ),
    }
    template = base_prompts.get(
        dim,
        "对 {dim}/{target} 执行进化优化。原因: {reason}"
    )
    prompt = template.format(dim=dim, target=target, reason=reason, priority=priority)
    prompt += clear_trigger_code
    return prompt


def _build_mandate(dispatch_entries: list, fallback_results: list = None) -> str:
    """构建强制派发指令文本，注入到 system prompt。"""
    lines = []
    lines.append("=" * 60)
    lines.append("MANDATORY EVOLUTION DISPATCH")
    lines.append("=" * 60)
    lines.append("")

    has_urgent = any(d.get("urgent") for d in dispatch_entries)

    if has_urgent:
        lines.append("WARNING: 以下 trigger 已连续多次未被处理，本次为紧急派发。")
        lines.append("如果本次仍不处理，下次会话将回退到 Python 引擎（无 LLM 智能）。")
        lines.append("")

    if fallback_results:
        lines.append("Python 回退已完成: {} 项".format(len(fallback_results)))
        for r in fallback_results:
            status = "OK" if r["success"] else "FAIL"
            lines.append("  - {}/{}: {}".format(r["dimension"], r["target"], status))
        lines.append("")

    lines.append("以下维度需要进化优化。你必须在处理完用户请求后，")
    lines.append("使用 Agent 工具派发以下进化 Agent（run_in_background=True）：")
    lines.append("")

    for i, d in enumerate(dispatch_entries, 1):
        ac = d["agent_call"]
        miss_tag = " MISSED x{}".format(d.get("consecutive_missed", 0)) if d.get("consecutive_missed", 0) > 0 else ""
        urgent_tag = " URGENT" if d.get("urgent") else ""
        lines.append("  [{}] Agent(subagent_type=\"{}\",{}{})".format(
            i, ac["subagent_type"], miss_tag, urgent_tag
        ))
        lines.append("      description=\"{}\",".format(ac["description"]))
        lines.append("      run_in_background=True,")
        prompt_preview = ac["prompt"][:120].replace("\n", " ")
        lines.append("      prompt=\"{}...\")".format(prompt_preview))
        lines.append("")

    lines.append("派发规则:")
    lines.append("  - 所有 evolver 互不依赖，可以并行派发（同一 response 中同时调用多个 Agent）")
    lines.append("  - 每个 evolver 完成后会自动清除自己在 pending_triggers 中的条目")
    lines.append("  - 保留 feedback_signals 不清除")
    lines.append("  - 输出进化结果摘要给用户")
    lines.append("")
    lines.append("这是自动化系统指令，不可跳过。每次会话只派发一次。")
    lines.append("=" * 60)

    return "\n".join(lines)


def _save_pending(path: Path, data: dict):
    """保存 pending_evolution.json。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _mark_dispatched(pending_path: Path, dim: str, target: str, session_id: str):
    """标记 trigger 已被派发（但尚未被 Agent evolver 处理）。"""
    if not pending_path.exists():
        return
    try:
        data = json.loads(pending_path.read_text())
        for t in data.get("pending_triggers", []):
            if t.get("dimension") == dim and t.get("target") == target:
                t["last_dispatched_session"] = session_id
        _save_pending(pending_path, data)
    except (json.JSONDecodeError, OSError) as exc:
        print("[auto_evolver] 无法标记派发: {}".format(exc), file=sys.stderr)


def _remove_trigger(pending_path: Path, dim: str, target: str):
    """从 pending_triggers 中移除已被处理的 trigger。"""
    if not pending_path.exists():
        return
    try:
        data = json.loads(pending_path.read_text())
        data["pending_triggers"] = [
            t for t in data.get("pending_triggers", [])
            if not (t.get("dimension") == dim and t.get("target") == target)
        ]
        _save_pending(pending_path, data)
    except (json.JSONDecodeError, OSError) as exc:
        print("[auto_evolver] 无法移除 trigger: {}".format(exc), file=sys.stderr)


def _write_history(claude_dir: Path, dim: str, target: str, result, session_id: str):
    """追加进化记录到 evolution_history.jsonl（统一 schema）。"""
    history_file = claude_dir / "data" / "evolution_history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": session_id,
        "dimension": dim,
        "target": target,
        "source": "python",
        "success": result.success if hasattr(result, 'success') else False,
        "score_before": getattr(result, 'score_before', None),
        "score_after": getattr(result, 'score_after', None),
        "changes": getattr(result, 'changes_made', []) or [],
        "summary": getattr(result, 'summary', ''),
    }
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
