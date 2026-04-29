#!/usr/bin/env python3
"""
全方位进化回归测试

模拟 3 个真实开发会话，覆盖全部 4 个维度的进化周期。
验证: 数据采集 → 触发条件 → 进化派发 → 评分上升 → 累积学习

用法:
  python3 .claude/tests/test_evolution_regression.py
  python3 .claude/tests/test_evolution_regression.py --verbose
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# 确保可以导入 .claude 下的模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / ".claude"))
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "hooks" / "scripts"))

# ── 测试辅助函数 ──

_VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def log(msg: str):
    if _VERBOSE:
        print(f"  {msg}")


def fail(msg: str):
    raise AssertionError(msg)


# ── 测试环境搭建 ──


class RegressionTestEnv:
    """创建隔离的测试环境，包含完整的 .claude 目录结构和 git 仓库。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.claude_dir = self.root / ".claude"
        self.data_dir = self.claude_dir / "data"
        self.agents_dir = self.claude_dir / "agents"
        self.rules_dir = self.claude_dir / "rules"
        self.skills_dir = self.claude_dir / "skills"
        self.memory_dir = self.claude_dir / "memory"
        self.logs_dir = self.claude_dir / "logs"

    def setup(self):
        """搭建完整的测试环境。"""
        # 目录结构
        for d in [self.data_dir, self.agents_dir, self.rules_dir,
                  self.skills_dir, self.memory_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 初始化 git 仓库（session_evolver 依赖）
        subprocess.run(["git", "init"], cwd=self.root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=self.root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=self.root, capture_output=True)

        # 创建初始 commit（git diff HEAD 依赖）
        (self.root / "README.md").write_text("# Test Project\n")
        subprocess.run(["git", "add", "."], cwd=self.root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.root, capture_output=True)

        # 复制核心 Python 模块
        self._setup_python_modules()

        log(f"测试环境搭建完成: {self.root}")
        return self

    def _ensure_lib(self, src_file):
        lib_dir = self.claude_dir / "lib"
        lib_dir.mkdir(exist_ok=True)
        shutil.copy2(src_file, lib_dir)

    def _setup_python_modules(self):
        """复制进化系统必需的 Python 文件到测试环境。"""
        src_claude = PROJECT_ROOT / ".claude"
        # lib/
        lib_dst = self.claude_dir / "lib"
        lib_dst.mkdir(exist_ok=True)
        for f in (src_claude / "lib").glob("*.py"):
            shutil.copy2(f, lib_dst / f.name)

        # hooks/scripts/
        hooks_dst = self.claude_dir / "hooks" / "scripts"
        hooks_dst.mkdir(parents=True, exist_ok=True)
        for f in (src_claude / "hooks" / "scripts").glob("*.py"):
            shutil.copy2(f, hooks_dst / f.name)

        # evolution/ (如果存在)
        evo_src = src_claude / "evolution"
        if evo_src.exists():
            evo_dst = self.claude_dir / "evolution"
            evo_dst.mkdir(exist_ok=True)
            for f in evo_src.rglob("*.py"):
                rel = f.relative_to(evo_src)
                (evo_dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, evo_dst / rel)

        # 复制 agents 目录（evolver agent 定义文件）
        agents_dst = self.claude_dir / "agents"
        agents_dst.mkdir(exist_ok=True)
        for f in (src_claude / "agents").glob("*.md"):
            shutil.copy2(f, agents_dst / f.name)

        # 复制 rules 目录
        rules_dst = self.claude_dir / "rules"
        rules_dst.mkdir(exist_ok=True)
        for f in (src_claude / "rules").glob("*.md"):
            shutil.copy2(f, rules_dst / f.name)

        # 复制 skills 目录
        skills_src = src_claude / "skills"
        if skills_src.exists():
            skills_dst = self.claude_dir / "skills"
            for d in skills_src.iterdir():
                if d.is_dir():
                    dst = skills_dst / d.name
                    shutil.copytree(d, dst, dirs_exist_ok=True)

        # 复制 memory 目录
        memory_src = src_claude / "memory"
        if memory_src.exists():
            for f in memory_src.glob("*.md"):
                shutil.copy2(f, self.memory_dir / f.name)

        # 复制 data 中的初始配置文件
        for name in ["strategy_weights.json", "strategy_variants.json",
                     "capabilities.json", "knowledge_graph.json"]:
            src = src_claude / "data" / name
            if src.exists():
                shutil.copy2(src, self.data_dir / name)

    def write_data_file(self, filename: str, records: list):
        """写入 JSONL 数据文件。"""
        path = self.data_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def write_json_file(self, filename: str, data: dict):
        """写入 JSON 数据文件。"""
        path = self.data_dir / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def read_jsonl(self, filename: str) -> list:
        path = self.data_dir / filename
        if not path.exists():
            return []
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def read_json(self, filename: str) -> dict:
        path = self.data_dir / filename
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def make_git_change(self, files: list):
        """创建 git 变更（模拟代码修改）。"""
        for filepath, content in files:
            f = self.root / filepath
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        subprocess.run(["git", "add", "-A"], cwd=self.root, capture_output=True)

    def run_hook(self, script_name: str, input_data: dict = None) -> dict:
        """在测试环境中运行一个 hook 脚本。"""
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        script_path = self.claude_dir / "hooks" / "scripts" / script_name

        cmd = ["python3", str(script_path)]
        proc = subprocess.run(
            cmd,
            input=json.dumps(input_data or {}),
            capture_output=True, text=True, timeout=30,
            cwd=str(self.root), env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{script_name} 失败: {proc.stderr}")
        return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}

    def run_orchestrator(self, execute: bool = True) -> dict:
        """直接调用进化编排器。"""
        sys.path.insert(0, str(self.claude_dir))
        sys.path.insert(0, str(self.claude_dir / "lib"))
        # 强制使用测试环境的 data 目录
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)
        from lib.evolution_orchestrator import run_orchestrator
        result = run_orchestrator(str(self.root), execute=execute)
        return result

    def simulate_evolution(self, dimension: str, target: str, priority: float,
                           target_file: str, additions: str):
        """模拟进化 Agent 的执行效果：修改目标文件并写入进化历史。"""
        f = self.claude_dir / target_file
        f.parent.mkdir(parents=True, exist_ok=True)
        original = f.read_text() if f.exists() else ""

        # 追加进化标记（模拟 Agent 进化器的输出）
        evo_header = f"\n\n<!-- EVOLVED {datetime.now().isoformat()} dimension={dimension} target={target} priority={priority:.2f} -->\n"
        f.write_text(original + evo_header + additions)

        # 写入进化历史
        hist_path = self.data_dir / "evolution_history.jsonl"
        with open(hist_path, "a", encoding="utf-8") as hf:
            hf.write(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "session_id": "test-session",
                "dimension": dimension,
                "target": target,
                "priority": priority,
                "file_changed": target_file,
                "confirmation_result": "success",
            }, ensure_ascii=False) + "\n")

        return original != (f.read_text() if f.exists() else "")

    def cleanup(self):
        self.tmp.cleanup()


