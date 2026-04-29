#!/usr/bin/env python3
"""
Token 效率管理 — 三层渐进式加载 + 数据压缩 + 预算控制

原则: 原始 JSONL 永不进入 LLM 上下文，只传摘要。
"""
import json, re, sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class TokenBudget:
    """Token 预算管理器"""

    L1_METADATA = 200       # SessionStart 注入
    L2_SUMMARY = 1000       # Stop orchestrator 输出
    L3_DETAIL = 5000        # 进化 Agent 输入

    @staticmethod
    def estimate(text: str) -> int:
        """估算 token 数 (英文 0.75 词/token, 中文 0.5 字/token)"""
        en_words = len(re.findall(r'[a-zA-Z]+', text))
        cn_chars = len(re.findall(r'[一-鿿]', text))
        return int(en_words / 0.75 + cn_chars / 0.5)

    @staticmethod
    def truncate(text: str, max_tokens: int) -> str:
        """截断到预算内"""
        if TokenBudget.estimate(text) <= max_tokens:
            return text
        lines = text.split("\n")
        result = []
        current = 0
        for line in lines:
            lt = TokenBudget.estimate(line)
            if current + lt > max_tokens:
                result.append(f"... (截断, 剩余 {len(lines)-len(result)} 行)")
                break
            result.append(line)
            current += lt
        return "\n".join(result)

    # 别名：与设计文档 evolution-system-design.md 命名保持一致
    truncate_to_budget = truncate

    @staticmethod
    def check(label: str, text: str, budget: int) -> bool:
        estimated = TokenBudget.estimate(text)
        if estimated > budget:
            print(f"⚠️ Token 超支 [{label}]: {estimated} > {budget}", file=sys.stderr)
            return False
        return True


def summarize_skill_usage(raw_data: list) -> dict:
    """压缩 Skill 使用数据 (100:1)"""
    if not raw_data:
        return {"total_calls": 0}
    sessions = set(r.get("session_id", "") for r in raw_data)
    return {
        "total_calls": len(raw_data),
        "unique_sessions": len(sessions),
        "by_day": _by_day([r.get("timestamp", "")[:10] for r in raw_data]),
        "last_used": max((r.get("timestamp", "") for r in raw_data), default=None),
    }


def summarize_agent_perf(raw_data: list) -> dict:
    """压缩 Agent 执行数据 (100:1)"""
    if not raw_data:
        return {"total_launches": 0}
    tasks = [r.get("task", "") for r in raw_data]
    return {
        "total_launches": len(raw_data),
        "unique_sessions": len(set(r.get("session_id", "") for r in raw_data)),
        "task_samples": tasks[:10],
        "by_day": _by_day([r.get("timestamp", "")[:10] for r in raw_data]),
    }


def summarize_rule_violations(raw_data: list) -> dict:
    """压缩违规数据 (100:1)"""
    if not raw_data:
        return {"total": 0}
    by_rule = {}
    for r in raw_data:
        rule = r.get("rule", "unknown")
        sev = r.get("severity", "low")
        by_rule.setdefault(rule, {}).setdefault(sev, 0)
        by_rule[rule][sev] += 1
    return {
        "total": len(raw_data),
        "by_rule": by_rule,
        "top_file": max(
            set(r.get("file", "") for r in raw_data),
            key=lambda f: sum(1 for r in raw_data if r.get("file") == f),
            default=None,
        ),
    }


def summarize_for_evolver(dimension: str, raw_data: list) -> dict:
    """统一入口: 按维度压缩原始数据"""
    if dimension == "skill":
        return summarize_skill_usage(raw_data)
    elif dimension == "agent":
        return summarize_agent_perf(raw_data)
    elif dimension == "rule":
        return summarize_rule_violations(raw_data)
    return {"summary": f"{len(raw_data)} records"}


def compact_old_data(data_dir: Path, keep_days: int = 7):
    """
    压缩旧数据: 保留最近 N 天原始记录，更早的只保留统计摘要。
    压缩比 ~200:1
    """
    cutoff = datetime.now() - timedelta(days=keep_days)
    for jsonl_file in data_dir.glob("*.jsonl"):
        recent, old = [], []
        for line in _safe_read_lines(jsonl_file):
            record = _safe_parse(line)
            if not record:
                continue
            ts_str = record.get("timestamp", "2000-01-01")
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                ts = datetime(2000, 1, 1)
            if ts > cutoff:
                recent.append(record)
            else:
                old.append(record)

        if old:
            summary_file = data_dir / f"{jsonl_file.stem}_archive_summary.json"
            summary = {
                "compacted_at": datetime.now().isoformat(),
                "original_count": len(old),
                "date_range": f"{old[0].get('timestamp','?')[:10]} ~ {old[-1].get('timestamp','?')[:10]}",
                "stats": _basic_stats(old),
            }
            tmp = summary_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
            import os as _os
            _os.replace(str(tmp), str(summary_file))

        if recent or old:
            tmp = jsonl_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for r in recent:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            import os as _os
            _os.replace(str(tmp), str(jsonl_file))


def _by_day(timestamps: list) -> dict:
    by = {}
    for ts in timestamps:
        by[ts] = by.get(ts, 0) + 1
    return by


def _safe_read_lines(path: Path):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield line.strip()


def _safe_parse(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _basic_stats(records: list) -> dict:
    return {
        "count": len(records),
    }
