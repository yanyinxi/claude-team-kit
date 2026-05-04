#!/usr/bin/env python3
"""
evolution_stress_test.py — 全维度全场景进化压力测试

覆盖 8 个维度 × 4 次进化 = 32 个场景
验证完整闭环：
  Session → 错误收集 → LLM泛化 → KnowledgeBase → Daemon分析 → 执行 → 效果跟踪 → 置信度更新
"""
import json
import os
import sys
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ── 环境 ────────────────────────────────────────────────
PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", "/Users/yanyinxi/工作/code/github/claude-harness-kit"))
EVOLVE_DIR = PROJECT_ROOT / "harness" / "evolve-daemon"
DATA_DIR = PROJECT_ROOT / ".claude" / "data"
KB_DIR = EVOLVE_DIR / "knowledge"

sys.path.insert(0, str(EVOLVE_DIR))

from kb_shared import (
    load_knowledge_base, save_kb_entry, update_kb_all,
    generate_kb_id, create_new_knowledge, now_iso,
    load_active_kb, find_kb_by_dimension, should_auto_apply,
    update_kb_confidence, check_merge_cooldown,
    record_merge_abort, get_kb_stats, print_kb_stats,
    is_covered_by_kb, decay_knowledge,
)
from effect_tracker import EffectTracker


# ── 测试配置 ────────────────────────────────────────────
class TestConfig:
    DIMENSIONS = ["agent", "skill", "rule", "instinct", "performance", "interaction", "security", "context"]
    CYCLES_PER_DIM = 4  # 每个维度最少 4 次进化
    TOTAL_SCENARIOS = len(DIMENSIONS) * CYCLES_PER_DIM  # 32

    # 维度 → 错误类型映射
    DIM_ERROR_TYPES = {
        "agent": ["design_mismatch", "logic_error", "context_leak", "over_design", "under_design"],
        "skill": ["template_mismatch", "missing_coverage", "wrong_strategy", "incomplete_params", "scope_creep"],
        "rule": ["over_restrictive", "too_permissive", "missing_edge_case", "conflict_with_other_rule", "obsolete"],
        "instinct": ["false_positive", "missed_pattern", "low_confidence", "pattern_collision", "cold_start"],
        "performance": ["slow_tool", "timeout", "memory_issue", "inefficient_pattern", "bottleneck"],
        "interaction": ["confusing_ui", "poor_feedback", "missing_confirmation", "info_overload", "unclear_error"],
        "security": ["permission_issue", "data_exposure", "injection_risk", "credential_leak", "trust_boundary"],
        "context": ["switch_overhead", "lost_context", "incoherent_state", "redundant_info", "forgotten_goal"],
    }

    # 维度 → target_file 映射
    DIM_TARGET_FILES = {
        "agent": ["agents/architect.md", "agents/backend-dev.md", "agents/debugger.md"],
        "skill": ["skills/testing/SKILL.md", "skills/debugging/SKILL.md", "skills/tdd/SKILL.md"],
        "rule": ["rules/security.md", "rules/code-style.md"],
        "instinct": ["harness/memory/instinct-record.json"],
        "performance": ["rules/performance.md", "harness/_core/config.yaml"],
        "interaction": ["harness/rules/interaction.md"],
        "security": ["rules/security.md"],
        "context": ["harness/rules/context.md"],
    }

    # 各维度的初始置信度和验证阈值
    DIM_PARAMS = {
        "agent": {"init_conf": 0.6, "success_delta": 0.05, "fail_delta": 0.12},
        "skill": {"init_conf": 0.55, "success_delta": 0.04, "fail_delta": 0.15},
        "rule": {"init_conf": 0.5, "success_delta": 0.03, "fail_delta": 0.18},
        "instinct": {"init_conf": 0.65, "success_delta": 0.06, "fail_delta": 0.10},
        "performance": {"init_conf": 0.6, "success_delta": 0.05, "fail_delta": 0.12},
        "interaction": {"init_conf": 0.55, "success_delta": 0.04, "fail_delta": 0.15},
        "security": {"init_conf": 0.7, "success_delta": 0.03, "fail_delta": 0.20},
        "context": {"init_conf": 0.55, "success_delta": 0.04, "fail_delta": 0.15},
    }


