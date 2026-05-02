#!/usr/bin/env python3
"""
test_error_collection.py — 错误收集系统集成测试

测试场景:
1. 模拟工具执行失败 (PostToolUseFailure)
2. 验证错误被正确记录到 error.jsonl
3. 验证 source 字段可溯源到 CHK 源码
4. 验证并发写入不丢数据
5. 验证敏感数据被脱敏
"""
import json
import os
import sys
import tempfile
import shutil
import threading
from pathlib import Path

# 添加 hooks/bin 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "bin"))


class TestErrorCollection:
    """错误收集系统集成测试"""

    @classmethod
    def setup_class(cls):
        """创建临时测试项目"""
        cls.test_dir = tempfile.mkdtemp(prefix="chk-error-test-")
        cls.project_dir = Path(cls.test_dir) / "test-project"
        cls.project_dir.mkdir()
        cls.data_dir = cls.project_dir / ".claude" / "data"
        cls.data_dir.mkdir(parents=True, exist_ok=True)

        # 设置环境变量
        cls.env_backup = {}
        cls._set_env("CLAUDE_PROJECT_DIR", str(cls.project_dir))
        cls._set_env("CLAUDE_SESSION_ID", "test-session-integration")
        cls._set_env("CLAUDE_MODE", "team")
        cls._set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")

    @classmethod
    def teardown_class(cls):
        """清理测试环境"""
        for key in ["CLAUDE_PROJECT_DIR", "CLAUDE_SESSION_ID", "CLAUDE_MODE", "CLAUDE_HOOK_EVENT"]:
            os.environ.pop(key, None)
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    @staticmethod
    def _set_env(key, value):
        os.environ[key] = value

    def test_error_jsonl_created(self):
        """✓ 错误收集系统创建 error.jsonl"""
        from collect_error import collect_tool_failure, write_error

        hook_data = {
            "tool_name": "Bash",
            "error": "command exited with code 1",
            "tool_input": {"command": "ls /nonexistent"},
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_tool_failure()
        success = write_error(record)

        assert success is True, "write_error 应返回 True"
        assert (self.data_dir / "error.jsonl").exists(), "error.jsonl 应被创建"

        sys.stdin = sys.__stdin__
        print("  ✓ test_error_jsonl_created PASS")

    def test_error_record_structure(self):
        """✓ 错误记录结构完整"""
        from collect_error import collect_tool_failure, write_error

        hook_data = {
            "tool_name": "Read",
            "error": "File not found: /tmp/missing.txt",
            "tool_input": {"file_path": "/tmp/missing.txt"},
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_tool_failure()
        write_error(record)

        # 读取验证（读取最后一行，因为前面的测试也写入了）
        with open(self.data_dir / "error.jsonl") as f:
            lines = f.readlines()
            error = json.loads(lines[-1])

        # 验证必需字段
        assert "timestamp" in error
        assert error["type"] == "tool_failure"
        assert "hooks/bin/" in error["source"]
        assert error["tool"] == "Read"
        assert error["context"]["mode"] == "team"
        assert error["context"]["session_id"] == "test-session-integration"

        sys.stdin = sys.__stdin__
        print("  ✓ test_error_record_structure PASS")

    def test_source_traceability(self):
        """✓ source 字段可溯源到 CHK 源码"""
        from collect_error import collect_tool_failure, write_error

        hook_data = {"tool_name": "Edit", "error": "permission denied"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_tool_failure()

        # source 应指向 hooks/bin/collect_error.py:行号
        assert ":" in record["source"], "source 应包含行号"
        assert "collect_error.py" in record["source"], "source 应指向 collect_error.py"

        sys.stdin = sys.__stdin__
        print(f"  ✓ test_source_traceability (source={record['source']}) PASS")

    def test_sensitive_data_redaction(self):
        """✓ 敏感数据被正确脱敏"""
        from collect_error import collect_tool_failure, write_error

        hook_data = {
            "tool_name": "Bash",
            "error": "auth failed",
            "tool_input": {
                "command": "curl -H 'Authorization: Bearer sk-xxx' https://api.example.com",
                "api_key": "sk-ant-secret123456",
                "password": "SuperSecret123",
            },
        }
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_tool_failure()
        write_error(record)

        # 读取验证
        with open(self.data_dir / "error.jsonl") as f:
            lines = f.readlines()
            error = json.loads(lines[-1])

        tool_input = error["context"]["tool_input"]
        assert tool_input.get("api_key") == "[REDACTED]", "api_key 应被脱敏"
        assert tool_input.get("password") == "[REDACTED]", "password 应被脱敏"
        assert "sk-ant" not in str(tool_input), "敏感内容不应出现"

        sys.stdin = sys.__stdin__
        print("  ✓ test_sensitive_data_redaction PASS")

    def test_concurrent_writes(self):
        """✓ 并发写入 100 条错误不丢数据"""
        threads = []
        errors_written = []
        lock = threading.Lock()

        def write_error_thread(index):
            # 在线程序列化 hook_data
            hook_json = json.dumps({
                "tool_name": "Bash",
                "error": f"Concurrent error #{index}",
                "tool_input": {"command": f"cmd_{index}"},
            })
            # 直接构建 record，不依赖 stdin
            from collect_error import collect_tool_failure
            from error_writer import write_error
            import io
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(hook_json)
            try:
                record = collect_tool_failure()
                success = write_error(record)
            finally:
                sys.stdin = old_stdin
            with lock:
                errors_written.append(success)

        # 并发写入 100 条
        for i in range(100):
            t = threading.Thread(target=write_error_thread, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 验证
        assert all(errors_written), "所有写入都应成功"

        with open(self.data_dir / "error.jsonl") as f:
            lines = f.readlines()

        # 应该有 100 + 前面测试的 4 条
        assert len(lines) >= 100, f"应有至少 100 条错误记录，实际 {len(lines)}"

        print(f"  ✓ test_concurrent_writes ({len(lines)} records) PASS")

    def test_error_type_classification(self):
        """✓ 错误类型分类正确"""
        from collect_error import collect_tool_failure, collect_chk_internal_error
        from error_writer import write_error, ErrorType

        # 测试 tool_failure
        hook_data = {"tool_name": "Bash", "error": "failed"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))
        record = collect_tool_failure()
        assert record["type"] == ErrorType.TOOL_FAILURE, "PostToolUseFailure → tool_failure"

        # 测试 chk_internal_error
        internal = collect_chk_internal_error("ValueError: test")
        assert internal["error"] == "CHK internal error", "CHK internal error 类型"

        sys.stdin = sys.__stdin__
        print("  ✓ test_error_type_classification PASS")

    def test_recent_tools_context(self):
        """✓ 从 sessions.jsonl 补全 recent_tools"""
        from collect_error import collect_tool_failure, write_error

        # 创建 sessions.jsonl
        sessions_file = self.data_dir / "sessions.jsonl"
        sessions_file.write_text(json.dumps({
            "session_id": "test-session",
            "recent_tools": ["Read", "Edit", "Bash", "Write", "Grep"],
            "agents_used": ["executor", "code-reviewer"],
            "skills_used": ["security-audit"],
        }) + "\n")

        # 创建 agent_calls.jsonl（一次性写入，避免覆盖）
        agent_calls = self.data_dir / "agent_calls.jsonl"
        agent_calls.write_text(
            json.dumps({"agent": "executor", "task": "fix bug"}) + "\n" +
            json.dumps({"agent": "code-reviewer", "task": "review"}) + "\n"
        )

        # 创建 skill_calls.jsonl
        skill_calls = self.data_dir / "skill_calls.jsonl"
        skill_calls.write_text(json.dumps({"skill": "security-audit", "result": "passed"}) + "\n")

        hook_data = {"tool_name": "Bash", "error": "failed"}
        sys.stdin = __import__("io").StringIO(json.dumps(hook_data))

        record = collect_tool_failure()

        assert record["context"]["recent_tools"] == ["Read", "Edit", "Bash", "Write", "Grep"]
        assert "executor" in record["context"]["agents_used"]
        assert "security-audit" in record["context"]["skills_used"]

        sys.stdin = sys.__stdin__
        print("  ✓ test_recent_tools_context PASS")

    def test_main_entry_point(self):
        """✓ main() 入口正确处理错误"""
        from collect_error import main
        from io import StringIO

        hook_data = {
            "tool_name": "Write",
            "error": "disk full",
            "tool_input": {"file_path": "/tmp/test.txt", "content": "..."},
        }
        sys.stdin = StringIO(json.dumps(hook_data))

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        main()

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        result = json.loads(output)
        assert result["collected"] is True, f"应返回 collected=True: {result}"
        assert result["type"] == "tool_failure"

        sys.stdin = sys.__stdin__
        print("  ✓ test_main_entry_point PASS")


# ── 运行测试 ─────────────────────────────────────────────────────────────────

def run_tests():
    print("\n" + "=" * 60)
    print("  错误收集系统集成测试")
    print("=" * 60)

    test = TestErrorCollection()
    test.setup_class()

    tests = [
        test.test_error_jsonl_created,
        test.test_error_record_structure,
        test.test_source_traceability,
        test.test_sensitive_data_redaction,
        test.test_concurrent_writes,
        test.test_error_type_classification,
        test.test_recent_tools_context,
        test.test_main_entry_point,
    ]

    passed = 0
    failed = 0

    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: 意外错误 - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    test.teardown_class()

    print("-" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
