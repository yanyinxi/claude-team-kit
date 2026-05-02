#!/usr/bin/env python3
"""
evolve-daemon 单元测试套件 — 测试 analyzer / proposer / rollback / daemon 核心逻辑。
覆盖:
  - analyzer: 聚合正确性（空 sessions / 多 corrections / 多 sessions）
  - proposer: 无 API Key 时模板降级；proposal 保存路径
  - daemon check: 触发条件（≥5 sessions / ≥3 patterns / ≥6h）
  - rollback: 指标评估逻辑（keep/observe/rollback）
  - instinct_updater: 读写 instinct-record.json
  - lifecycle: 成熟度升级 / 衰减
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVOLVE_DIR = PROJECT_ROOT / "evolve-daemon"

# 将 evolve-daemon 和 knowledge 加入 path
sys.path.insert(0, str(EVOLVE_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "knowledge"))

PASS = 0
FAIL = 0


def get_module(name: str):
    import importlib
    return importlib.import_module(name)


def make_session(session_id: str, corrections: list, timestamp: Optional[str] = None,
                 status: str = "success") -> dict:
    return {
        "session_id": session_id,
        "timestamp": timestamp or datetime.now().isoformat(),
        "corrections": corrections,
        "status": status,
        "correction_count": len(corrections),
        "failure_count": 0,
    }


# ── analyzer 测试 ────────────────────────────────────────────────────────────

def test_analyzer_empty_sessions():
    global PASS, FAIL
    analyzer = get_module("analyzer")
    config = {"thresholds": {"min_corrections": 1}}
    result = analyzer.aggregate_and_analyze([], config, PROJECT_ROOT)
    assert result.get("total_sessions") == 0
    PASS += 1
    print("  ✅ analyzer: 空 sessions 不崩溃")


def test_analyzer_single_correction():
    global PASS, FAIL
    analyzer = get_module("analyzer")
    sessions = [
        make_session("s1", [{"target": "skill:testing", "context": "test context"}])
    ]
    config = {"thresholds": {"min_corrections": 1}}
    result = analyzer.aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    assert result.get("total_sessions") == 1
    assert "correction_hotspots" in result
    PASS += 1
    print("  ✅ analyzer: 单次纠正正确聚合")


def test_analyzer_multi_session():
    global PASS, FAIL
    analyzer = get_module("analyzer")
    sessions = [
        make_session("s1", [{"target": "agent:backend-dev", "root_cause_hint": "missing-test"}]),
        make_session("s2", [{"target": "agent:backend-dev", "root_cause_hint": "missing-test"}]),
        make_session("s3", [{"target": "agent:backend-dev", "root_cause_hint": "missing-test"}]),
    ]
    config = {"thresholds": {"min_corrections": 1}}
    result = analyzer.aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    hotspots = result.get("correction_hotspots", {})
    assert hotspots.get("agent:backend-dev", 0) >= 2
    PASS += 1
    print("  ✅ analyzer: 多会话聚合正确")


def test_analyzer_pattern_grouping():
    global PASS, FAIL
    analyzer = get_module("analyzer")
    sessions = [
        make_session("s1", [{"target": "x", "root_cause_hint": "bug1"}]),
        make_session("s2", [{"target": "x", "root_cause_hint": "bug1"}]),
        make_session("s3", [{"target": "x", "root_cause_hint": "bug1"}]),
        make_session("s4", [{"target": "y", "root_cause_hint": "bug2"}]),
    ]
    config = {"thresholds": {"min_corrections": 1}}
    result = analyzer.aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    patterns = result.get("correction_patterns", {})
    # x:bug1 应该被聚合成组
    assert len(patterns) >= 1
    PASS += 1
    print("  ✅ analyzer: 同一模式正确分组")


# ── daemon check_thresholds 测试 ──────────────────────────────────────────

def test_daemon_threshold_5_sessions():
    global PASS, FAIL
    daemon = get_module("daemon")
    sessions = [make_session(f"s{i}", []) for i in range(5)]
    config = daemon.load_config()
    triggers = daemon.check_thresholds(sessions, config)
    should_run = any("new_sessions" in t for t in triggers)
    if should_run:
        PASS += 1
        print("  ✅ daemon: ≥5 sessions 触发 check")
    else:
        FAIL += 1
        print(f"  ❌ daemon: 5 sessions 未触发 → {triggers}")


def test_daemon_threshold_4_sessions_no_trigger():
    global PASS, FAIL
    daemon = get_module("daemon")
    sessions = [make_session(f"s{i}", []) for i in range(4)]
    config = daemon.load_config()
    triggers = daemon.check_thresholds(sessions, config)
    should_run = any("new_sessions" in t for t in triggers)
    if not should_run:
        PASS += 1
        print("  ✅ daemon: 4 sessions 不触发")
    else:
        FAIL += 1
        print(f"  ❌ daemon: 4 sessions 错误触发 → {triggers}")


def test_daemon_threshold_time_elapsed():
    global PASS, FAIL
    daemon = get_module("daemon")
    sessions = [make_session("s1", [])]
    old_time = (datetime.now() - timedelta(hours=7)).isoformat()
    config = daemon.load_config()
    last_time = datetime.fromisoformat(old_time)
    triggers = daemon.check_thresholds(sessions, config, last_time)
    time_trigger = any("time_elapsed" in t for t in triggers)
    if time_trigger:
        PASS += 1
        print("  ✅ daemon: ≥6h 间隔触发 time_elapsed")
    else:
        FAIL += 1
        print(f"  ❌ daemon: 7h 未触发 time_elapsed → {triggers}")


def test_daemon_threshold_pattern_group():
    global PASS, FAIL
    daemon = get_module("daemon")
    sessions = [
        make_session("s1", [{"target": "x", "root_cause_hint": "bug1"}]),
        make_session("s2", [{"target": "x", "root_cause_hint": "bug1"}]),
        make_session("s3", [{"target": "x", "root_cause_hint": "bug1"}]),
    ]
    config = daemon.load_config()
    triggers = daemon.check_thresholds(sessions, config)
    pattern_trigger = any("pattern" in t for t in triggers)
    if pattern_trigger:
        PASS += 1
        print("  ✅ daemon: ≥3 同模式纠正触发")
    else:
        FAIL += 1
        print(f"  ❌ daemon: 3 同模式未触发 → {triggers}")


# ── rollback evaluate_proposal 测试 ────────────────────────────────────────

def test_rollback_keep_when_improved():
    global PASS, FAIL
    rollback = get_module("rollback")
    baseline = {"task_success_rate": 0.8, "correction_rate": 0.2,
                "agent_failure_rate": 0.1, "satisfaction_score": 4.0}
    metrics = {"task_success_rate": 0.85, "correction_rate": 0.15,
               "agent_failure_rate": 0.08, "satisfaction_score": 4.2}
    decision = rollback.evaluate_proposal({}, metrics, baseline)
    if decision == "keep":
        PASS += 1
        print("  ✅ rollback: 指标改善 → keep")
    else:
        FAIL += 1
        print(f"  ❌ rollback: 改善应返回 keep，实际 {decision}")


def test_rollback_rollback_on_degradation():
    global PASS, FAIL
    rollback = get_module("rollback")
    baseline = {"task_success_rate": 1.0, "correction_rate": 0.0,
                "agent_failure_rate": 0.0, "satisfaction_score": 5.0}
    metrics = {"task_success_rate": 0.7, "correction_rate": 0.5,
               "agent_failure_rate": 0.3, "satisfaction_score": 2.0}
    decision = rollback.evaluate_proposal({}, metrics, baseline)
    if decision == "rollback":
        PASS += 1
        print("  ✅ rollback: 指标退化 → rollback")
    else:
        FAIL += 1
        print(f"  ❌ rollback: 退化应返回 rollback，实际 {decision}")


def test_rollback_observe_on_neutral():
    global PASS, FAIL
    rollback = get_module("rollback")
    baseline = {"task_success_rate": 0.8, "correction_rate": 0.2,
                "agent_failure_rate": 0.1, "satisfaction_score": 4.0}
    metrics = {"task_success_rate": 0.8, "correction_rate": 0.2,
               "agent_failure_rate": 0.1, "satisfaction_score": 4.0}
    decision = rollback.evaluate_proposal({}, metrics, baseline)
    if decision in ("keep", "observe"):
        PASS += 1
        print(f"  ✅ rollback: 中性指标 → {decision}")
    else:
        FAIL += 1
        print(f"  ❌ rollback: 中性应返回 keep/observe，实际 {decision}")


def test_rollback_collect_metrics():
    global PASS, FAIL
    rollback = get_module("rollback")
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_dir = Path(tmpdir)
        sessions_file = metrics_dir / "sessions.jsonl"
        sessions_file.write_text("\n".join([
            json.dumps({"timestamp": datetime.now().isoformat(), "status": "success",
                        "correction_count": 0, "failure_count": 0}),
            json.dumps({"timestamp": datetime.now().isoformat(), "status": "success",
                        "correction_count": 1, "failure_count": 0}),
        ]) + "\n")
        m = rollback.collect_metrics("test", metrics_dir)
        assert "task_success_rate" in m
        assert "correction_rate" in m
        PASS += 1
        print("  ✅ rollback: collect_metrics 正常收集")


# ── instinct_updater 测试 ───────────────────────────────────────────────────

def test_instinct_add_and_read():
    global PASS, FAIL
    instinct_updater = get_module("instinct_updater")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_record = Path(tmpdir) / "instinct-record.json"
        # Mock the path
        original_path = instinct_updater.Path
        # Patch at module level
        with patch.object(instinct_updater, "Path", lambda x=tmpdir: Path(x)):
            # 直接调用 add_pattern
            try:
                record_id = instinct_updater.add_pattern(
                    pattern="测试模式",
                    correction="测试纠正",
                    confidence=0.5,
                )
                PASS += 1
                print(f"  ✅ instinct_updater: add_pattern 成功 → {record_id}")
            except Exception as e:
                FAIL += 1
                print(f"  ❌ instinct_updater: {e}")


def test_instinct_load_init():
    global PASS, FAIL
    instinct_updater = get_module("instinct_updater")
    data = instinct_updater.load_instinct()
    assert "records" in data
    assert isinstance(data["records"], list)
    PASS += 1
    print("  ✅ instinct_updater: load_instinct 初始化正确")


# ── lifecycle 测试 ───────────────────────────────────────────────────────────

def test_lifecycle_draft_to_verified():
    global PASS, FAIL
    lifecycle = get_module("lifecycle")
    config = lifecycle.load_lifecycle_config()
    entry = {"id": "test-1", "maturity": "draft", "usage_count": 1}
    promo = lifecycle.check_maturity_promotion(entry, config)
    if promo == "verified":
        PASS += 1
        print("  ✅ lifecycle: draft→verified 正确升级")
    else:
        FAIL += 1
        print(f"  ❌ lifecycle: draft→verified 应返回 verified，实际 {promo}")


def test_lifecycle_verified_to_proven():
    global PASS, FAIL
    lifecycle = get_module("lifecycle")
    config = lifecycle.load_lifecycle_config()
    entry = {"id": "test-2", "maturity": "verified", "project_count": 2}
    promo = lifecycle.check_maturity_promotion(entry, config)
    if promo == "proven":
        PASS += 1
        print("  ✅ lifecycle: verified→proven 正确升级")
    else:
        FAIL += 1
        print(f"  ❌ lifecycle: verified→proven 应返回 proven，实际 {promo}")


def test_lifecycle_decay_proven():
    global PASS, FAIL
    lifecycle = get_module("lifecycle")
    config = lifecycle.load_lifecycle_config()
    old_date = (datetime.now() - timedelta(days=400)).isoformat()
    entry = {"id": "test-3", "maturity": "proven", "last_used_at": old_date}
    decay = lifecycle.apply_decay(entry, config)
    if decay == "verified":
        PASS += 1
        print("  ✅ lifecycle: proven 12月+未用 → verified 衰减")
    else:
        FAIL += 1
        print(f"  ❌ lifecycle: proven 衰减应返回 verified，实际 {decay}")


def test_lifecycle_no_decay_recent():
    global PASS, FAIL
    lifecycle = get_module("lifecycle")
    config = lifecycle.load_lifecycle_config()
    recent = (datetime.now() - timedelta(days=30)).isoformat()
    entry = {"id": "test-4", "maturity": "proven", "last_used_at": recent}
    decay = lifecycle.apply_decay(entry, config)
    if decay is None:
        PASS += 1
        print("  ✅ lifecycle: proven 30天未用 → 无衰减")
    else:
        FAIL += 1
        print(f"  ❌ lifecycle: recent 不应衰减，实际 {decay}")


# ── proposer 测试 ────────────────────────────────────────────────────────────

def test_proposer_template_generates_file():
    global PASS, FAIL
    proposer = get_module("proposer")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        analysis = {
            "total_sessions": 5,
            "correction_hotspots": {"agent:backend-dev": 3},
            "correction_patterns": {},
            "primary_target": "backend-dev",
        }
        config = {
            "paths": {"proposals_dir": ".claude/proposals"},
        }
        try:
            # 禁用 API key 测试模板模式
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
                path = proposer.generate_proposal(analysis, config, root)
            if path and path.exists():
                content = path.read_text()
                if "改进提案" in content and "backend-dev" in content:
                    PASS += 1
                    print("  ✅ proposer: 模板模式生成正确提案文件")
                else:
                    FAIL += 1
                    print("  ❌ proposer: 提案文件内容不完整")
            else:
                FAIL += 1
                print(f"  ❌ proposer: 未生成提案文件")
        except Exception as e:
            FAIL += 1
            print(f"  ❌ proposer: 异常 → {e}")


def test_proposer_no_hotspots_no_proposal():
    global PASS, FAIL
    proposer = get_module("proposer")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        analysis = {"total_sessions": 1, "correction_hotspots": {}, "primary_target": "x"}
        config = {"paths": {"proposals_dir": ".claude/proposals"}}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            path = proposer.generate_proposal(analysis, config, root)
        # 空 hotspots 可能返回空 Path
        if path == Path() or not path.exists():
            PASS += 1
            print("  ✅ proposer: 无热点时跳过提案")
        else:
            FAIL += 1
            print(f"  ❌ proposer: 无热点时应跳过，实际生成 {path}")


# ── 汇总 ────────────────────────────────────────────────────────────────────

def main():
    global PASS, FAIL
    print("=" * 60)
    print("evolve-daemon 单元测试套件")
    print("=" * 60)

    print("\n[analyzer]")
    test_analyzer_empty_sessions()
    test_analyzer_single_correction()
    test_analyzer_multi_session()
    test_analyzer_pattern_grouping()

    print("\n[daemon check_thresholds]")
    test_daemon_threshold_5_sessions()
    test_daemon_threshold_4_sessions_no_trigger()
    test_daemon_threshold_time_elapsed()
    test_daemon_threshold_pattern_group()

    print("\n[rollback]")
    test_rollback_keep_when_improved()
    test_rollback_rollback_on_degradation()
    test_rollback_observe_on_neutral()
    test_rollback_collect_metrics()

    print("\n[instinct_updater]")
    test_instinct_load_init()
    test_instinct_add_and_read()

    print("\n[lifecycle]")
    test_lifecycle_draft_to_verified()
    test_lifecycle_verified_to_proven()
    test_lifecycle_decay_proven()
    test_lifecycle_no_decay_recent()

    print("\n[proposer]")
    test_proposer_template_generates_file()
    test_proposer_no_hotspots_no_proposal()

    print(f"\n{'='*60}")
    print(f"结果: ✅ {PASS} / ❌ {FAIL}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())