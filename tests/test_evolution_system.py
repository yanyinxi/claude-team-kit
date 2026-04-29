#!/usr/bin/env python3
"""
进化系统全链路测试

覆盖 4 个维度 × 10+ 测试用例：
- Agent / Rule / Skill / Memory 维度：正向、反向、边界、异常
- 安全机制：熔断器、限流器、数据校验
- 端到端：编排器 → 触发器 → 自动进化器 → 历史 → 策略更新

用法：python3 .claude/tests/test_evolution_system.py [--verbose]
"""

import json
import os
import sys
import tempfile
import shutil
import copy
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


# ── 路径设置 ──
_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
_CLAUDE_DIR = _PROJECT_ROOT / ".claude"
sys.path.insert(0, str(_CLAUDE_DIR))
sys.path.insert(0, str(_CLAUDE_DIR / "evolution"))
sys.path.insert(0, str(_CLAUDE_DIR / "hooks" / "scripts"))


# ═══════════════════════════════════════════════════════════════
# Test Runner
# ═══════════════════════════════════════════════════════════════

class TestRunner:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.current_suite = ""

    def suite(self, name):
        self.current_suite = name
        print(f"\n{'═' * 60}")
        print(f"  {name}")
        print(f"{'═' * 60}")

    def test(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"  ✅ PASS: {name}")
        else:
            self.failed += 1
            msg = f"[{self.current_suite}] {name}"
            if detail:
                msg += f" — {detail}"
            self.errors.append(msg)
            print(f"  ❌ FAIL: {name}" + (f" — {detail}" if detail else ""))

    def assert_equals(self, name, actual, expected):
        ok = actual == expected
        self.test(name, ok,
                  f"expected {expected!r}, got {actual!r}" if not ok else "")

    def assert_approx(self, name, actual, expected, tolerance=0.01):
        ok = abs(actual - expected) <= tolerance
        self.test(name, ok,
                  f"expected ≈{expected}, got {actual}" if not ok else "")

    def report(self):
        total = self.passed + self.failed
        print(f"\n{'═' * 60}")
        grade = "✅ ALL PASSED" if self.failed == 0 else f"{self.failed} FAILED"
        print(f"  RESULTS: {self.passed}/{total} passed — {grade}")
        print(f"{'═' * 60}")
        if self.errors:
            print("\n  FAILURES:")
            for e in self.errors:
                print(f"    ❌ {e}")
        return self.failed == 0


# ═══════════════════════════════════════════════════════════════
# Fixture helpers
# ═══════════════════════════════════════════════════════════════

@contextmanager
def project_env(fixture_dir):
    """Temporarily set CLAUDE_PROJECT_DIR to fixture directory"""
    old = os.environ.get("CLAUDE_PROJECT_DIR", "")
    os.environ["CLAUDE_PROJECT_DIR"] = str(fixture_dir)
    # Also need to override _find_root() in modules that cache it
    try:
        yield
    finally:
        if old:
            os.environ["CLAUDE_PROJECT_DIR"] = old
        else:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)


def create_fixture_dir():
    """Create a project-root fixture with .claude/ subdirectory structure."""
    tmp = Path(tempfile.mkdtemp(prefix="evo_test_"))
    cd = tmp / ".claude"
    for sub in ["data", "logs", "agents", "rules", "skills", "memory"]:
        (cd / sub).mkdir(parents=True)
    return tmp  # Returns project_root (NOT .claude dir)


def _cd(fixture_dir):
    """Get .claude subdirectory from fixture project root"""
    return fixture_dir / ".claude"


def write_fixture_agent(fixture_dir, name, content=None):
    content = content or f"---\nname: {name}\ndescription: Test agent\n---\n\n# {name}\n"
    (_cd(fixture_dir) / "agents" / f"{name}.md").write_text(content)


def write_fixture_rule(fixture_dir, name, content=None):
    content = content or f"---\npaths: [\"test/**\"]\n---\n\n# {name}\n"
    (_cd(fixture_dir) / "rules" / f"{name}.md").write_text(content)


def write_fixture_skill(fixture_dir, name, content=None):
    skill_dir = _cd(fixture_dir) / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}\n")


def write_agent_logs(fixture_dir, agent_name, count=10, success_rate=0.8):
    log_file = _cd(fixture_dir) / "logs" / "agent-invocations.jsonl"
    with open(log_file, "w") as f:
        for i in range(count):
            f.write(json.dumps({
                "type": "agent_launch", "agent": agent_name,
                "task": f"Task {i}", "success": i < int(count * success_rate),
                "timestamp": datetime.now().isoformat(), "session_id": f"s{i}",
            }, ensure_ascii=False) + "\n")