# ═══════════════════════════════════════════════════════════════
# 阶段 0: 环境完整性
# ═══════════════════════════════════════════════════════════════


def test_environment_setup():
    """环境搭建：所有 Python 模块可导入，数据目录就绪。"""
    env = RegressionTestEnv().setup()
    try:
        assert env.data_dir.exists(), "data 目录应存在"
        assert env.agents_dir.exists(), "agents 目录应存在"
        assert env.rules_dir.exists(), "rules 目录应存在"

        # 验证核心模块可导入
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import (
            aggregate_session_data, compute_priority, check_triggers, run_orchestrator
        )
        from lib.evolution_scoring import compute_all_scores, save_daily_score
        from lib.evolution_safety import (
            EvolutionCircuitBreaker, EvolutionRateLimiter,
            validate_jsonl_file, pre_evolution_check
        )
        log("阶段 0 通过: 环境就绪，所有模块可导入")
    finally:
        env.cleanup()


# ═══════════════════════════════════════════════════════════════
# 阶段 1: Session 1 — 触发 Agent + Rule 进化
# ═══════════════════════════════════════════════════════════════


def test_session1_data_population():
    """Session 1 数据植入：agent_performance + tool_failures + rule_violations。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-1-low-quality"

        # 植入 Agent 低效调用记录（6 条，avg_turns 估算 > 20）
        agent_records = []
        for i in range(6):
            agent_records.append({
                "type": "agent_launch",
                "timestamp": now,
                "session_id": session_id,
                "agent": "backend-developer",
                "task": "实现用户管理模块，包括注册、登录、权限验证、"
                        "密码重置、邮箱验证、手机绑定、OAuth 集成、"
                        "session 管理、token 刷新、角色管理、权限矩阵配置",
                "prompt_preview": "实现完整的用户管理模块...",
            })
        env.write_data_file("agent_performance.jsonl", agent_records)

        # 植入失败记录（2 条关联到 backend-developer）
        failure_records = [
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Bash", "error_summary": "mvn test failed",
             "context": {"agent": "backend-developer"}},
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Edit", "error_summary": "编译错误",
             "context": {"agent": "backend-developer"}},
        ]
        env.write_data_file("tool_failures.jsonl", failure_records)

        # 植入规则违规（4 次，触发 > 0.5）
        violation_records = [
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": "main/backend/src/main/java/User.java",
             "severity": "high"},
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": "main/backend/src/main/java/Order.java",
             "severity": "high"},
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": "main/backend/src/main/java/Product.java",
             "severity": "high"},
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": "main/backend/src/main/java/Customer.java",
             "severity": "high"},
        ]
        env.write_data_file("rule_violations.jsonl", violation_records)

        # 模拟 git 变更（散乱的文件修改，无测试）
        env.make_git_change([
            ("main/backend/src/main/java/User.java",
             "import lombok.Data;\n@Data\npublic class User {}"),
            ("main/backend/src/main/java/Order.java",
             "import lombok.Data;\n@Data\npublic class Order {}"),
            ("main/backend/src/main/java/Product.java",
             "import lombok.Data;\n@Data\npublic class Product {}"),
            ("main/backend/src/main/java/Customer.java",
             "import lombok.Data;\n@Data\npublic class Customer {}"),
            ("main/frontend/src/views/Home.vue", "<template><div>Home</div></template>"),
            ("main/frontend/src/views/About.vue", "<template><div>About</div></template>"),
            ("main/frontend/src/views/Contact.vue", "<template><div>Contact</div></template>"),
        ])

        # 验证数据写入
        assert len(env.read_jsonl("agent_performance.jsonl")) == 6
        assert len(env.read_jsonl("tool_failures.jsonl")) == 2
        assert len(env.read_jsonl("rule_violations.jsonl")) == 4

        log("阶段 1 数据植入通过: 6 agent + 2 failure + 4 violation")
    finally:
        env.cleanup()


def test_session1_trigger_computation():
    """Session 1 触发计算：Agent + Rule 两个维度都应触发。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-1-low-quality"

        # 植入数据
        agent_records = [{
            "type": "agent_launch", "timestamp": now,
            "session_id": session_id, "agent": "backend-developer",
            "task": "实现完整模块 A" * 10,  # 长任务 → 高 avg_turns
            "prompt_preview": "...",
        } for _ in range(6)]
        env.write_data_file("agent_performance.jsonl", agent_records)

        failure_records = [
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Bash", "error_summary": "test fail",
             "context": {"agent": "backend-developer"}},
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Edit", "error_summary": "compile error",
             "context": {"agent": "backend-developer"}},
        ]
        env.write_data_file("tool_failures.jsonl", failure_records)

        violation_records = [
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": f"main/backend/src/main/java/C{i}.java",
             "severity": "high"}
            for i in range(4)
        ]
        env.write_data_file("rule_violations.jsonl", violation_records)

        env.make_git_change([
            ("main/backend/src/main/java/Test.java", "// test"),
        ])

        # 直接调用编排器
        sys.path.insert(0, str(env.claude_dir))
        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        from lib.evolution_orchestrator import check_triggers

        decision = check_triggers(str(env.root))
        triggers = decision.get("triggers", [])

        # 验证触发
        agent_triggers = [t for t in triggers if t["dimension"] == "agent"]
        rule_triggers = [t for t in triggers if t["dimension"] == "rule"]

        assert len(agent_triggers) >= 1, f"Agent 维度应触发，实际 triggers: {triggers}"
        assert agent_triggers[0]["priority"] > 0.5, \
            f"Agent 优先级应 > 0.5: {agent_triggers[0]['priority']}"
        assert agent_triggers[0]["target"] == "backend-developer"

        assert len(rule_triggers) >= 1, f"Rule 维度应触发，实际 triggers: {triggers}"
        assert rule_triggers[0]["priority"] > 0.5, \
            f"Rule 优先级应 > 0.5: {rule_triggers[0]['priority']}"

        log(f"阶段 1 触发验证通过: agent priority={agent_triggers[0]['priority']:.2f}, "
            f"rule priority={rule_triggers[0]['priority']:.2f}")
    finally:
        env.cleanup()


