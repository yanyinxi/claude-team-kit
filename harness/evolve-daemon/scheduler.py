#!/usr/bin/env python3
"""
内置定时任务调度器 — 基于 APScheduler 实现异步定时触发。

使用方式：
  python3 -m evolve_daemon.scheduler start   # 启动调度器（前台运行）
  python3 -m evolve_daemon.scheduler stop    # 停止调度器
  python3 -m evolve_daemon.scheduler status  # 查看状态
"""
import argparse
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

# APScheduler 可能是可选依赖
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False


def get_project_root():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def load_config():
    """加载配置"""
    config_path = Path(__file__).parent / "config.yaml"
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        # Fallback 默认配置
        return {
            "daemon": {
                "mode": "external",
                "scheduler_interval": "30 minutes",
                "run_on_startup": False,
                "heartbeat_check_minutes": 180,  # 3 小时
                "auto_start_on_install": True,
            }
        }


def parse_interval(interval_str: str) -> int:
    """
    解析间隔字符串，返回秒数。

    支持格式：
      - "30 seconds" / "30 s"
      - "30 minutes" / "30 m"
      - "2 hours" / "2 h"

    返回：秒数
    """
    interval_str = interval_str.strip().lower()

    # 解析数字和单位
    parts = interval_str.split()
    if len(parts) != 2:
        raise ValueError(f"Invalid interval format: {interval_str}. Expected like '30 minutes'")

    try:
        value = int(parts[0])
    except ValueError:
        raise ValueError(f"Invalid interval value: {parts[0]}")

    unit = parts[1].lower()

    if unit in ("second", "seconds", "s"):
        return value
    elif unit in ("minute", "minutes", "m"):
        return value * 60
    elif unit in ("hour", "hours", "h"):
        return value * 3600
    else:
        raise ValueError(f"Unknown time unit: {unit}. Use 'seconds', 'minutes', or 'hours'")


def run_evolution_cycle():
    """执行一次完整的进化周期"""
    root = get_project_root()
    daemon_path = root / "evolve-daemon" / "daemon.py"

    if not daemon_path.exists():
        print(f"[{datetime.now().isoformat()}] daemon.py not found: {daemon_path}")
        return False

    # 调用 daemon.py run
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(daemon_path), "run"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 分钟超时
            cwd=str(root),
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        )

        timestamp = datetime.now().isoformat()
        if result.returncode == 0:
            print(f"[{timestamp}] 进化周期完成")
            if result.stdout.strip():
                for line in result.stdout.strip().split("\n")[-3:]:
                    print(f"    {line}")
            return True
        else:
            print(f"[{timestamp}] 进化周期失败 (exit={result.returncode})")
            if result.stderr.strip():
                for line in result.stderr.strip().split("\n")[:3]:
                    print(f"    {line}")
            return False

    except subprocess.TimeoutExpired:
        print(f"[{datetime.now().isoformat()}] 进化周期超时（5分钟）")
        return False
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] 进化周期异常: {e}")
        return False


def get_last_evolution_time(data_dir: Path) -> datetime | None:
    """获取上次进化的时间"""
    state_file = data_dir / "analysis_state.json"
    if not state_file.exists():
        return None
    try:
        import json
        state = json.loads(state_file.read_text(encoding="utf-8"))
        last_time = state.get("last_analyze_time")
        if last_time:
            return datetime.fromisoformat(last_time)
    except Exception:
        pass
    return None


def check_heartbeat(config: dict, data_dir: Path) -> dict:
    """
    心跳检测：检查是否需要触发进化

    返回：
        {
            "healthy": True/False,
            "reason": str,
            "should_run": True/False,
            "last_evolution": datetime or None,
            "minutes_since_evolution": int or None,
        }
    """
    heartbeat_minutes = config.get("daemon", {}).get("heartbeat_check_minutes", 180)

    last_time = get_last_evolution_time(data_dir)
    now = datetime.now()

    if last_time is None:
        return {
            "healthy": False,
            "reason": "从未执行过进化",
            "should_run": True,
            "last_evolution": None,
            "minutes_since_evolution": None,
        }

    minutes_since = int((now - last_time).total_seconds() / 60)

    if minutes_since >= heartbeat_minutes:
        return {
            "healthy": False,
            "reason": f"距离上次进化已过 {minutes_since} 分钟，超过阈值 {heartbeat_minutes} 分钟",
            "should_run": True,
            "last_evolution": last_time,
            "minutes_since_evolution": minutes_since,
        }

    return {
        "healthy": True,
        "reason": f"上次进化在 {minutes_since} 分钟前，系统运行正常",
        "should_run": False,
        "last_evolution": last_time,
        "minutes_since_evolution": minutes_since,
    }


