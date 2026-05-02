#!/usr/bin/env python3
"""collect-session 测试"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


class TestCollectSession:
    """Stop Hook 测试 - 聚合所有数据源"""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """创建临时项目结构"""
        (tmp_path / "CLAUDE.md").write_text("# Test Project")
        (tmp_path / ".claude" / "data").mkdir(parents=True)
        (tmp_path / "src.py").write_text("# source")
        return tmp_path

    @pytest.fixture
    def script_path(self):
        return Path(__file__).parent.parent / "hooks" / "bin" / "collect-session.py"

    def test_aggregates_agent_calls(self, temp_project, script_path):
        """应该从 agent_calls.jsonl 汇总 agents_used"""
        agent_calls = temp_project / ".claude" / "data" / "agent_calls.jsonl"
        agent_calls.write_text(
            json.dumps({"agent": "Explore", "task": "find files", "timestamp": datetime.now().isoformat()}) + "\n"
            + json.dumps({"agent": "claude-harness-kit:executor", "task": "write code", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        session_start = temp_project / ".claude" / "data" / ".session_start"
        session_start.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "mode": "solo"
        }))

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "solo"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        sessions = temp_project / ".claude" / "data" / "sessions.jsonl"
        lines = sessions.read_text().strip().splitlines()
        last_session = json.loads(lines[-1])

        assert "agents_used" in last_session
        assert len(last_session["agents_used"]) >= 2

    def test_aggregates_failures(self, temp_project, script_path):
        """应该从 failures.jsonl 统计 tool_failures"""
        failures = temp_project / ".claude" / "data" / "failures.jsonl"
        failures.write_text(
            json.dumps({"tool": "Bash", "error": "Exit code 1", "timestamp": datetime.now().isoformat()}) + "\n"
            + json.dumps({"tool": "Read", "error": "FileNotFoundError", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        session_start = temp_project / ".claude" / "data" / ".session_start"
        session_start.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "mode": "solo"
        }))

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "solo"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        sessions = temp_project / ".claude" / "data" / "sessions.jsonl"
        lines = sessions.read_text().strip().splitlines()
        last_session = json.loads(lines[-1])

        assert last_session["tool_failures"] >= 2

    def test_calculates_duration_from_session_start(self, temp_project, script_path):
        """应该从 .session_start 计算 duration_minutes"""
        start_time = datetime.now() - timedelta(minutes=30)
        session_start = temp_project / ".claude" / "data" / ".session_start"
        session_start.write_text(json.dumps({
            "timestamp": start_time.isoformat(),
            "mode": "solo"
        }))

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "solo"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        sessions = temp_project / ".claude" / "data" / "sessions.jsonl"
        lines = sessions.read_text().strip().splitlines()
        last_session = json.loads(lines[-1])

        assert last_session["duration_minutes"] >= 25

    def test_reports_git_files_changed(self, temp_project, script_path):
        """应该执行 git diff 统计 git_files_changed"""
        session_start = temp_project / ".claude" / "data" / ".session_start"
        session_start.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "mode": "solo"
        }))

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "solo"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        sessions = temp_project / ".claude" / "data" / "sessions.jsonl"
        lines = sessions.read_text().strip().splitlines()
        last_session = json.loads(lines[-1])

        assert "git_files_changed" in last_session
        assert isinstance(last_session["git_files_changed"], int)

    def test_rich_context_contains_tool_distribution(self, temp_project, script_path):
        """rich_context 应该包含工具使用分布"""
        agent_calls = temp_project / ".claude" / "data" / "agent_calls.jsonl"
        agent_calls.write_text(
            json.dumps({"agent": "Explore", "task": "", "timestamp": datetime.now().isoformat()}) + "\n"
            + json.dumps({"agent": "Explore", "task": "", "timestamp": datetime.now().isoformat()}) + "\n"
            + json.dumps({"agent": "executor", "task": "", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        session_start = temp_project / ".claude" / "data" / ".session_start"
        session_start.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "mode": "solo"
        }))

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "solo"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        sessions = temp_project / ".claude" / "data" / "sessions.jsonl"
        lines = sessions.read_text().strip().splitlines()
        last_session = json.loads(lines[-1])

        assert "rich_context" in last_session
        assert len(last_session["rich_context"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])