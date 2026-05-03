#!/usr/bin/env python3
"""
validator.py 测试文件

测试内容:
- 提案格式验证（validate_session）
- validate_sessions_file 文件批量验证
- 安全检查完整性（malformed JSON、quarantine 机制）
- clean_old_sessions 过期数据清理
- get_data_quality_stats 数据质量统计
"""
import pytest
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

EVOLVE_DIR = Path(__file__).parent.parent.parent / "evolve-daemon"
import importlib.util

spec = importlib.util.spec_from_file_location("validator_mod", EVOLVE_DIR / "validator.py")
validator_mod = importlib.util.module_from_spec(spec)
sys.modules["validator_mod"] = validator_mod
spec.loader.exec_module(validator_mod)


# =============================================================================
# validate_session 格式验证测试
# =============================================================================

class TestValidateSession:
    """测试 validate_session 单个 session 格式验证"""

    def test_valid_session_returns_true(self):
        """
        符合所有规范的 session 应通过验证。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 15,
            "corrections": [],
            "failure_types": {},
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is True
        assert error is None

    def test_missing_session_id_returns_false(self):
        """
        缺少 session_id 的 session 应返回 False。
        """
        session = {
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "session_id" in error

    def test_missing_timestamp_returns_false(self):
        """
        缺少 timestamp 的 session 应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "duration_minutes": 10,
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "timestamp" in error.lower()

    def test_invalid_timestamp_format_returns_false(self):
        """
        timestamp 格式错误（不可解析为 isoformat）应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "not-a-date",
            "duration_minutes": 10,
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "timestamp" in error.lower()

    def test_negative_duration_returns_false(self):
        """
        duration_minutes 为负数应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": -5,
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "duration" in error.lower()

    def test_non_integer_duration_returns_false(self):
        """
        duration_minutes 类型非整数应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": "ten",
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False

    def test_correction_not_dict_returns_false(self):
        """
        corrections 中的项不是 dict 应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
            "corrections": ["not a dict"],
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "Correction" in error

    def test_correction_missing_target_returns_false(self):
        """
        correction 缺少 'target' 字段应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
            "corrections": [{"context": "some context"}],
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "target" in error

    def test_failure_types_not_dict_returns_false(self):
        """
        failure_types 不是 dict 应返回 False。
        """
        session = {
            "session_id": "sess-001",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
            "failure_types": "not a dict",
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False
        assert "failure_types" in error


# =============================================================================
# validate_sessions_file 批量文件验证测试
# =============================================================================

class TestValidateSessionsFile:
    """测试 validate_sessions_file 批量验证逻辑"""

    def test_nonexistent_file_returns_zeros(self, tmp_path):
        """
        文件不存在时应返回全零统计。
        """
        sessions_file = tmp_path / "nonexistent.jsonl"
        result = validator_mod.validate_sessions_file(sessions_file)

        assert result["total"] == 0
        assert result["valid"] == 0
        assert result["invalid"] == 0

    def test_empty_file_returns_zeros(self, tmp_path):
        """
        空文件应返回全零统计。
        """
        sessions_file = tmp_path / "empty.jsonl"
        sessions_file.write_text("")

        result = validator_mod.validate_sessions_file(sessions_file)
        assert result["total"] == 0

    def test_all_valid_lines(self, tmp_path):
        """
        全部有效的行应返回 valid = total。
        """
        sessions_file = tmp_path / "valid.jsonl"
        valid_sessions = [
            {"session_id": f"s{i}", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 10}
            for i in range(5)
        ]
        sessions_file.write_text("\n".join(json.dumps(s) for s in valid_sessions))

        result = validator_mod.validate_sessions_file(sessions_file)
        assert result["total"] == 5
        assert result["valid"] == 5
        assert result["invalid"] == 0

    def test_mixed_valid_invalid_lines(self, tmp_path):
        """
        混合有效/无效行应正确分类统计。
        """
        sessions_file = tmp_path / "mixed.jsonl"
        lines = [
            json.dumps({"session_id": "s1", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 10}),
            "not json",
            json.dumps({"session_id": "s2", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 10}),
            json.dumps({"timestamp": "2026-01-01T10:00:00", "duration_minutes": 10}),  # missing session_id
        ]
        sessions_file.write_text("\n".join(lines))

        result = validator_mod.validate_sessions_file(sessions_file)
        assert result["total"] == 4
        assert result["valid"] == 2
        assert result["invalid"] == 2
        assert len(result["errors"]) == 2

    def test_invalid_json_is_quarantined(self, tmp_path):
        """
        无效 JSON 行应被隔离到 quarantine 目录。
        """
        sessions_file = tmp_path / "invalid.jsonl"
        lines = [
            json.dumps({"session_id": "s1", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 10}),
            "not json at all",
        ]
        sessions_file.write_text("\n".join(lines))

        quarantine_dir = tmp_path / "quarantine"
        result = validator_mod.validate_sessions_file(sessions_file, quarantine_dir)

        assert result["quarantined"] == 1
        assert quarantine_dir.exists()
        quarantined_files = list(quarantine_dir.glob("sessions_invalid_*.jsonl"))
        assert len(quarantined_files) == 1

    def test_valid_lines_overwrite_original(self, tmp_path):
        """
        验证后有效行应覆盖原文件。
        """
        sessions_file = tmp_path / "clean.jsonl"
        lines = [
            json.dumps({"session_id": "s1", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 10}),
            "invalid line",
        ]
        sessions_file.write_text("\n".join(lines))

        validator_mod.validate_sessions_file(sessions_file)

        # 文件应只包含有效行
        remaining = sessions_file.read_text().strip()
        assert "invalid line" not in remaining
        assert "s1" in remaining


# =============================================================================
# 安全检查完整性测试
# =============================================================================

class TestSecurityChecks:
    """测试安全检查完整性"""

    def test_validate_session_rejects_empty_session_id(self):
        """
        session_id 为空字符串应被视为无效。
        """
        session = {
            "session_id": "",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False

    def test_validate_session_rejects_none_session_id(self):
        """
        session_id 为 None 应被视为无效。
        """
        session = {
            "session_id": None,
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
        }

        is_valid, error = validator_mod.validate_session(session)
        assert is_valid is False

    def test_validate_session_with_corrections_validates_each(self):
        """
        有多个 corrections 时应对每一条进行验证。
        """
        session = {
            "session_id": "s1",
            "timestamp": "2026-01-01T10:00:00",
            "duration_minutes": 10,
            "corrections": [
                {"target": "agent-1", "context": "ctx1"},
                {"target": "agent-2"},  # 缺少 context 但 target 存在，此字段非必需
            ],
        }

        is_valid, error = validator_mod.validate_session(session)
        # 两条 correction 都有 target，所以应该通过
        assert is_valid is True

    def test_validate_sessions_file_handles_whitespace_lines(self, tmp_path):
        """
        空行和纯空白行应被忽略（不计入 valid 计数）。
        """
        sessions_file = tmp_path / "whitespace.jsonl"
        content = (
            json.dumps({"session_id": "s1", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 10})
            + "\n\n"
            + json.dumps({"session_id": "s2", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 5})
            + "\n   \n"
        )
        sessions_file.write_text(content)

        result = validator_mod.validate_sessions_file(sessions_file)
        assert result["valid"] == 2
        # total 计入所有非空行（blank lines 在 strip 前会被计入 splitlines）
        assert result["total"] == 3


# =============================================================================
# clean_old_sessions 过期清理测试
# =============================================================================

class TestCleanOldSessions:
    """测试 clean_old_sessions 过期数据清理"""

    def test_nonexistent_file_returns_zeros(self, tmp_path):
        """
        文件不存在时应返回零统计。
        """
        sessions_file = tmp_path / "nonexistent.jsonl"
        result = validator_mod.clean_old_sessions(sessions_file)

        assert result["cleaned"] == 0
        assert result["kept"] == 0

    def test_empty_file_returns_zeros(self, tmp_path):
        """
        空文件时应返回零统计。
        """
        sessions_file = tmp_path / "empty.jsonl"
        sessions_file.write_text("")

        result = validator_mod.clean_old_sessions(sessions_file)
        assert result["cleaned"] == 0

    def test_old_sessions_are_cleaned(self, tmp_path):
        """
        超过 max_age_days 的 session 应被清理。
        """
        sessions_file = tmp_path / "old.jsonl"
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        new_date = (datetime.now() - timedelta(days=30)).isoformat()

        sessions_file.write_text(
            json.dumps({"session_id": "old-1", "timestamp": old_date, "duration_minutes": 5}) + "\n"
            + json.dumps({"session_id": "old-2", "timestamp": old_date, "duration_minutes": 10}) + "\n"
            + json.dumps({"session_id": "new-1", "timestamp": new_date, "duration_minutes": 15})
        )

        result = validator_mod.clean_old_sessions(sessions_file, max_age_days=90)
        assert result["cleaned"] == 2
        assert result["kept"] == 1

        # 验证文件内容
        lines = sessions_file.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_invalid_json_cleaned_as_well(self, tmp_path):
        """
        无法解析的 JSON 行应被视为过期并被清理。
        """
        sessions_file = tmp_path / "invalid.jsonl"
        old_date = (datetime.now() - timedelta(days=100)).isoformat()

        sessions_file.write_text(
            json.dumps({"session_id": "old-1", "timestamp": old_date, "duration_minutes": 5}) + "\n"
            + "not valid json"
        )

        result = validator_mod.clean_old_sessions(sessions_file, max_age_days=90)
        # 两条都是"过期"的（invalid JSON 无法解析 timestamp）
        assert result["cleaned"] == 2


# =============================================================================
# get_data_quality_stats 质量统计测试
# =============================================================================

class TestDataQualityStats:
    """测试 get_data_quality_stats 数据质量统计"""

    def test_nonexistent_file_returns_empty(self, tmp_path):
        """
        文件不存在时应返回空字典。
        """
        sessions_file = tmp_path / "nonexistent.jsonl"
        stats = validator_mod.get_data_quality_stats(sessions_file)
        assert stats == {}

    def test_empty_file_returns_zeros(self, tmp_path):
        """
        空文件应返回全零统计。
        """
        sessions_file = tmp_path / "empty.jsonl"
        sessions_file.write_text("")

        stats = validator_mod.get_data_quality_stats(sessions_file)
        assert stats["total_sessions"] == 0
        # 空文件时 stats 只有 total_sessions=0 和其他零值初始字段，不含派生字段
        assert all(v == 0 for k, v in stats.items() if k != "total_sessions")

    def test_stats_calculated_correctly(self, tmp_path):
        """
        数据质量统计应正确计算各项指标。
        """
        sessions_file = tmp_path / "stats.jsonl"
        sessions = [
            {
                "session_id": "s1",
                "timestamp": "2026-01-01T10:00:00",
                "duration_minutes": 10,
                "agents_used": ["architect"],
                "tool_failures": 2,
                "corrections": [{"target": "a"}],
            },
            {
                "session_id": "s2",
                "timestamp": "2026-01-01T11:00:00",
                "duration_minutes": 20,
                "tool_failures": 0,
            },
        ]
        sessions_file.write_text("\n".join(json.dumps(s) for s in sessions))

        stats = validator_mod.get_data_quality_stats(sessions_file)

        assert stats["total_sessions"] == 2
        assert stats["sessions_with_agents"] == 1
        assert stats["sessions_with_failures"] == 1
        assert stats["sessions_with_corrections"] == 1
        assert stats["average_duration"] == 15.0
        assert stats["average_failures"] == 1.0
        assert stats["agents_usage_rate"] == 0.5
        assert stats["failures_rate"] == 0.5
        assert stats["corrections_rate"] == 0.5

    def test_invalid_lines_skipped_in_stats(self, tmp_path):
        """
        解析失败的行应在统计中被跳过。
        """
        sessions_file = tmp_path / "mixed_stats.jsonl"
        sessions_file.write_text(
            json.dumps({"session_id": "s1", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 5})
            + "\nnot json\n"
            + json.dumps({"session_id": "s2", "timestamp": "2026-01-01T11:00:00", "duration_minutes": 10})
        )

        stats = validator_mod.get_data_quality_stats(sessions_file)
        assert stats["total_sessions"] == 2


# =============================================================================
# run_validation 完整流程测试
# =============================================================================

class TestRunValidation:
    """测试 run_validation 完整验证流程"""

    def test_disabled_validation_returns_disabled_status(self, tmp_path):
        """
        validation.enabled = False 时应返回 disabled 状态。
        """
        config = {"validation": {"enabled": False}}
        result = validator_mod.run_validation(root=tmp_path, config=config)

        assert result["status"] == "disabled"

    def test_no_data_returns_no_data_status(self, tmp_path):
        """
        sessions.jsonl 不存在时应返回 no_data 状态。
        """
        config = {"validation": {"enabled": True}}
        result = validator_mod.run_validation(root=tmp_path, config=config)

        assert result["status"] == "no_data"

    def test_validation_completed_with_valid_sessions(self, tmp_path):
        """
        正常验证完成后应包含 validation、clean 和 quality 结果。
        """
        data_dir = tmp_path / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        sessions_file = data_dir / "sessions.jsonl"
        sessions_file.write_text(
            json.dumps({"session_id": "s1", "timestamp": "2026-01-01T10:00:00", "duration_minutes": 5})
        )

        config = {"validation": {"enabled": True, "quarantine_malformed": False}}
        result = validator_mod.run_validation(root=tmp_path, config=config)

        assert result["status"] == "completed"
        assert "validation" in result
        assert "clean" in result
        assert "quality" in result
        assert result["validation"]["valid"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])