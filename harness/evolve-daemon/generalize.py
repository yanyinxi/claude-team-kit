#!/usr/bin/env python3
"""
generalize.py — LLM 泛化判断逻辑

核心职责：
1. 判断新错误应该 reuse / merge / new
2. 新根因的深度分析（5类归因 + 抽象层级）
3. merge 的风险评估（confidence < 0.6 → abort）
4. 本地规则降级（无 API Key 时）

三步 LLM 分析：
  第一步：批量关联分析（reuse / merge / new）
  第二步：新根因深度分析（action=new 时）
  第三步：merge 风险评估（action=merge 时）
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from kb_shared import (
    load_active_kb,
    find_kb_by_id,
    check_merge_cooldown,
    record_merge_abort,
    generate_kb_id,
    create_new_knowledge,
    save_kb_entry,
    update_kb_all,
    now_iso,
    notify_llm_failure,
    get_haiku_model,
    get_sonnet_model,
    create_llm_client,
)


# ── LLM 调用 ───────────────────────────────────────────────
def _has_llm_access() -> bool:
    """检查是否有 LLM 调用能力（代理或真实 API Key）"""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_BASE_URL")
    )


def call_haiku(system: str, user: str, config: dict | None = None) -> dict | None:
    """用 Haiku 做简单判断（reuse/new）"""
    try:
        client = create_llm_client()
        model = (config or {}).get("extract_model") or get_haiku_model()
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.1,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # 提取文本内容（跳过 thinking block，处理 ```json 包裹）
        text = ""
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                text = block.text.strip()
                break
        if not text:
            raise ValueError(f"No text block in response: {[type(b).__name__ for b in response.content]}")
        # 去掉 ```json ... ``` 包裹
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        notify_llm_failure(str(e), "Haiku 调用失败", "")
        return None


def call_sonnet(system: str, user: str, config: dict | None = None) -> dict | None:
    """用 Sonnet 做深度分析（新根因、merge 风险）"""
    try:
        client = create_llm_client()
        model = (config or {}).get("analyze_model") or get_sonnet_model()
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.3,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # 提取文本内容（跳过 thinking block，处理 ```json 包裹）
        text = ""
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                text = block.text.strip()
                break
        if not text:
            raise ValueError(f"No text block in response: {[type(b).__name__ for b in response.content]}")
        # 去掉 ```json ... ``` 包裹（Sonnet 深度分析返回的 JSON 常用此格式）
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        notify_llm_failure(str(e), "Sonnet 调用失败", "")
        return None


def call_llm_fallback(user: str, errors: list[dict]) -> list[dict]:
    """
    无 API Key 时的本地规则降级。
    用硬编码的启发式规则判断 reuse / new。
    """
    print("  [generalize] API Key 未配置，使用本地规则降级")

    results = []
    for i, error in enumerate(errors):
        error_text = error.get("error", "").lower()
        matched = None

        # 危险命令误判
        for kw in ["rm -rf", "git clean", "chmod -r", "sudo rm"]:
            if kw in error_text:
                matched = "danger_command_false_positive"
                break

        # 超时
        if "timeout" in error_text or "超时" in error_text:
            matched = "timeout_error"

        # 权限
        if "permission" in error_text or "denied" in error_text:
            matched = "permission_error"

        # 路径不存在
        if "not found" in error_text or "没有找到" in error_text:
            matched = "path_not_found"

        if matched:
            results.append({
                "error_index": i,
                "action": "reuse",
                "matched_id": None,  # 需要查 KB
                "confidence": 0.5,
                "reasoning_chain": [f"本地规则匹配: {matched}"],
                "risk_assessment": {"confidence": 0.5, "if_wrong": "可能导致误分类"},
                "error_type": matched,
                "root_cause": f"本地规则检测: {matched}",
                "solution": "需人工确认",
            })
        else:
            results.append({
                "error_index": i,
                "action": "new",
                "confidence": 0.3,
                "reasoning_chain": ["无匹配规则，标记为新知识"],
                "risk_assessment": {"confidence": 0.3, "if_wrong": "新增错误知识"},
                "error_type": "unknown",
                "root_cause": "无法归类",
                "solution": "需人工 review",
            })

    return results


# ── Prompt 构建 ────────────────────────────────────────────
def build_step1_prompt(errors: list[dict], kb: list[dict]) -> tuple[str, str]:
    """构建第一步 prompt：批量关联分析"""

    # 格式化知识库
    kb_text = ""
    if kb:
        for entry in kb[:20]:  # 最多显示20条
            kb_text += f"""- [{entry['id']}] {entry['error_type']}
    根因: {entry.get('root_cause', 'N/A')}
    具体例子: {', '.join(entry.get('specific_examples', [])[:3])}
    置信度: {entry.get('confidence', 0):.2f}
