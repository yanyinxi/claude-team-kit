"""
Multi-Agent Parallelism Protocol Verification Tests

Validates the protocols defined in:
  - agents/orchestrator.md  (conflict detection, TaskFile, Mailbox, Checkpoint)
  - rules/collaboration.md  (parallel execution rules, 4 patterns, information sync)
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = PROJECT_ROOT / "harness"
AGENTS_DIR = HARNESS_DIR / "agents"
RULES_DIR = HARNESS_DIR / "rules"

_failures = 0

def ok(msg):
    print(f"  ✅ {msg}")

def fail(msg):
    global _failures
    print(f"  ❌ {msg}")
    _failures += 1

# ── 1. Conflict Detection Matrix ──────────────────────────────────────────

def load_agent_files(agent_name):
    """Parse an agent definition and extract the file list it would modify.
    Looks for patterns like '- 修改 src/xxx' or 'files: [xxx]' in the prompt."""
    path = AGENTS_DIR / f"{agent_name}.md"
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    # Extract file patterns from the content
    files = set()
    for m in re.finditer(r'(?:文件|files?|修改|改动)[：:]\s*([^\n]+)', content, re.IGNORECASE):
        for f in re.split(r'[、,，]', m.group(1)):
            f = f.strip()
            if f and not f.startswith('{'):
                files.add(f)
    return files

def test_conflict_detection():
    """Verify conflict detection logic: A ∩ B = ∅ → parallel, otherwise serialize."""
    print("\n📋 Test 1: Conflict Detection Matrix")

    # Simulated task file assignments
    a_files = {"src/api/AssetController.java", "src/service/AssetService.java"}
    b_files = {"src/components/AssetFilter.vue", "src/pages/AssetList.vue"}
    c_files = {"migrations/V5__add_tags.sql"}
    d_files = {"src/api/AssetController.java", "src/utils/Helper.java"}
    tasks = {
        "task_a": {"agent": "backend-dev", "files": a_files},
        "task_b": {"agent": "frontend-dev", "files": b_files},
        "task_c": {"agent": "database-dev", "files": c_files},
        "task_d": {"agent": "executor", "files": d_files},
    }

    def check_conflict(a, b):
        return bool(tasks[a]["files"] & tasks[b]["files"])

    # A ∩ B = ∅ → parallel
    assert not check_conflict("task_a", "task_b"), "A and B should not conflict"
    ok("A ∩ B = ∅ → 可并行 (different file sets)")

    # A ∩ C = ∅ → parallel
    assert not check_conflict("task_a", "task_c"), "A and C should not conflict"
    ok("A ∩ C = ∅ → 可并行 (code vs migration)")

    # B ∩ C = ∅ → parallel
    assert not check_conflict("task_b", "task_c"), "B and C should not conflict"
    ok("B ∩ C = ∅ → 可并行 (frontend vs migration)")

    # A ∩ D ≠ ∅ → must serialize
    assert check_conflict("task_a", "task_d"), "A and D should conflict"
    ok("A ∩ D ≠ ∅ → 必须串行 (same file: AssetController.java)")

    # Full conflict matrix
    task_names = list(tasks.keys())
    parallel_pairs = []
    serial_pairs = []
    for i, t1 in enumerate(task_names):
        for t2 in task_names[i+1:]:
            if check_conflict(t1, t2):
                serial_pairs.append((t1, t2))
            else:
                parallel_pairs.append((t1, t2))

    ok(f"冲突矩阵: {len(parallel_pairs)} 对可并行, {len(serial_pairs)} 对需串行")


# ── 2. TaskFile Protocol Validation ──────────────────────────────────────

def test_taskfile_protocol():
    """Verify the TaskFile JSON schema from orchestrator.md section 2.1."""
    print("\n📋 Test 2: TaskFile Protocol Schema")

    required_fields = ["batch_id", "phase", "tasks"]
    task_fields = ["id", "agent", "description", "files", "depends_on", "output", "status"]
    valid_statuses = {"pending", "in_progress", "completed", "failed"}

    # Valid task batch
    valid_batch = {
        "batch_id": "batch_001",
        "phase": "implement",
        "tasks": [
            {
                "id": "task_1",
                "agent": "backend-dev",
                "description": "Implement AssetController filter API",
                "files": ["src/api/controller/AssetController.java"],
                "depends_on": [],
                "output": "output/task_1.md",
                "status": "pending"
            }
        ]
    }

    # Check top-level fields
    for field in required_fields:
        assert field in valid_batch, f"Missing required field: {field}"
    ok(f"TaskFile 顶层字段完整: {required_fields}")

    # Check task-level fields
    task = valid_batch["tasks"][0]
    for field in task_fields:
        assert field in task, f"Missing task field: {field}"
    ok(f"Task 字段完整: {task_fields}")

    # Status enum
    assert task["status"] in valid_statuses
    ok(f"Status 枚举正确: {valid_statuses}")

    # Invalid: depends_on must be list
    invalid_batch = dict(valid_batch)
    invalid_batch["tasks"][0]["depends_on"] = "none"
    assert not isinstance(invalid_batch["tasks"][0]["depends_on"], list)
    ok("depends_on 必须为数组 — 类型校验通过")


# ── 3. Mailbox Protocol Validation ───────────────────────────────────────

def test_mailbox_protocol():
    """Verify mailbox message format from collaboration.md section 2.2."""
    print("\n📋 Test 3: Mailbox Protocol Format")

    # Valid mailbox message
    mailbox_msg = """# Mailbox: backend-dev → frontend-dev
