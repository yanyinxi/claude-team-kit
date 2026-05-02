#!/usr/bin/env python3
"""
evolve_dispatcher.test.py — TDD 测试文件
"""
import pytest
from pathlib import Path
import sys, os

EVOLVE_DIR = Path(__file__).parent
import importlib.util
spec = importlib.util.spec_from_file_location("disp_mod", EVOLVE_DIR / "evolve_dispatcher.py")
dispatcher = importlib.util.module_from_spec(spec)
sys.modules["disp_mod"] = dispatcher
spec.loader.exec_module(dispatcher)


class TestGetDimension:
    """get_dimension() 测试"""

    def test_agent_prefix(self):
        assert dispatcher.get_dimension("agent:backend-dev") == "agent"

    def test_skill_prefix(self):
        assert dispatcher.get_dimension("skill:testing") == "skill"

    def test_rule_prefix(self):
        assert dispatcher.get_dimension("rule:security") == "rule"

    def test_tool_prefix(self):
        assert dispatcher.get_dimension("tool:Read") == "tool"

    def test_unknown_prefix(self):
        assert dispatcher.get_dimension("unknown:xxx") == "instinct"


class TestMeetsThreshold:
    """meets_threshold() 测试"""

    def test_below_agent_threshold(self):
        assert dispatcher.meets_threshold("agent", 2) is False

    def test_at_agent_threshold(self):
        assert dispatcher.meets_threshold("agent", 3) is True

    def test_above_agent_threshold(self):
        assert dispatcher.meets_threshold("agent", 5) is True

    def test_rule_needs_more_corrections(self):
        """Rule 维度需要 5 次纠正"""
        assert dispatcher.meets_threshold("rule", 4) is False
        assert dispatcher.meets_threshold("rule", 5) is True

    def test_instinct_low_threshold(self):
        """Instinct 维度阈值较低"""
        assert dispatcher.meets_threshold("instinct", 1) is False
        assert dispatcher.meets_threshold("instinct", 2) is True


class TestDispatchEvolution:
    """dispatch_evolution() 测试"""

    def test_empty_hotspots_returns_empty(self):
        result = dispatcher.dispatch_evolution({}, {}, EVOLVE_DIR)
        assert result == []

    def test_empty_analysis_returns_empty(self):
        result = dispatcher.dispatch_evolution({"correction_hotspots": {}}, {}, EVOLVE_DIR)
        assert result == []

    def test_agent_hotspot_generates_agent_decision(self):
        analysis = {
            "correction_hotspots": {"agent:backend-dev": 5},
            "correction_patterns": {"agent:backend-dev:print_debug": {"count": 5, "examples": []}},
            "primary_target": "agent:backend-dev",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        agent_decs = [r for r in result if r["dimension"] == "agent"]
        assert len(agent_decs) == 1
        assert agent_decs[0]["target"] == "agent:backend-dev"
        assert agent_decs[0]["action"] in ("auto_apply", "propose")

    def test_skill_hotspot_generates_skill_decision(self):
        analysis = {
            "correction_hotspots": {"skill:testing": 5},
            "correction_patterns": {},
            "primary_target": "skill:testing",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        skill_decs = [r for r in result if r["dimension"] == "skill"]
        assert len(skill_decs) == 1

    def test_tool_hotspot_routes_to_instinct(self):
        analysis = {
            "correction_hotspots": {"tool:Read": 3},
            "correction_patterns": {},
            "primary_target": "tool:Read",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        instinct_decs = [r for r in result if r["dimension"] == "instinct"]
        assert len(instinct_decs) == 1

    def test_below_threshold_not_included(self):
        analysis = {
            "correction_hotspots": {"agent:backend-dev": 2},
            "correction_patterns": {},
            "primary_target": "agent:backend-dev",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        assert len(result) == 0

    def test_multiple_dimensions(self):
        analysis = {
            "correction_hotspots": {
                "agent:backend-dev": 5,
                "skill:testing": 3,
                "tool:Bash": 3,
            },
            "correction_patterns": {},
            "primary_target": "agent:backend-dev",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        dimensions = {r["dimension"] for r in result}
        assert "agent" in dimensions
        assert "skill" in dimensions
        assert "instinct" in dimensions

    def test_decision_has_required_fields(self):
        analysis = {
            "correction_hotspots": {"agent:backend-dev": 5},
            "correction_patterns": {},
            "primary_target": "agent:backend-dev",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        dec = result[0]
        assert all(k in dec for k in ("dimension", "target", "action", "confidence", "risk_level", "id"))

    def test_low_risk_pattern_auto_apply(self):
        analysis = {
            "correction_hotspots": {"agent:backend-dev": 5},
            "correction_patterns": {"agent:backend-dev:print_debug": {"count": 5, "examples": []}},
            "primary_target": "agent:backend-dev",
        }
        result = dispatcher.dispatch_evolution(analysis, {}, EVOLVE_DIR)
        agent_dec = [r for r in result if r["dimension"] == "agent"][0]
        assert agent_dec["action"] == "auto_apply"
        assert agent_dec["risk_level"] == "low"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
