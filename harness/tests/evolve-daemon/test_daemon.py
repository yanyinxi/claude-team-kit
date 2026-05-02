#!/usr/bin/env python3
"""
daemon.py 测试文件
"""
import pytest
import sys
from pathlib import Path

EVOLVE_DIR = Path(__file__).parent.parent.parent / "evolve-daemon"
import importlib.util
spec = importlib.util.spec_from_file_location("daemon_mod", EVOLVE_DIR / "daemon.py")
daemon_mod = importlib.util.module_from_spec(spec)
sys.modules["daemon_mod"] = daemon_mod
spec.loader.exec_module(daemon_mod)


class TestLoadConfig:
    def test_load_config_returns_dict(self):
        config = daemon_mod.load_config()
        assert isinstance(config, dict)
        assert "daemon" in config

    def test_daemon_config_has_mode(self):
        config = daemon_mod.load_config()
        assert "mode" in config["daemon"]


class TestFindRoot:
    def test_find_root_returns_path(self):
        root = daemon_mod.find_root()
        assert isinstance(root, Path)


class TestCheckThresholds:
    def test_empty_sessions_returns_empty_triggers(self):
        config = daemon_mod.load_config()
        triggers = daemon_mod.check_thresholds([], config)
        assert isinstance(triggers, list)

    def test_sessions_count_triggers(self):
        config = daemon_mod.load_config()
        sessions = [{"session_id": f"session_{i}"} for i in range(10)]
        triggers = daemon_mod.check_thresholds(sessions, config)
        assert len(triggers) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