"""
    else:
        kb_text = "(知识库为空)"

    # 格式化错误
    errors_text = ""
    for i, err in enumerate(errors):
        errors_text += f"""- [{i}] 错误: "{err.get('error', '')[:80]}"
  工具: {err.get('tool', 'unknown')}
  上下文: {err.get('context', '')[:100]}
"""

    system = """你是一个 AI 工程诊断专家。

你的任务：
1. 先判断这批错误之间是否有关联（可能在说同一件事）
2. 再判断这些错误和知识库中哪些已有知识相关
3. 最后决定每个错误应该 reuse / merge / new

判断标准：
- reuse: 新错误的根因和某个已有知识的根因完全相同
- merge: 新错误的根因和多个已有知识的根因相关，可以合并成更通用的模式
- new: 新错误的根因是全新的，和任何已有知识都不相关

注意：
- 宁可保守，也不要错误归类
- 如果不确定，标记为 new
- confidence 表示你对这个判断的把握程度（0.0-1.0）

输出格式：严格 JSON"""
    user = f"""知识库（已有知识）：
{kb_text}

待分析错误（{len(errors)} 个）：
{errors_text}

请输出 JSON 数组：
[
  {{
    "error_index": 0,
    "action": "reuse" | "merge" | "new",
    "confidence": 0.0-1.0,
    "reasoning_chain": ["观察: ...", "推断: ...", "结论: ..."],
    "risk_assessment": {{
      "if_wrong": "会导致什么问题",
      "confidence": 0.0-1.0,
      "requires_strict_test": true/false
    }},
    "matched_id": "kb-xxx" | null,
    "matched_pattern": "匹配到的模式描述",
    "merge_ids": ["kb-aaa", "kb-bbb"] | null,
    "new_root_cause": null,
    "new_solution": null
  }}
]"""

    return system, user


def build_step2_prompt(error: dict, kb_entry: dict | None = None) -> tuple[str, str]:
    """构建第二步 prompt：新根因深度分析"""

    kb_context = ""
    if kb_entry:
        kb_context = f"""参考知识库中相似知识：
- [{kb_entry['id']}] {kb_entry['error_type']}
  根因: {kb_entry.get('root_cause', '')}
  抽象层级: {kb_entry.get('abstraction_level', 3)}"""

    system = """你是一个 AI 工程诊断专家。

对于标记为 "new" 的错误，请深度分析：

1. 根因归类（选择最匹配的）：
   - context_missing: 缺少执行前上下文检查
   - skill_gap: Skill 覆盖不足，缺少该场景
   - rule_incomplete: 规则不够精确或缺少边界情况
   - agent_misjudge: Agent 判断偏差
   - tool_behavior: 工具行为不符合预期
   - unknown: 无法归类

2. 根因深度（1-5级）：
   - Level 1: "具体工具 的 具体问题"
   - Level 3: "工具类型 缺少 检查类型"
   - Level 5: "系统 缺少 机制描述"

3. 建议的解决方案：
   - target_file: 应该修改哪个文件？（Agent / Skill / Rule）
   - change_type: append | replace | new_section
   - before/after: 具体改动内容

输出格式：严格 JSON"""
    user = f"""待分析错误：
错误: "{error.get('error', '')}"
工具: {error.get('tool', 'unknown')}
上下文: {error.get('context', '')}"

{kb_context}

请输出 JSON：
{{
  "root_cause_category": "context_missing | skill_gap | rule_incomplete | agent_misjudge | tool_behavior | unknown",
  "root_cause": "一句话描述根因",
  "abstraction_level": 1-5,
  "abstraction_rationale": "为什么是这个层级",
  "generalizable_to": ["可能推广到的场景A", "场景B"] | null,
  "solution": {{
    "target_file": "harness/agents/xxx.md | skills/xxx/SKILL.md | rules/xxx.md",
    "change_type": "append | replace | new_section",
    "before": "当前内容",
    "after": "改动后内容"
  }},
  "confidence": 0.0-1.0,
  "reasoning_chain": ["...", "..."]
}}"""

    return system, user


def build_step3_prompt(
    kb_entries: list[dict],
    merged_pattern: str,
) -> tuple[str, str]:
    """构建第三步 prompt：merge 风险评估"""

    kb_text = "\n".join([
        f"- [{e['id']}] {e['error_type']}\n  根因: {e.get('root_cause', '')}\n  例子: {', '.join(e.get('specific_examples', [])[:2])}"
        for e in kb_entries
    ])

    system = """你是一个模式安全评估专家。

你将评估多个知识是否应该合并。合并是危险的：合并错了会导致多个场景同时出错。

请诚实评估：
1. 这些知识真的根因相同吗？
2. 合并后失去了什么细节？
3. 合并后在哪些场景可能失效？

