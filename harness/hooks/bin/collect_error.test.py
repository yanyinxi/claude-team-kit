#!/usr/bin/env python3
"""
collect-error.py 测试套件
TDD 流程: RED → GREEN → REFACTOR
"""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


# ── 测试辅助 ──────────────────────────────────────────────────────────────────

class TempProject:
    """临时项目目录，模拟 <project>/.claude/data/ 结构"""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="chk-test-")
        self.root = Path(self.tmp)
        self.data_dir = self.root / ".claude" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 设置环境变量
        self._orig_env = {}
        self._set_env("CLAUDE_PROJECT_DIR", str(self.root))
        self._set_env("CLAUDE_SESSION_ID", f"test-{self.root.name}")
        self._set_env("CLAUDE_MODE", "team")
        self._set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")

    def _set_env(self, key, value):
        self._orig_env[key] = os.environ.get(key)
        os.environ[key] = value

    def cleanup(self):
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)


# ── 测试用例 ──────────────────────────────────────────────────────────────────

def test_collect_tool_failure_basic():
    """✓ 收集工具执行失败"""
    import collect_error

    proj = TempProject()
    try:
        # 模拟 stdin 输入
        hook_data = {
            "tool_name": "Bash",
            "error": "command failed with exit code 1",
            "tool_input": {"command": "ls -la"},
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        assert record["type"] == "tool_failure", f"type: {record['type']}"
        assert record["tool"] == "Bash", f"tool: {record['tool']}"
        assert record["error"] == "command failed with exit code 1"
        assert "timestamp" in record
        assert "context" in record
        assert record["context"]["mode"] == "team"

        print("  ✓ test_collect_tool_failure_basic PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_error_source_traceable():
    """✓ source 字段可溯源到 CHK 源码"""
    import collect_error

    proj = TempProject()
    try:
        hook_data = {
            "tool_name": "Write",
            "error": "Permission denied",
            "tool_input": {"file_path": "/tmp/test.txt"},
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        # source 应该指向 hooks/bin 目录
        assert "hooks/bin/" in record["source"], f"source 应包含 'hooks/bin/'，实际: {record['source']}"
        # 格式应为: hooks/bin/xxx.py:行号
        assert ":" in record["source"], f"source 应包含 ':' 行号分隔符"

        print(f"  ✓ test_error_source_traceable (source={record['source']}) PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_sensitive_data_sanitized():
    """✓ 敏感数据被脱敏"""
    import collect_error

    proj = TempProject()
    try:
        hook_data = {
            "tool_name": "Bash",
            "error": "Auth failed",
            "tool_input": {
                "command": "curl -H 'Authorization: Bearer sk-xxx'",
                "api_key": "sk-ant-secret123",
            },
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        tool_input = record["context"]["tool_input"]
        assert tool_input.get("api_key") == "[REDACTED]", f"api_key 应被脱敏: {tool_input}"
        assert "sk-ant" not in str(tool_input), "敏感内容不应出现在 tool_input 中"

        print("  ✓ test_sensitive_data_sanitized PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_recent_tools_context():
    """✓ 从 sessions.jsonl 补全 recent_tools"""
    import collect_error

    proj = TempProject()
    try:
        # 创建 sessions.jsonl
        sessions_file = proj.data_dir / "sessions.jsonl"
        sessions_file.write_text(json.dumps({
            "session_id": "test-session",
            "recent_tools": ["Read", "Edit", "Bash", "Write", "Grep"],
        }) + "\n")

        hook_data = {"tool_name": "Bash", "error": "failed"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        assert "recent_tools" in record["context"]
        assert record["context"]["recent_tools"] == ["Read", "Edit", "Bash", "Write", "Grep"]

        print("  ✓ test_recent_tools_context PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_agents_skills_tracked():
    """✓ agents 和 skills 被正确追踪"""
    import collect_error

    proj = TempProject()
    try:
        # 创建 agent_calls.jsonl 和 skill_calls.jsonl（一次性写入，避免覆盖）
        agent_calls = proj.data_dir / "agent_calls.jsonl"
        agent_calls.write_text(
            json.dumps({"agent": "executor", "task": "fix bug"}) + "\n" +
            json.dumps({"agent": "code-reviewer", "task": "review"}) + "\n"
        )

        skill_calls = proj.data_dir / "skill_calls.jsonl"
        skill_calls.write_text(json.dumps({"skill": "security-audit", "result": "passed"}) + "\n")

        hook_data = {"tool_name": "Agent", "error": "timeout"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        assert "executor" in record["context"]["agents_used"]
        assert "code-reviewer" in record["context"]["agents_used"]
        assert "security-audit" in record["context"]["skills_used"]

        print("  ✓ test_agents_skills_tracked PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_main_writes_to_error_jsonl():
    """✓ main() 正确写入 error.jsonl"""
    import collect_error
    from error_writer import write_error

    proj = TempProject()
    try:
        hook_data = {
            "tool_name": "Read",
            "error": "File not found",
            "tool_input": {"file_path": "/nonexistent.txt"},
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        # 捕获 stdout
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        collect_error.main()

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        result = json.loads(output)
        assert result["collected"] is True, f"应返回 collected=True: {result}"

        # 验证 error.jsonl 被创建
        error_file = proj.data_dir / "error.jsonl"
        assert error_file.exists(), "error.jsonl 应被创建"

        lines = error_file.read_text().strip().splitlines()
        assert len(lines) >= 1, "应至少写入一行"

        record = json.loads(lines[-1])
        assert record["type"] == "tool_failure"
        assert record["tool"] == "Read"

        print("  ✓ test_main_writes_to_error_jsonl PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_chk_internal_error_collection():
    """✓ CHK 自身错误被正确收集"""
    import collect_error

    proj = TempProject()
    try:
        error_detail = "Traceback (most recent call last):\n  File 'hooks/bin/collect-error.py', line 42\n    raise ValueError('test error')\nValueError: test error"

        record = collect_error.collect_chk_internal_error(error_detail)

        assert record["type"] == "tool_failure"  # 使用 TOOL_FAILURE 作为默认
        assert record["error"] == "CHK internal error"
        assert "Traceback" in record.get("error_detail", "")
        assert "hooks/bin/" in record["source"]

        print("  ✓ test_chk_internal_error_collection PASS")
    finally:
        proj.cleanup()


def test_hook_event_in_metadata():
    """✓ hook_event 被正确记录到 metadata"""
    import collect_error

    proj = TempProject()
    try:
        os.environ["CLAUDE_HOOK_EVENT"] = "PostToolUseFailure"

        hook_data = {"tool_name": "Bash", "error": "failed"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        assert record["metadata"]["hook_event"] == "PostToolUseFailure"

        print("  ✓ test_hook_event_in_metadata PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__
        os.environ.pop("CLAUDE_HOOK_EVENT", None)


def test_error_type_classification():
    """✓ 错误类型分类正确"""
    import collect_error
    from error_writer import ErrorType

    proj = TempProject()
    try:
        os.environ["CLAUDE_HOOK_EVENT"] = "PostToolUseFailure"
        hook_data = {"tool_name": "Edit", "error": "Invalid JSON"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_error.collect_tool_failure()

        # PostToolUseFailure 事件 → tool_failure 类型
        assert record["type"] == ErrorType.TOOL_FAILURE
        assert record["metadata"]["hook_event"] == "PostToolUseFailure"

        print("  ✓ test_error_type_classification PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


def test_multiple_failures_in_session():
    """✓ 同一会话多次失败都被记录"""
    import collect_error

    proj = TempProject()
    try:
        # 模拟多次工具失败
        for i in range(3):
            hook_data = {
                "tool_name": "Bash",
                "error": f"Failure #{i}",
                "tool_input": {"command": f"cmd_{i}"},
            }
            sys.stdin = __import__("io").StringIO(json.dumps(hook_data))
            record = collect_error.collect_tool_failure()
            collect_error.write_error(record)

        # 验证所有错误都被记录
        error_file = proj.data_dir / "error.jsonl"
        lines = error_file.read_text().strip().splitlines()
        assert len(lines) == 3, f"应记录 3 条错误，实际 {len(lines)}"

        errors = [json.loads(line)["error"] for line in lines]
        assert "Failure #0" in errors
        assert "Failure #1" in errors
        assert "Failure #2" in errors

        print("  ✓ test_multiple_failures_in_session PASS")
    finally:
        proj.cleanup()
        sys.stdin = sys.__stdin__


# ── 测试运行器 ────────────────────────────────────────────────────────────────

def run_all_tests():
    tests = [
        test_collect_tool_failure_basic,
        test_error_source_traceable,
        test_sensitive_data_sanitized,
        test_recent_tools_context,
        test_agents_skills_tracked,
        test_main_writes_to_error_jsonl,
        test_chk_internal_error_collection,
        test_hook_event_in_metadata,
        test_error_type_classification,
        test_multiple_failures_in_session,
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("  collect-error.py 测试套件")
    print("=" * 60)

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: 意外错误 - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("-" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