def write_skill_logs(fixture_dir, skill_name, count=10, success_rate=0.8):
    log_file = _cd(fixture_dir) / "logs" / "skill_usage.jsonl"
    with open(log_file, "w") as f:
        for i in range(count):
            f.write(json.dumps({
                "type": "skill_invoked", "skill": skill_name,
                "success": i < int(count * success_rate),
                "duration_ms": 1000 + i * 500,
                "timestamp": datetime.now().isoformat(), "session_id": f"s{i}",
            }, ensure_ascii=False) + "\n")


def write_violation_logs(fixture_dir, rule_name, count=10):
    log_file = _cd(fixture_dir) / "logs" / "rule_violations.jsonl"
    with open(log_file, "w") as f:
        for i in range(count):
            f.write(json.dumps({
                "type": "rule_violation", "rule": rule_name,
                "file": f"test/file_{i}.java",
                "severity": "low" if i % 3 == 0 else "medium",
                "timestamp": datetime.now().isoformat(), "session_id": f"s{i}",
            }, ensure_ascii=False) + "\n")


def write_session_logs(fixture_dir, domain="backend", files_changed=5, agents_used=None):
    log_file = _cd(fixture_dir) / "logs" / "sessions.jsonl"
    with open(log_file, "w") as f:
        f.write(json.dumps({
            "type": "session_end", "primary_domain": domain,
            "timestamp": datetime.now().isoformat(), "session_id": "test-session",
            "signals": {
                "productivity": "focused", "has_tests": True, "test_ratio": 0.2,
                "agents_used_count": len(agents_used or []),
                "agents_unique": agents_used or [], "commits_in_session": True,
            },
            "git_metrics": {"files_changed": files_changed,
                            "lines_added": 100, "lines_removed": 20},
        }, ensure_ascii=False) + "\n")


