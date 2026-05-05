#!/usr/bin/env python3
"""
数据验证器 — 验证 sessions.jsonl 格式，隔离异常数据。

作用:
1. 验证 session 数据格式
2. 过滤无效数据
3. 隔离格式错误的数据到 quarantine/
4. 统计数据质量
"""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加 harness 到 Python path
_harness_root = Path(__file__).parent.parent.parent
if str(_harness_root) not in sys.path:
    sys.path.insert(0, str(_harness_root))

from harness._core.exceptions import handle_exception, safe_execute

logger = logging.getLogger(__name__)


import kb_shared
from _daemon_config import load_config, _default_config
from _find_root import find_root


def validate_session(session: dict) -> tuple[bool, Optional[str]]:
    """
    验证单个 session 的格式。

    返回: (is_valid, error_message)
    """
    # 必须有 session_id
    if not session.get("session_id"):
        return False, "Missing session_id"

    # 必须有 timestamp
    if not session.get("timestamp"):
        return False, "Missing timestamp"

    # 验证 timestamp 格式
    try:
        datetime.fromisoformat(session.get("timestamp", ""))
    except (ValueError, TypeError):
        return False, f"Invalid timestamp format: {session.get('timestamp')}"

    # duration_minutes 必须是非负整数
    duration = session.get("duration_minutes", 0)
    if not isinstance(duration, int) or duration < 0:
        return False, f"Invalid duration_minutes: {duration}"

    # corrections 格式检查（如果有）
    for c in session.get("corrections", []):
        if not isinstance(c, dict):
            return False, "Correction must be dict"
        if "target" not in c:
            return False, "Correction missing 'target'"

    # failure_types 格式检查（如果有）
    failure_types = session.get("failure_types", {})
    if not isinstance(failure_types, dict):
        return False, "failure_types must be dict"

    return True, None


def validate_sessions_file(sessions_file: Path, quarantine_dir: Optional[Path] = None) -> dict:
    """
    验证 sessions.jsonl 文件。

    返回:
    {
        "total": 100,
        "valid": 98,
        "invalid": 2,
        "quarantined": 1,
        "errors": [...]
    }
    """
    if not sessions_file.exists():
        return {"total": 0, "valid": 0, "invalid": 0, "quarantined": 0, "errors": []}

    valid_sessions = []
    invalid_lines = []
    errors = []

    try:
        content = sessions_file.read_text().strip()
        if not content:
            return {"total": 0, "valid": 0, "invalid": 0, "quarantined": 0, "errors": []}

        lines = content.splitlines()
        total = len(lines)

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            try:
                session = json.loads(line)
                is_valid, error_msg = validate_session(session)

                if is_valid:
                    valid_sessions.append(session)
                else:
                    invalid_lines.append((i, line, error_msg))
                    errors.append(f"Line {i + 1}: {error_msg}")

            except json.JSONDecodeError as e:
                invalid_lines.append((i, line, f"JSON decode error: {e}"))
                errors.append(f"Line {i + 1}: JSON decode error")

        # 隔离无效数据
        quarantined_count = 0
        if quarantine_dir and invalid_lines:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            quarantine_file = quarantine_dir / f"sessions_invalid_{timestamp}.jsonl"
            with open(quarantine_file, "w") as f:
                for _, line, _ in invalid_lines:
                    f.write(line + "\n")
                    quarantined_count += 1

        # 覆写有效数据（原子操作：先写临时文件，再重命名）
        if valid_sessions:
            temp_file = sessions_file.with_suffix(".jsonl.tmp")
            temp_file.write_text(
                "\n".join(json.dumps(s, ensure_ascii=False) for s in valid_sessions) + "\n",
                encoding="utf-8"
            )
            temp_file.replace(sessions_file)
        else:
            # 空文件也用原子操作
            sessions_file.write_text("", encoding="utf-8")

        return {
            "total": total,
            "valid": len(valid_sessions),
            "invalid": len(invalid_lines),
            "quarantined": quarantined_count,
            "errors": errors,
        }

    except Exception as e:
        return {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "quarantined": 0,
            "errors": [str(e)],
        }


