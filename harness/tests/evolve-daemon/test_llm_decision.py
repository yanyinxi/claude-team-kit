#!/usr/bin/env python3
"""
llm_decision.py 测试文件

测试内容:
- API key 不存在时抛出 EnvironmentError
- 决策阈值逻辑
- 规则保护逻辑 (熔断器、高风险检查)
- 使用 mock 避免实际 API 调用
"""
import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

EVOLVE_DIR = Path(__file__).parent.parent.parent / "evolve-daemon"
import importlib.util

spec = importlib.util.spec_from_file_location("llm_decision_mod", EVOLVE_DIR / "llm_decision.py")
llm_decision_mod = importlib.util.module_from_spec(spec)
sys.modules["llm_decision_mod"] = llm_decision_mod
spec.loader.exec_module(llm_decision_mod)


# =============================================================================
# 环境变量 / API Key 测试
# =============================================================================

class TestApiKeyEnvironmentError:
    """测试 API key 不存在时抛出 EnvironmentError"""

    def test_call_claude_api_raises_when_no_api_key(self):
        """
        当 ANTHROPIC_API_KEY 环境变量未设置时，call_claude_api 应抛出 EnvironmentError。
        """
        # 确保环境变量未设置
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(EnvironmentError) as exc_info:
                llm_decision_mod.call_claude_api(
                    system_prompt="test prompt",
                    user_message="test message",
                    config={}
                )
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_decide_action_raises_when_no_api_key(self):
        """
        顶层 decide_action 函数在无 API key 时应将 EnvironmentError 向上传递。
        """
        sessions = [{"session_id": "s1", "corrections": [{"target": "test", "context": "ctx", "user_correction": "fix"}]}]
        analysis = {"correction_hotspots": {"test": 3}, "primary_target": "test"}
        config = {"decision": {"enabled": True}, "claude_api": {}}

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(EnvironmentError):
                llm_decision_mod.decide_action(sessions, analysis, config)


# =============================================================================
# 决策阈值逻辑测试
# =============================================================================

class TestDecisionThresholdLogic:
    """测试决策阈值相关逻辑"""

    def test_disabled_decision_returns_skip(self):
        """
        当 decision.enabled = False 时，decide_action 应直接返回 skip。
        """
        sessions = [{"session_id": "s1", "corrections": []}]
        analysis = {"correction_hotspots": {"test": 1}}
        config = {"decision": {"enabled": False}}

        result = llm_decision_mod.decide_action(sessions, analysis, config)
        assert result["action"] == "skip"
        assert result["reason"] == "LLM decision disabled"

    def test_no_hotspots_returns_skip(self):
        """
        当 correction_hotspots 为空时，decide_action 应返回 skip。
        """
        sessions = [{"session_id": "s1", "corrections": []}]
        analysis = {"correction_hotspots": {}}
        config = {"decision": {"enabled": True}}

        result = llm_decision_mod.decide_action(sessions, analysis, config)
        assert result["action"] == "skip"
        assert result["reason"] == "No correction hotspots"

    def test_high_risk_triggers_propose_action(self):
        """
        当 assess_risk 返回 >= 0.9 时，decide_action 应返回 propose 而不调用 API。
        """
        sessions = [{"session_id": "s1", "corrections": []}]
        analysis = {
            "correction_hotspots": {"permission_test": 5},
            "multi_file_change": False,
            "primary_target": "permission_test"
        }
        config = {
            "decision": {
                "enabled": True,
                "risk_rules": {"high_risk_patterns": ["permission"]},
            },
            "claude_api": {}
        }

        result = llm_decision_mod.decide_action(sessions, analysis, config)
        assert result["action"] == "propose"
        assert result["risk_level"] == "high"

    def test_auto_apply_threshold_not_met_returns_propose(self):
        """
        当 LLM 返回 auto_apply 但置信度低于阈值时，应降级为 propose。
        """
        sessions = [{"session_id": "s1", "corrections": [{"target": "test", "context": "ctx", "user_correction": "fix"}]}]
        analysis = {"correction_hotspots": {"test": 2}, "primary_target": "test"}
        config = {
            "decision": {"enabled": True, "auto_apply_threshold": 0.8},
            "claude_api": {}
        }

        # Mock LLM 返回 auto_apply 但置信度只有 0.5（低于 0.8 阈值）
        mock_response = {
            "action": "auto_apply",
            "reason": "Low risk change",
            "confidence": 0.5,
            "risk_level": "low",
            "target_file": "agents/test.md",
            "suggested_change": "append: new line"
        }

        with patch.object(llm_decision_mod, "call_claude_api", return_value=mock_response):
            result = llm_decision_mod.decide_action(sessions, analysis, config)
            assert result["action"] == "propose"  # 降级为 propose

    def test_auto_apply_threshold_met_returns_auto_apply(self):
        """
        当 LLM 返回 auto_apply 且置信度 >= 阈值时，应返回 auto_apply。
        注意：需要 mock find_root 以避免 is_new_target 干扰阈值判断。
        """
        sessions = [{"session_id": "s1", "corrections": [{"target": "test", "context": "ctx", "user_correction": "fix"}]}]
        analysis = {"correction_hotspots": {"test": 2}, "primary_target": "test"}
        config = {
            "decision": {"enabled": True, "auto_apply_threshold": 0.8},
            "claude_api": {}
        }

        mock_response = {
            "action": "auto_apply",
            "reason": "Low risk change",
            "confidence": 0.9,  # 高于 0.8 阈值
            "risk_level": "low",
            "target_file": "agents/test.md",
            "suggested_change": "append: new line"
        }

        # mock load_instinct 返回已知 target，避免 is_new_target 提升风险
        mock_instinct = {"records": [{"pattern": "agent:test context"}]}

        with patch.object(llm_decision_mod, "call_claude_api", return_value=mock_response):
            with patch.object(llm_decision_mod, "load_instinct", return_value=mock_instinct):
                result = llm_decision_mod.decide_action(sessions, analysis, config)
                assert result["action"] == "auto_apply"
                assert result["confidence"] == 0.9
                assert result["target_file"] == "agents/test.md"