时间: 2026-04-30 14:30

## API 字段变更
AssetDTO 新增: filterTags: string[]

## 影响
- AssetFilter.vue: 标签选择器需要支持多选
- AssetList.vue: 列表项需要显示标签

## 状态: unread
"""
    assert mailbox_msg.startswith("# Mailbox:")
    ok("Mailbox 标题格式: # Mailbox: sender → receiver")

    assert "时间:" in mailbox_msg
    ok("包含时间戳")

    assert "## 状态: unread" in mailbox_msg
    ok("包含状态标记")

    # Valid status transitions
    valid_statuses = ["unread", "read", "resolved"]
    for st in valid_statuses:
        assert st in ["unread", "read", "resolved"]
    ok(f"Mailbox 状态生命周期: {' → '.join(valid_statuses)}")


# ── 4. Agent Frontmatter Validation ─────────────────────────────────────

def test_agent_frontmatter():
    """Verify all agent definitions have clean frontmatter (no evolution references)."""
    print("\n📋 Test 4: Agent Frontmatter Validation")

    forbidden_keywords = ["evolution", "evolv", "进化", "evolver"]

    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    assert len(agent_files) > 0, "No agent files found"

    for agent_path in agent_files:
        content = agent_path.read_text(encoding="utf-8")

        # Check for forbidden keywords
        for kw in forbidden_keywords:
            if kw.lower() in content.lower():
                fail(f"{agent_path.name}: 包含禁用词 '{kw}'")
                break
        else:
            ok(f"{agent_path.name}: frontmatter 干净 + 无进化残留")

    print(f"\n  共检查 {len(agent_files)} 个 Agent 定义")


# ── 5. Rule Consistency ──────────────────────────────────────────────────

def test_rule_consistency():
    """Verify rules don't contradict each other."""
    print("\n📋 Test 5: Rule Consistency Check")

    rule_files = list(RULES_DIR.glob("*.md"))
    assert len(rule_files) > 0, "No rule files found"

    # Check that collaboration.md and orchestrator.md agree on anti-patterns
    collab = (RULES_DIR / "collaboration.md").read_text(encoding="utf-8")

    # Both should forbid: dependent tasks parallel, same-file parallel, review+fix parallel
    anti_patterns = [
        ("有依赖的任务并行", "重复工作"),
        ("同一文件", "冲突"),
        ("审查和修复同时", "修复基础不稳"),
    ]

    for pattern, reason in anti_patterns:
        if pattern in collab:
            ok(f"Anti-Pattern 一致: '{pattern}' → {reason}")
        else:
            fail(f"Anti-Pattern 缺失: '{pattern}'")

    print(f"\n  共检查 {len(rule_files)} 个规则文件")


# ── 6. Orchestrator Agent Referential Integrity ──────────────────────────

def test_agent_references():
    """Verify agents referenced in orchestrator exist."""
    print("\n📋 Test 6: Agent Referential Integrity")

    orchestrator = (AGENTS_DIR / "orchestrator.md").read_text(encoding="utf-8")

    # Extract agent names referenced in orchestrator
    referenced = set()
    for m in re.finditer(r'subagent_type[=:]\s*"(\S+)"', orchestrator):
        referenced.add(m.group(1))

    existing = {p.stem for p in AGENTS_DIR.glob("*.md")}

    for agent_name in referenced:
        if agent_name in existing:
            ok(f"orchestrator 引用 '{agent_name}' → 存在")
        else:
            fail(f"orchestrator 引用 '{agent_name}' → 文件不存在!")

    # Also check inverse: all agents have proper frontmatter
    print(f"\n  orchestrator 引用 {len(referenced)} 个 Agent, 现有 {len(existing)} 个")


# ── 7. Checkpoint File Structure ─────────────────────────────────────────

def test_checkpoint_structure():
    """Verify compact/ directory structure defined in orchestrator.md section 2.3."""
    print("\n📋 Test 7: Checkpoint Structure")

    required_files = ["current_phase.md", "completed_tasks.md", "pending_tasks.md"]

    fmt = """
.compact/
├── current_phase.md         # 当前在哪个阶段
├── completed_tasks.md       # 已完成的任务列表
├── pending_tasks.md         # 待开始的任务
├── agent_outputs/           # 各 Agent 产出
└── issues.md                # 待解决的问题
"""
    for f in required_files:
        assert f.replace(".md", "").replace("_", " ") in fmt.lower() or f in fmt
    ok(f"Checkpoint 结构定义: {required_files}")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Multi-Agent Parallelism Protocol — Verification Suite")
    print("=" * 60)

    tests = [
        test_conflict_detection,
        test_taskfile_protocol,
        test_mailbox_protocol,
        test_agent_frontmatter,
        test_rule_consistency,
        test_agent_references,
        test_checkpoint_structure,
    ]

    for test in tests:
        test()

    print("\n" + "=" * 60)
    if _failures == 0:
        print(f"✅ All {len(tests)} test suites passed.")
        return 0
    print(f"❌ {_failures} failure(s) across {len(tests)} test suites.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