def clean_old_sessions(sessions_file: Path, max_age_days: int = 90) -> dict:
    """
    清理超过指定天数的 session。

    返回清理统计。
    """
    if not sessions_file.exists():
        return {"cleaned": 0, "kept": 0}

    cutoff = datetime.now() - __import__("datetime").timedelta(days=max_age_days)
    kept_sessions = []
    cleaned = 0

    try:
        sessions = kb_shared.read_jsonl(sessions_file)
        for session in sessions:
            try:
                session_time = datetime.fromisoformat(session.get("timestamp", "2000-01-01"))
                if session_time >= cutoff:
                    kept_sessions.append(session)
                else:
                    cleaned += 1
            except (ValueError, TypeError):
                cleaned += 1

        # 原子写入：先写临时文件，再重命名
        if kept_sessions:
            temp_file = sessions_file.with_suffix(".jsonl.tmp")
            temp_file.write_text(
                "\n".join(json.dumps(s, ensure_ascii=False) for s in kept_sessions) + "\n",
                encoding="utf-8"
            )
            temp_file.replace(sessions_file)
        else:
            sessions_file.write_text("", encoding="utf-8")

    except OSError as e:
        handle_exception(e, f"清理旧会话失败: {sessions_file}", default_return={"cleaned": 0, "kept": 0}, log_level="warning")

    return {"cleaned": cleaned, "kept": len(kept_sessions)}


def get_data_quality_stats(sessions_file: Path) -> dict:
    """
    统计数据质量。

    返回:
    {
        "total_sessions": 100,
        "sessions_with_agents": 80,
        "sessions_with_failures": 30,
        "sessions_with_corrections": 10,
        "average_duration": 15.5,
        "average_failures": 1.2,
    }
    """
    if not sessions_file.exists():
        return {}

    stats = {
        "total_sessions": 0,
        "sessions_with_agents": 0,
        "sessions_with_failures": 0,
        "sessions_with_corrections": 0,
        "total_duration": 0,
        "total_failures": 0,
    }

    try:
        content = sessions_file.read_text().strip()
        if not content:
            return stats

        for line in content.splitlines():
            if not line.strip():
                continue

            try:
                session = json.loads(line)
                stats["total_sessions"] += 1

                if session.get("agents_used"):
                    stats["sessions_with_agents"] += 1

                if session.get("tool_failures", 0) > 0:
                    stats["sessions_with_failures"] += 1

                if session.get("corrections"):
                    stats["sessions_with_corrections"] += 1

                stats["total_duration"] += session.get("duration_minutes", 0)
                stats["total_failures"] += session.get("tool_failures", 0)

            except json.JSONDecodeError:
                continue

        total = max(stats["total_sessions"], 1)
        stats["average_duration"] = round(stats["total_duration"] / total, 1)
        stats["average_failures"] = round(stats["total_failures"] / total, 2)
        stats["agents_usage_rate"] = round(stats["sessions_with_agents"] / total, 2)
        stats["failures_rate"] = round(stats["sessions_with_failures"] / total, 2)
        stats["corrections_rate"] = round(stats["sessions_with_corrections"] / total, 2)

    except OSError as e:
        handle_exception(e, f"统计数据质量失败: {sessions_file}", default_return=stats, log_level="warning")

    return stats


def run_validation(root: Optional[Path] = None, config: Optional[dict] = None) -> dict:
    """
    运行完整验证流程。
    """
    if root is None:
        root = find_root()

    if config is None:
        config = load_config()

    if not config.get("validation", {}).get("enabled", True):
        return {"status": "disabled", "message": "Validation is disabled"}

    data_dir = root / config.get("paths", {}).get("data_dir", ".claude/data")
    sessions_file = data_dir / "sessions.jsonl"

    if not sessions_file.exists():
        return {"status": "no_data", "message": "sessions.jsonl not found"}

    quarantine_dir = None
    if config.get("validation", {}).get("quarantine_malformed", True):
        quarantine_dir = data_dir / "quarantine"

    # 执行验证
    validation_result = validate_sessions_file(sessions_file, quarantine_dir)

    # 清理旧数据
    max_age_days = config.get("validation", {}).get("max_age_days", 90)
    clean_result = clean_old_sessions(sessions_file, max_age_days)

    # 统计质量
    quality = get_data_quality_stats(sessions_file)

    return {
        "status": "completed",
        "validation": validation_result,
        "clean": clean_result,
        "quality": quality,
        "message": f"Validated: {validation_result['valid']}/{validation_result['total']} valid, cleaned {clean_result['cleaned']} old sessions",
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="数据验证器")
    parser.add_argument("action", choices=["validate", "clean", "stats"])
    parser.add_argument("--file", help="sessions.jsonl 路径")
    parser.add_argument("--max-age-days", type=int, default=90)

    args = parser.parse_args()

    root = find_root()
    data_dir = root / ".claude" / "data"
    sessions_file = Path(args.file) if args.file else data_dir / "sessions.jsonl"

    if args.action == "validate":
        result = run_validation()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.action == "clean":
        result = clean_old_sessions(sessions_file, args.max_age_days)
        print(json.dumps(result, indent=2))

    elif args.action == "stats":
        stats = get_data_quality_stats(sessions_file)
        print(json.dumps(stats, indent=2))