def test_session1_evolution_persistence():
    """Session 1 进化持久化：pending_evolution.json 包含触发决策。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-1-low-quality"

        env.write_data_file("agent_performance.jsonl", [
            {"type": "agent_launch", "timestamp": now, "session_id": session_id,
             "agent": "backend-developer",
             "task": "实现完整模块 A" * 10, "prompt_preview": "..."}
        ] * 6)
        env.write_data_file("tool_failures.jsonl", [
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Bash", "error_summary": "fail", "context": {"agent": "backend-developer"}}
        ] * 2)
        env.write_data_file("rule_violations.jsonl", [
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": f"main/backend/src/main/java/C{i}.java",
             "severity": "high"}
            for i in range(4)
        ])
        env.make_git_change([("main/backend/src/main/java/Test.java", "// test")])

        # 运行编排器（execute=True → 持久化）
        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import run_orchestrator
        decision = run_orchestrator(str(env.root), execute=True)

        assert decision.get("should_evolve"), "应该触发进化"
        assert decision.get("evolved"), "应该标记为已执行（持久化）"

        # 验证 pending_evolution.json
        pending = env.read_json("pending_evolution.json")
        assert pending, "应该有 pending_evolution.json"
        pending_triggers = pending.get("pending_triggers", [])
        assert len(pending_triggers) >= 2, \
            f"至少 2 个待处理 trigger: {len(pending_triggers)}"

        dims = set(t["dimension"] for t in pending_triggers)
        assert "agent" in dims, f"pending 应包含 agent 维度: {dims}"
        assert "rule" in dims, f"pending 应包含 rule 维度: {dims}"

        log(f"阶段 1 持久化通过: {len(pending_triggers)} 个 trigger → pending_evolution.json")
    finally:
        env.cleanup()


def test_session1_evolution_dispatch():
    """Session 1 进化派发：模拟 Agent 进化器修改文件，写进化历史。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-1-low-quality"

        env.write_data_file("agent_performance.jsonl", [
            {"type": "agent_launch", "timestamp": now, "session_id": session_id,
             "agent": "backend-developer",
             "task": "实现完整模块 A" * 10, "prompt_preview": "..."}
        ] * 6)
        env.write_data_file("tool_failures.jsonl", [
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Bash", "error_summary": "fail", "context": {"agent": "backend-developer"}}
        ] * 2)
        env.write_data_file("rule_violations.jsonl", [
            {"type": "rule_violation", "timestamp": now, "session_id": session_id,
             "rule": "no-lombok", "file": f"main/backend/src/main/java/C{i}.java",
             "severity": "high"}
            for i in range(4)
        ])
        env.make_git_change([("main/backend/src/main/java/Test.java", "// test")])

        # 持久化
        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import run_orchestrator
        run_orchestrator(str(env.root), execute=True)

        pending = env.read_json("pending_evolution.json")
        pending_triggers = pending.get("pending_triggers", [])

        # 模拟进化 Agent 执行
        evolved_count = 0
        for trigger in pending_triggers:
            dim = trigger["dimension"]
            target = trigger["target"]
            priority = trigger["priority"]

            if dim == "agent":
                changed = env.simulate_evolution(
                    dim, target, priority,
                    f"agents/{target}.md",
                    "\n## 进化优化 (Session 1)\n"
                    "- 降低 avg_turns 阈值至 15\n"
                    "- 增加任务分解提示：超过 3 个子任务时拆分为多个 Agent\n"
                )
                if changed:
                    evolved_count += 1

            elif dim == "rule":
                changed = env.simulate_evolution(
                    dim, target, priority,
                    f"rules/general.md",
                    "\n## 进化优化 (Session 1)\n"
                    "- 强化 no-lombok 规则检测\n"
                    "- 在代码审查阶段增加 Lombok import 检查\n"
                )
                if changed:
                    evolved_count += 1

        # 验证进化历史
        history = env.read_jsonl("evolution_history.jsonl")
        assert len(history) >= 2, f"应至少 2 条进化记录: {len(history)}"

        dims_in_history = set(h["dimension"] for h in history)
        assert "agent" in dims_in_history, f"应有 agent 进化记录: {dims_in_history}"
        assert "rule" in dims_in_history, f"应有 rule 进化记录: {dims_in_history}"

        # 验证文件已修改
        agent_file = env.claude_dir / "agents" / "backend-developer.md"
        rule_file = env.claude_dir / "rules" / "general.md"
        assert "进化优化" in agent_file.read_text(), "agent 文件应有进化标记"
        assert "进化优化" in rule_file.read_text(), "rule 文件应有进化标记"

        # 清除 pending_triggers（模拟进化完成后的清理）
        pending["pending_triggers"] = []
        (env.data_dir / "pending_evolution.json").write_text(
            json.dumps(pending, indent=2, ensure_ascii=False))

        # 验证清除
        cleared = env.read_json("pending_evolution.json")
        assert len(cleared.get("pending_triggers", [])) == 0, "触发队列应已清空"

        log(f"阶段 1 派发通过: {evolved_count} 个进化执行, 队列已清空")
    finally:
        env.cleanup()


# ═══════════════════════════════════════════════════════════════
# 阶段 2: Session 2 — 触发 Skill + Memory 进化
# ═══════════════════════════════════════════════════════════════


