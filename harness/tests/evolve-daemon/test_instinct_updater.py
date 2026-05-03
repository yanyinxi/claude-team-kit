#!/usr/bin/env python3
"""
instinct_updater.py 测试文件

测试内容:
- promote_confidence 置信度提升
- demote_confidence 置信度降低
- 置信度上限于 max_confidence (默认 0.95)
- 置信度下限于 decay_floor (默认 0.1)
- reinforce_pattern 是 promote_confidence 的别名
- 置信度恢复机制：success 跟踪后本能记录置信度提升
"""
import pytest
import json
import sys
from pathlib import Path
from datetime import datetime

EVOLVE_DIR = Path(__file__).parent.parent.parent / "evolve-daemon"
import importlib.util

spec = importlib.util.spec_from_file_location("instinct_updater_mod", EVOLVE_DIR / "instinct_updater.py")
instinct_mod = importlib.util.module_from_spec(spec)
sys.modules["instinct_updater_mod"] = instinct_mod
spec.loader.exec_module(instinct_mod)


# =============================================================================
# promote_confidence 测试
# =============================================================================

class TestPromoteConfidence:
    """测试 promote_confidence 置信度提升"""

    def test_promote_increases_confidence(self, tmp_path):
        """
        promote_confidence 应增加置信度。
        """
        # 添加一条初始记录
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.3,
            source="test",
            root=tmp_path
        )

        # 提升置信度
        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)

        # 读取验证
        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record is not None
        assert record["confidence"] == 0.4  # 0.3 + 0.1
        assert record["reinforcement_count"] == 1

    def test_promote_caps_at_max_confidence(self, tmp_path):
        """
        置信度不应超过 max_confidence (默认 0.95)。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.9,
            source="test",
            root=tmp_path
        )

        instinct_mod.promote_confidence(record_id, delta=0.2, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        # 0.9 + 0.2 = 1.1，但上限是 0.95
        assert record["confidence"] <= 0.95

    def test_promote_updates_last_reinforced_at(self, tmp_path):
        """
        promote 应更新 last_reinforced_at 时间戳。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.3,
            source="test",
            root=tmp_path
        )

        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record["last_reinforced_at"] is not None
        assert record["decay_status"] == "active"

    def test_promote_nonexistent_id_no_error(self, tmp_path):
        """
        promote 不存在的 ID 应不报错（静默忽略）。
        """
        # 不应抛出异常
        instinct_mod.promote_confidence("non-existent-id", delta=0.1, root=tmp_path)

    def test_promote_multiple_times_accumulates(self, tmp_path):
        """
        多次 promote 应累加置信度。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.3,
            source="test",
            root=tmp_path
        )

        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)
        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)
        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record["confidence"] == 0.6  # 0.3 + 0.1 * 3
        assert record["reinforcement_count"] == 3


# =============================================================================
# demote_confidence 测试
# =============================================================================

class TestDemoteConfidence:
    """测试 demote_confidence 置信度降低"""

    def test_demote_decreases_confidence(self, tmp_path):
        """
        demote_confidence 应降低置信度。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.5,
            source="test",
            root=tmp_path
        )

        instinct_mod.demote_confidence(record_id, delta=0.1, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record["confidence"] == 0.4  # 0.5 - 0.1

    def test_demote_floors_at_decay_floor(self, tmp_path):
        """
        置信度不应低于 decay_floor (默认 0.1)。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.15,
            source="test",
            root=tmp_path
        )

        instinct_mod.demote_confidence(record_id, delta=0.2, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        # 0.15 - 0.2 = -0.05，但下限是 0.1
        assert record["confidence"] >= 0.1

    def test_demote_decrements_reinforcement_count(self, tmp_path):
        """
        demote 应减少 reinforcement_count（但不低于 0）。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.5,
            source="test",
            root=tmp_path
        )

        # 先 promote 建立 reinforcement_count
        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)
        instinct_mod.promote_confidence(record_id, delta=0.1, root=tmp_path)

        instinct_mod.demote_confidence(record_id, delta=0.1, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record["reinforcement_count"] == 1  # 2 - 1


# =============================================================================
# reinforce_pattern 测试
# =============================================================================

class TestReinforcePattern:
    """测试 reinforce_pattern（promote_confidence 的别名）"""

    def test_reinforce_is_alias_for_promote(self, tmp_path):
        """
        reinforce_pattern 应与 promote_confidence 等效。
        """
        record_id = instinct_mod.add_pattern(
            pattern="测试模式",
            correction="测试纠正",
            confidence=0.3,
            source="test",
            root=tmp_path
        )

        instinct_mod.reinforce_pattern(record_id, delta=0.15, root=tmp_path)

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record["confidence"] == 0.45  # 0.3 + 0.15


# =============================================================================
# 置信度恢复机制集成测试
# =============================================================================

class TestConfidenceRecoveryMechanism:
    """测试置信度恢复机制：效果跟踪成功后本能记录置信度提升"""

    def test_effect_tracker_calls_promote_on_success(self, tmp_path, monkeypatch):
        """
        EffectTracker.track(outcome='success') 应调用 promote_confidence。
        """
        # 导入 effect_tracker
        effect_tracker_path = EVOLVE_DIR / "effect_tracker.py"
        spec2 = importlib.util.spec_from_file_location("effect_tracker_mod", effect_tracker_path)
        et_mod = importlib.util.module_from_spec(spec2)
        sys.modules["effect_tracker_mod"] = et_mod
        spec2.loader.exec_module(et_mod)

        # 添加一条本能记录
        record_id = instinct_mod.add_pattern(
            pattern="效果跟踪测试",
            correction="测试纠正",
            confidence=0.3,
            source="test",
            root=tmp_path
        )

        # 创建跟踪器（使用 tmp_path 作为 root）
        tracker = et_mod.EffectTracker(root=tmp_path)

        # 跟踪成功效果
        tracker.track(record_id, "success", {"test": True})

        # 验证置信度已提升
        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        assert record is not None
        assert record["confidence"] > 0.3, "成功跟踪后置信度应提升"

    def test_effect_tracker_does_not_promote_on_failure(self, tmp_path):
        """
        EffectTracker.track(outcome='failure') 不应调用 promote_confidence。
        """
        effect_tracker_path = EVOLVE_DIR / "effect_tracker.py"
        spec2 = importlib.util.spec_from_file_location("effect_tracker_mod2", effect_tracker_path)
        et_mod = importlib.util.module_from_spec(spec2)
        sys.modules["effect_tracker_mod2"] = et_mod
        spec2.loader.exec_module(et_mod)

        record_id = instinct_mod.add_pattern(
            pattern="失败跟踪测试",
            correction="测试纠正",
            confidence=0.5,
            source="test",
            root=tmp_path
        )

        tracker = et_mod.EffectTracker(root=tmp_path)
        tracker.track(record_id, "failure", {"test": True})

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        # 失败不应该提升置信度，保持 0.5
        assert record["confidence"] == 0.5

    def test_repeated_success_raises_confidence_over_time(self, tmp_path):
        """
        连续多次成功应持续提升置信度（直到上限）。
        """
        effect_tracker_path = EVOLVE_DIR / "effect_tracker.py"
        spec2 = importlib.util.spec_from_file_location("effect_tracker_mod3", effect_tracker_path)
        et_mod = importlib.util.module_from_spec(spec2)
        sys.modules["effect_tracker_mod3"] = et_mod
        spec2.loader.exec_module(et_mod)

        record_id = instinct_mod.add_pattern(
            pattern="重复成功测试",
            correction="测试纠正",
            confidence=0.3,
            source="test",
            root=tmp_path
        )

        tracker = et_mod.EffectTracker(root=tmp_path)

        # 跟踪 5 次成功
        for _ in range(5):
            tracker.track(record_id, "success")

        instinct = instinct_mod.load_instinct(tmp_path)
        record = next((r for r in instinct["records"] if r["id"] == record_id), None)
        # 0.3 + 0.1 * 5 = 0.8，但不超过 0.95
        assert 0.8 <= record["confidence"] <= 0.95
        assert record["reinforcement_count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])