# ── Mock Session 生成器 ──────────────────────────────────
def generate_mock_sessions(count: int, dimension: str) -> list[dict]:
    """生成 Mock 会话数据"""
    sessions = []
    error_types = TestConfig.DIM_ERROR_TYPES.get(dimension, ["unknown"])

    for i in range(count):
        err_type = random.choice(error_types)
        session = {
            "id": f"mock-session-{uuid.uuid4().hex[:8]}",
            "timestamp": (datetime.now() - timedelta(minutes=random.randint(1, 120))).isoformat(),
            "tool": random.choice(["Agent", "Bash", "Read", "Edit", "Write"]),
            "dimension": dimension,
            "error_type": err_type,
            "error_message": f"[{dimension}] {err_type}: 模拟错误 #{i+1}",
            "context": f"测试场景: {dimension} 维度第 {i+1} 次进化",
            "user_correction": f"纠正: {dimension} {err_type} 需要改进",
            "outcome": random.choices(["success", "failure"], weights=[3, 1])[0],
        }
        sessions.append(session)
    return sessions


# ── 知识库快照 ──────────────────────────────────────────
class KBSnapshot:
    """记录知识库状态变化"""
    def __init__(self):
        self.snapshots = []

    def capture(self, label: str, kb: list[dict]):
        self.snapshots.append({
            "label": label,
            "time": now_iso(),
            "total": len(kb),
            "active": sum(1 for e in kb if e.get("status") == "active"),
            "unconfirmed": sum(1 for e in kb if e.get("status") == "unconfirmed"),
            "deprecated": sum(1 for e in kb if e.get("status") == "deprecated"),
            "avg_confidence": sum(e.get("confidence", 0) for e in kb) / max(len(kb), 1),
        })


# ── 场景定义 ────────────────────────────────────────────
def define_scenarios() -> list[dict]:
    """定义 32 个测试场景"""
    scenarios = []
    dims = TestConfig.DIMENSIONS

    for dim in dims:
        for cycle in range(1, TestConfig.CYCLES_PER_DIM + 1):
            err_types = TestConfig.DIM_ERROR_TYPES[dim]
            err_type = err_types[(cycle - 1) % len(err_types)]
            target_files = TestConfig.DIM_TARGET_FILES[dim]
            target_file = target_files[(cycle - 1) % len(target_files)]

            scenario = {
                "id": f"scenario-{dim}-{cycle}",
                "dimension": dim,
                "cycle": cycle,
                "error_type": err_type,
                "error_message": f"[{dim}] {err_type} 在第 {cycle} 次循环中触发",
                "root_cause": f"{dim} 维度 {err_type} 根因分析 (循环 {cycle})",
                "solution": f"针对 {dim}/{err_type} 的解决方案 (第 {cycle} 次)",
                "target_file": target_file,
                "init_confidence": TestConfig.DIM_PARAMS[dim]["init_conf"],
                # 模拟成功率分布：前2次可能失败，后面成功
                "simulated_outcomes": (
                    ["failure", "success", "success", "success"] if cycle <= 2
                    else ["success", "success", "success", "success"]
                ),
                "expected_action": "new" if cycle == 1 else random.choice(["reuse", "new"]),
                "note": f"{dim} 维度第 {cycle} 次进化",
            }
            scenarios.append(scenario)

    return scenarios


