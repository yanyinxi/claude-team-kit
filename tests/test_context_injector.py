#!/usr/bin/env python3
"""context-injector 测试"""
import json
import os
import sys
import subprocess
from pathlib import Path

import pytest


class TestContextInjector:
    @pytest.fixture
    def temp_project(self, tmp_path):
        """创建临时项目结构"""
        (tmp_path / "CLAUDE.md").write_text("""# CLAUDE.md

## 技术栈
- Python

## 关键路径
- src/

## 架构约定
测试项目
""")
        (tmp_path / ".claude" / "data").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def script_path(self):
        return Path(__file__).parent.parent / "hooks" / "bin" / "context-injector.py"

    def test_record_session_start_writes_timestamp(self, temp_project, script_path):
        """SessionStart 应该记录开始时间到 .session_start 文件"""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "solo"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        session_start_file = temp_project / ".claude" / "data" / ".session_start"
        assert session_start_file.exists(), "SessionStart 应该创建 .session_start 文件"

        data = json.loads(session_start_file.read_text())
        assert "timestamp" in data, "应包含 timestamp"
        assert "mode" in data, "应包含 mode"

    def test_session_start_file_format(self, temp_project, script_path):
        """验证 session_start 文件格式"""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(temp_project)
        env["CLAUDE_MODE"] = "team"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env
        )

        session_start_file = temp_project / ".claude" / "data" / ".session_start"
        data = json.loads(session_start_file.read_text())

        assert "timestamp" in data
        assert data["mode"] == "team"
        assert "duration_seconds" not in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])