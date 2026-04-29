#!/usr/bin/env python3
"""
Strategy Updater - Stop Hook

基于 sessions.jsonl 中的真实会话数据更新策略权重。
这不是拍脑袋打分，而是读取本次会话的真实指标后做 EMA 更新。

评分规则（基于可验证的事实）：
- 有实质产出（files > 0）：+基础分
- 有测试文件（test_ratio > 0）：+质量分
- 变更聚焦（files <= 5）或有节制（files <= 15）：+加分
- 变更失控（files > 20）或 lines > 1000：-扣分
- 使用了多个 agent 协作：+协作加分

每次会话结束后：
1. 读 sessions.jsonl 最后一条记录
2. 基于 signals 计算 session_score
3. 对 primary_domain 做 EMA 更新：new = 0.7 * old + 0.3 * session_score
"""

import fcntl
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
from constants import EMA_ALPHA, INITIAL_WEIGHT, SCORE_MIN, SCORE_MAX, SCORE_BASE


def read_latest_session(sessions_file: Path) -> Optional[Dict[str, Any]]:
    """读取 sessions.jsonl 的最后一条 session_end 记录。损坏的行会被跳过。"""
    if not sessions_file.exists():
        return None
    try:
        with open(sessions_file, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # 跳过损坏行，继续向前找
        if record.get("type") == "session_end":
            return record
    return None


def score_session(session: Dict[str, Any]) -> float:
    signals = session.get("signals", {})
    metrics = session.get("git_metrics", {})

    score = SCORE_BASE

    productivity = signals.get("productivity", "none")
    score += {"none": -1.5, "focused": 2.0, "broad": 1.0, "sprawling": -0.5}.get(productivity, 0.0)

    if signals.get("has_tests"):
        score += signals.get("test_ratio", 0) * 2.0

    agents_count = signals.get("agents_used_count", 0)
    if agents_count >= 3:
        score += 1.0
    elif agents_count >= 1:
        score += 0.3

    lines_total = metrics.get("lines_added", 0) + metrics.get("lines_removed", 0)
    if lines_total > 1000:
        score -= 1.0

    if signals.get("commits_in_session"):
        score += 0.5

    return max(SCORE_MIN, min(SCORE_MAX, score))


def update_weights(
    weights_file: Path,
    domain: str,
    session_score: float,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """EMA 更新策略权重，带元数据记录。"""
    if weights_file.exists():
        with open(weights_file, "r", encoding="utf-8") as f:
            weights = json.load(f)
    else:
        weights = {}

    current = weights.get(domain, INITIAL_WEIGHT)
    # 保留 _comment 等元字段
    if isinstance(current, dict):
        current = current.get("weight", INITIAL_WEIGHT)

    new_weight = current * (1 - EMA_ALPHA) + session_score * EMA_ALPHA
    weights[domain] = round(new_weight, 2)

    # 元数据记录（真实可审计）
    if "metadata" not in weights:
        weights["metadata"] = {}
    prev = weights["metadata"].get(domain, {})
    weights["metadata"][domain] = {
        "last_updated": datetime.now().isoformat(),
        "last_session_score": round(session_score, 2),
        "last_signals": session.get("signals", {}),
        "execution_count": prev.get("execution_count", 0) + 1,
    }

    # 原子写入：先写临时文件，再 rename（防止并发写入损坏）
    fd, tmp_path = tempfile.mkstemp(
        dir=weights_file.parent,
        prefix=".strategy_weights_",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(weights, f, indent=2, ensure_ascii=False)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(tmp_path, weights_file)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return weights


def main():
    """Stop hook 入口：基于真实会话指标更新策略权重。"""
    # Stop hook stdin 不可靠，只做 best effort 解析
    try:
        sys.stdin.read()
    except OSError:
        pass

    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    sessions_file = project_root / ".claude" / "logs" / "sessions.jsonl"
    weights_file = project_root / ".claude" / "data" / "strategy_weights.json"

    session = read_latest_session(sessions_file)
    if not session:
        print("ℹ️  无 session 记录可用于策略更新", file=sys.stderr)
        return

    domain = session.get("primary_domain", "general")
    if domain == "idle":
        print("ℹ️  本次会话无实质变更，跳过策略更新", file=sys.stderr)
        return

    session_score = score_session(session)
    update_weights(weights_file, domain, session_score, session)

    print(
        f"📈 策略已更新 [{domain}]: score={session_score:.2f}, "
        f"signals={session.get('signals', {}).get('productivity')}",
        file=sys.stderr
    )


if __name__ == "__main__":
    main()