class SchedulerManager:
    """调度器管理器"""

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._scheduler = None
            self._config = None
            self._running = False
            self._initialized = True

    def load_config(self):
        self._config = load_config()
        return self._config

    def is_available(self) -> bool:
        """检查 APScheduler 是否可用"""
        return APSCHEDULER_AVAILABLE

    def is_running(self) -> bool:
        return self._running and self._scheduler is not None and self._scheduler.running

    def get_data_dir(self) -> Path:
        """获取数据目录"""
        config = self.load_config()
        paths = config.get("paths", {})
        data_dir = paths.get("data_dir", ".claude/data")
        return get_project_root() / data_dir

    def start(self, force: bool = False) -> dict:
        """
        启动调度器

        Args:
            force: 是否强制启动（即使心跳检测正常）
        """
        if not APSCHEDULER_AVAILABLE:
            return {"success": False, "error": "APScheduler not installed. Run: pip install APScheduler"}

        if self.is_running() and not force:
            return {"success": False, "error": "Scheduler already running"}

        config = self.load_config()
        daemon_config = config.get("daemon", {})

        # 检查模式
        mode = daemon_config.get("mode", "external")
        if mode not in ("internal", "both"):
            return {"success": False, "error": f"Daemon mode is '{mode}', not 'internal' or 'both'"}

        # 解析间隔
        interval_str = daemon_config.get("scheduler_interval", "30 minutes")
        try:
            interval_seconds = parse_interval(interval_str)
        except ValueError as e:
            return {"success": False, "error": f"Invalid scheduler_interval: {e}"}

        # 心跳检测
        data_dir = self.get_data_dir()
        heartbeat_config = daemon_config.get("heartbeat_check_minutes", 180)
        heartbeat_result = check_heartbeat(config, data_dir)

        # 如果心跳正常且非强制启动，检查是否需要先运行一次
        should_run_now = force or heartbeat_result["should_run"]

        # 创建调度器
        self._scheduler = BackgroundScheduler()

        # 添加心跳检测任务（更频繁地检查）
        heartbeat_interval = max(interval_seconds, 60)  # 至少 1 分钟
        self._scheduler.add_job(
            self._heartbeat_check,
            trigger=IntervalTrigger(seconds=heartbeat_interval),
            id="heartbeat_check",
            name="Heartbeat Check",
            replace_existing=True,
        )

        # 添加定时进化任务
        self._scheduler.add_job(
            self._scheduled_evolution,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="evolution_cycle",
            name="Auto-Evolve Cycle",
            replace_existing=True,
        )

        # 启动
        self._scheduler.start()
        self._running = True

        # 立即运行一次（如果需要）
        if should_run_now and daemon_config.get("run_on_startup", False):
            print("执行启动时检查...")
            self._scheduled_evolution()

        result = {
            "success": True,
            "mode": mode,
            "interval": interval_str,
            "interval_seconds": interval_seconds,
            "run_on_startup": daemon_config.get("run_on_startup", False),
            "heartbeat_check": heartbeat_result,
            "next_run": None,
        }

        # 获取下次运行时间
        job = self._scheduler.get_job("evolution_cycle")
        if job and job.next_run_time:
            result["next_run"] = job.next_run_time.isoformat()

        return result

    def _heartbeat_check(self):
        """心跳检测任务"""
        config = self.load_config()
        data_dir = self.get_data_dir()
        result = check_heartbeat(config, data_dir)

        if result["should_run"]:
            print(f"[{datetime.now().isoformat()}] 心跳检测: {result['reason']}")
            print("    触发紧急进化...")
            run_evolution_cycle()

    def _scheduled_evolution(self):
        """定时进化任务"""
        print(f"[{datetime.now().isoformat()}] 执行定时进化...")
        run_evolution_cycle()

    def stop(self) -> dict:
        """停止调度器"""
        if not self.is_running():
            return {"success": False, "error": "Scheduler not running"}

        self._scheduler.shutdown(wait=False)
        self._running = False
        self._scheduler = None

        return {"success": True}

    def status(self) -> dict:
        """获取调度器状态"""
        if not APSCHEDULER_AVAILABLE:
            return {
                "available": False,
                "installed": False,
                "running": False,
                "error": "APScheduler not installed. Run: pip install APScheduler",
            }

        config = self.load_config()
        daemon_config = config.get("daemon", {})
        mode = daemon_config.get("mode", "external")
        data_dir = self.get_data_dir()

        # 心跳状态
        heartbeat_result = check_heartbeat(config, data_dir)

        if not self.is_running():
            return {
                "available": True,
                "installed": True,
                "running": False,
                "mode": mode,
                "scheduler_interval": daemon_config.get("scheduler_interval", "30 minutes"),
                "heartbeat": heartbeat_result,
            }

        job = self._scheduler.get_job("evolution_cycle")
        return {
            "available": True,
            "installed": True,
            "running": True,
            "mode": mode,
            "scheduler_interval": daemon_config.get("scheduler_interval", "30 minutes"),
            "heartbeat": heartbeat_result,
            "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "last_run": job.last_run_time.isoformat() if job and job.last_run_time else None,
        }

    def trigger_now(self) -> dict:
        """立即触发一次进化周期"""
        if not self.is_running():
            return {"success": False, "error": "Scheduler not running"}

        # 在后台线程中运行
        run_evolution_cycle()
        return {"success": True}