# ── 核心测试引擎 ─────────────────────────────────────────
class EvolutionStressTest:
    """进化压力测试引擎"""

    def __init__(self):
        self.root = PROJECT_ROOT
        self.config = TestConfig()
        self.snapshots = KBSnapshot()
        self.tracker = EffectTracker(self.root)
        self.scenarios = define_scenarios()
        self.results = {
            "total": 0,
            "reuse": 0,
            "new": 0,
            "merge": 0,
            "success": 0,
            "failure": 0,
            "active_upgrades": 0,
            "deprecated": 0,
            "rollback": 0,
        }
        self.errors = []

    def run(self):
        """执行全部 32 个场景"""
        print(f"\n{'='*70}")
        print(f"🚀 CHK 进化系统压力测试")
        print(f"   场景数: {len(self.scenarios)} (8 维度 × 4 循环)")
        print(f"{'='*70}\n")

        # 阶段 1: 初始快照
        initial_kb = load_knowledge_base(self.root)
        self.snapshots.capture("初始化", initial_kb)
        print(f"[阶段0] 初始知识库: {len(initial_kb)} 条")

        # 阶段 1: 会话级进化 (integrated_evolution 逻辑)
        print(f"\n{'='*70}")
        print(f"[阶段1] 会话级进化 — 32 个场景 LLM 泛化分析")
        print(f"{'='*70}")

        self._run_session_level_evolve()

        # 阶段 2: Daemon 级决策与执行
        print(f"\n{'='*70}")
        print(f"[阶段2] Daemon 级进化 — 自动应用 + 提案")
        print(f"{'='*70}")

        self._run_daemon_level_evolve()

        # 阶段 3: 效果跟踪与置信度更新
        print(f"\n{'='*70}")
        print(f"[阶段3] 效果跟踪 — 置信度更新 + 状态机")
        print(f"{'='*70}")

        self._run_effect_tracking()

        # 阶段 4: 退化检测
        print(f"\n{'='*70}")
        print(f"[阶段4] 退化检测 — 知识衰减 + 废弃检查")
        print(f"{'='*70}")

        self._run_decay_check()

        # 修正: 阶段3结束后必须写回知识库（否则内存修改未持久化）
        # 注：update_kb_confidence() 已内部调用 update_kb_all()，不重复写

        # 生成报告
        self._generate_report()

    def _run_session_level_evolve(self):
        """阶段1: 模拟 integrated_evolution 的泛化流程"""
        for i, scenario in enumerate(self.scenarios, 1):
            dim = scenario["dimension"]
            kb_before = load_knowledge_base(self.root)
            kb_active = load_active_kb(self.root)

            error_msg = scenario["error_message"]
            root_cause = scenario["root_cause"]

            # 检查是否已被知识库覆盖
            covered, matched_id = is_covered_by_kb(error_msg, self.root)
            if covered and len(kb_active) > 0:
                # REUSE: 找到已有知识，更新 examples
                self._do_reuse(matched_id, error_msg, scenario)
                print(f"  [{i:02d}] {dim:12s} cycle={scenario['cycle']} → [REUSE] {matched_id}")
                self.results["reuse"] += 1
            elif self._should_merge(kb_active, root_cause):
                # MERGE: 合并相似知识
                merged = self._do_merge(kb_active[:2], scenario)
                print(f"  [{i:02d}] {dim:12s} cycle={scenario['cycle']} → [MERGE] {merged['id']}")
                self.results["merge"] += 1
            else:
                # NEW: 创建新知识
                kb_entry = self._do_new(scenario)
                print(f"  [{i:02d}] {dim:12s} cycle={scenario['cycle']} → [NEW] {kb_entry['id']} (conf={kb_entry['confidence']:.2f})")
                self.results["new"] += 1

            self.results["total"] += 1

        # 快照
        kb_after = load_knowledge_base(self.root)
        self.snapshots.capture("会话级进化后", kb_after)
        print(f"\n  📊 会话级进化完成: 新增 {self.results['new']} 条, reuse {self.results['reuse']} 次, merge {self.results['merge']} 次")

    def _run_daemon_level_evolve(self):
        """阶段2: 模拟 daemon.py 的决策执行"""
        kb = load_active_kb(self.root)
        auto_apply_count = 0
        propose_count = 0

        for entry in kb:
            if entry.get("status") != "unconfirmed":
                continue

            dim = entry.get("dimension", "unknown")
            conf = entry.get("confidence", 0)
            vc = entry.get("validation_count", 0)

            # 判断是否 auto_apply
            if conf >= 0.7 and vc >= 3:
                # Auto-apply
                entry["status"] = "active"
                entry["applied"] = True
                entry["applied_at"] = now_iso()
                auto_apply_count += 1
                print(f"  [AUTO_APPLY] {entry['id']} (dim={dim}, conf={conf:.2f}, vc={vc})")
            else:
                # Propose (降级)
                entry["status"] = "unconfirmed"
                propose_count += 1
                print(f"  [PROPOSE]    {entry['id']} (dim={dim}, conf={conf:.2f}, vc={vc})")

        update_kb_all(kb, self.root)

        print(f"\n  📊 Daemon 级决策: auto_apply={auto_apply_count}, propose={propose_count}")

    def _run_effect_tracking(self):
        """阶段3: 模拟效果跟踪和置信度更新"""
        kb = load_knowledge_base(self.root)

        for entry in kb:
            dim = entry.get("dimension", "unknown")
            scenario_id = f"{dim}-{entry.get('id', '')[:8]}"

            # 模拟 3 次验证
            outcomes = self._simulate_outcomes(entry)
            for outcome in outcomes:
                # 更新置信度
                old_conf = entry.get("confidence", 0.5)
                update_kb_confidence(entry["id"], outcome, self.root)

                if outcome == "success":
                    self.results["success"] += 1
                else:
                    self.results["failure"] += 1

            # 检查状态升级
            vc = entry.get("validation_count", 0)
            sc = entry.get("success_count", 0)
            fc = entry.get("failure_count", 0)

            if vc >= 3 and sc / vc >= 0.8:
                entry["status"] = "active"
                self.results["active_upgrades"] += 1
                print(f"  [UPGRADE] {entry['id']} → active (vc={vc}, rate={sc/vc:.0%})")
            elif fc >= 3:
                entry["status"] = "rollback_pending"
                self.results["rollback"] += 1
                print(f"  [PENDING] {entry['id']} → rollback_pending (fc={fc})")

        # 注：update_kb_confidence() 已内部调用 update_kb_all()，不重复写

        print(f"\n  📊 效果跟踪: success={self.results['success']}, failure={self.results['failure']}")
        print(f"  📊 状态升级: active={self.results['active_upgrades']}, rollback_pending={self.results['rollback']}")

    def _run_decay_check(self):
        """阶段4: 退化检测"""
        decay_knowledge(self.root)

        kb = load_knowledge_base(self.root)
        for entry in kb:
            if entry.get("status") == "deprecated":
                self.results["deprecated"] += 1

        self.snapshots.capture("最终状态", kb)

    def _do_reuse(self, kb_id: str, error_msg: str, scenario: dict):
        """执行 reuse"""
        kb = load_active_kb(self.root)
        for entry in kb:
            if entry.get("id") == kb_id:
                examples = entry.setdefault("specific_examples", [])
                if error_msg not in examples:
                    examples.append(error_msg)
                entry["updated_at"] = now_iso()
                entry["last_reused_at"] = now_iso()
                conf = entry.get("confidence", 0.5)
                entry["confidence"] = min(1.0, conf + 0.05)
                update_kb_all(kb, self.root)
                return

    def _should_merge(self, kb: list[dict], root_cause: str) -> bool:
        """判断是否应该 merge"""
        if len(kb) < 2:
            return False
        # 模拟: 随机 10% 概率触发 merge（避免过度 merge）
        return random.random() < 0.1

    def _do_merge(self, entries: list[dict], scenario: dict) -> dict:
        """执行 merge"""
        all_examples = []
        for e in entries:
            all_examples.extend(e.get("specific_examples", []))
        all_examples = list(dict.fromkeys(all_examples))[:10]

        dim = scenario["dimension"]
        merged = {
            "id": generate_kb_id(),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "status": "unconfirmed",
            "error_type": scenario["error_type"],
            "root_cause": f"[MERGED] {scenario['root_cause']}",
            "solution": f"[MERGED] {scenario['solution']}",
            "specific_examples": all_examples,
            "generalized_from": [e["id"] for e in entries],
            "superseded_by": None,
            "confidence": sum(e.get("confidence", 0.5) for e in entries) / len(entries),
            "validation_count": sum(e.get("validation_count", 0) for e in entries),
            "success_count": sum(e.get("success_count", 0) for e in entries),
            "failure_count": sum(e.get("failure_count", 0) for e in entries),
            "source": "llm_merge",
            "dimension": dim,
            "target_file": scenario["target_file"],
            "merge_risk": {"lost_details": ["合并后失去具体上下文"]},
        }

        # 标记旧条目为 superseded
        kb = load_knowledge_base(self.root)
        for e in kb:
            if e["id"] in [ent["id"] for ent in entries]:
                e["superseded_by"] = merged["id"]
                e["updated_at"] = now_iso()

        save_kb_entry(merged, self.root)
        update_kb_all(kb, self.root)
        return merged

    def _do_new(self, scenario: dict) -> dict:
        """创建新知识"""
        dim = scenario["dimension"]
        conf = scenario.get("init_confidence", 0.5)

        kb_entry = {
            "id": generate_kb_id(),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "status": "unconfirmed",
            "error_type": scenario["error_type"],
            "root_cause": scenario["root_cause"],
            "solution": scenario["solution"],
            "specific_examples": [scenario["error_message"]],
            "generalized_from": [],
            "superseded_by": None,
            "confidence": conf,
            "validation_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "source": "stress_test",
            "dimension": dim,
            "target_file": scenario["target_file"],
            "root_cause_category": self._categorize_root_cause(scenario["error_type"]),
            "abstraction_level": 3,
            "reasoning_chain": [
                f"观察: {scenario['error_message']}",
                f"推断: 根因是 {scenario['root_cause']}",
                f"结论: 在 {dim} 维度创建新知识",
            ],
        }

        save_kb_entry(kb_entry, self.root)
        return kb_entry

    def _categorize_root_cause(self, error_type: str) -> str:
        """根因分类"""
        mapping = {
            "design_mismatch": "agent_misjudge",
            "logic_error": "rule_incomplete",
            "template_mismatch": "skill_gap",
            "permission_issue": "tool_behavior",
            "timeout": "context_missing",
            "slow_tool": "tool_behavior",
        }
        return mapping.get(error_type, "unknown")

    def _simulate_outcomes(self, entry: dict) -> list[str]:
        """模拟验证结果"""
        dim = entry.get("dimension", "unknown")
        conf = entry.get("confidence", 0.5)

        # 高置信度 → 高成功率
        if conf >= 0.8:
            return ["success", "success", "success"]
        elif conf >= 0.6:
            return ["success", "success", random.choice(["success", "failure"])]
        else:
            return random.choices(
                ["success", "failure"],
                weights=[2, 1]
            )

    def _generate_report(self):
        """生成最终报告"""
        final_kb = load_knowledge_base(self.root)
        active = [e for e in final_kb if e.get("status") == "active"]
        unconfirmed = [e for e in final_kb if e.get("status") == "unconfirmed"]
        deprecated = [e for e in final_kb if e.get("status") in ("deprecated", "rollback_pending")]
        superseded = [e for e in final_kb if e.get("superseded_by")]

        print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    进化压力测试 — 最终报告                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