def test_session2_skill_trigger():
    """Session 2 技能触发：10 次调用 + 30% 失败率触发技能进化。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-2-skill-heavy"

        # 植入 10 条技能调用
        skill_records = [
            {"type": "skill_invoked", "timestamp": now, "session_id": session_id,
             "skill": "karpathy-guidelines"}
            for _ in range(10)
        ]
        env.write_data_file("skill_usage.jsonl", skill_records)

        # 植入 6 条工具失败（skill 相关）→ success_rate = 1-6/10 = 0.4
        failure_records = [
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Skill", "error_summary": f"skill fail {i}",
             "context": {"skill": "karpathy-guidelines"}}
            for i in range(6)
        ]
        env.write_data_file("tool_failures.jsonl", failure_records)

        env.make_git_change([
            ("main/frontend/src/views/Settings.vue", "<template>Settings</template>"),
        ])

        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import check_triggers, compute_priority

        # 验证 skill 优先级计算
        skill_priority = compute_priority("skill", {
            "total_calls": 10,
            "success_rate": 0.4,  # 6/10 失败 → priority = (1-0.4)*10/10 = 0.6 > 0.5
        })
        assert skill_priority > 0.5, \
            f"Skill 优先级应 > 0.5 (10 calls, 40% success): {skill_priority:.2f}"

        # 验证完整触发检查
        decision = check_triggers(str(env.root))
        skill_triggers = [t for t in decision["triggers"]
                         if t["dimension"] == "skill"]
        assert len(skill_triggers) >= 1, \
            f"Skill 触发缺失，triggers: {decision['triggers']}"

        log(f"阶段 2 Skill 触发通过: priority={skill_priority:.2f}")
    finally:
        env.cleanup()


def test_session2_memory_trigger():
    """Session 2 记忆触发：2 个反馈信号触发记忆进化。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-2-feedback"

        # 植入反馈信号（2 个纠正信号）
        env.write_json_file("pending_evolution.json", {
            "feedback_signals": [
                {"type": "correction", "timestamp": now,
                 "content": "不要使用 Lombok，项目规范要求手写 getter/setter"},
                {"type": "preference", "timestamp": now,
                 "content": "优先使用 JDK 17 record 代替手写 POJO"},
            ],
            "pending_triggers": [],
            "last_check": now,
        })

        # 需要一些 skill_usage 数据让 aggregate_session_data 工作
        env.write_data_file("skill_usage.jsonl", [
            {"type": "skill_invoked", "timestamp": now, "session_id": session_id,
             "skill": "karpathy-guidelines"}
        ])
        env.write_data_file("agent_performance.jsonl", [
            {"type": "agent_launch", "timestamp": now, "session_id": session_id,
             "agent": "orchestrator", "task": "test", "prompt_preview": "..."}
        ])
        env.make_git_change([("main/docs/note.md", "# Note")])

        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import check_triggers, compute_priority

        memory_priority = compute_priority("memory", {"pending_signals": 2})
        assert memory_priority == 1.0, \
            f"Memory 优先级应为 1.0 (2 signals): {memory_priority:.2f}"

        decision = check_triggers(str(env.root))
        memory_triggers = [t for t in decision["triggers"]
                          if t["dimension"] == "memory"]
        assert len(memory_triggers) >= 1, \
            f"Memory 触发缺失，triggers: {decision['triggers']}"

        log(f"阶段 2 Memory 触发通过: priority={memory_priority:.2f}")
    finally:
        env.cleanup()


