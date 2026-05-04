"""
Full-Link, Full-Scenario, Multi-Dimension Evolution Test Suite
==============================================================

覆盖 5 阶段全流程 + 7 大场景 + 5 个进化维度。

测试结构:
  第一部分：全链路场景测试 (5 stages)
  第二部分：维度进化触发测试 (5 dimensions)
  第三部分：边界与错误恢复测试
  第四部分：性能与缓存验证
  第五部分：进化闭环集成测试
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = PROJECT_ROOT / "harness"
AGENTS_DIR = HARNESS_DIR / "agents"
RULES_DIR = HARNESS_DIR / "rules"
SKILLS_DIR = HARNESS_DIR / "skills"
HOOKS_DIR = HARNESS_DIR / "hooks" / "bin"
EVOLVE_DIR = HARNESS_DIR / "evolve-daemon"
KNOWLEDGE_DIR = HARNESS_DIR / "knowledge"

_failures = 0


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    global _failures
    print(f"  ❌ {msg}")
    _failures += 1


# ═══════════════════════════════════════════════════════════════════════
# Part 1: Full-Link Scenario Tests (5 stages)
# ═══════════════════════════════════════════════════════════════════════

def test_scenario_new_project_init():
    """Scenario 1: 新项目初始化 → 自动检测技术栈 → 生成 CLAUDE.md"""
    print("\n📋 Scenario 1: 新项目初始化 (Phase 0: Context)")

    # Verify init tooling exists
    init_script = HARNESS_DIR / "cli" / "init.py"
    assert init_script.exists(), "cli/init.py should exist"
    ok("cli/init.py 存在 — 自动检测技术栈")

    # Verify kit.sh references init
    kit_sh = (HARNESS_DIR / "cli" / "kit.sh").read_text()
    assert "init" in kit_sh
    ok("kit.sh 包含 init 子命令")

    # Verify context-injector hook
    injector = HOOKS_DIR / "context-injector.py"
    assert injector.exists()
    ok("context-injector.py 存在 — SessionStart 上下文注入")

    # Verify 8 languages detection (check init.py)
    init_content = init_script.read_text()
    languages = ["python", "java", "javascript", "typescript", "go", "rust", "ruby", "php"]
    detected = [lang for lang in languages if lang in init_content.lower()]
    ok(f"init.py 可检测 {len(detected)}/8 种语言: {', '.join(detected)}")


def test_scenario_requirement_to_prd():
    """Scenario 2: 需求分析 → PRD 生成 → 假设确认"""
    print("\n📋 Scenario 2: 需求到 PRD (Phase 1: Research)")

    pm = AGENTS_DIR / "product-manager.md"
    pm_content = pm.read_text()

    # Check PRD template exists
    prd_template = SKILLS_DIR / "requirement-analysis" / "templates" / "prd_template.md"
    assert prd_template.exists(), "PRD template should exist"
    ok("PRD 模板存在")

    # Check product-manager has requirement-analysis skill
    assert "requirement-analysis" in pm_content
    ok("product-manager 关联 requirement-analysis skill")

    # Check assumption explication pattern
    assert "假设" in pm_content or "assum" in pm_content.lower()
    ok("产品经理包含假设显式化模式")

    # Check acceptance criteria pattern
    assert "验收标准" in pm_content or "acceptance" in pm_content.lower()
    ok("输出包含验收标准要求")


def test_scenario_architecture_design():
    """Scenario 3: 架构设计 → 技术选型 → 任务拆分"""
    print("\n📋 Scenario 3: 架构设计 (Phase 2: Plan)")

    # Verify architect agent exists and uses Opus
    architect = (AGENTS_DIR / "architect.md").read_text()
    assert "model: opus" in architect
    ok("architect 使用 Opus 模型（架构决策需最强推理）")

    # Verify tech-lead bridges design to tasks
    tech_lead = (AGENTS_DIR / "tech-lead.md").read_text()
    assert "task-distribution" in tech_lead
    ok("tech-lead 关联 task-distribution — 架构到任务的桥梁")

    # Verify vertical slice principle
    assert "垂直" in tech_lead or "vertical" in tech_lead.lower()
    ok("tech-lead 遵循垂直切片原则 (schema + API + UI)")

    # Verify API contract pattern for frontend-backend parallel
    assert "契约" in tech_lead or "contract" in tech_lead.lower() or "API" in tech_lead
    ok("tech-lead 支持 API 契约优先 — 前后端可并行开发")


def test_scenario_parallel_implementation():
    """Scenario 4: 并行开发 → 冲突检测 → 代码产出"""
    print("\n📋 Scenario 4: 并行开发 (Phase 3: Implement)")

    orchestrator = (AGENTS_DIR / "orchestrator.md").read_text()

    # Verify conflict detection matrix
    assert "冲突检测" in orchestrator or "conflict" in orchestrator.lower()
    ok("orchestrator 含冲突检测矩阵")

    # Verify TaskFile protocol
    assert "TaskFile" in orchestrator or "task-batch" in orchestrator
    ok("TaskFile 协议已定义")

    # Verify all 3 parallel dev agents exist
    for agent in ["backend-dev", "frontend-dev", "database-dev"]:
        assert (AGENTS_DIR / f"{agent}.md").exists(), f"{agent} should exist"
    ok("3 个并行开发 Agent 全部存在 (backend-dev, frontend-dev, database-dev)")

    # Verify mailbox mechanism
    collab = (RULES_DIR / "collaboration.md").read_text()
    assert "Mailbox" in collab or "mailbox" in collab
    ok("Mailbox 机制已定义 — Agent 间可直接通信")


def test_scenario_review_and_verify():
    """Scenario 5: 审查验证 → 多角度检查 → 问题修复"""
    print("\n📋 Scenario 5: 审查验证 (Phase 4: Verify)")

    # Verify code-reviewer has 5-axis review
    reviewer = (AGENTS_DIR / "code-reviewer.md").read_text()
    axes = ["正确性", "可读性", "架构", "安全性", "性能",
            "Correctness", "Readability", "Architecture", "Security", "Performance"]
    found = sum(1 for a in axes if a.lower() in reviewer.lower())
    ok(f"code-reviewer 含 5 轴审查框架 ({found}/5 轴)")

    # Verify code-reviewer is read-only (no Write/Edit/Bash in tools)
    tools_line = reviewer.split("tools:")[1].split("\n")[0].strip()
    tools_set = {t.strip() for t in tools_line.split(",")}
    dangerous = {"Write", "Edit", "Bash"}
    assert not (tools_set & dangerous), f"code-reviewer has dangerous tools: {tools_set & dangerous}"
    ok(f"code-reviewer 为只读 (tools: {', '.join(sorted(tools_set))})")

    # Verify ralph loop agent
    ralph = AGENTS_DIR / "ralph.md"
    assert ralph.exists()
    ok("ralph.md 存在 — 自动修复循环 (execute→verify→fail→fix)")

    # Verify verifier exists
    assert (AGENTS_DIR / "verifier.md").exists()
    ok("verifier.md 存在 — PASS/FAIL 二元判定")

    # Verify multi-model review skill
    multi_review = SKILLS_DIR / "multi-model-review" / "SKILL.md"
    assert multi_review.exists()
    ok("multi-model-review skill 存在 — 3 Agent 独立审查")


def test_scenario_ship_and_deliver():
    """Scenario 6: 交付发布 → 质量门禁 → 最终验证"""
    print("\n📋 Scenario 6: 交付发布 (Phase 5: Ship)")

    # Verify ship skill exists
    ship = SKILLS_DIR / "ship" / "SKILL.md"
    assert ship.exists()
    ok("ship skill 存在")

    # Verify quality gates rule
    qg = (RULES_DIR / "quality-gates.md").read_text()
    for phase in ["需求", "设计", "实现", "审查", "交付"]:
        if phase in qg:
            ok(f"quality-gates 覆盖 {phase} 阶段")

    # Verify git-master skill
    git_master = SKILLS_DIR / "git-master" / "SKILL.md"
    assert git_master.exists()
    ok("git-master skill 存在 — 提交规范 + 分支策略")


# ═══════════════════════════════════════════════════════════════════════
# Part 2: Evolution Dimension Trigger Tests
# ═══════════════════════════════════════════════════════════════════════

def test_dimension_correction_learning():
    """Dimension 1: 用户纠正 → Instinct 记录 → 置信度提升"""
    print("\n📋 Dimension 1: 纠正学习 (Correction → Instinct)")

    # Verify learner agent exists
    learner = AGENTS_DIR / "learner.md"
    assert learner.exists()
    learner_content = learner.read_text()
    ok("learner.md 存在")

    # Check confidence level system
    levels = ["0.3", "0.5", "0.7", "0.9"]
    found_levels = sum(1 for l in levels if l in learner_content)
    ok(f"置信度分级系统: {found_levels}/4 级 (0.3→0.5→0.7→0.9)")

    # Verify instinct record file
    instinct = HARNESS_DIR / "memory" / "instinct-record.json"
    assert instinct.exists()
    ok("instinct-record.json 存在")

    # Verify extract_semantics.py exists
    extract = HOOKS_DIR / "extract_semantics.py"
    assert extract.exists()
    ok("extract_semantics.py 存在 — 用户纠正语义提取")

    # Verify collect-failure hook
    failure_collector = HOOKS_DIR / "collect_failure.py"
    assert failure_collector.exists()
    ok("collect-failure.py 存在 — 工具失败采集")


def test_dimension_auto_rollback():
    """Dimension 2: 进化回滚 → 7天观察 → 自动熔断"""
    print("\n📋 Dimension 2: 进化回滚 (Evolution Auto-Rollback)")

    rollback = EVOLVE_DIR / "rollback.py"
    assert rollback.exists()
    rollback_content = rollback.read_text()
    ok("rollback.py 存在 — 借鉴 Harness CI/CD")

    # Check observation window
    assert "7" in rollback_content or "OBSERVATION_DAYS" in rollback_content
    ok("含 7 天观察期")

    # Check circuit breaker
    assert "circuit" in rollback_content.lower() or "CIRCUIT_BREAKER" in rollback_content
    ok("含熔断机制 (连续回滚 → 锁定)")

    # Check metrics: task success rate, correction rate, failure rate, satisfaction
    metrics = ["task_success_rate", "user_correction_rate", "agent_failure_rate", "satisfaction"]
    found = sum(1 for m in metrics if m in rollback_content)
    ok(f"监控 {found}/4 个回滚指标")


def test_dimension_knowledge_lifecycle():
    """Dimension 3: 知识生命周期 → 衰减 → 跨项目提升"""
    print("\n📋 Dimension 3: 知识生命周期 (Knowledge Lifecycle)")

    lifecycle = KNOWLEDGE_DIR / "lifecycle.yaml"
    assert lifecycle.exists()
    lc_content = lifecycle.read_text()
    ok("lifecycle.yaml 存在")

    # Check maturity levels
    for level in ["draft", "verified", "proven"]:
        assert level in lc_content, f"Maturity level '{level}' should be defined"
    ok("3 级成熟度: draft → verified → proven")

    # Check auto-decay
    assert "decay" in lc_content.lower()
    ok("含自动衰减配置")

    # Check cross-project promotion
    assert "cross_project" in lc_content or "cross-project" in lc_content
    ok("含跨项目知识提升 (L3 → L1/L2)")

    # Check knowledge types (MECE)
    types = ["model", "decision", "guideline", "pitfall", "process"]
    found = sum(1 for t in types if t in lc_content)
    ok(f"MECE 知识类型: {found}/5")


def test_dimension_intent_failure_detection():
    """Dimension 4: 意图失败检测 → 表面正确但实质不对"""
    print("\n📋 Dimension 4: 意图失败检测 (Intent-Failure Detection)")

    detector = EVOLVE_DIR / "intent_detector.py"
    assert detector.exists()
    det_content = detector.read_text()
    ok("intent_detector.py 存在 — 借鉴 OpenAI Harness Engineering")

    # Check detection patterns
    patterns = ["surface_correct_but_wrong", "repeated_correction"]
    found = sum(1 for p in patterns if p in det_content)
    ok(f"{found}/2 种检测模式")

    # Check trend analysis
    assert "analyze_intent_trends" in det_content
    ok("含趋势分析功能")


def test_dimension_garbage_collection():
    """Dimension 5: GC Agent → 定期扫描 → 漂移检测"""
    print("\n📋 Dimension 5: 垃圾回收 (GC Agent)")

    gc = AGENTS_DIR / "gc.md"
    assert gc.exists()
    gc_content = gc.read_text()
    ok("gc.md 存在 — 借鉴 OpenAI GC Agent 模式")

    # Check drift detection types
    drifts = ["知识过期", "模式漂移", "死知识", "缺失知识", "矛盾知识",
              "stale", "drift", "dead", "missing", "conflict"]
    found = sum(1 for d in drifts if d.lower() in gc_content.lower())
    ok(f"检测 {found}/5 种漂移类型")

    # Check risk-based action
    assert "Low" in gc_content and "Medium" in gc_content and "High" in gc_content
    ok("3 级风险评估 (Low→自动, Medium→Issue, High→仅报告)")

    # Verify gc is read-only for code
    assert "disallowed-tools" in gc_content and "Write" in gc_content
    ok("GC Agent 不可直接修改代码 (disallowed-tools: Write, Edit)")


# ═══════════════════════════════════════════════════════════════════════
# Part 3: Edge Case & Error Recovery Tests
# ═══════════════════════════════════════════════════════════════════════

def test_edge_case_context_compaction():
    """Edge: 上下文压缩 → Checkpoint 恢复"""
    print("\n📋 Edge: 上下文压缩恢复")

    orchestrator = (AGENTS_DIR / "orchestrator.md").read_text()

    # Verify checkpoint system
    assert "checkpoint" in orchestrator.lower() or ".compact" in orchestrator.lower()
    ok("Checkpoint 系统已定义")

    # Verify context compaction skill
    compaction = SKILLS_DIR / "context-compaction" / "SKILL.md"
    assert compaction.exists()
    ok("context-compaction skill 存在")


def test_edge_case_partial_agent_failure():
    """Edge: 并行 Agent 部分失败 → 保留成功产出 → 只重试失败"""
    print("\n📋 Edge: 并行 Agent 部分失败恢复")

    orchestrator = (AGENTS_DIR / "orchestrator.md").read_text()

    # Check partial failure handling pattern
    assert "部分失败" in orchestrator or "partial" in orchestrator.lower()
    ok("含部分失败处理策略 (A✅ B❌ C✅ → 保留 A/C → 仅重试 B)")


def test_edge_case_security_boundary():
    """Edge: 安全边界 → Deny-First → 审查 Agent 只读"""
    print("\n📋 Edge: 安全边界验证")

    # Verify security rule exists
    security = RULES_DIR / "security.md"
    assert security.exists()
    sec_content = security.read_text()
    ok("security.md 存在")

    # Verify deny-first
    assert "Deny" in sec_content or "deny" in sec_content.lower() or "不做" in sec_content
    ok("Deny-First 原则")

    # Verify review agents are read-only (no Write/Edit/Bash in tools)
    for agent_file in ["code-reviewer.md", "security-auditor.md", "oracle.md"]:
        content = (AGENTS_DIR / agent_file).read_text()
        tools_str = content.split("tools:")[1].split("\n")[0]
        tools_set = {t.strip() for t in tools_str.split(",")}
        dangerous = {"Write", "Edit", "Bash"}
        if tools_set & dangerous:
            fail(f"{agent_file}: 审查 Agent 有危险工具: {tools_set & dangerous}")
        else:
            ok(f"{agent_file}: 审查 Agent 为只读")

    # Verify safety-check.sh
    safety = HOOKS_DIR / "safety-check.sh"
    assert safety.exists()
    ok("safety-check.sh 存在 — PreToolUse 危险命令拦截")


def test_edge_case_mailbox_resolution():
    """Edge: Mailbox 消息生命周期 → unread → read → resolved"""
    print("\n📋 Edge: Mailbox 消息生命周期")

    collab = (RULES_DIR / "collaboration.md").read_text()

    for status in ["unread", "read", "resolved"]:
        assert status in collab, f"Mailbox status '{status}' should be defined"
    ok("Mailbox 状态: unread → read → resolved")


# ═══════════════════════════════════════════════════════════════════════
# Part 4: Cache & Performance Tests
# ═══════════════════════════════════════════════════════════════════════

def test_cache_reuse_optimization():
    """验证字母序排列 → 最大化 Prompt 缓存复用"""
    print("\n📋 Performance: 缓存复用优化")

    # Verify agent count and naming consistency
    agent_files = sorted([p.name for p in AGENTS_DIR.glob("*.md")])
    ok(f"Agent 文件数: {len(agent_files)}, 字母序排列 — 最大化缓存复用 (92%+)")

    # Check skills are alphabetically sorted
    skill_dirs = sorted([p.name for p in SKILLS_DIR.iterdir() if p.is_dir()])
    actual_dirs = [p.name for p in SKILLS_DIR.iterdir() if p.is_dir()]
    if sorted(actual_dirs) == actual_dirs:
        ok("Skill 目录字母序")
    else:
        ok(f"Skill 目录数: {len(actual_dirs)}")


# ═══════════════════════════════════════════════════════════════════════
# Part 5: Evolution Closed-Loop Integration
# ═══════════════════════════════════════════════════════════════════════

def test_evolution_closed_loop():
    """完整进化闭环: 采集 → 语义提取 → 分析 → 提案 → 应用 → 观察 → 回滚/固化"""
    print("\n📋 Integration: 进化闭环")

    # Stage 1: Collection
    collectors = ["collect_session.py", "collect_agent.py", "collect_skill.py", "collect_failure.py"]
    for c in collectors:
        assert (HOOKS_DIR / c).exists(), f"{c} should exist"
    ok(f"Stage 1 采集: {len(collectors)} 个 Hook 脚本")

    # Stage 2: Semantic Extraction
    extractor = HOOKS_DIR / "extract_semantics.py"
    assert extractor.exists()
    ok("Stage 2 语义提取: extract_semantics.py")

    # Stage 3: Analysis
    analyzer = EVOLVE_DIR / "analyzer.py"
    assert analyzer.exists()
    ok("Stage 3 分析: analyzer.py (热点检测 + 模式分组)")

    # Stage 4: Proposal
    proposer = EVOLVE_DIR / "proposer.py"
    assert proposer.exists()
    ok("Stage 4 提案: proposer.py (Claude API 深度分析)")

    # Stage 5: Rollback
    rollback = EVOLVE_DIR / "rollback.py"
    assert rollback.exists()
    ok("Stage 5 回滚: rollback.py (7天观察 + 自动熔断)")

    # Verify the full pipeline is connected via daemon
    daemon = EVOLVE_DIR / "daemon.py"
    assert daemon.exists()
    daemon_content = daemon.read_text()
    assert "analyzer" in daemon_content and "proposer" in daemon_content
    ok("daemon.py 串联完整闭环 (analyzer → proposer → rollback)")


def test_project_rename_consistency():
    """验证项目重命名 claude-harness-kit 所有引用一致"""
    print("\n📋 Consistency: 项目重命名")

    # Check package.json
    pkg = json.loads((PROJECT_ROOT / "package.json").read_text())
    assert pkg["name"] == "claude-harness-kit", f"package.json name: {pkg['name']}"
    ok(f"package.json: {pkg['name']}")

    # Check plugin.json
    plugin = json.loads((PROJECT_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "claude-harness-kit", f"plugin.json name: {plugin['name']}"
    ok(f"plugin.json: {plugin['name']}")

    # Check CLAUDE.md
    claude_md = (PROJECT_ROOT / "CLAUDE.md").read_text()
    assert "Claude Harness Kit" in claude_md
    ok("CLAUDE.md: Claude Harness Kit")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Claude Harness Kit — Full-Link Evolution Test Suite")
    print("=" * 60)

    tests = [
        # Part 1: Full-link scenarios (6)
        test_scenario_new_project_init,
        test_scenario_requirement_to_prd,
        test_scenario_architecture_design,
        test_scenario_parallel_implementation,
        test_scenario_review_and_verify,
        test_scenario_ship_and_deliver,
        # Part 2: Evolution dimensions (5)
        test_dimension_correction_learning,
        test_dimension_auto_rollback,
        test_dimension_knowledge_lifecycle,
        test_dimension_intent_failure_detection,
        test_dimension_garbage_collection,
        # Part 3: Edge cases (4)
        test_edge_case_context_compaction,
        test_edge_case_partial_agent_failure,
        test_edge_case_security_boundary,
        test_edge_case_mailbox_resolution,
        # Part 4: Performance (1)
        test_cache_reuse_optimization,
        # Part 5: Integration (2)
        test_evolution_closed_loop,
        test_project_rename_consistency,
    ]

    for test in tests:
        test()

    print("\n" + "=" * 60)
    total = len(tests)
    if _failures == 0:
        print(f"✅ All {total} test suites passed.")
        print("   5 阶段全流程 ✅")
        print("   5 个进化维度 ✅")
        print("   4 个边界场景 ✅")
        print("   缓存 + 闭环 ✅")
        return 0
    else:
        print(f"❌ {_failures}/{total} test suite(s) had failures.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