# 全局单例
_manager = SchedulerManager()


def main():
    parser = argparse.ArgumentParser(
        description="内置定时任务调度器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 -m evolve_daemon.scheduler start   # 启动调度器
  python3 -m evolve_daemon.scheduler stop    # 停止调度器
  python3 -m evolve_daemon.scheduler status  # 查看状态
  python3 -m evolve_daemon.scheduler run     # 立即运行一次
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # start
    start_parser = subparsers.add_parser("start", help="启动调度器")
    start_parser.add_argument("--daemon", action="store_true", help="后台运行")

    # stop
    subparsers.add_parser("stop", help="停止调度器")

    # status
    subparsers.add_parser("status", help="查看调度器状态")

    # run
    subparsers.add_parser("run", help="立即执行一次进化周期")

    # check-apScheduler
    subparsers.add_parser("check", help="检查 APScheduler 是否可用")

    args = parser.parse_args()

    if args.command == "check":
        if APSCHEDULER_AVAILABLE:
            print("APScheduler 已安装")
            config = _manager.load_config()
            daemon_config = config.get("daemon", {})
            print(f"   模式: {daemon_config.get('mode', 'external')}")
            print(f"   间隔: {daemon_config.get('scheduler_interval', '30 minutes')}")
        else:
            print("APScheduler 未安装")
            print("   安装: pip install APScheduler")
        return

    if args.command == "status":
        status = _manager.status()
        print(f"状态: {status}")
        return

    if args.command == "start":
        result = _manager.start()
        if result.get("success"):
            print(f"调度器已启动")
            print(f"   模式: {result.get('mode')}")
            print(f"   间隔: {result.get('interval')} ({result.get('interval_seconds')}s)")
            print(f"   下次运行: {result.get('next_run')}")
            if result.get("run_on_startup"):
                print(f"   启动时立即运行: 是")

            if args.daemon:
                print("\n[后台运行中，按 Ctrl+C 停止]")
                try:
                    while True:
                        time.sleep(60)
                except KeyboardInterrupt:
                    print("\n正在停止调度器...")
                    _manager.stop()
                    print("已停止")
        else:
            print(f"启动失败: {result.get('error')}")
        return

    if args.command == "stop":
        result = _manager.stop()
        if result.get("success"):
            print("调度器已停止")
        else:
            print(f"停止失败: {result.get('error')}")
        return

    if args.command == "run":
        print("立即执行一次进化周期...")
        run_evolution_cycle()
        return

    # 默认显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()