# =============================================================================
# 风险评估逻辑测试
# =============================================================================

class TestRiskAssessment:
    """测试 assess_risk 风险评估逻辑"""

    def test_assess_risk_high_risk_pattern_returns_high(self):
        """
        包含高风险 pattern（如 permission）的 target 应返回较高风险值。
        """
        analysis = {
            "correction_hotspots": {"permission_check": 2},
            "multi_file_change": False
        }
        config = {
            "decision": {"risk_rules": {"high_risk_patterns": ["permission", "security", "auth"]}}
        }

        risk = llm_decision_mod.assess_risk(analysis, config)
        assert risk >= 0.9

    def test_assess_risk_multi_file_change_returns_high(self):
        """
        多文件修改场景应返回较高风险值（>= 0.8）。
        """
        analysis = {
            "correction_hotspots": {"test": 2},
            "multi_file_change": True
        }
        config = {"decision": {"risk_rules": {}}}

        risk = llm_decision_mod.assess_risk(analysis, config)
        assert risk >= 0.8

    def test_assess_risk_default_risk_value(self):
        """
        无特殊风险因素时，默认风险应为 0.3。
        """
        analysis = {"correction_hotspots": {}, "multi_file_change": False}
        config = {"decision": {"risk_rules": {}}}

        risk = llm_decision_mod.assess_risk(analysis, config)
        assert risk == 0.3

    def test_assess_risk_capped_at_one(self):
        """
        风险值最大不超过 1.0。
        """
        analysis = {
            "correction_hotspots": {"permission_check": 5},
            "multi_file_change": True
        }
        config = {
            "decision": {"risk_rules": {"high_risk_patterns": ["permission"]}}
        }

        risk = llm_decision_mod.assess_risk(analysis, config)
        assert risk <= 1.0


# =============================================================================
# call_claude_api mock 测试
# =============================================================================

class TestCallClaudeApiMock:
    """测试 call_claude_api 使用 mock 避免实际 API 调用"""

    def test_call_claude_api_with_mock_sdk(self):
        """
        使用 mock 的 Anthropic SDK client，避免真实网络调用。
        """
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "action": "propose",
            "reason": "test reason",
            "confidence": 0.6,
            "risk_level": "medium"
        }))]

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                result = llm_decision_mod.call_claude_api(
                    system_prompt="test",
                    user_message="test",
                    config={}
                )
                assert result["action"] == "propose"
                assert result["confidence"] == 0.6

    def test_call_claude_api_invalid_json_returns_propose(self):
        """
        LLM 返回非 JSON 时，call_claude_api 应返回默认 propose 决策。
        """
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="this is not json")]

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                result = llm_decision_mod.call_claude_api(
                    system_prompt="test",
                    user_message="test",
                    config={}
                )
                assert result["action"] == "propose"
                assert result["reason"] == "Invalid JSON from LLM"


# =============================================================================
# 辅助函数测试
# =============================================================================

class TestHelperFunctions:
    """测试辅助函数"""

    def test_load_config_returns_dict(self):
        """load_config 应返回非空字典"""
        config = llm_decision_mod.load_config()
        assert isinstance(config, dict)
        assert "decision" in config

    def test_default_config_has_threshold(self):
        """默认配置应包含 auto_apply_threshold"""
        config = llm_decision_mod._default_config()
        assert config["decision"]["auto_apply_threshold"] == 0.8

    def test_is_new_target_true_for_unknown(self):
        """is_new_target 对未知 target 应返回 True"""
        instinct = {"records": [{"pattern": "agent:known_agent"}]}
        assert llm_decision_mod.is_new_target("unknown_agent", instinct) is True

    def test_is_new_target_false_for_existing(self):
        """is_new_target 对已存在的 target 应返回 False"""
        instinct = {"records": [{"pattern": "agent:existing_agent"}]}
        assert llm_decision_mod.is_new_target("existing_agent", instinct) is False

    def test_get_existing_targets_extracts_agents_and_skills(self):
        """get_existing_targets 应正确提取 agent 和 skill"""
        instinct = {
            "records": [
                {"pattern": "agent:backend-dev context"},
                {"pattern": "skill:testing context"},
                {"pattern": "other:format"},
            ]
        }
        targets = llm_decision_mod.get_existing_targets(instinct)
        assert "backend-dev" in targets
        assert "testing" in targets

    def test_get_decision_stats_empty_file(self, tmp_path):
        """空的 decision_history.json 应返回零值统计"""
        history_file = tmp_path / "decision_history.json"
        stats = llm_decision_mod.get_decision_stats(history_file)
        assert stats["total"] == 0
        assert stats["auto_apply"] == 0

    def test_get_decision_stats_with_history(self, tmp_path):
        """get_decision_stats 应正确统计各类决策"""
        history_file = tmp_path / "decision_history.json"
        history_file.write_text(json.dumps([
            {"action": "auto_apply"},
            {"action": "propose"},
            {"action": "auto_apply"},
            {"action": "skip"},
        ]))

        stats = llm_decision_mod.get_decision_stats(history_file)
        assert stats["total"] == 4
        assert stats["auto_apply"] == 2
        assert stats["propose"] == 1
        assert stats["skip"] == 1
        assert stats["auto_apply_rate"] == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])