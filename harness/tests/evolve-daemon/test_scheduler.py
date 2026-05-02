#!/usr/bin/env python3
"""
scheduler 模块测试
"""
import pytest
import sys
from pathlib import Path

EVOLVE_DIR = Path(__file__).parent.parent.parent / "evolve-daemon"
import importlib.util
spec = importlib.util.spec_from_file_location("sched_mod", EVOLVE_DIR / "scheduler.py")
sched_mod = importlib.util.module_from_spec(spec)
sys.modules["sched_mod"] = sched_mod
spec.loader.exec_module(sched_mod)


class TestParseInterval:
    def test_parse_seconds(self):
        assert sched_mod.parse_interval("30 seconds") == 30
        assert sched_mod.parse_interval("30 s") == 30
        assert sched_mod.parse_interval("60 seconds") == 60

    def test_parse_minutes(self):
        assert sched_mod.parse_interval("30 minutes") == 1800
        assert sched_mod.parse_interval("30 m") == 1800
        assert sched_mod.parse_interval("1 minute") == 60

    def test_parse_hours(self):
        assert sched_mod.parse_interval("2 hours") == 7200
        assert sched_mod.parse_interval("2 h") == 7200
        assert sched_mod.parse_interval("1 hour") == 3600

    def test_parse_invalid_format(self):
        import pytest
        with pytest.raises(ValueError):
            sched_mod.parse_interval("invalid")
        with pytest.raises(ValueError):
            sched_mod.parse_interval("30")
        with pytest.raises(ValueError):
            sched_mod.parse_interval("abc minutes")

    def test_parse_invalid_unit(self):
        import pytest
        with pytest.raises(ValueError):
            sched_mod.parse_interval("30 days")


class TestSchedulerManager:
    def test_singleton(self):
        m1 = sched_mod.SchedulerManager()
        m2 = sched_mod.SchedulerManager()
        assert m1 is m2

    def test_status_returns_dict(self):
        m = sched_mod.SchedulerManager()
        m._running = False
        m._scheduler = None
        status = m.status()
        assert isinstance(status, dict)
        assert "available" in status

    def test_apscheduler_available_is_bool(self):
        assert isinstance(sched_mod.APSCHEDULER_AVAILABLE, bool)


class TestConfigLoading:
    def test_load_config_structure(self):
        config = sched_mod.load_config()
        assert "daemon" in config
        assert "mode" in config["daemon"]
        assert "scheduler_interval" in config["daemon"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
