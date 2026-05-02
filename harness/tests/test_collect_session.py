#!/usr/bin/env python3
"""
测试: collect_session.py 数据采集功能

验证:
1. 会话数据正确写入 sessions.jsonl
2. failure_types 正确分类
3. agent_stats 正确聚合
4. git_stats 正确统计
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# 添加 hooks/bin 到模块路径（在导入前设置）
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "bin"))

# 模拟环境变量
os.environ["CLAUDE_PROJECT_DIR"] = tempfile.mkdtemp()

import pytest


class TestClassifyErrorType:
    """测试错误分类逻辑"""

    def test_permission_error(self):
        from collect_session import classify_error_type
        assert classify_error_type("Permission denied") == "permission_error"
        assert classify_error_type("Access denied to file") == "permission_error"

    def test_not_found_error(self):
        from collect_session import classify_error_type
        assert classify_error_type("File not found") == "not_found_error"
        assert classify_error_type("No such file or directory") == "not_found_error"

    def test_timeout_error(self):
        from collect_session import classify_error_type
        assert classify_error_type("Connection timeout") == "timeout_error"
        assert classify_error_type("Request timed out") == "timeout_error"

    def test_syntax_error(self):
        from collect_session import classify_error_type
        assert classify_error_type("Syntax error in JSON") == "syntax_error"
        assert classify_error_type("Failed to parse config") == "syntax_error"

    def test_unknown_error(self):
        from collect_session import classify_error_type
        assert classify_error_type("Something went wrong") == "unknown_error"


class TestAggregateFailures:
    """测试失败聚合逻辑"""

    def test_empty_failures(self):
        from collect_session import aggregate_failures
        root = Path(tempfile.mkdtemp())
        result = aggregate_failures(root)
        assert result["total"] == 0
        assert result["failure_types"] == {}

    def test_with_failures(self):
        from collect_session import aggregate_failures
        root = Path(tempfile.mkdtemp())
        # 实际路径是 root / ".claude" / "data" / "failures.jsonl"
        data_dir = root / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        failures_file = data_dir / "failures.jsonl"
        failures_file.write_text(
            json.dumps({"tool": "Read", "error": "Permission denied", "timestamp": "2026-05-02T10:00:00"}) + "\n"
            + json.dumps({"tool": "Bash", "error": "File not found", "timestamp": "2026-05-02T10:01:00"}) + "\n"
        )
        result = aggregate_failures(root)
        assert result["total"] == 2
        assert result["failure_types"]["permission_error"] == 1
        assert result["failure_types"]["not_found_error"] == 1
        assert result["failure_tools"]["Read"] == 1
        assert result["failure_tools"]["Bash"] == 1

    def test_failure_classification(self):
        from collect_session import aggregate_failures
        root = Path(tempfile.mkdtemp())
        # 实际路径是 root / ".claude" / "data" / "failures.jsonl"
        data_dir = root / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        failures_file = data_dir / "failures.jsonl"
        failures_file.write_text(
            json.dumps({"tool": "Bash", "error": "Connection timeout", "timestamp": "2026-05-02T10:00:00"}) + "\n"
            + json.dumps({"tool": "Bash", "error": "Permission denied", "timestamp": "2026-05-02T10:01:00"}) + "\n"
        )
        result = aggregate_failures(root)
        assert result["failure_types"]["timeout_error"] == 1
        assert result["failure_types"]["permission_error"] == 1


class TestBuildSession:
    """测试会话构建逻辑"""

    def test_minimal_session(self):
        from collect_session import build_session, find_project_root
        root = find_project_root()
        session = build_session(root)
        assert "session_id" in session
        assert "timestamp" in session
        assert "mode" in session
        assert "duration_minutes" in session
        assert "agents_used" in session
        assert "tool_failures" in session
        assert "git_files_changed" in session

    def test_rich_context_structure(self):
        from collect_session import build_session, find_project_root
        root = find_project_root()
        session = build_session(root)
        assert "rich_context" in session
        ctx = session["rich_context"]
        assert "agent_stats" in ctx or "failure_stats" in ctx


class TestAppendSession:
    """测试会话追加逻辑"""

    def test_append_creates_file(self):
        from collect_session import append_session, find_project_root
        root = find_project_root()
        data_dir = root / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        session = {
            "session_id": "test-123",
            "timestamp": "2026-05-02T10:00:00",
            "mode": "solo",
            "duration_minutes": 5,
        }
        log_file = append_session(root, session)

        assert log_file.exists()
        content = log_file.read_text()
        assert "test-123" in content
        assert "2026-05-02T10:00:00" in content

    def test_append_jsonl_format(self):
        from collect_session import append_session, find_project_root
        root = find_project_root()
        data_dir = root / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        sessions_file = data_dir / "sessions.jsonl"
        if sessions_file.exists():
            sessions_file.unlink()

        for i in range(3):
            session = {
                "session_id": f"test-{i}",
                "timestamp": "2026-05-02T10:00:00",
            }
            append_session(root, session)

        content = sessions_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # 必须是有效 JSON


class TestShouldTriggerAnalysis:
    """测试分析触发判断"""

    def test_no_trigger_low_failures(self):
        from collect_session import should_trigger_analysis
        session = {"tool_failures": 2, "agent_success_rate": 0.9}
        assert should_trigger_analysis(session, {}) == False

    def test_trigger_high_failures(self):
        from collect_session import should_trigger_analysis
        session = {"tool_failures": 6, "agent_success_rate": 0.9}
        assert should_trigger_analysis(session, {}) == True

    def test_trigger_low_success_rate(self):
        from collect_session import should_trigger_analysis
        session = {"tool_failures": 2, "agent_success_rate": 0.3}
        assert should_trigger_analysis(session, {}) == True

    def test_trigger_repeated_error_type(self):
        from collect_session import should_trigger_analysis
        session = {
            "tool_failures": 2,
            "agent_success_rate": 0.9,
            "failure_types": {"permission_error": 5}
        }
        assert should_trigger_analysis(session, {}) == True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))