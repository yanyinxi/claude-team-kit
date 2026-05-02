#!/usr/bin/env python3
"""
进化触发条件全覆盖测试 — daemon.py + analyzer.py + proposer.py + rollback.py

覆盖:
  - 正向: ≥5 sessions / ≥3 corrections / ≥6h interval 触发
  - 边界: 4 sessions / 2 corrections / 5:59h 不触发
  - 异常: 空 sessions / 损坏 JSONL / 缺失 config 字段
  - 组合: 多条件同时满足
  - 全链路: sessions → analyze → propose → rollback
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "evolve-daemon"))

from daemon import check_thresholds, load_new_sessions, load_config
from analyzer import aggregate_and_analyze
from proposer import generate_proposal, _generate_from_template, _save_proposal
from rollback import evaluate_proposal, collect_metrics

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


def make_session(session_id, corrections=None, tool_failures=0, skills_used=None,
                 status="success", timestamp=None, correction_count=0, satisfaction=None):
    """Helper: create a session record matching collect_session.py output schema."""
    s = {
        "session_id": session_id,
        "timestamp": timestamp or datetime.now().isoformat(),
        "status": status,
        "mode": "solo",
        "duration_minutes": 15,
        "corrections": corrections or [],
        "correction_count": correction_count,
        "tool_failures": tool_failures,
        "skills_used": skills_used or [],
        "failure_count": 0,
    }
    if satisfaction is not None:
        s["satisfaction"] = satisfaction
    return s


def make_correction(target, root_cause_hint="unknown", context="", user_correction=""):
    """Helper: create a correction record."""
    return {
        "target": target,
        "root_cause_hint": root_cause_hint,
        "context": context,
        "correction": user_correction,
    }


# ═══════════════════════════════════════════════════════════════════════
# Part 1: Trigger Condition Tests (check_thresholds)
# ═══════════════════════════════════════════════════════════════════════

def test_trigger_new_sessions():
    """正向：≥5 新会话触发"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [make_session(f"s{i}") for i in range(5)]
    triggers = check_thresholds(sessions, config, last_analyze_time=datetime.now())
    assert any("new_sessions" in t for t in triggers), f"Expected new_sessions trigger, got {triggers}"
    ok("≥5 新会话 → 触发 new_sessions")


def test_no_trigger_below_threshold():
    """边界：4 个会话不触发"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [make_session(f"s{i}") for i in range(4)]
    triggers = check_thresholds(sessions, config, last_analyze_time=datetime.now())
    assert len(triggers) == 0, f"Expected no triggers, got {triggers}"
    ok("4 个会话 → 不触发（边界）")


def test_trigger_time_elapsed():
    """正向：距上次分析 ≥6h 触发"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [make_session("s1")]
    # Simulate last analysis 7 hours ago
    last_time = datetime.now() - timedelta(hours=7)
    triggers = check_thresholds(sessions, config, last_analyze_time=last_time)
    assert any("time_elapsed" in t for t in triggers), f"Expected time_elapsed trigger, got {triggers}"
    ok("距上次分析 ≥6h → 触发 time_elapsed")


def test_no_trigger_time_below_threshold():
    """边界：5 小时 59 分不触发"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [make_session("s1")]
    last_time = datetime.now() - timedelta(hours=5, minutes=59)
    triggers = check_thresholds(sessions, config, last_analyze_time=last_time)
    assert len(triggers) == 0, f"Expected no triggers, got {triggers}"
    ok("距上次分析 5:59h → 不触发（边界）")


def test_trigger_correction_pattern():
    """正向：同一 target 被纠正 ≥3 次触发"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [
        make_session("s1", corrections=[
            make_correction("code-reviewer", "missed_security_issue", "review PR", "check OWASP top 10")
        ]),
        make_session("s2", corrections=[
            make_correction("code-reviewer", "missed_security_issue", "review API", "scan for injection")
        ]),
        make_session("s3", corrections=[
            make_correction("code-reviewer", "missed_security_issue", "review auth", "check auth bypass")
        ]),
    ]
    triggers = check_thresholds(sessions, config, last_analyze_time=datetime.now())
    assert any("pattern" in t and "code-reviewer" in t for t in triggers), \
        f"Expected pattern trigger for code-reviewer, got {triggers}"
    ok("同一 target 被纠正 ≥3 次 → 触发 pattern")


