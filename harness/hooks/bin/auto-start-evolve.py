#!/usr/bin/env python3
"""
自动启动进化调度器

当插件首次加载时（SessionStart），自动检查并启动进化调度器。
"""
import os
import sys
from pathlib import Path
from datetime import datetime


def main():
    """自动启动调度器"""
    try:
        import yaml

        # 获取插件根目录
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if not plugin_root:
            print("[auto-start-evolve] CLAUDE_PLUGIN_ROOT not set, skipping")
            sys.exit(0)

        # 加载配置
        config_path = Path(plugin_root) / "evolve-daemon" / "config.yaml"
        if not config_path.exists():
            print("[auto-start-evolve] config.yaml not found, skipping")
            sys.exit(0)

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        daemon_config = config.get("daemon", {})
        auto_start = daemon_config.get("auto_start_on_install", True)

        if not auto_start:
            print("[auto-start-evolve] auto_start_on_install=false, skipping")
            sys.exit(0)

        # 检查是否已运行
        project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
        sys.path.insert(0, str(project_root / "evolve-daemon"))

        from scheduler import SchedulerManager, APSCHEDULER_AVAILABLE

        if not APSCHEDULER_AVAILABLE:
            print("[auto-start-evolve] APScheduler not installed, skipping")
            sys.exit(0)

        manager = SchedulerManager()

        if manager.is_running():
            status = manager.status()
            print(f"[auto-start-evolve] Scheduler already running, mode={status.get('mode')}")
            sys.exit(0)

        # 启动调度器
        result = manager.start(force=False)

        if result.get("success"):
            mode = result.get("mode")
            interval = result.get("interval")
            heartbeat = result.get("heartbeat_check", {})

            print(f"[auto-start-evolve] Scheduler started successfully")
            print(f"  Mode: {mode}")
            print(f"  Interval: {interval}")

            if heartbeat.get("should_run"):
                print(f"  Heartbeat: {heartbeat.get('reason')} - will trigger evolution")
            else:
                print(f"  Heartbeat: {heartbeat.get('reason')}")
        else:
            error = result.get("error", "Unknown error")
            print(f"[auto-start-evolve] Failed to start scheduler: {error}")

    except ImportError:
        # PyYAML 或其他依赖未安装
        print("[auto-start-evolve] Dependencies not ready, skipping")
        sys.exit(0)
    except Exception as e:
        # 静默失败，不影响正常流程
        print(f"[auto-start-evolve] Error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()