如果不确定，请返回 abort。宁可少合并，不要错误合并。

输出格式：严格 JSON"""
    user = f"""建议合并的知识（{len(kb_entries)} 个）：
{kb_text}

建议的合并模式：{merged_pattern}

请输出 JSON：
{{
  "merge_is_safe": true/false,
  "confidence_in_merge": 0.0-1.0,
  "recommendation": "proceed | abort",
  "lost_details": ["合并后会失去的具体细节"],
  "failure_scenarios": ["合并后可能失效的场景"],
  "reasoning_chain": ["...", "..."]
}}

注意：如果 confidence_in_merge < 0.6，强制返回 abort。"""

    return system, user


# ── 核心泛化逻辑 ────────────────────────────────────────────
def process_errors(
    errors: list[dict],
    root: Path | None = None,
    config: dict | None = None,
) -> list[dict]:
    """
    处理一批错误的完整流程。

    返回：每个错误的处理结果
    [
      {
        "error_index": 0,
        "action": "reuse" | "merge" | "new",
        "matched_id": "kb-xxx" | null,
        "confidence": 0.0-1.0,
        "reasoning_chain": [...],
        "merged_kb": dict | null,
        "new_kb": dict | null,
        "abort_reason": null,
        ...
      }
    ]
    """
    if not errors:
        return []

    kb = load_active_kb(root)
    has_llm = _has_llm_access()

    # ── 第一步：批量关联分析 ──────────────────────────────
    if has_llm:
        system, user = build_step1_prompt(errors, kb)
        step1_results = call_haiku(system, user, config)
    else:
        step1_results = call_llm_fallback(user="", errors=errors)

    if not step1_results or not isinstance(step1_results, list):
        print("  [generalize] LLM 返回无效，使用本地规则")
        step1_results = call_llm_fallback(user="", errors=errors)

    # ── 第二步：新根因深度分析 ─────────────────────────────
    for i, result in enumerate(step1_results):
        if result.get("action") == "new" and has_llm:
            error = errors[i]
            matched_kb = None
            if result.get("matched_id"):
                matched_kb = find_kb_by_id(result["matched_id"], root)

            system, user = build_step2_prompt(error, matched_kb)
            depth = call_sonnet(system, user, config)

            if depth:
                result["root_cause_category"] = depth.get("root_cause_category", "unknown")
                result["abstraction_level"] = depth.get("abstraction_level", 3)
                result["new_root_cause"] = depth.get("root_cause", "")
                result["solution"] = depth.get("solution", {})
                result["confidence"] = depth.get("confidence", result.get("confidence", 0.5))
                result["reasoning_chain"] = depth.get("reasoning_chain", result.get("reasoning_chain", []))

    # ── 第三步：merge 风险评估 ───────────────────────────
    merge_results = [r for r in step1_results if r.get("action") == "merge"]
    if merge_results:
        # 按 merge_ids 分组
        merge_groups = {}
        for mr in merge_results:
            ids = tuple(sorted(mr.get("merge_ids", [])))
            if ids:
                merge_groups.setdefault(ids, []).append(mr)

        for ids, group in merge_groups.items():
            # 检查冷却期
            if check_merge_cooldown(list(ids), hours=6):
                for mr in group:
                    mr["action"] = "new"
                    mr["abort_reason"] = "merge abort cooldown (6h)"
                continue

            # 获取被合并的知识
            kb_entries = [find_kb_by_id(kbid, root) for kbid in ids]
            kb_entries = [e for e in kb_entries if e]

            if not kb_entries:
                for mr in group:
                    mr["action"] = "new"
                    mr["abort_reason"] = "target kb not found"
                continue

            # 获取 LLM 建议的合并模式
            merged_pattern = group[0].get("matched_pattern", "merged_pattern")

            # 调用 Sonnet 评估风险
            if has_llm:
                system, user = build_step3_prompt(kb_entries, merged_pattern)
                risk = call_sonnet(system, user, config)

                if risk:
                    conf = risk.get("confidence_in_merge", 0)
                    if conf < 0.6 or risk.get("recommendation") == "abort":
                        # abort：降级为 new，记录冷却期
                        for mr in group:
                            mr["action"] = "new"
                            mr["abort_reason"] = f"merge confidence {conf:.2f} < 0.6"
                        record_merge_abort(list(ids), risk.get("lost_details", ["low confidence"]))
                        print(f"  [generalize] merge abort: confidence {conf:.2f} < 0.6")
                        continue

                    # proceed：执行 merge
                    merged_kb = _do_merge(kb_entries, merged_pattern, risk, root)
                    for mr in group:
                        mr["merged_kb"] = merged_kb

    # ── 第四步：写入知识库 ────────────────────────────────
    for i, result in enumerate(step1_results):
        error = errors[i]
        action = result.get("action", "new")

        if action == "reuse":
            _do_reuse(result, error, root)

        elif action == "new":
            new_kb = _do_new(result, error, root)
            result["new_kb"] = new_kb

        # merge 已在第三步处理

    return step1_results


def _do_reuse(result: dict, error: dict, root: Path | None):
    """执行 reuse：更新已有知识的 specific_examples"""
    matched_id = result.get("matched_id")
    if not matched_id:
        return

    kb = load_active_kb(root)
    for entry in kb:
        if entry.get("id") == matched_id:
            # 新增具体例子
            error_text = error.get("error", "")
            if error_text not in entry.get("specific_examples", []):
                entry.setdefault("specific_examples", []).append(error_text)

            # 置信度微调：reuse 本身增加验证
            conf = result.get("confidence", 0.5)
            delta = conf * 0.05
            entry["confidence"] = min(1.0, entry.get("confidence", 0.5) + delta)
            entry["updated_at"] = now_iso()
            entry["last_reused_at"] = now_iso()

            update_kb_all(kb, root)
            print(f"  [reuse] {matched_id} ← {error.get('error', '')[:50]}")
            return


def _do_merge(kb_entries: list[dict], merged_pattern: str, risk: dict, root: Path | None) -> dict:
    """执行 merge：合并多个知识为一个更通用的"""
    # 1. 创建新知识
    all_examples = []
    for e in kb_entries:
        all_examples.extend(e.get("specific_examples", []))
    all_examples = list(dict.fromkeys(all_examples))  # 去重

    avg_conf = sum(e.get("confidence", 0.5) for e in kb_entries) / len(kb_entries)

    merged = {
        "id": generate_kb_id(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "unconfirmed",
        "error_type": merged_pattern,
        "error_type_detail": risk.get("lost_details", ["多个知识合并"])[0] if risk.get("lost_details") else "",
        "root_cause": kb_entries[0].get("root_cause", ""),
        "solution": kb_entries[0].get("solution", ""),
        "specific_examples": all_examples,
        "generalized_from": [e["id"] for e in kb_entries],
        "superseded_by": None,
        "confidence": avg_conf,  # 取被合并知识的平均值
        "validation_count": sum(e.get("validation_count", 0) for e in kb_entries),
        "success_count": sum(e.get("success_count", 0) for e in kb_entries),
        "failure_count": sum(e.get("failure_count", 0) for e in kb_entries),
        "source": "llm_merge",
        "dimension": kb_entries[0].get("dimension", "instinct"),
        "merge_risk": {
            "lost_details": risk.get("lost_details", []),
            "failure_scenarios": risk.get("failure_scenarios", []),
            "original_confidence": [e.get("confidence", 0) for e in kb_entries],
        },
    }

    # 2. 标记旧知识为 superseded
    all_kb = load_active_kb(root)
    for e in all_kb:
        if e["id"] in [kb["id"] for kb in kb_entries]:
            e["superseded_by"] = merged["id"]
            e["updated_at"] = now_iso()

    # 3. 追加新知识
    save_kb_entry(merged, root)
    update_kb_all(all_kb, root)

    print(f"  [merge] {merged['id']} = {merged['generalized_from']} (confidence: {avg_conf:.2f})")
    return merged


def _do_new(result: dict, error: dict, root: Path | None) -> dict | None:
    """创建新知识"""
    kb_entry = create_new_knowledge(
        error=error,
        analysis={
            "error_type": result.get("error_type", result.get("new_root_cause", "unknown")),
            "error_type_detail": "",
            "root_cause": result.get("new_root_cause", ""),
            "solution": result.get("solution", {}),
            "dimension": result.get("dimension", "instinct"),
        },
        reasoning_chain=result.get("reasoning_chain", []),
        root_cause_category=result.get("root_cause_category", "unknown"),
        abstraction_level=result.get("abstraction_level", 3),
        solution=result.get("solution"),
        root=root,
    )

    save_kb_entry(kb_entry, root)
    print(f"  [new] {kb_entry['id']} ← {error.get('error', '')[:50]}")
    return kb_entry


# ── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LLM 泛化判断")
    parser.add_argument("--errors", help="错误 JSON 文件路径")
    args = parser.parse_args()

    if args.errors:
        errors = json.loads(Path(args.errors).read_text())
    else:
        # 测试数据
        errors = [
            {"error": "rm -rf /tmp/build", "tool": "Bash", "context": "npm run clean"},
            {"error": "git clean -fd", "tool": "Bash", "context": "git reset --hard"},
        ]

    results = process_errors(errors)
    print(json.dumps(results, indent=2, ensure_ascii=False))