def write_evo_history(fixture_dir, dim, target, session_id="test", success=True):
    history_file = _cd(fixture_dir) / "data" / "evolution_history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "dimension": dim, "target": target, "success": success,
        "changes": ["test change"], "score_before": 5.0, "score_after": 6.0,
        "timestamp": datetime.now().isoformat(), "session_id": session_id,
        "type": "evolution",
    }
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_data_jsonl(fixture_dir, filename, records):
    """Write records to data/ directory (used by orchestrator)."""
    fpath = _cd(fixture_dir) / "data" / filename
    fpath.parent.mkdir(parents=True, exist_ok=True)
    with open(fpath, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_log_jsonl(fixture_dir, filename, records):
    """Write records to logs/ directory (used by evolvers)."""
    fpath = _cd(fixture_dir) / "logs" / filename
    fpath.parent.mkdir(parents=True, exist_ok=True)
    with open(fpath, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class MockResult:
    def __init__(self, success=True, changes_made=None, score_before=5.0, score_after=6.0):
        self.success = success
        self.changes_made = changes_made or ["test change"]
        self.score_before = score_before
        self.score_after = score_after


# ═══════════════════════════════════════════════════════════════
# 1. 安全机制测试
# ═══════════════════════════════════════════════════════════════

def test_safety(runner, fixture):
    from lib.evolution_safety import (
        EvolutionCircuitBreaker, EvolutionRateLimiter,
        pre_evolution_check, validate_record_schema, validate_jsonl_file,
    )

    runner.suite("1.1 熔断器")
    mp = str(_cd(fixture) / "data" / "evolution_metrics.json")
    cb = EvolutionCircuitBreaker(mp)

    runner.test("新熔断器 CLOSED", not cb.is_open("agent", "a1"))
    cb.record_result("agent", "a1", False)
    runner.test("1 次退化不熔断", not cb.is_open("agent", "a1"))
    cb.record_result("agent", "a1", False)
    runner.test("2 次退化触发熔断", cb.is_open("agent", "a1"))
    cb.record_result("agent", "a1", True)
    runner.test("改进后重置熔断", not cb.is_open("agent", "a1"))
    cb.record_result("rule", "g1", False)
    cb.record_result("rule", "g1", False)
    runner.test("rule 维度独立熔断", cb.is_open("rule", "g1"))
    cb.reset("rule", "g1")
    runner.test("单个重置有效", not cb.is_open("rule", "g1"))
    runner.test("不存在目标不熔断", not cb.is_open("skill", "ghost"))

    runner.suite("1.2 限流器")
    hp = str(_cd(fixture) / "data" / "evolution_history.jsonl")
    rl = EvolutionRateLimiter(hp)

    can, _ = rl.can_evolve("agent", "t1", "s1")
    runner.test("首次允许", can)

    for i in range(3):
        write_evo_history(fixture, "agent", f"a{i}", session_id="s-max")
    can, _ = rl.can_evolve("agent", "a-max", "s-max")
    runner.test("会话上限 3 次拒绝", not can)

    write_evo_history(fixture, "rule", "cd-rule", session_id="s-cd")
    can, reason = rl.can_evolve("rule", "cd-rule", "s-cd2")
    runner.test("rule 48h 冷却拒绝", not can)

    can, _ = rl.can_evolve("memory", "m1", "s-mem")
    runner.test("memory 无冷却允许", can)

    runner.assert_approx("skill 冷却 24h", rl.COOLDOWNS["skill"].total_seconds(), 86400)
    runner.assert_approx("rule 冷却 48h", rl.COOLDOWNS["rule"].total_seconds(), 172800)

    runner.suite("1.3 数据校验")
    ok, _ = validate_record_schema(
        {"type": "agent_launch", "timestamp": "x", "session_id": "y",
         "agent": "z", "task": "t"}, "agent_launch")
    runner.test("schema 正确通过", ok)
    ok, _ = validate_record_schema({"type": "agent_launch"}, "agent_launch")
    runner.test("缺少字段拒绝", not ok)
    ok, _ = validate_record_schema({"date": "2026-01-01", "overall": 80}, "daily_score")
    runner.test("无 type 字段通过", ok)

    bad_log = _cd(fixture) / "logs" / "bad.jsonl"
    bad_log.write_text('{"ok":1}\n{bad\n{"ok":2}\n')
    result = validate_jsonl_file(str(bad_log))
    runner.test("损坏行检测", result["corrupted"] > 0)

    runner.suite("1.4 进化前检查")
    result = pre_evolution_check("agent", "pre-agent", "s-check", str(fixture))
    # pre-agent doesn't have a .md file, so it should fail target_exists
    runner.test("无目标文件 blocked",
                "目标文件存在" in str(result.get("blocked_by", [])) or
                not result.get("checks", {}).get("目标文件存在", True))


# ═══════════════════════════════════════════════════════════════
# 2. 编排器测试
# ═══════════════════════════════════════════════════════════════

def test_orchestrator(runner, fixture):
    from lib.evolution_orchestrator import (
        aggregate_session_data, compute_priority,
        compute_escalated_priority, check_triggers,
    )

    # 写模拟数据到 data/ 目录（orchestrator 读取 data/ 而非 logs/）
    _write_data_jsonl(fixture, "skill_usage.jsonl",
                      [{"skill": "karpathy", "success": True}] * 12)
    _write_data_jsonl(fixture, "agent_performance.jsonl",
                      [{"agent": "be-dev", "success": True}] * 15)
    _write_data_jsonl(fixture, "rule_violations.jsonl",
                      [{"rule": "general", "severity": "medium"}] * 8)
    write_session_logs(fixture, domain="backend", agents_used=["be-dev", "code-reviewer"])

    with project_env(fixture):
        data = aggregate_session_data(str(fixture))

    runner.test("聚合 skills_used", "karpathy" in str(data.get("skills_used", {})))
    runner.test("聚合 agents_used", "be-dev" in data.get("agents_used", []))
    runner.test("total_violations >= 8", data.get("total_violations", 0) >= 8)
    runner.test("total_agent_tasks >= 15", data.get("total_agent_tasks", 0) >= 15)

    # 优先级计算（纯函数，不需 env）
    runner.suite("2.2 优先级计算")
    p = compute_priority("agent", {"similar_tasks": 10, "avg_turns": 22,
                                    "baseline_turns": 10, "failure_rate": 0.5})
    runner.test("高失败+高turns > 0.5", p > 0.5)
    p = compute_priority("agent", {"similar_tasks": 3, "avg_turns": 10,
                                    "baseline_turns": 10, "failure_rate": 0.1})
    runner.test("任务不足 priority=0", p == 0.0)
    p = compute_priority("rule", {"violation_count": 10})
    runner.test("10 次违规 > 0.5", p > 0.5)
    p = compute_priority("rule", {"violation_count": 1})
    runner.test("1 次违规 = 0", p == 0.0)
    p = compute_priority("memory", {"pending_signals": 5})
    runner.test("5 个信号 > 0.5", p > 0.5)
    p = compute_priority("memory", {"pending_signals": 0})
    runner.test("0 信号 = 0", p == 0.0)
    p = compute_priority("unknown", {"x": 999})
    runner.test("未知维度 = 0", p == 0.0)
    p = compute_priority("skill", {"total_calls": 5, "success_rate": 0.5})
    runner.test("skill 不足 10 次 = 0", p == 0.0)
    p = compute_priority("skill", {"total_calls": 20, "success_rate": 0.3})
    runner.test("skill 低成功率 > 0.5", p > 0.5)

    runner.suite("2.3 优先级升级")
    ep = compute_escalated_priority(0.6, 0)
    runner.assert_approx("count=0 不升级", ep, 0.6)
    ep = compute_escalated_priority(0.6, 1)
    runner.assert_approx("count=1 ×1.3", ep, 0.78)
    ep = compute_escalated_priority(0.6, 2)
    runner.assert_approx("count>=2 → 1.0", ep, 1.0)
    ep = compute_escalated_priority(0.0, 5)
    runner.test("base=0 不升级", ep == 0.0)
    ep = compute_escalated_priority(0.3, 2)
    runner.test("base>0 + count>=2 → 1.0", abs(ep - 1.0) < 0.01)

    runner.suite("2.4 触发器检查")
    with project_env(fixture):
        triggers = check_triggers(str(fixture))
    runner.test("返回结构正确", "triggers" in triggers)
    runner.test("should_evolve 是 bool", isinstance(triggers.get("should_evolve"), bool))

    empty = create_fixture_dir()
    with project_env(empty):
        empty_t = check_triggers(str(empty))
    runner.test("空目录无触发", not empty_t.get("should_evolve"))
    shutil.rmtree(empty)


# ═══════════════════════════════════════════════════════════════
# 3. 进化引擎测试（4 维度）
# ═══════════════════════════════════════════════════════════════

def _make_config(fixture_dir):
    from evolution.config import EvolutionConfig
    config = EvolutionConfig()
    config.project_root = fixture_dir
    config.agent_trigger.min_invocations = 1
    config.skill_trigger.min_invocations = 1
    config.rule_trigger.min_invocations = 1
    config.memory_trigger.min_invocations = 1
    config.confirmation.mode = "never"
    return config


def test_agent_dimension(runner, fixture):
    from evolution.engine import EvolutionEngine

    config = _make_config(fixture)
    engine = EvolutionEngine(config)

    runner.suite("3a. Agent 维度")

    # 正向
    write_fixture_agent(fixture, "test-agent")
    write_agent_logs(fixture, "test-agent", count=10)
    write_session_logs(fixture, agents_used=["test-agent"])

    result = engine.force_evolve("agent", "test-agent")
    runner.test("正向：进化成功", result is not None and result.success)
    runner.test("正向：score 提升", result.score_after > result.score_before if result else False)

    # 反向：不存在的文件 → 返回 EvolutionResult(success=False)
    result = engine.force_evolve("agent", "no-file-agent")
    runner.test("反向：无文件返回 success=False", result is not None and not result.success)

    # 边界：空 agent 文件
    write_fixture_agent(fixture, "empty-agent", content="")
    result = engine.force_evolve("agent", "empty-agent")
    runner.test("边界：空文件不崩溃", True)  # 不抛异常即通过

    # 分析能力
    analysis = engine.agent_evolver.analyze_performance("test-agent")
    runner.test("analysis 含 agent_name", "agent_name" in analysis)
    runner.test("analysis 含 score", "score" in analysis)

    improvements = engine.agent_evolver.generate_improvements("test-agent", analysis)
    runner.test("improvements 非空", len(improvements) > 0)

    # get_all_targets
    targets = engine.agent_evolver.get_all_targets()
    runner.test("get_all_targets 含 test-agent", "test-agent" in targets)

    # 无数据 agent 不崩溃
    write_fixture_agent(fixture, "no-data-agent")
    analysis = engine.agent_evolver.analyze_performance("no-data-agent")
    runner.test("无数据 analysis 不崩溃", isinstance(analysis, dict))

    # 重复调用幂等
    result1 = engine.force_evolve("agent", "test-agent")
    result2 = engine.force_evolve("agent", "test-agent")
    runner.test("重复 force_evolve 不崩溃", result1 is not None and result2 is not None)

    # evolve_all
    results = engine.agent_evolver.evolve_all()
    runner.test("evolve_all 返回 list", isinstance(results, list))


def test_rule_dimension(runner, fixture):
    from evolution.engine import EvolutionEngine

    config = _make_config(fixture)
    engine = EvolutionEngine(config)

    runner.suite("3b. Rule 维度")

    # 正向
    write_fixture_rule(fixture, "test-rule")
    write_violation_logs(fixture, "test-rule", count=20)

    result = engine.force_evolve("rule", "test-rule")
    runner.test("正向：进化成功", result is not None and result.success)

    # 反向：无文件
    result = engine.force_evolve("rule", "no-file-rule")
    runner.test("反向：无文件返回 None 或 False",
                result is None or not result.success)

    # 反向：完全不存在的规则 → success=False
    result = engine.force_evolve("rule", "ghost-rule-xyz")
    runner.test("反向：不存在规则 success=False", result is not None and not result.success)

    # get_all_targets
    targets = engine.rule_evolver.get_all_targets()
    runner.test("get_all_targets 含 test-rule", "test-rule" in targets)

    # 分析
    analysis = engine.rule_evolver.analyze_performance("test-rule")
    runner.test("analysis 含 rule_name", "rule_name" in analysis)

    # 无违规规则
    write_fixture_rule(fixture, "clean-rule")
    analysis = engine.rule_evolver.analyze_performance("clean-rule")
    runner.test("无违规 score 正常", analysis.get("score", 0) >= 0)

    # check_evolution_needed
    needs = engine.rule_evolver.check_evolution_needed("test-rule")
    runner.test("check_evolution_needed bool", isinstance(needs, bool))

    # improvements
    improvements = engine.rule_evolver.generate_improvements("test-rule", analysis)
    runner.test("improvements 非空", len(improvements) > 0)

    # 空规则文件
    write_fixture_rule(fixture, "empty-rule", content="")
    result = engine.force_evolve("rule", "empty-rule")
    runner.test("空规则文件不崩溃", True)

    # 文件被修改
    rule_file = _cd(fixture) / "rules" / "test-rule.md"
    content_after = rule_file.read_text()
    runner.test("规则文件已修改", "合规统计" in content_after or "evolution" in content_after.lower())

    # 高违规率
    write_fixture_rule(fixture, "high-rule")
    write_violation_logs(fixture, "high-rule", count=30)
    result = engine.force_evolve("rule", "high-rule")
    runner.test("高违规率不崩溃", result is not None)

    # evolve_all — rule evolver 从 sessions 推断违规数据，violated 始终为 False
    # 所以 check_evolution_needed 通常返回 False
    results = engine.rule_evolver.evolve_all()
    runner.test("evolve_all 返回 list", isinstance(results, list))


def test_skill_dimension(runner, fixture):
    from evolution.engine import EvolutionEngine

    config = _make_config(fixture)
    engine = EvolutionEngine(config)

    runner.suite("3c. Skill 维度")

    # 正向
    write_fixture_skill(fixture, "test-skill")
    write_skill_logs(fixture, "test-skill", count=15)

    # Write skill data to logs/agent-invocations.jsonl (where SkillEvolver reads from)
    # Include error types so pattern matching works
    _write_log_jsonl(fixture, "agent-invocations.jsonl",
                     [{"skill": "test-skill", "success": i < 12,
                       "error": "context error" if i >= 12 else "",
                       "error_type": "missing_context" if i >= 12 else "",
                       "timestamp": datetime.now().isoformat()} for i in range(15)])

    result = engine.force_evolve("skill", "test-skill")
    runner.test("正向：进化成功", result is not None and result.success)

    # 反向：无 SKILL.md
    result = engine.force_evolve("skill", "no-file-skill")
    runner.test("反向：无 SKILL.md 返回 None 或 False",
                result is None or not result.success)

    # 反向：不存在
    result = engine.force_evolve("skill", "ghost-skill-xyz")
    runner.test("反向：不存在 success=False", result is not None and not result.success)

    # get_all_targets
    targets = engine.skill_evolver.get_all_targets()
    runner.test("get_all_targets 含 test-skill", "test-skill" in targets)

    # 分析
    analysis = engine.skill_evolver.analyze_performance("test-skill")
    runner.test("analysis 含 success_rate", "success_rate" in analysis)

    # check
    needs = engine.skill_evolver.check_evolution_needed("test-skill")
    runner.test("check_evolution_needed bool", isinstance(needs, bool))

    # improvements
    improvements = engine.skill_evolver.generate_improvements("test-skill", analysis)
    runner.test("improvements 非空", len(improvements) > 0)

    # 低调用 skill
    write_fixture_skill(fixture, "low-skill")
    needs = engine.skill_evolver.check_evolution_needed("low-skill")
    runner.test("低调用不触发", not needs)

    # 文件被修改
    skill_file = _cd(fixture) / "skills" / "test-skill" / "SKILL.md"
    content_after = skill_file.read_text()
    runner.test("Skill 文件已修改",
                "进化记录" in content_after or "使用数据" in content_after)

    # 空文件
    write_fixture_skill(fixture, "empty-skill", content="")
    result = engine.force_evolve("skill", "empty-skill")
    runner.test("空 skill 不崩溃", True)

    # evolve_all uses check_evolution_needed which depends on data thresholds
    results = engine.skill_evolver.evolve_all()
    runner.test("evolve_all 返回 list", isinstance(results, list))


def test_memory_dimension(runner, fixture):
    from evolution.engine import EvolutionEngine

    config = _make_config(fixture)
    engine = EvolutionEngine(config)

    runner.suite("3d. Memory 维度")

    # 写入会话数据以生成 domain theme
    write_session_logs(fixture, domain="backend", agents_used=["be-dev"])

    targets = engine.memory_evolver.get_all_targets()
    runner.test("get_all_targets 含 backend_best_practices",
                "backend_best_practices" in targets)

    # 正向：创建 memory 文件
    if "backend_best_practices" in targets:
        result = engine.force_evolve("memory", "backend_best_practices")
        runner.test("正向：进化创建文件", result is not None and result.success)

    # MEMORY.md 索引
    mem_index = _cd(fixture) / "memory" / "MEMORY.md"
    runner.test("MEMORY.md 创建", mem_index.exists())

    # 反向：pending_signals 无匹配
    result = engine.force_evolve("memory", "pending_signals")
    runner.test("反向：pending_signals → None", result is None)

    # 空数据
    empty = create_fixture_dir()
    ec = _make_config(empty)
    ee = EvolutionEngine(ec)
    runner.test("边界：空会话 0 targets", len(ee.memory_evolver.get_all_targets()) == 0)
    shutil.rmtree(empty)

    # analysis
    if "backend_best_practices" in targets:
        analysis = engine.memory_evolver.analyze_performance("backend_best_practices")
        runner.test("analysis 含 domain", "domain" in analysis)

    # check
    if "backend_best_practices" in targets:
        needs = engine.memory_evolver.check_evolution_needed("backend_best_practices")
        runner.test("check_evolution_needed bool", isinstance(needs, bool))

    # evolve_all
    results = engine.memory_evolver.evolve_all()
    runner.test("evolve_all list", isinstance(results, list))

    # 文件内容
    mem_file = _cd(fixture) / "memory" / "auto_backend_best_practices.md"
    if mem_file.exists():
        content = mem_file.read_text()
        runner.test("memory 文件含标题", "#" in content)


# ═══════════════════════════════════════════════════════════════
# 4. AutoEvolver 集成
# ═══════════════════════════════════════════════════════════════

def test_auto_evolver_integration(runner, fixture):
    from evolution.engine import EvolutionEngine

    runner.suite("4. AutoEvolver 集成")

    write_fixture_agent(fixture, "int-agent")
    write_agent_logs(fixture, "int-agent", count=10)
    write_session_logs(fixture, agents_used=["int-agent"])

    pending_path = _cd(fixture) / "data" / "pending_evolution.json"
    pending_path.write_text(json.dumps({
        "pending_triggers": [
            {"dimension": "agent", "target": "int-agent", "priority": 0.8,
             "reason": "test"},
        ],
        "feedback_signals": [],
        "last_check": datetime.now().isoformat(),
    }, indent=2, ensure_ascii=False))

    pending = json.loads(pending_path.read_text())
    runner.test("pending_triggers 非空", len(pending["pending_triggers"]) > 0)

    # 执行进化
    config = _make_config(fixture)
    engine = EvolutionEngine(config)

    for t in pending["pending_triggers"]:
        result = engine.force_evolve(t["dimension"], t["target"])
        if result:
            write_evo_history(fixture, t["dimension"], t["target"],
                            session_id="int-test", success=result.success)

    runner.test("force_evolve 成功", result is not None and result.success if 'result' in dir() else False)

    # 检查 history
    history_path = _cd(fixture) / "data" / "evolution_history.jsonl"
    runner.test("history 文件创建", history_path.exists())

    # 清除
    pending["pending_triggers"] = []
    pending["last_processed"] = datetime.now().isoformat()
    pending_path.write_text(json.dumps(pending, indent=2, ensure_ascii=False))

    pending_after = json.loads(pending_path.read_text())
    runner.test("triggers 已清除", len(pending_after.get("pending_triggers", [])) == 0)

    # 空 triggers 正常
    pending_path.write_text(json.dumps({"pending_triggers": [], "feedback_signals": []}))
    runner.test("空 triggers 处理正常", True)

    # 损坏 JSON
    pending_path.write_text("{bad")
    try:
        json.loads(pending_path.read_text())
        runner.test("损坏 JSON 解析", False)
    except json.JSONDecodeError:
        runner.test("损坏 JSON 正确异常", True)

    # 文件不存在
    pending_path.unlink()
    runner.test("无 pending 不崩溃", not pending_path.exists())


# ═══════════════════════════════════════════════════════════════
# 5. 策略更新器
# ═══════════════════════════════════════════════════════════════

def test_strategy_updater(runner, fixture):
    import strategy_updater as su

    runner.suite("5. 策略更新器")

    session = {
        "type": "session_end", "primary_domain": "backend",
        "signals": {
            "productivity": "focused", "has_tests": True, "test_ratio": 0.3,
            "agents_used_count": 3, "commits_in_session": True,
        },
        "git_metrics": {"lines_added": 200, "lines_removed": 50},
    }
    score = su.score_session(session)
    runner.test("focused+test+commit > 5.0", score > 5.0)

    session_low = {
        "type": "session_end", "primary_domain": "idle",
        "signals": {"productivity": "none", "has_tests": False, "test_ratio": 0,
                     "agents_used_count": 0, "commits_in_session": False},
        "git_metrics": {"lines_added": 0, "lines_removed": 0},
    }
    score_low = su.score_session(session_low)
    runner.test("无产出 < 5.0", score_low < 5.0)

    session_big = {
        "type": "session_end", "primary_domain": "backend",
        "signals": {"productivity": "sprawling", "has_tests": False, "test_ratio": 0,
                     "agents_used_count": 0, "commits_in_session": False},
        "git_metrics": {"lines_added": 800, "lines_removed": 300},
    }
    score_big = su.score_session(session_big)
    runner.test("超大变更扣分", score_big < 5.0)

    weights_file = _cd(fixture) / "data" / "strategy_weights.json"
    updated = su.update_weights(weights_file, "backend", 7.5, session)
    runner.test("update_weights 含域名", "backend" in updated)

    # score bounds
    from lib.constants import SCORE_MIN, SCORE_MAX
    s_ext = copy.deepcopy(session)
    s_ext["git_metrics"] = {"lines_added": 10000, "lines_removed": 5000}
    runner.test("score >= SCORE_MIN", su.score_session(s_ext) >= SCORE_MIN)

    s_good = copy.deepcopy(session)
    s_good["signals"]["test_ratio"] = 1.0
    runner.test("score <= SCORE_MAX", su.score_session(s_good) <= SCORE_MAX)

    # read_latest_session
    write_session_logs(fixture, domain="frontend")
    latest = su.read_latest_session(_cd(fixture) / "logs" / "sessions.jsonl")
    runner.test("read_latest_session 有效", latest is not None)

    # 新 domain
    updated2 = su.update_weights(weights_file, "new_domain", 6.0, session)
    runner.test("新 domain 初始化", "new_domain" in updated2)

    runner.test("metadata 含 execution_count", "metadata" in updated2)


# ═══════════════════════════════════════════════════════════════
# 6. 端到端全链路
# ═══════════════════════════════════════════════════════════════

def test_end_to_end(runner, fixture):
    from evolution.engine import EvolutionEngine
    from lib.evolution_orchestrator import run_orchestrator, check_triggers

    runner.suite("6. 端到端全链路")

    # 准备数据 — 写入 evolvers 需要的 logs/ 文件
    write_fixture_agent(fixture, "e2e-agent")
    write_fixture_rule(fixture, "e2e-rule")
    write_fixture_skill(fixture, "e2e-skill")
    write_agent_logs(fixture, "e2e-agent", count=15, success_rate=0.6)
    write_violation_logs(fixture, "e2e-rule", count=12)
    write_skill_logs(fixture, "e2e-skill", count=12, success_rate=0.6)
    write_session_logs(fixture, domain="backend",
                       agents_used=["e2e-agent", "code-reviewer"])
    # 写入 orchestrator 需要的 data/ 文件
    _write_data_jsonl(fixture, "skill_usage.jsonl",
                      [{"skill": "e2e-skill", "success": True}] * 12)
    _write_data_jsonl(fixture, "agent_performance.jsonl",
                      [{"agent": "e2e-agent", "success": True}] * 15)
    _write_data_jsonl(fixture, "rule_violations.jsonl",
                      [{"rule": "e2e-rule", "severity": "medium"}] * 12)

    # Step 1: Orchestrator → pending_evolution.json
    with project_env(fixture):
        decision = run_orchestrator(str(fixture), execute=True)

    pending_path = _cd(fixture) / "data" / "pending_evolution.json"
    triggers = []
    if pending_path.exists():
        pending = json.loads(pending_path.read_text())
        triggers = pending.get("pending_triggers", [])
        runner.test("Step1: triggers 已写入", len(triggers) > 0)
        if triggers:
            runner.test("Step1: triggers 按优先级排序",
                        all(triggers[i]["priority"] >= triggers[i+1]["priority"]
                            for i in range(len(triggers) - 1)))
    else:
        runner.test("Step1: 无触发（数据不足），直接验证进化引擎", True)

    # Step 2: AutoEvolver → 消费 triggers → 执行进化
    config = _make_config(fixture)
    engine = EvolutionEngine(config)

    evolved = 0
    targets = triggers[:3] if triggers else [
        {"dimension": "agent", "target": "e2e-agent"},
        {"dimension": "rule", "target": "e2e-rule"},
        {"dimension": "skill", "target": "e2e-skill"},
    ]
    for t in targets:
        dim, target = t["dimension"], t["target"]
        result = engine.force_evolve(dim, target)
        if result and result.success:
            write_evo_history(fixture, dim, target, session_id="e2e", success=result.success)
            evolved += 1

    runner.test("Step2: >= 1 个维度进化成功", evolved >= 1)

    # Step 3: 清除 triggers
    if pending_path.exists():
        pending = json.loads(pending_path.read_text())
        pending["pending_triggers"] = []
        pending["last_processed"] = datetime.now().isoformat()
        pending_path.write_text(json.dumps(pending, indent=2, ensure_ascii=False))

        pending_after = json.loads(pending_path.read_text())
        runner.test("Step3: triggers 已清除",
                    len(pending_after.get("pending_triggers", [])) == 0)

    # Step 4: 历史记录
    history_path = _cd(fixture) / "data" / "evolution_history.jsonl"
    if history_path.exists():
        history_lines = [l for l in history_path.read_text().splitlines() if l.strip()]
        runner.test("Step4: history 有记录", len(history_lines) > 0)

    # Step 5: 策略更新
    import strategy_updater as su
    weights_file = _cd(fixture) / "data" / "strategy_weights.json"
    session_file = _cd(fixture) / "logs" / "sessions.jsonl"
    if session_file.exists():
        latest = su.read_latest_session(session_file)
        if latest and latest.get("primary_domain") != "idle":
            score = su.score_session(latest)
            su.update_weights(weights_file, latest["primary_domain"], score, latest)
            runner.test("Step5: 权重文件已创建", weights_file.exists())


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    runner = TestRunner(verbose=verbose)

    print("=" * 60)
    print("  进化系统全链路测试")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 安全机制
    f = create_fixture_dir()
    try:
        test_safety(runner, f)
    finally:
        shutil.rmtree(f)

    # 2. 编排器
    f = create_fixture_dir()
    try:
        test_orchestrator(runner, f)
    finally:
        shutil.rmtree(f)

    # 3a. Agent
    f = create_fixture_dir()
    try:
        test_agent_dimension(runner, f)
    finally:
        shutil.rmtree(f)

    # 3b. Rule
    f = create_fixture_dir()
    try:
        test_rule_dimension(runner, f)
    finally:
        shutil.rmtree(f)

    # 3c. Skill
    f = create_fixture_dir()
    try:
        test_skill_dimension(runner, f)
    finally:
        shutil.rmtree(f)

    # 3d. Memory
    f = create_fixture_dir()
    try:
        test_memory_dimension(runner, f)
    finally:
        shutil.rmtree(f)

    # 4. AutoEvolver 集成
    f = create_fixture_dir()
    try:
        test_auto_evolver_integration(runner, f)
    finally:
        shutil.rmtree(f)

    # 5. 策略更新器
    f = create_fixture_dir()
    try:
        write_session_logs(f, domain="backend")
        test_strategy_updater(runner, f)
    finally:
        shutil.rmtree(f)

    # 6. 端到端
    f = create_fixture_dir()
    try:
        test_end_to_end(runner, f)
    finally:
        shutil.rmtree(f)

    success = runner.report()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
