#!/usr/bin/env python3
"""
integrated_evolution.py — 会话级进化引擎（重写版）

核心职责：
1. 会话结束时自动触发（Stop Hook）
2. 收集本会话错误
3. 调用 LLM 泛化分析（reuse / merge / new）
4. 写入统一 knowledge_base.jsonl
5. 冷启动迁移 + LLM 失败飞书通知

不修改任何文件，只积累知识。

数据流：
  Post Session Hook
    → 收集本会话 error.jsonl
    → LLM 批量泛化分析
    → 写入 knowledge_base.jsonl
    → 下次 daemon 调度时读取并应用
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 路径配置 ────────────────────────────────────────────────
PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
EVOLVE_DIR = PROJECT_ROOT / "harness" / "evolve-daemon"
DATA_DIR = PROJECT_ROOT / ".claude" / "data"
ERROR_LOG = DATA_DIR / "error.jsonl"

sys.path.insert(0, str(EVOLVE_DIR))

from kb_shared import (
    load_knowledge_base,
    migrate_from_instinct,
    decay_knowledge,
    print_kb_stats,
    check_merge_cooldown,
    notify_llm_failure,
    now_iso,
)
from generalize import process_errors


# ── 错误收集 ───────────────────────────────────────────────
def collect_session_errors(max_age_hours: int = 24) -> list[dict]:
    """
    收集本会话的错误。
    只收集最近 max_age_hours 小时内的新错误。
    """
    if not ERROR_LOG.exists():
        return []

    errors = []
    cutoff = None
    if max_age_hours > 0:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

    with open(ERROR_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # 过滤：本会话的错误（通过 session_id 或时间判断）
                ts = entry.get("timestamp", "")
                if cutoff and ts:
                    try:
                        ts_dt = datetime.fromisoformat(ts)
                        if ts_dt < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass

                errors.append({
                    "error": entry.get("error", ""),
                    "tool": entry.get("tool", entry.get("metadata", {}).get("tool", "unknown")),
                    "context": _extract_context(entry),
                    "session_id": entry.get("metadata", {}).get("session_id", "unknown"),
                })
            except json.JSONDecodeError:
                continue

    return errors


def _extract_context(entry: dict) -> str:
    """从错误条目中提取上下文"""
    meta = entry.get("metadata", {})
    ctx = meta.get("context", {})

    if isinstance(ctx, dict):
        parts = []
        if ctx.get("tool_input"):
            ti = ctx.get("tool_input", {})
            if isinstance(ti, dict):
                cmd = ti.get("command", ti.get("query", str(ti)))
                parts.append(f"命令: {cmd[:100]}")
        if ctx.get("mode"):
            parts.append(f"模式: {ctx.get('mode')}")
        if ctx.get("agents_used"):
            parts.append(f"Agent: {', '.join(ctx.get('agents_used', [])[:2])}")
        return " | ".join(parts) if parts else ""

    return str(ctx)[:200]


# ── 主流程 ─────────────────────────────────────────────────
def run_session_evolution(max_errors: int = 10, max_age_hours: int = 24):
    """
    会话级进化主流程。

    每次会话结束时调用。
    """
    print(f"\n{'='*60}")
    print(f"🔄 CHK 会话级进化 - 开始")
    print(f"  时间: {now_iso()}")
    print(f"{'='*60}")

    # ── 步骤0：冷启动迁移 ──────────────────────────────
    migrated = migrate_from_instinct(PROJECT_ROOT)
    if migrated > 0:
        print(f"  [迁移] 从 instinct-record 迁移了 {migrated} 条")

    # ── 步骤1：收集错误 ────────────────────────────────
    errors = collect_session_errors(max_age_hours=max_age_hours)
    print(f"\n  [收集] 本会话错误: {len(errors)} 条")

    if not errors:
        print("  [结论] 没有新错误需要分析")
        return

    # 限制处理数量
    if len(errors) > max_errors:
        print(f"  [限制] 错误数量 {len(errors)} > {max_errors}，取前 {max_errors} 条")
        errors = errors[:max_errors]

    # ── 步骤2：加载知识库状态 ─────────────────────────
    kb_before = load_knowledge_base(PROJECT_ROOT)
    kb_active = [e for e in kb_before if not e.get("superseded_by")]
    print(f"  [知识库] 当前活跃知识: {len(kb_active)} 条")

    # ── 步骤3：过滤已知错误 ──────────────────────────
    from kb_shared import is_covered_by_kb
    unknown_errors = []
    covered_count = 0

    for err in errors:
        covered, _ = is_covered_by_kb(err.get("error", ""), PROJECT_ROOT)
        if covered:
            covered_count += 1
        else:
            unknown_errors.append(err)

    if covered_count > 0:
        print(f"  [过滤] {covered_count} 条已被知识库覆盖，跳过")

    if not unknown_errors:
        print("  [结论] 所有错误已被知识库覆盖，无需分析")
        return

    print(f"  [分析] 待分析新错误: {len(unknown_errors)} 条")

    # ── 步骤4：LLM 泛化分析 ──────────────────────────
    print(f"\n  [LLM] 调用泛化分析...")
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    try:
        results = process_errors(unknown_errors, PROJECT_ROOT, config=_load_config())
    except Exception as e:
        print(f"  [错误] 泛化分析失败: {e}")
        if api_key:
            notify_llm_failure(str(e), f"{len(unknown_errors)} 个错误分析失败", "")
        return

    # ── 步骤5：汇总结果 ───────────────────────────────
    reuse_count = sum(1 for r in results if r.get("action") == "reuse")
    merge_count = sum(1 for r in results if r.get("action") == "merge")
    new_count = sum(1 for r in results if r.get("action") == "new")

    print(f"\n  [结果]")
    print(f"    reuse:  {reuse_count} 条")
    print(f"    merge:  {merge_count} 条")
    print(f"    new:    {new_count} 条")

    # ── 步骤6：知识库更新后状态 ────────────────────────
    kb_after = load_knowledge_base(PROJECT_ROOT)
    kb_after_active = [e for e in kb_after if not e.get("superseded_by")]
    print(f"\n  [知识库] 更新后活跃知识: {len(kb_after_active)} 条")

    # ── 步骤7：退化检测 ───────────────────────────────
    decay_knowledge(PROJECT_ROOT)

    # ── 步骤8：打印统计 ───────────────────────────────
    print_kb_stats(PROJECT_ROOT)

    print(f"\n{'='*60}")
    print(f"✅ 会话级进化完成")
    print(f"{'='*60}")


def _load_config() -> dict:
    """加载配置"""
    config_path = EVOLVE_DIR / "config.yaml"
    if not config_path.exists():
        return {}

    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


# ── 独立运行（调试用）─────────────────────────────────────
def run_full_analysis():
    """不限制会话，强制分析所有未知错误"""
    print("\n[调试模式] 强制分析所有错误")
    run_session_evolution(max_age_hours=0)


# ── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CHK 会话级进化引擎")
    parser.add_argument("--max-errors", type=int, default=10, help="最多处理错误数")
    parser.add_argument("--max-age-hours", type=int, default=24, help="错误最大保留小时数")
    parser.add_argument("--full", action="store_true", help="强制分析所有错误（调试用）")

    args = parser.parse_args()

    if args.full:
        run_full_analysis()
    else:
        run_session_evolution(
            max_errors=args.max_errors,
            max_age_hours=args.max_age_hours,
        )