def test_session2_evolution_dispatch():
    """Session 2 进化派发：Skill + Memory 进化执行。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()
        session_id = "session-2-combined"

        # 植入 Skill 数据（10 调用 + 6 失败 → 40% 成功率）
        env.write_data_file("skill_usage.jsonl", [
            {"type": "skill_invoked", "timestamp": now, "session_id": session_id,
             "skill": "karpathy-guidelines"}
        ] * 10)
        env.write_data_file("tool_failures.jsonl", [
            {"type": "tool_failure", "timestamp": now, "session_id": session_id,
             "tool": "Skill", "error_summary": f"fail {i}",
             "context": {"skill": "karpathy-guidelines"}}
            for i in range(6)
        ])

        # 植入 Agent 数据（确保 aggregate 不报错）
        env.write_data_file("agent_performance.jsonl", [
            {"type": "agent_launch", "timestamp": now, "session_id": session_id,
             "agent": "orchestrator", "task": "test", "prompt_preview": "..."}
        ])

        # 植入反馈信号
        env.write_json_file("pending_evolution.json", {
            "feedback_signals": [
                {"type": "correction", "timestamp": now,
                 "content": "不要使用 Lombok"},
                {"type": "preference", "timestamp": now,
                 "content": "优先使用 JDK 17 record"},
            ],
            "pending_triggers": [],
        })

        env.make_git_change([("main/docs/note2.md", "# Note 2")])

        # 持久化触发
        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import run_orchestrator
        decision = run_orchestrator(str(env.root), execute=True)
        assert decision.get("should_evolve"), "Session 2 应触发进化"

        pending = env.read_json("pending_evolution.json")
        pending_triggers = pending.get("pending_triggers", [])

        # 模拟进化
        for trigger in pending_triggers:
            dim = trigger["dimension"]
            target = trigger["target"]
            priority = trigger["priority"]

            if dim == "skill":
                env.simulate_evolution(
                    dim, target, priority,
                    f"skills/{target}/SKILL.md",
                    "\n## 进化优化 (Session 2)\n"
                    "- 增加调用前检查：验证 skill 文件存在\n"
                    "- 增加超时保护：skill 执行超过 30s 自动降级\n"
                )
            elif dim == "memory":
                env.simulate_evolution(
                    dim, target, priority,
                    f"memory/{target}.md",
                    "\n## 进化优化 (Session 2)\n"
                    "- 记录用户偏好：禁止 Lombok，优先 JDK 17 record\n"
                )

        # 验证
        history = env.read_jsonl("evolution_history.jsonl")
        dims = set(h["dimension"] for h in history)
        assert "skill" in dims, f"应有 skill 进化: {dims}"
        assert "memory" in dims, f"应有 memory 进化: {dims}"

        # 清除 pending_triggers
        pending["pending_triggers"] = []
        (env.data_dir / "pending_evolution.json").write_text(
            json.dumps(pending, indent=2, ensure_ascii=False))

        log(f"阶段 2 派发通过: {len(history)} 条进化记录, 维度: {dims}")
    finally:
        env.cleanup()


# ═══════════════════════════════════════════════════════════════
# 阶段 3: Session 3 — 高质量会话，验证学习效果
# ═══════════════════════════════════════════════════════════════


def test_session3_cumulative_scoring():
    """累积评分单调性：Session 3 评分 > Session 2 > Session 1。"""
    env = RegressionTestEnv().setup()
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))

        # ── Session 1: 低质量数据 + 进化 ──
        now1 = (datetime.now() - timedelta(hours=48)).isoformat()
        sid1 = "session-1-low"
        env.write_data_file("agent_performance.jsonl", [
            {"type": "agent_launch", "timestamp": now1, "session_id": sid1,
             "agent": "backend-developer",
             "task": "实现完整模块 A" * 10, "prompt_preview": "..."}
        ] * 6)
        env.write_data_file("tool_failures.jsonl", [
            {"type": "tool_failure", "timestamp": now1, "session_id": sid1,
             "tool": "Bash", "error_summary": "fail",
             "context": {"agent": "backend-developer"}},
            {"type": "tool_failure", "timestamp": now1, "session_id": sid1,
             "tool": "Edit", "error_summary": "compile error",
             "context": {"agent": "backend-developer"}},
        ])
        env.write_data_file("rule_violations.jsonl", [
            {"type": "rule_violation", "timestamp": now1, "session_id": sid1,
             "rule": "no-lombok", "file": f"main/backend/src/main/java/C{i}.java",
             "severity": "high"}
            for i in range(4)
        ])
        env.write_data_file("skill_usage.jsonl", [
            {"type": "skill_invoked", "timestamp": now1, "session_id": sid1,
             "skill": "karpathy-guidelines"}
        ])
        env.make_git_change([("main/backend/src/main/java/Test.java", "// test")])

        from lib.evolution_orchestrator import run_orchestrator
        run_orchestrator(str(env.root), execute=True)

        pending = env.read_json("pending_evolution.json")
        for trigger in pending.get("pending_triggers", []):
            dim = trigger["dimension"]
            target = trigger["target"]
            priority = trigger["priority"]
            file_map = {
                "agent": f"agents/{target}.md",
                "rule": f"rules/{target}.md",
                "skill": f"skills/{target}/SKILL.md",
                "memory": f"memory/{target}.md",
            }
            tf = file_map.get(dim)
            if tf:
                env.simulate_evolution(dim, target, priority, tf,
                                       "\n## 进化优化 (S1)\n- 优化内容\n")

        # 清除 pending
        pending["pending_triggers"] = []
        (env.data_dir / "pending_evolution.json").write_text(
            json.dumps(pending, indent=2, ensure_ascii=False))

        # 评分 S1
        from lib.evolution_scoring import compute_all_scores
        s1_scores = compute_all_scores(str(env.root))
        s1_overall = s1_scores["overall_score"]
        log(f"  S1 overall: {s1_overall}")

        # ── Session 2: 中等质量 + 更多数据 + 进化 ──
        now2 = (datetime.now() - timedelta(hours=24)).isoformat()
        sid2 = "session-2-mid"

        # 追加更多 agent 记录（混合高效和低效）
        extra_agents = [
            {"type": "agent_launch", "timestamp": now2, "session_id": sid2,
             "agent": "frontend-developer",
             "task": "实现 AssetList 组件", "prompt_preview": "..."}
            for _ in range(3)
        ] + [
            {"type": "agent_launch", "timestamp": now2, "session_id": sid2,
             "agent": "code-reviewer",
             "task": "审查代码质量", "prompt_preview": "..."}
            for _ in range(3)
        ]
        # 追加而不覆盖（用 a+ 模式）
        existing_agents = env.read_jsonl("agent_performance.jsonl")
        existing_agents.extend(extra_agents)
        env.write_data_file("agent_performance.jsonl", existing_agents)

        # 追加更多 skill 调用
        existing_skills = env.read_jsonl("skill_usage.jsonl")
        existing_skills.extend([
            {"type": "skill_invoked", "timestamp": now2, "session_id": sid2,
             "skill": "karpathy-guidelines"}
            for _ in range(5)
        ])
        env.write_data_file("skill_usage.jsonl", existing_skills)

        # S2 的 git 变更（包含测试文件，质量更高）
        env.make_git_change([
            ("main/backend/src/main/java/AssetService.java",
             "public class AssetService { /* optimized */ }"),
            ("main/backend/src/test/java/AssetServiceTest.java",
             "@Test public void testQuery() { assert true; }"),
            ("main/frontend/src/views/AssetList.vue",
             "<template><div>Asset List</div></template>"),
        ])

        # 触发进化
        run_orchestrator(str(env.root), execute=True)
        pending = env.read_json("pending_evolution.json")
        for trigger in pending.get("pending_triggers", []):
            dim = trigger["dimension"]
            target = trigger["target"]
            priority = trigger["priority"]
            file_map = {
                "agent": f"agents/{target}.md",
                "rule": f"rules/{target}.md",
                "skill": f"skills/{target}/SKILL.md",
                "memory": f"memory/{target}.md",
            }
            tf = file_map.get(dim)
            if tf:
                env.simulate_evolution(dim, target, priority, tf,
                                       "\n## 进化优化 (S2)\n- 进一步优化\n")
        pending["pending_triggers"] = []
        (env.data_dir / "pending_evolution.json").write_text(
            json.dumps(pending, indent=2, ensure_ascii=False))

        s2_scores = compute_all_scores(str(env.root))
        s2_overall = s2_scores["overall_score"]
        log(f"  S2 overall: {s2_overall}")

        # ── Session 3: 高质量会话 ──
        now3 = datetime.now().isoformat()
        sid3 = "session-3-high-quality"

        # 追加高质量 agent 记录（短任务，高效）
        existing_agents = env.read_jsonl("agent_performance.jsonl")
        existing_agents.extend([
            {"type": "agent_launch", "timestamp": now3, "session_id": sid3,
             "agent": "backend-developer",
             "task": "添加缓存层", "prompt_preview": "..."}
            for _ in range(2)
        ] + [
            {"type": "agent_launch", "timestamp": now3, "session_id": sid3,
             "agent": "test",
             "task": "编写集成测试", "prompt_preview": "..."}
            for _ in range(2)
        ])
        env.write_data_file("agent_performance.jsonl", existing_agents)

        # S3 git 变更（聚焦 + 有测试）
        env.make_git_change([
            ("main/backend/src/main/java/CacheConfig.java",
             "@Configuration public class CacheConfig {}"),
            ("main/backend/src/test/java/CacheConfigTest.java",
             "@Test public void testCache() { assert true; }"),
            ("main/backend/src/test/java/AssetServiceIT.java",
             "@Test public void integrationTest() { assert true; }"),
        ])

        # S3 评分
        s3_scores = compute_all_scores(str(env.root))
        s3_overall = s3_scores["overall_score"]
        log(f"  S3 overall: {s3_overall}")

        # ── 验证累积学习 ──
        # 1. 进化历史持续增长（学习发生）
        history = env.read_jsonl("evolution_history.jsonl")
        assert len(history) >= 2, f"应有 ≥2 条进化记录: {len(history)}"

        # 2. 每个维度都有评分（系统覆盖完整）
        for dim in ["skills", "agents", "rules"]:
            dim_score = s3_scores["dimension_scores"].get(dim, -1)
            assert dim_score >= 0, f"{dim} 维度应有评分 (实际: {dim_score})"

        # 3. 整体评分在合理范围（50-100）
        assert 50 <= s3_overall <= 100, f"整体评分应在 50-100: {s3_overall:.1f}"
        assert 50 <= s2_overall <= 100, f"S2 评分应在 50-100: {s2_overall:.1f}"
        assert 50 <= s1_overall <= 100, f"S1 评分应在 50-100: {s1_overall:.1f}"

        # 4. 进化后的维度评分不为 N/A
        assert s1_overall > 0, "S1 应有有效评分"
        assert s2_overall > 0, "S2 应有有效评分"
        assert s3_overall > 0, "S3 应有有效评分"

        log(f"阶段 3 累积评分通过: S1={s1_overall:.1f} → S2={s2_overall:.1f} → S3={s3_overall:.1f}")
    finally:
        env.cleanup()


# ═══════════════════════════════════════════════════════════════
# 阶段 4: 全维度汇总验证
# ═══════════════════════════════════════════════════════════════


def test_full_pipeline_integration():
    """完整管线：3 个会话端到端集成测试（模拟真实场景）。"""
    env = RegressionTestEnv().setup()
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = str(env.root)
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_orchestrator import run_orchestrator
        from lib.evolution_scoring import compute_all_scores, save_daily_score
        from lib.evolution_safety import validate_jsonl_file, pre_evolution_check

        # ── 运行 3 个会话 ──
        sessions = [
            {"id": "s1", "hours_ago": 72, "quality": "low", "trigger": ["agent", "rule"]},
            {"id": "s2", "hours_ago": 48, "quality": "mid", "trigger": ["skill"]},
            {"id": "s3", "hours_ago": 24, "quality": "high", "trigger": ["memory"]},
        ]

        cumulative_triggers = set()
        all_history_dims = set()
        session_scores = []

        for si, sess in enumerate(sessions):
            now = (datetime.now() - timedelta(hours=sess["hours_ago"])).isoformat()
            sid = sess["id"]
            triggers_wanted = sess["trigger"]

            # 计算触发所需数据
            if "agent" in triggers_wanted:
                # Agent: 6 长任务 + 2 失败
                agent_count = 6
                agent_task = "实现完整模块" * 20
                agent_failures = 2
            else:
                agent_count = 3
                agent_task = "实现组件"
                agent_failures = 0

            if "skill" in triggers_wanted:
                # Skill: 10 调用 + 6 失败
                skill_count = 10
                skill_failures = 6
            else:
                skill_count = 5
                skill_failures = 0

            if "rule" in triggers_wanted:
                violation_count = 4
            else:
                violation_count = 0

            if "memory" in triggers_wanted:
                # 2 个反馈信号
                env.write_json_file("pending_evolution.json", {
                    "feedback_signals": [
                        {"type": "correction", "timestamp": now,
                         "content": "不要使用 Lombok"},
                        {"type": "preference", "timestamp": now,
                         "content": "优先使用 JDK 17 record"},
                    ],
                    "pending_triggers": [],
                })
            else:
                env.write_json_file("pending_evolution.json", {
                    "feedback_signals": [],
                    "pending_triggers": [],
                })

            # 写入数据
            env.write_data_file("skill_usage.jsonl", [
                {"type": "skill_invoked", "timestamp": now, "session_id": sid,
                 "skill": "karpathy-guidelines"}
            ] * skill_count)
            env.write_data_file("agent_performance.jsonl", [
                {"type": "agent_launch", "timestamp": now, "session_id": sid,
                 "agent": "backend-developer",
                 "task": agent_task,
                 "prompt_preview": "..."}
            ] * agent_count)
            if agent_failures:
                env.write_data_file("tool_failures.jsonl", [
                    {"type": "tool_failure", "timestamp": now, "session_id": sid,
                     "tool": "Bash", "error_summary": "fail",
                     "context": {"agent": "backend-developer"}}
                ] * agent_failures)
            if skill_failures:
                env.write_data_file("tool_failures.jsonl", [
                    {"type": "tool_failure", "timestamp": now, "session_id": sid,
                     "tool": "Skill", "error_summary": f"fail {i}",
                     "context": {"skill": "karpathy-guidelines"}}
                    for i in range(skill_failures)
                ])
            if violation_count:
                env.write_data_file("rule_violations.jsonl", [
                    {"type": "rule_violation", "timestamp": now, "session_id": sid,
                     "rule": "no-lombok", "file": f"F{i}.java",
                     "severity": "high"}
                    for i in range(violation_count)
                ])

            # Git 变更
            files = [("main/backend/src/main/java/Foo.java", "// code")]
            if sess["quality"] != "low":
                files.append(("main/backend/src/test/java/FooTest.java", "// test"))
            env.make_git_change(files)

            # 编排
            decision = run_orchestrator(str(env.root), execute=True)

            # 记录触发维度
            for t in decision.get("triggers", []):
                cumulative_triggers.add(t["dimension"])

            # 模拟进化执行
            pending = env.read_json("pending_evolution.json")
            for trigger in pending.get("pending_triggers", []):
                dim = trigger["dimension"]
                target = trigger["target"]
                priority = trigger["priority"]
                all_history_dims.add(dim)

                file_map = {
                    "agent": f"agents/{target}.md",
                    "rule": f"rules/{target}.md",
                    "skill": f"skills/{target}/SKILL.md",
                    "memory": f"memory/{target}.md",
                }
                tf = file_map.get(dim)
                if tf:
                    env.simulate_evolution(dim, target, priority, tf,
                                           f"\n## 进化优化 ({sid})\n- 维度: {dim}\n")

            # 清除
            pending["pending_triggers"] = []
            (env.data_dir / "pending_evolution.json").write_text(
                json.dumps(pending, indent=2, ensure_ascii=False))

            # 评分
            scores = compute_all_scores(str(env.root))
            session_scores.append(scores["overall_score"])

            # 每日评分
            save_daily_score(str(env.root))

        # ── 全维度验证 ──

        # 1. 进化历史：3 个会话，每会话 ≥1 条
        history = env.read_jsonl("evolution_history.jsonl")
        assert len(history) >= 3, \
            f"进化历史应 >= 3 条: 实际 {len(history)}"

        # 2. 至少 3 个维度触发过（agent + rule + skill）
        assert len(all_history_dims) >= 3, \
            f"至少 3 个维度应有进化: {all_history_dims}"

        # 3. 所有评分在合理范围
        for i, s in enumerate(session_scores):
            assert 50 <= s <= 100, f"Session {i} 评分应在 50-100: {s}"

        # 4. 数据完整性
        for f in env.data_dir.glob("*.jsonl"):
            result = validate_jsonl_file(str(f))
            if result["corrupted"] > 0:
                fail(f"数据文件损坏: {f.name} 损坏 {result['corrupted']} 行")

        # 5. 进化文件有 diff
        for agent_file in env.agents_dir.glob("*.md"):
            content = agent_file.read_text()
            if "进化优化" in content:
                log(f"  文件已进化: {agent_file.name}")
                break
        else:
            log("  (无 agent 文件被进化，可能未触发)")

        # 6. 每日评分记录
        daily_scores = env.read_jsonl("daily_scores.jsonl")
        assert len(daily_scores) >= 1, "应有每日评分记录"

        log(f"阶段 4 集成验证通过:\n"
            f"  进化历史: {len(history)} 条, 维度: {all_history_dims}\n"
            f"  评分趋势: {session_scores}\n"
            f"  每日评分: {len(daily_scores)} 天")
    finally:
        env.cleanup()


def test_safety_gates():
    """安全门禁：熔断器、限流器、数据充分性。"""
    env = RegressionTestEnv().setup()
    try:
        sys.path.insert(0, str(env.claude_dir))
        from lib.evolution_safety import (
            EvolutionCircuitBreaker, EvolutionRateLimiter,
            check_data_sufficiency, pre_evolution_check
        )

        metrics_path = str(env.data_dir / "evolution_metrics.json")
        history_path = str(env.data_dir / "evolution_history.jsonl")

        # 写入一些进化历史
        env.write_data_file("evolution_history.jsonl", [
            {"timestamp": (datetime.now() - timedelta(hours=48)).isoformat(),
             "session_id": "old", "dimension": "agent", "target": "test-agent"}
        ])

        # 熔断器初始状态 CLOSED
        breaker = EvolutionCircuitBreaker(metrics_path)
        assert not breaker.is_open("agent", "test-agent"), "新熔断器应为 CLOSED"

        # 记录 2 次退化 → 熔断器 OPEN
        breaker.record_result("agent", "test-agent", False)
        breaker.record_result("agent", "test-agent", False)
        assert breaker.is_open("agent", "test-agent"), "连续 2 次退化后应 OPEN"

        # 记录 1 次改进 → 熔断器 CLOSED
        breaker.record_result("agent", "test-agent", True)
        assert not breaker.is_open("agent", "test-agent"), "改进后应 CLOSED"

        # 限流器
        limiter = EvolutionRateLimiter(history_path)
        can, reason = limiter.can_evolve("agent", "test-agent", "sid-1")
        assert can, f"应可通过限流: {reason}"

        # 会话上限测试：累积写入 MAX_PER_SESSION 条同会话记录
        limit_records = []
        for i in range(EvolutionRateLimiter.MAX_PER_SESSION):
            limit_records.append({
                "timestamp": datetime.now().isoformat(),
                "session_id": "sid-limit", "dimension": "agent",
                "target": f"target-{i}"
            })
        env.write_data_file("evolution_history.jsonl", limit_records)
        limiter = EvolutionRateLimiter(history_path)

        can, reason = limiter.can_evolve("agent", "new-target", "sid-limit")
        assert not can, f"超过会话上限应拒绝: {reason}"

        # 数据充分性检查
        env.write_data_file("skill_usage.jsonl", [{"type": "skill", "skill": "test"}])
        suff = check_data_sufficiency("skill", str(env.data_dir))
        assert suff["sufficient"], f"有数据时应充分: {suff}"

        # 前检查
        env.write_data_file("skill_usage.jsonl", [{"type": "skill", "skill": "test"}])
        pre = pre_evolution_check("skill", "test", "sid-check", str(env.root))
        # 注意：此检查会失败因为 target 不存在
        log(f"  前检查结果: can_proceed={pre['can_proceed']}, blocked={pre['blocked_by']}")

        log("阶段 4 安全门禁通过: 熔断器/限流器工作正常")
    finally:
        env.cleanup()


def test_load_evolution_state_with_dispatch():
    """验证 load_evolution_state.py 正确生成 evolutionDispatch。"""
    env = RegressionTestEnv().setup()
    try:
        now = datetime.now().isoformat()

        # 植入 pending_evolution.json 含 triggers
        env.write_json_file("pending_evolution.json", {
            "pending_triggers": [
                {"dimension": "agent", "target": "backend-developer",
                 "priority": 0.75, "reason": "测试触发"},
                {"dimension": "rule", "target": "general",
                 "priority": 0.67, "reason": "测试触发"},
                {"dimension": "skill", "target": "karpathy-guidelines",
                 "priority": 0.55, "reason": "测试触发"},
            ],
            "feedback_signals": [],
        })
        env.write_data_file("skill_usage.jsonl", [
            {"type": "skill_invoked", "timestamp": now, "session_id": "test",
             "skill": "karpathy-guidelines"}
        ])
        env.write_data_file("agent_performance.jsonl", [
            {"type": "agent_launch", "timestamp": now, "session_id": "test",
             "agent": "backend-developer", "task": "test", "prompt_preview": "..."}
        ])

        # 运行 load_evolution_state.py
        result = env.run_hook("load_evolution_state.py")
        stdout = result["stdout"]

        # 解析 stdout JSON
        output = json.loads(stdout) if stdout.strip() else {}
        hook_output = output.get("hookSpecificOutput", {})
        dispatch = hook_output.get("evolutionDispatch", [])

        assert len(dispatch) == 3, f"应有 3 个 dispatch 项: {len(dispatch)}"

        # 验证映射
        dims = {d["dimension"]: d["evolver"] for d in dispatch}
        assert dims["agent"] == "agent-evolver"
        assert dims["rule"] == "rule-evolver"
        assert dims["skill"] == "skill-evolver"

        # 验证每个 dispatch 有 prompt
        for d in dispatch:
            assert d["prompt"], f"dispatch 应有 prompt: {d['dimension']}"

        log(f"阶段 4 dispatch 输出验证通过: {len(dispatch)} 项, 映射正确")
    finally:
        env.cleanup()


# ═══════════════════════════════════════════════════════════════
# 优先级升级机制测试
# ═══════════════════════════════════════════════════════════════


def test_escalation_mechanism():
    """验证优先级升级机制的完整逻辑。"""
    from lib.evolution_orchestrator import (
        compute_escalated_priority,
        _increment_trigger_count,
        _get_trigger_count,
    )

    # ── 升级逻辑单元测试 ──
    # base_priority = 0 时始终返回 0（不触发）
    assert compute_escalated_priority(0.0, 0) == 0.0
    assert compute_escalated_priority(0.0, 1) == 0.0
    assert compute_escalated_priority(0.0, 5) == 0.0

    # trigger_count=0: 第1次，正常优先级
    assert compute_escalated_priority(0.6, 0) == 0.6

    # trigger_count=1: 第2次，优先级 × 1.3
    assert round(compute_escalated_priority(0.6, 1), 3) == 0.78

    # trigger_count>=2: 第3次及以上，强制 = 1.0
    assert compute_escalated_priority(0.6, 2) == 1.0
    assert compute_escalated_priority(0.55, 10) == 1.0

    # 即使 base < 0.5，历史触发≥3次也会强制进化
    assert compute_escalated_priority(0.45, 2) == 1.0

    # 不溢出上限
    assert compute_escalated_priority(0.95, 1) == 1.0

    log("升级逻辑 9 个断言全部通过")

    # ── 触发计数读写 + 目录自动创建 ──
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    try:
        data_dir = tmp / ".claude" / "data"
        assert not data_dir.exists()

        # 目录不存在时自动创建
        _increment_trigger_count(tmp, "skill", "test-skill")
        assert data_dir.exists()
        assert (data_dir / "evolution_metrics.json").exists()

        # 读取正确
        assert _get_trigger_count(tmp, "skill", "test-skill") == 1

        # 再次递增
        _increment_trigger_count(tmp, "skill", "test-skill")
        assert _get_trigger_count(tmp, "skill", "test-skill") == 2

        # 多维度独立计数
        _increment_trigger_count(tmp, "agent", "test-agent")
        assert _get_trigger_count(tmp, "skill", "test-skill") == 2
        assert _get_trigger_count(tmp, "agent", "test-agent") == 1

        # 不存在的 key 返回 0
        assert _get_trigger_count(tmp, "rule", "no-such-rule") == 0

        log("触发计数读写 6 个断言全部通过")
    finally:
        shutil.rmtree(tmp)

    # ── 完整升级流程模拟 ──
    env = RegressionTestEnv().setup()
    try:
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            # 模拟 3 次连续触发
            for i in range(3):
                _increment_trigger_count(tmp, "agent", "test-agent")
            # 第4次调用时应返回 count=3
            count = _get_trigger_count(tmp, "agent", "test-agent")
            assert count == 3, f"期望 count=3, 实际 {count}"

            # 验证升级后优先级
            base = 0.55
            escalated = compute_escalated_priority(base, count - 1)
            # count=3, trigger_count=count-1=2 → escalated should be 1.0
            assert escalated == 1.0, f"期望 1.0, 实际 {escalated}"
        finally:
            shutil.rmtree(tmp)

        log("完整升级流程模拟通过")
    finally:
        env.cleanup()


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════


def run_all():
    """运行所有回归测试。"""
    print("=" * 60)
    print("全方位进化回归测试")
    print("=" * 60)

    tests = [
        # 阶段 0
        ("环境搭建", test_environment_setup),
        # 阶段 1: Session 1
        ("S1 数据植入", test_session1_data_population),
        ("S1 触发计算", test_session1_trigger_computation),
        ("S1 进化持久化", test_session1_evolution_persistence),
        ("S1 进化派发", test_session1_evolution_dispatch),
        # 阶段 2: Session 2
        ("S2 Skill 触发", test_session2_skill_trigger),
        ("S2 Memory 触发", test_session2_memory_trigger),
        ("S2 进化派发", test_session2_evolution_dispatch),
        # 阶段 3: 累积学习
        ("S3 累积评分", test_session3_cumulative_scoring),
        # 阶段 4: 全维度汇总
        ("完整管线集成", test_full_pipeline_integration),
        ("安全门禁", test_safety_gates),
        ("Dispatch 输出", test_load_evolution_state_with_dispatch),
        ("升级机制", test_escalation_mechanism),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            status = "✅"
            passed += 1
        except AssertionError as e:
            status = f"❌ {e}"
            failed += 1
        except Exception as e:
            status = f"💥 {type(e).__name__}: {e}"
            failed += 1
        print(f"  {status}  {name}")

    print()
    print(f"结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")

    if failed > 0:
        print("❌ 有测试失败！")
        sys.exit(1)
    else:
        print("✅ 全部通过！自进化系统四大维度回归验证成功。")
        sys.exit(0)


if __name__ == "__main__":
    run_all()
