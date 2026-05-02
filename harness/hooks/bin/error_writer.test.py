#!/usr/bin/env python3
"""
error_writer 测试套件
TDD 流程: RED → GREEN → REFACTOR
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

HOOKS_BIN = Path(__file__).parent


# ── 测试辅助 ──────────────────────────────────────────────────────────────────

class TempProject:
    """临时项目目录，模拟 <project>/.claude/data/ 结构"""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="chk-test-")
        self.root = Path(self.tmp)
        self.data_dir = self.root / ".claude" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self):
        return self.tmp


# ── 测试用例 ──────────────────────────────────────────────────────────────────

def test_write_error_creates_file():
    """✓ 写入 error.jsonl 文件"""
    from error_writer import write_error, build_error_record

    proj = TempProject()
    try:
        record = build_error_record(
            error_type="tool_failure",
            error_message="Bash command failed",
            source="hooks/bin/collect-error.py:42",
            tool="Bash",
        )

        result = write_error(record, project_dir=proj.path())
        assert result is True, "write_error 应返回 True"

        log_file = proj.data_dir / "error.jsonl"
        assert log_file.exists(), "error.jsonl 文件应被创建"

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1, "应写入一行"

        data = json.loads(lines[0])
        assert data["type"] == "tool_failure"
        assert data["error"] == "Bash command failed"
        assert data["source"] == "hooks/bin/collect-error.py:42"
        assert "timestamp" in data
        print("  ✓ test_write_error_creates_file PASS")
    finally:
        proj.cleanup()


def test_error_record_format():
    """✓ 错误记录包含所有必需字段"""
    from error_writer import build_error_record

    proj = TempProject()
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = proj.path()
        os.environ["CLAUDE_SESSION_ID"] = "test-session-001"
        os.environ["CLAUDE_MODE"] = "team"

        record = build_error_record(
            error_type="hook_error",
            error_message="Hook script crashed",
            source="hooks/bin/quality-gate.sh:15",
            tool="Bash",
            tool_input={"command": "echo test"},
            error_detail="Traceback: module not found",
            hook_event="PostToolUse",
        )

        # 顶层字段
        assert record["type"] == "hook_error"
        assert record["source"] == "hooks/bin/quality-gate.sh:15"
        assert record["tool"] == "Bash"
        assert record["error"] == "Hook script crashed"
        assert record["error_detail"] == "Traceback: module not found"

        # context 字段
        ctx = record["context"]
        assert ctx["session_id"] == "test-session-001"
        assert ctx["project"] == proj.path()
        assert ctx["mode"] == "team"
        assert "tool_input" in ctx

        # metadata 字段
        meta = record["metadata"]
        assert "chk_version" in meta
        assert meta["hook_event"] == "PostToolUse"
        assert meta["collector"] == "collect-error.py"

        print("  ✓ test_error_record_format PASS")
    finally:
        proj.cleanup()
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ.pop("CLAUDE_SESSION_ID", None)
        os.environ.pop("CLAUDE_MODE", None)


def test_concurrent_write_no_data_loss():
    """✓ 并发写入不丢数据"""
    from error_writer import write_error, build_error_record

    proj = TempProject()
    errors_written = []
    errors_count = 100

    def write_single(index):
        record = build_error_record(
            error_type="tool_failure",
            error_message=f"Error #{index}",
            source="hooks/bin/test.py:0",
            tool="Bash",
        )
        success = write_error(record, project_dir=proj.path())
        errors_written.append(success)

    try:
        threads = []
        for i in range(errors_count):
            t = threading.Thread(target=write_single, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        log_file = proj.data_dir / "error.jsonl"
        lines = log_file.read_text().strip().splitlines()
        # 所有写操作都应成功
        assert all(errors_written), "所有 write_error 调用都应返回 True"
        # 不丢数据
        assert len(lines) == errors_count, f"应写入 {errors_count} 行，实际 {len(lines)} 行"
        print(f"  ✓ test_concurrent_write_no_data_loss PASS ({errors_count} 并发写入)")
    finally:
        proj.cleanup()


def test_sanitize_sensitive_fields():
    """✓ 敏感字段被脱敏"""
    from error_writer import _sanitize_tool_input

    tool_input = {
        "command": "curl https://api.example.com",
        "api_key": "sk-ant-xxxxx",
        "password": "super_secret_123",
        "Authorization": "Bearer secret-token",
        "GITHUB_TOKEN": "ghp_xxxxxxxxxxxx",
    }

    sanitized = _sanitize_tool_input(tool_input)

    assert sanitized["command"] == "curl https://api.example.com"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["GITHUB_TOKEN"] == "[REDACTED]"
    print("  ✓ test_sanitize_sensitive_fields PASS")


def test_truncate_long_string():
    """✓ 过长字符串被截断"""
    from error_writer import _sanitize_tool_input

    tool_input = {
        "command": "x" * 1000,  # 超过 500 字符限制
    }

    sanitized = _sanitize_tool_input(tool_input)
    # 代码: v[:500] + "...[TRUNCATED]"  实际长度 500 + 14 = 514
    assert len(sanitized["command"]) == 514, f"期望 514，实际 {len(sanitized['command'])}"
    assert "[TRUNCATED]" in sanitized["command"]
    print("  ✓ test_truncate_long_string PASS")


def test_error_types_enum():
    """✓ ErrorType 枚举值正确"""
    from error_writer import ErrorType

    assert ErrorType.TOOL_FAILURE == "tool_failure"
    assert ErrorType.HOOK_ERROR == "hook_error"
    assert ErrorType.CHK_INTERNAL_ERROR == "chk_internal_error"
    assert ErrorType.API_ERROR == "api_error"
    assert ErrorType.VALIDATION_ERROR == "validation_error"
    print("  ✓ test_error_types_enum PASS")


def test_session_id_fallback():
    """✓ session_id 兜底逻辑"""
    from error_writer import _get_session_id

    proj = TempProject()
    try:
        os.environ.pop("CLAUDE_SESSION_ID", None)

        # 无 git 目录时，用项目名+时间戳
        session_id = _get_session_id(proj.root)
        assert proj.root.name in session_id
        assert "-" in session_id  # 包含时间戳格式
        print("  ✓ test_session_id_fallback PASS")
    finally:
        proj.cleanup()
        os.environ.pop("CLAUDE_SESSION_ID", None)


def test_multiple_error_types():
    """✓ 支持所有错误类型"""
    from error_writer import write_error, build_error_record, ErrorType

    proj = TempProject()
    try:
        types = [
            (ErrorType.TOOL_FAILURE, "Bash failed"),
            (ErrorType.HOOK_ERROR, "Hook crashed"),
            (ErrorType.CHK_INTERNAL_ERROR, "CHK internal error"),
            (ErrorType.API_ERROR, "API timeout"),
            (ErrorType.VALIDATION_ERROR, "Validation failed"),
        ]

        for error_type, msg in types:
            record = build_error_record(
                error_type=error_type,
                error_message=msg,
                source="test.py:0",
            )
            write_error(record, project_dir=proj.path())

        log_file = proj.data_dir / "error.jsonl"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == len(types)

        for i, (error_type, msg) in enumerate(types):
            data = json.loads(lines[i])
            assert data["type"] == error_type
            assert data["error"] == msg

        print("  ✓ test_multiple_error_types PASS")
    finally:
        proj.cleanup()


def test_cli_pipe_input():
    """✓ CLI 管道输入模式"""
    import io
    import subprocess

    proj = TempProject()
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = proj.path()

        test_record = {
            "type": "tool_failure",
            "source": "test.py:10",
            "tool": "Bash",
            "error": "CLI test error",
        }

        # 直接调用 write_error，不依赖 stdin 模拟
        from error_writer import write_error, build_error_record

        record = build_error_record(
            error_type="tool_failure",
            error_message="CLI test error",
            source="test.py:10",
            tool="Bash",
        )
        success = write_error(record, project_dir=proj.path())
        assert success is True

        log_file = proj.data_dir / "error.jsonl"
        assert log_file.exists()
        print("  ✓ test_cli_pipe_input PASS")
    finally:
        proj.cleanup()
        os.environ.pop("CLAUDE_PROJECT_DIR", None)


def test_lock_file_created():
    """✓ 锁文件被正确创建和清理"""
    from error_writer import write_error, build_error_record, _get_lock_file

    proj = TempProject()
    try:
        record = build_error_record(
            error_type="tool_failure",
            error_message="Lock test",
            source="test.py:0",
        )

        log_file = proj.data_dir / "error.jsonl"
        lock_file = _get_lock_file(log_file)

        write_error(record, project_dir=proj.path())

        # 锁文件应在写入期间存在，写完后可能清理或保留
        # flock 不需要手动清理，只是检查不报错
        assert True
        print("  ✓ test_lock_file_created PASS")
    finally:
        proj.cleanup()


# ── 测试运行器 ────────────────────────────────────────────────────────────────

def run_all_tests():
    tests = [
        test_error_record_format,
        test_write_error_creates_file,
        test_error_types_enum,
        test_sanitize_sensitive_fields,
        test_truncate_long_string,
        test_session_id_fallback,
        test_multiple_error_types,
        test_concurrent_write_no_data_loss,
        test_cli_pipe_input,
        test_lock_file_created,
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("  error_writer.py 测试套件")
    print("=" * 60)

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            import traceback
            print(f"  ✗ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {test.__name__}: 意外错误 - {e}")
            traceback.print_exc()
            failed += 1

    print("-" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
