#!/usr/bin/env python3
"""
进化系统端到端测试

测试目标：证明进化系统能从真实数据中正确学习。

场景：
1. 高质量会话（focused + tests）→ 应该被高分奖励
2. 低质量会话（sprawling + no tests）→ 应该被低分惩罚
3. 多次累积 → EMA 应该平滑收敛
4. agent 调用记录 → 真实写入和聚合
5. 权重持久化 → 跨会话保留

每个场景都不依赖 hook 数据，直接调用模块函数验证算法正确性。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 让测试能导入 hook 脚本
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks" / "scripts"))

from strategy_updater import score_session, update_weights, read_latest_session  # noqa: E402


def make_session(domain: str, productivity: str, has_tests: bool, test_ratio: float,
                 lines: int, agents_count: int, has_commit: bool) -> dict:
    """构造模拟的会话记录。"""
    return {
        "type": "session_end",
        "primary_domain": domain,
        "git_metrics": {
            "files_changed": 5 if productivity == "focused" else 25,
            "lines_added": lines // 2,
            "lines_removed": lines // 2,
        },
        "signals": {
            "productivity": productivity,
            "has_tests": has_tests,
            "test_ratio": test_ratio,
            "volume_lines": lines,
            "agents_used_count": agents_count,
            "agents_unique": [f"agent-{i}" for i in range(agents_count)],
            "commits_in_session": has_commit,
        },
    }


def test_scoring_logic():
    """评分函数合理性"""
    ideal = make_session("backend", "focused", True, 0.4, 200, 4, True)
    score_ideal = score_session(ideal)
    assert score_ideal > 7.5, f"理想会话应得高分，实际: {score_ideal:.2f}"

    bad = make_session("backend", "sprawling", False, 0.0, 1500, 1, False)
    score_bad = score_session(bad)
    assert score_bad < 5.0, f"糟糕会话应得低分，实际: {score_bad:.2f}"

    idle = make_session("idle", "none", False, 0.0, 0, 0, False)
    score_idle = score_session(idle)
    assert score_idle < 4.5, f"无产出会话应被惩罚，实际: {score_idle:.2f}"

    mediocre = make_session("backend", "focused", False, 0.0, 100, 1, True)
    score_mediocre = score_session(mediocre)
    assert score_mediocre > 6.5, f"聚焦无测试应中等偏上，实际: {score_mediocre:.2f}"

    # 评分单调性: 理想 > 中等 > 糟糕
    assert score_ideal > score_mediocre > score_bad, \
        f"评分单调性失败: {score_ideal:.2f} > {score_mediocre:.2f} > {score_bad:.2f}"


def test_ema_update():
    """EMA 权重更新"""
    with tempfile.TemporaryDirectory() as tmp:
        weights_file = Path(tmp) / "weights.json"

        session1 = make_session("backend", "focused", True, 0.5, 100, 3, True)
        score1 = score_session(session1)
        update_weights(weights_file, "backend", score1, session1)

        with open(weights_file) as f:
            data = json.load(f)
        expected = round(5.0 * 0.7 + score1 * 0.3, 2)
        assert data["backend"] == expected, f"首次 EMA 更新: {data['backend']} != {expected}"
        assert data["metadata"]["backend"]["execution_count"] == 1

        for _ in range(10):
            update_weights(weights_file, "backend", 9.0, session1)

        with open(weights_file) as f:
            data = json.load(f)
        assert data["backend"] > 8.0, f"连续高分后应收敛到高位: {data['backend']}"
        assert data["metadata"]["backend"]["execution_count"] == 11

        prev_weight = data["backend"]
        update_weights(weights_file, "backend", 2.0, session1)
        with open(weights_file) as f:
            data = json.load(f)
        assert data["backend"] < prev_weight, "低分应使权重下降"
        expected = round(prev_weight * 0.7 + 2.0 * 0.3, 2)
        assert abs(data["backend"] - expected) <= 0.05, \
            f"EMA 平滑性: {data['backend']} vs {expected}"


def test_session_log_io():
    """会话日志读写"""
    with tempfile.TemporaryDirectory() as tmp:
        sessions_file = Path(tmp) / "sessions.jsonl"

        result = read_latest_session(sessions_file)
        assert result is None, "不存在文件应返回 None"

        records = [
            make_session("backend", "focused", True, 0.3, 100, 2, True),
            make_session("frontend", "broad", False, 0.0, 200, 1, False),
            make_session("tests", "focused", True, 1.0, 50, 1, True),
        ]
        with open(sessions_file, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        latest = read_latest_session(sessions_file)
        assert latest is not None and latest.get("primary_domain") == "tests", \
            f"应读取最后一条记录: {latest}"

        with open(sessions_file, "a") as f:
            f.write("invalid json line\n")
        latest = read_latest_session(sessions_file)
        assert latest is not None and latest.get("primary_domain") == "tests", \
            "应跳过损坏行，找到最后有效记录"


def test_hook_subprocess():
    """Hook 脚本子进程调用"""
    project_root = Path(__file__).resolve().parents[2]

    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": tmp}
        Path(tmp, ".claude", "logs").mkdir(parents=True, exist_ok=True)
        Path(tmp, ".claude", "data").mkdir(parents=True, exist_ok=True)

        # 测试 session_evolver（在无 git 环境下不应崩溃）
        result = subprocess.run(
            ["python3", str(project_root / ".claude/hooks/scripts/session_evolver.py")],
            input='{"session_id":"test-1"}',
            capture_output=True, text=True, env=env, timeout=10
        )
        assert result.returncode == 0, f"session_evolver 崩溃: {result.stderr}"

        sessions_file = Path(tmp, ".claude/logs/sessions.jsonl")
        assert sessions_file.exists(), "session_evolver 应写入 sessions.jsonl"


def test_cumulative_learning():
    """累积学习行为（核心）"""
    with tempfile.TemporaryDirectory() as tmp:
        weights_file = Path(tmp) / "weights.json"

        for _ in range(10):
            bad = make_session("backend", "sprawling", False, 0.0, 1500, 1, False)
            update_weights(weights_file, "backend", score_session(bad), bad)

        with open(weights_file) as f:
            mid_data = json.load(f)
        weight_after_bad = mid_data["backend"]
        assert weight_after_bad < 5.0, f"10次糟糕后权重应低于5.0: {weight_after_bad:.2f}"

        for _ in range(10):
            good = make_session("backend", "focused", True, 0.4, 200, 4, True)
            update_weights(weights_file, "backend", score_session(good), good)

        with open(weights_file) as f:
            final_data = json.load(f)
        weight_after_good = final_data["backend"]
        assert weight_after_good > weight_after_bad, \
            f"优质后应更高: {weight_after_good:.2f} vs {weight_after_bad:.2f}"
        assert final_data["metadata"]["backend"]["execution_count"] == 20

        last_signals = final_data["metadata"]["backend"]["last_signals"]
        assert last_signals.get("productivity") == "focused" and last_signals.get("has_tests"), \
            f"最新会话信号丢失: {last_signals}"
