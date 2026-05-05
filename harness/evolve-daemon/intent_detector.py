"""
Intent-Failure Detection — 意图失败检测

借鉴 OpenAI Harness Engineering: "Agent followed the rules but missed the product's intent."

检测逻辑:
  1. Agent 产出被用户手动大量修改 → 表面正确但实质不对
  2. 同一任务类型反复出现纠正 → 规则/Skill 未覆盖关键意图
  3. 上游产出在下游被大量重写 → 意图传递断裂
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import kb_shared


def detect_intent_failures(sessions_dir: Path, threshold: float = 0.30) -> list:
    """
    Analyze session data for intent-failure patterns.

    Args:
        sessions_dir: Directory containing session JSONL files
        threshold: Edit diff ratio above which is considered intent failure (default 0.30)

    Returns:
        List of detected intent failure records
    """
    failures = []
    sessions = kb_shared.load_sessions(sessions_dir)

    for session in sessions:
        # Pattern 1: Agent claimed completion but user edited heavily
        if _agent_claimed_done(session) and _user_edited_heavily(session, threshold):
            failures.append({
                "type": "surface_correct_but_wrong",
                "session_id": session.get("id"),
                "task": session.get("task_description", ""),
                "agent_output": _summarize(session.get("agent_output", ""), 200),
                "user_edit_diff_ratio": session.get("edit_diff_ratio", 0.0),
                "detected_at": datetime.now().isoformat(),
                "root_cause_hint": "Agent satisfied acceptance criteria but missed underlying intent"
            })

        # Pattern 2: Repeated corrections on same task type
        corrections = session.get("corrections", [])
        if len(corrections) >= 2:
            # Check if corrections cluster around specific topics
            topics = [c.get("target", "") for c in corrections]
            if _has_repeated_topics(topics):
                failures.append({
                    "type": "repeated_correction",
                    "session_id": session.get("id"),
                    "topic": _most_common(topics),
                    "correction_count": len(corrections),
                    "detected_at": datetime.now().isoformat(),
                    "root_cause_hint": f"Skill/Agent definition may be missing guidance on: {_most_common(topics)}"
                })

    return failures


def _agent_claimed_done(session: dict) -> bool:
    """Check if agent reported task completion."""
    status = session.get("status", "")
    output = session.get("agent_output", "")
    return status == "completed" or "完成" in output or "done" in output.lower()


def _user_edited_heavily(session: dict, threshold: float) -> bool:
    """Check if user made significant manual edits after agent completion."""
    edit_ratio = session.get("edit_diff_ratio", 0.0)
    return edit_ratio > threshold


def _has_repeated_topics(topics: list) -> bool:
    """Check if same topic appears multiple times in corrections."""
    if len(topics) < 2:
        return False
    # Group similar topics by normalizing
    normalized = [_normalize_topic(t) for t in topics]
    for topic in set(normalized):
        if normalized.count(topic) >= 2:
            return True
    return False


def _normalize_topic(topic: str) -> str:
    """Normalize topic string for comparison."""
    # Remove agent: or skill: prefixes
    topic = re.sub(r'^(agent|skill|rule):\s*', '', topic)
    return topic.strip().lower()


def _most_common(items: list) -> str:
    if not items:
        return "unknown"
    normalized = [_normalize_topic(i) for i in items]
    return max(set(normalized), key=normalized.count)


def _summarize(text: str, max_len: int) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text


def analyze_intent_trends(sessions_dir: Path, days: int = 30) -> dict:
    """
    Analyze intent-failure trends over time.
    Returns counts and trends for dashboard display.
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    sessions = kb_shared.load_sessions(sessions_dir)

    recent = [s for s in sessions if s.get("timestamp", "") >= cutoff]
    failures = detect_intent_failures(sessions_dir)

    return {
        "period_days": days,
        "total_sessions": len(recent),
        "intent_failures": len(failures),
        "failure_rate": len(failures) / max(len(recent), 1),
        "by_type": {
            "surface_correct_but_wrong": len([f for f in failures if f["type"] == "surface_correct_but_wrong"]),
            "repeated_correction": len([f for f in failures if f["type"] == "repeated_correction"]),
        }
    }


if __name__ == "__main__":
    import sys
    sessions_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".claude/data/")
    failures = detect_intent_failures(sessions_dir)
    print(json.dumps(failures, indent=2, ensure_ascii=False))