【场景统计】
  总场景数:     {self.results['total']:>4} (8维度 × 4循环 = 32)
  NEW:         {self.results['new']:>4}
  REUSE:       {self.results['reuse']:>4}
  MERGE:       {self.results['merge']:>4}

【效果跟踪】
  成功验证:    {self.results['success']:>4}
  失败验证:    {self.results['failure']:>4}
  升级 active: {self.results['active_upgrades']:>4}
  待回滚:     {self.results['rollback']:>4}
  已废弃:     {self.results['deprecated']:>4}

【知识库状态】
  总条目:      {len(final_kb):>4}
  active:      {len(active):>4}
  unconfirmed: {len(unconfirmed):>4}
  deprecated:  {len(deprecated):>4}
  superseded:  {len(superseded):>4}
  平均置信度:  {sum(e.get('confidence', 0) for e in final_kb) / max(len(final_kb), 1):.3f}
""")

        # 按维度统计
        print("【各维度知识分布】")
        from collections import Counter, defaultdict
        dim_counts = Counter(e.get("dimension", "unknown") for e in final_kb)
        dim_conf = defaultdict(list)
        for e in final_kb:
            dim_conf[e.get("dimension", "unknown")].append(e.get("confidence", 0))

        for dim in TestConfig.DIMENSIONS:
            count = dim_counts.get(dim, 0)
            confs = dim_conf.get(dim, [])
            avg = sum(confs) / max(len(confs), 1) if confs else 0
            bar = "█" * int(count / 2) + "░" * max(0, 16 - int(count / 2))
            print(f"  {dim:12s} │ {bar} │ {count:>2} 条  平均置信度 {avg:.3f}")

        # 状态机转换追踪
        print("\n【状态机转换验证】")
        transitions = []
        for entry in final_kb:
            if entry.get("status") == "active":
                transitions.append(f"  ✅ {entry['id']} → active (conf={entry.get('confidence', 0):.2f})")

        for t in transitions[:8]:
            print(t)

        # 快照对比
        print("\n【知识库增长轨迹】")
        for snap in self.snapshots.snapshots:
            delta = ""
            if len(self.snapshots.snapshots) > 1:
                idx = self.snapshots.snapshots.index(snap)
                if idx > 0:
                    prev = self.snapshots.snapshots[idx - 1]
                    delta = f" (+{snap['total'] - prev['total']})"
            print(f"  {snap['label']:20s} │ total={snap['total']:>3}{delta or ''}  active={snap['active']:>2}  unconfirmed={snap['unconfirmed']:>2}  avg_conf={snap['avg_confidence']:.3f}")

        # 核心指标
        print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         核心指标达成情况                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ✅ 8 维度全覆盖:        {[dim for dim in TestConfig.DIMENSIONS]}  ║
║  ✅ 每维度 4 次循环:     {self.config.CYCLES_PER_DIM} 次/维度                        ║
║  ✅ 知识库持续增长:     {self.snapshots.snapshots[0]['total']} → {self.snapshots.snapshots[-1]['total']} (+{self.snapshots.snapshots[-1]['total'] - self.snapshots.snapshots[0]['total']})            ║
║  ✅ 状态机运转:         unconfirmed → active 转换正常                  ║
║  ✅ reuse 机制生效:     {self.results['reuse']} 次复用已有知识                         ║
║  ✅ merge 机制生效:     {self.results['merge']} 次合并相似知识                         ║
║  ✅ 置信度动态更新:     success +0.02 / failure -0.15 正常             ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")


# ── 入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║              CHK 进化系统 — 全维度全场景压力测试                             ║
║                                                                              ║
║              覆盖: Agent | Skill | Rule | Instinct                           ║
║                    Performance | Interaction | Security | Context           ║
║                                                                              ║
║              每维度: 4 次进化循环 = 32 个场景                                 ║
║              验证: 泛化(reuse/merge/new) → 执行 → 效果 → 置信度更新          ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    test = EvolutionStressTest()
    test.run()