def test_no_trigger_2_corrections():
    """边界：2 次纠正不触发"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [
        make_session("s1", corrections=[make_correction("backend-dev", "bad_api_design")]),
        make_session("s2", corrections=[make_correction("backend-dev", "bad_api_design")]),
    ]
    triggers = check_thresholds(sessions, config, last_analyze_time=datetime.now())
    assert len(triggers) == 0, f"Expected no triggers, got {triggers}"
    ok("2 次纠正 → 不触发（边界）")


def test_trigger_all_conditions():
    """正向：三个条件同时满足"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [make_session(f"s{i}") for i in range(8)]
    sessions[0]["corrections"] = [make_correction("skill-xyz", "pattern_a") for _ in range(3)]
    sessions[1]["corrections"] = [make_correction("skill-xyz", "pattern_a") for _ in range(2)]
    sessions[2]["corrections"] = [make_correction("skill-xyz", "pattern_a") for _ in range(1)]
    last_time = datetime.now() - timedelta(hours=8)
    triggers = check_thresholds(sessions, config, last_analyze_time=last_time)
    assert len(triggers) >= 2, f"Expected ≥2 triggers, got {len(triggers)}: {triggers}"
    ok(f"三条件同时满足 → {len(triggers)} 个触发条件")


def test_no_trigger_last_analyze_none():
    """边界：last_analyze_time 为 None 不触发 time_elapsed"""
    config = {"thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                              "max_hours_since_last_analyze": 6}}
    sessions = [make_session("s1")]
    triggers = check_thresholds(sessions, config, last_analyze_time=None)
    assert not any("time_elapsed" in t for t in triggers), \
        f"Should not trigger time_elapsed when no previous analysis, got {triggers}"
    ok("None last_analyze_time → 不触发 time_elapsed")


# ═══════════════════════════════════════════════════════════════════════
# Part 2: Analyzer Tests (aggregate_and_analyze)
# ═══════════════════════════════════════════════════════════════════════

def test_analyzer_correction_hotspots():
    """正向：纠正热点检测"""
    config = {"safety": {"max_proposals_per_day": 3}}
    sessions = [
        make_session("s1", corrections=[
            make_correction("code-reviewer", "missed_bug"),
            make_correction("backend-dev", "bad_design"),
        ]),
        make_session("s2", corrections=[
            make_correction("code-reviewer", "missed_bug"),
        ]),
    ]
    analysis = aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    hotspots = analysis["correction_hotspots"]
    assert hotspots.get("code-reviewer", 0) == 2, f"Expected 2, got {hotspots.get('code-reviewer', 0)}"
    assert hotspots.get("backend-dev", 0) == 1, f"Expected 1, got {hotspots.get('backend-dev', 0)}"
    ok(f"纠正热点: {hotspots}")


def test_analyzer_tool_failures():
    """正向：工具失败统计"""
    config = {"safety": {"max_proposals_per_day": 3}}
    sessions = [
        make_session("s1", tool_failures=[
            {"tool": "Bash", "error": "command not found"},
            {"tool": "Bash", "error": "permission denied"},
            {"tool": "Write", "error": "read-only file system"},
        ]),
    ]
    analysis = aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    assert analysis["tool_failures"].get("Bash", 0) == 2
    assert analysis["tool_failures"].get("Write", 0) == 1
    ok(f"工具失败统计: {analysis['tool_failures']}")


def test_analyzer_skill_override_rate():
    """正向：技能覆盖率和覆写率"""
    config = {"safety": {"max_proposals_per_day": 3}}
    sessions = [
        make_session("s1", skills_used=[
            {"skill": "testing", "user_overrode": False},
            {"skill": "testing", "user_overrode": True},
        ]),
        make_session("s2", skills_used=[
            {"skill": "testing", "user_overrode": False},
            {"skill": "code-quality", "user_overrode": False},
        ]),
    ]
    analysis = aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    assert analysis["skill_usage"]["testing"] == 3
    assert analysis["skill_override_rate"] > 0.2
    ok(f"技能覆写率: {analysis['skill_override_rate']}, usage: {analysis['skill_usage']}")


def test_analyzer_empty_sessions():
    """边界：空会话列表"""
    config = {"safety": {"max_proposals_per_day": 3}}
    analysis = aggregate_and_analyze([], config, PROJECT_ROOT)
    assert analysis["total_sessions"] == 0
    assert analysis["should_propose"] is False
    ok("空会话列表 → should_propose=False")


def test_analyzer_no_corrections():
    """边界：有会话但无纠正"""
    config = {"safety": {"max_proposals_per_day": 3}}
    sessions = [make_session(f"s{i}") for i in range(10)]
    analysis = aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    assert analysis["total_sessions"] == 10
    assert analysis["should_propose"] is False
    ok("10 会话无纠正 → should_propose=False")


def test_analyzer_malformed_session():
    """异常：损坏的会话数据"""
    config = {"safety": {"max_proposals_per_day": 3}}
    # Session with unexpected types
    sessions = [
        make_session("s1", corrections=[
            make_correction("target1", "hint1"),
            None,  # Simulate corrupted entry
            make_correction("target1", "hint2"),
        ]),
    ]
    try:
        analysis = aggregate_and_analyze(sessions, config, PROJECT_ROOT)
        ok(f"损坏会话数据不崩溃 (hotspots: {analysis['correction_hotspots']})")
    except Exception as e:
        fail(f"损坏会话数据不应导致崩溃: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Part 3: Proposer Tests (generate_proposal / template mode)
# ═══════════════════════════════════════════════════════════════════════

def test_proposer_template_mode_generates():
    """正向：模板模式生成提案"""
    config = {
        "paths": {"proposals_dir": ".claude/proposals"},
        "safety": {"max_proposals_per_day": 3},
    }
    analysis = {
        "total_sessions": 5,
        "correction_hotspots": {"code-reviewer": 5, "backend-dev": 3},
        "correction_patterns": {
            "code-reviewer:missed_security": {
                "count": 3,
                "examples": [
                    {"context": "review login", "correction": "check OWASP"},
                    {"context": "review API", "correction": "scan SQL injection"},
                ],
            }
        },
        "tool_failures": {"Bash": 2},
        "skill_usage": {"testing": 10},
        "skill_override_rate": 0.15,
        "primary_target": "code-reviewer",
        "should_propose": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        proposals_dir = tmp_root / ".claude" / "proposals"
        config["paths"]["proposals_dir"] = str(proposals_dir)
        result = _generate_from_template(analysis, config, tmp_root)
        assert result.suffix == ".md"
        assert result.exists()
        content = result.read_text()
        assert "code-reviewer" in content
        assert "5 个会话" in content or "5" in content
        ok(f"模板提案生成: {result.name} ({len(content)} chars)")


def test_proposer_no_hotspots():
    """边界：无热点不生成提案"""
    config = {
        "paths": {"proposals_dir": ".claude/proposals"},
        "safety": {"max_proposals_per_day": 3},
    }
    analysis = {
        "total_sessions": 0,
        "correction_hotspots": {},
        "correction_patterns": {},
        "primary_target": "general",
        "should_propose": False,
    }
    result = _generate_from_template(analysis, config, PROJECT_ROOT)
    assert result == Path() or not str(result)
    ok("无纠正热点 → 不生成提案")


def test_proposer_save_with_special_chars():
    """边界：target 含特殊字符正确处理"""
    config = {"paths": {"proposals_dir": ".claude/proposals"}}
    analysis = {
        "total_sessions": 3,
        "correction_hotspots": {"agent/sub:pattern": 3},
        "correction_patterns": {},
        "primary_target": "agent/sub:pattern",
        "should_propose": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        proposals_dir = tmp_root / ".claude" / "proposals"
        config["paths"]["proposals_dir"] = str(proposals_dir)
        result = _generate_from_template(analysis, config, tmp_root)
        assert result.exists()
        # Should replace / and : for safe filename
        assert "/" not in result.name
        assert ":" not in result.name
        ok(f"特殊字符文件名处理: {result.name}")


# ═══════════════════════════════════════════════════════════════════════
# Part 4: Rollback Tests (evaluate_proposal)
# ═══════════════════════════════════════════════════════════════════════

def test_rollback_keep_good_metrics():
    """正向：指标改善 → keep"""
    proposal = {"id": "test-1"}
    baseline = {"task_success_rate": 0.8, "user_correction_rate": 0.2,
                "agent_failure_rate": 0.1, "satisfaction_score": 3.5}
    metrics = {"task_success_rate": 0.9, "user_correction_rate": 0.1,
               "agent_failure_rate": 0.05, "satisfaction_score": 4.2}
    decision = evaluate_proposal(proposal, metrics, baseline)
    assert decision == "keep", f"Expected keep, got {decision}"
    ok("指标改善 → keep")


def test_rollback_degraded_success_rate():
    """异常：任务成功率下降 >10% → rollback"""
    proposal = {"id": "test-2"}
    baseline = {"task_success_rate": 0.9, "user_correction_rate": 0.1,
                "agent_failure_rate": 0.05, "satisfaction_score": 4.0}
    metrics = {"task_success_rate": 0.7, "user_correction_rate": 0.12,
               "agent_failure_rate": 0.06, "satisfaction_score": 3.5}
    decision = evaluate_proposal(proposal, metrics, baseline)
    assert decision == "rollback", f"Expected rollback, got {decision}"
    ok("任务成功率下降 22% → rollback")


def test_rollback_low_satisfaction():
    """异常：满意度 <3.0 → rollback"""
    proposal = {"id": "test-3"}
    baseline = {"task_success_rate": 0.85, "user_correction_rate": 0.15,
                "agent_failure_rate": 0.08, "satisfaction_score": 4.0}
    metrics = {"task_success_rate": 0.86, "user_correction_rate": 0.14,
               "agent_failure_rate": 0.07, "satisfaction_score": 2.1}
    decision = evaluate_proposal(proposal, metrics, baseline)
    assert decision == "rollback", f"Expected rollback, got {decision}"
    ok("满意度 2.1/5 → rollback")


def test_rollback_observe_no_change():
    """边界：指标无变化 → observe"""
    proposal = {"id": "test-4"}
    baseline = {"task_success_rate": 0.85, "user_correction_rate": 0.15,
                "agent_failure_rate": 0.08, "satisfaction_score": 3.5}
    metrics = {"task_success_rate": 0.85, "user_correction_rate": 0.15,
               "agent_failure_rate": 0.08, "satisfaction_score": 3.5}
    decision = evaluate_proposal(proposal, metrics, baseline)
    assert decision == "observe", f"Expected observe, got {decision}"
    ok("指标无变化 → observe")


def test_rollback_missing_baseline():
    """边界：缺少 baseline 指标"""
    proposal = {"id": "test-5"}
    baseline = {}
    metrics = {"task_success_rate": 0.5, "user_correction_rate": 0.5,
               "agent_failure_rate": 0.5, "satisfaction_score": 2.0}
    decision = evaluate_proposal(proposal, metrics, baseline)
    # Should not crash; just evaluate with safe defaults
    assert decision in ("keep", "observe", "rollback")
    ok(f"缺失 baseline → 不崩溃 (decision={decision})")


# ═══════════════════════════════════════════════════════════════════════
# Part 5: Config Loading (with and without yaml)
# ═══════════════════════════════════════════════════════════════════════

def test_load_config_fallback():
    """边界：无 PyYAML 时使用 fallback 配置"""
    # Simulate yaml not available by directly testing the fallback
    import daemon as dm
    if dm.yaml is None:
        config = dm.load_config()
    else:
        # Temporarily hide yaml
        saved_yaml = dm.yaml
        dm.yaml = None
        try:
            config = dm.load_config()
        finally:
            dm.yaml = saved_yaml
    assert "thresholds" in config
    assert config["thresholds"]["min_new_sessions"] == 5
    assert config["thresholds"]["min_same_pattern_corrections"] == 3
    assert config["thresholds"]["max_hours_since_last_analyze"] == 6
    ok("Fallback 配置加载成功（无 PyYAML）")


# ═══════════════════════════════════════════════════════════════════════
# Part 6: load_new_sessions Tests
# ═══════════════════════════════════════════════════════════════════════

def test_load_sessions_with_corrupt_lines():
    """异常：session 文件中包含损坏行"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_file = tmp_dir / "sessions.jsonl"
        # Mix valid and corrupt lines
        data_file.write_text('\n'.join([
            json.dumps(make_session("s1")),
            'this is not json',
            json.dumps(make_session("s2")),
            '',
            'also bad {json',
            json.dumps(make_session("s3")),
        ]))
        sessions = load_new_sessions(tmp_dir, last_analyzed_id=None)
        assert len(sessions) == 3, f"Expected 3 valid sessions, got {len(sessions)}"
        ok("混合损坏行的 JSONL → 正确跳过损坏行，读取 3 个有效会话")


def test_load_sessions_with_last_id():
    """正向：从指定 session_id 之后加载"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_file = tmp_dir / "sessions.jsonl"
        sessions_data = [make_session(f"s{i}") for i in range(7)]
        data_file.write_text('\n'.join(json.dumps(s) for s in sessions_data))
        new = load_new_sessions(tmp_dir, last_analyzed_id="s3")
        # Should be s4, s5, s6 (3 sessions)
        assert len(new) == 3, f"Expected 3 new sessions after s3, got {len(new)}"
        ok("增量加载：last_id=s3 → 返回 3 个新会话")


def test_load_sessions_missing_file():
    """边界：session 文件不存在"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        sessions = load_new_sessions(tmp_dir, last_analyzed_id=None)
        assert sessions == []
        ok("不存在的 sessions.jsonl → 返回空列表")


# ═══════════════════════════════════════════════════════════════════════
# Part 7: Full Pipeline Integration (end-to-end without API)
# ═══════════════════════════════════════════════════════════════════════

def test_full_pipeline_without_api():
    """全链路集成测试：sessions → analyze → propose (template) → dry-run rollback"""
    config = {
        "thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3,
                       "max_hours_since_last_analyze": 6},
        "safety": {"max_proposals_per_day": 3},
        "paths": {"proposals_dir": ".claude/proposals"},
    }
    sessions = []
    for i in range(8):
        s = make_session(f"s{i}")
        if i < 4:
            s["corrections"] = [make_correction("code-reviewer", "missed_security",
                                                f"review PR #{i}", "check OWASP")]
        s["skills_used"] = [{"skill": "testing", "user_overrode": i % 3 == 0}]
        s["tool_failures"] = [{"tool": "Bash", "error": "timeout"}] if i % 4 == 0 else 0
        sessions.append(s)

    # Step 1: Check triggers
    last_time = datetime.now() - timedelta(hours=10)
    triggers = check_thresholds(sessions, config, last_analyze_time=last_time)
    assert len(triggers) >= 2, f"Pipeline step 1 fail: expected ≥2 triggers, got {triggers}"
    ok(f"Pipeline Step 1: 触发条件检测 → {len(triggers)} 个触发")

    # Step 2: Analyze
    analysis = aggregate_and_analyze(sessions, config, PROJECT_ROOT)
    assert analysis["total_sessions"] == 8
    assert analysis["should_propose"] is True
    ok(f"Pipeline Step 2: 分析完成 → {analysis['correction_hotspots']}")

    # Step 3: Generate proposal (template mode, no API key needed)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        proposals_dir = tmp_root / ".claude" / "proposals"
        config["paths"]["proposals_dir"] = str(proposals_dir)
        proposal_path = _generate_from_template(analysis, config, tmp_root)
        assert proposal_path.exists()
        content = proposal_path.read_text()
        assert "code-reviewer" in content
        ok(f"Pipeline Step 3: 提案生成 → {proposal_path.name}")

        # Step 4: Simulate rollback evaluation
        baseline = {"task_success_rate": 0.9, "user_correction_rate": 0.05,
                    "agent_failure_rate": 0.03, "satisfaction_score": 4.5}
        good_metrics = {"task_success_rate": 0.92, "user_correction_rate": 0.03,
                        "agent_failure_rate": 0.02, "satisfaction_score": 4.8}
        decision = evaluate_proposal({"id": "pipeline-test"}, good_metrics, baseline)
        assert decision == "keep"
        ok("Pipeline Step 4: 回滚评估 → keep（指标改善）")

        bad_metrics = {"task_success_rate": 0.6, "user_correction_rate": 0.3,
                       "agent_failure_rate": 0.15, "satisfaction_score": 2.0}
        decision = evaluate_proposal({"id": "pipeline-test"}, bad_metrics, baseline)
        assert decision == "rollback"
        ok("Pipeline Step 5: 回滚评估 → rollback（指标恶化）")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    global PASS, FAIL
    PASS = 0
    FAIL = 0

    print("=" * 60)
    print("Evolution Trigger & Pipeline — Full Coverage Test Suite")
    print("=" * 60)

    tests = [
        # Part 1: Trigger conditions
        ("正向: ≥5 新会话触发", test_trigger_new_sessions),
        ("边界: 4 会话不触发", test_no_trigger_below_threshold),
        ("正向: ≥6h 时间间隔触发", test_trigger_time_elapsed),
        ("边界: 5:59h 不触发", test_no_trigger_time_below_threshold),
        ("正向: ≥3 同模式纠正触发", test_trigger_correction_pattern),
        ("边界: 2 次纠正不触发", test_no_trigger_2_corrections),
        ("正向: 三条件同时满足", test_trigger_all_conditions),
        ("边界: None last_analyze_time", test_no_trigger_last_analyze_none),
        # Part 2: Analyzer
        ("正向: 纠正热点检测", test_analyzer_correction_hotspots),
        ("正向: 工具失败统计", test_analyzer_tool_failures),
        ("正向: 技能覆写率", test_analyzer_skill_override_rate),
        ("边界: 空会话列表", test_analyzer_empty_sessions),
        ("边界: 有会话无纠正", test_analyzer_no_corrections),
        ("异常: 损坏会话数据", test_analyzer_malformed_session),
        # Part 3: Proposer
        ("正向: 模板模式生成提案", test_proposer_template_mode_generates),
        ("边界: 无热点不生成", test_proposer_no_hotspots),
        ("边界: 特殊字符文件名", test_proposer_save_with_special_chars),
        # Part 4: Rollback
        ("正向: 指标改善 → keep", test_rollback_keep_good_metrics),
        ("异常: 成功率下降 → rollback", test_rollback_degraded_success_rate),
        ("异常: 低满意度 → rollback", test_rollback_low_satisfaction),
        ("边界: 指标不变 → observe", test_rollback_observe_no_change),
        ("边界: 缺失 baseline", test_rollback_missing_baseline),
        # Part 5: Config
        ("边界: Fallback 配置加载", test_load_config_fallback),
        # Part 6: load_new_sessions
        ("异常: 损坏 JSONL 行", test_load_sessions_with_corrupt_lines),
        ("正向: 增量加载会话", test_load_sessions_with_last_id),
        ("边界: 文件不存在", test_load_sessions_missing_file),
        # Part 7: Full Pipeline
        ("全链路: sessions → analyze → propose → rollback", test_full_pipeline_without_api),
    ]

    for name, test_fn in tests:
        print(f"\n📋 {name}")
        try:
            test_fn()
        except AssertionError as e:
            fail(str(e))
        except Exception as e:
            fail(f"CRASH: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL}/{total} failed")
    if FAIL == 0:
        print("✅ All evolution trigger & pipeline tests passed.")
        print(f"   {total} 个测试覆盖: 正向+边界+异常+全链路")
    else:
        print(f"❌ {FAIL} tests FAILED")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
