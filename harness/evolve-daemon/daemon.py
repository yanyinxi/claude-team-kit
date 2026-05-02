#!/usr/bin/env python3
"""
进化守护进程入口 — 支持外部触发和内置定时任务。

用法:
  python3 daemon.py check          # 仅检查触发条件
  python3 daemon.py run            # 检查并执行分析（外部触发模式）
  python3 daemon.py start          # 启动内置调度器（内部定时触发）
  python3 daemon.py stop           # 停止内置调度器
  python3 daemon.py status         # 查看系统状态
  python3 daemon.py install-launchd  # macOS: 安装 LaunchAgent（外部触发）

触发条件（满足任一即触发）:
  - 累计 >= 5 个新会话未分析
  - 同一 target 被纠正 >= 3 次
  - 距上次分析 >= 6 小时

内置调度器配置（config.yaml）:
  daemon:
    mode: internal           # external/internal/both
    scheduler_interval: 30 minutes
    run_on_startup: true
"""
import json
import os
import sys
try:
    import yaml
except ImportError:
    yaml = None
from pathlib import Path
from datetime import datetime, timedelta


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    if yaml is not None:
        with open(config_path) as f:
            return yaml.safe_load(f)
    # Fallback: inline default config when PyYAML is not installed
    return {
        "daemon": {"schedule": "*/30 * * * *", "idle_trigger_minutes": 120, "extract_timeout_seconds": 5},
        "thresholds": {"min_new_sessions": 5, "min_same_pattern_corrections": 3, "max_hours_since_last_analyze": 6},
        "safety": {"max_proposals_per_day": 3, "auto_close_days": 7, "breaker": {"max_consecutive_rejects": 3, "pause_days": 30}},
        "paths": {"data_dir": ".claude/data", "proposals_dir": ".claude/proposals", "skills_dir": "skills", "agents_dir": "agents", "rules_dir": "rules", "instinct_dir": "instinct"},
    }


def find_root():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def load_new_sessions(data_dir: Path, last_analyzed_id: str | None = None) -> list[dict]:
    """加载自上次分析以来的新会话"""
    sessions_file = data_dir / "sessions.jsonl"
    if not sessions_file.exists():
        return []

    sessions = []
    with open(sessions_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    sessions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if last_analyzed_id:
        try:
            idx = next(i for i, s in enumerate(sessions)
                       if s.get("session_id") == last_analyzed_id)
            sessions = sessions[idx + 1:]
        except StopIteration:
            pass

    return sessions


def check_thresholds(sessions: list[dict], config: dict, last_analyze_time: datetime | None = None) -> list[str]:
    """检查是否满足触发条件"""
    thresholds = config["thresholds"]
    triggers = []

    # 条件1: 新会话数达标
    if len(sessions) >= thresholds["min_new_sessions"]:
        triggers.append(f"new_sessions: {len(sessions)} >= {thresholds['min_new_sessions']}")

    # 条件2: 距上次分析超过最大间隔
    if last_analyze_time:
        hours_since = (datetime.now() - last_analyze_time).total_seconds() / 3600
        if hours_since >= thresholds["max_hours_since_last_analyze"]:
            triggers.append(f"time_elapsed: {hours_since:.1f}h >= {thresholds['max_hours_since_last_analyze']}h")

    # 条件3: 同一 target 被同一模式多次纠正
    pattern_groups: dict[str, list] = {}
    for s in sessions:
        for c in s.get("corrections", []):
            key = f"{c.get('target', 'unknown')}:{c.get('root_cause_hint', 'unknown')}"
            pattern_groups.setdefault(key, []).append(c)

    for key, corrections in pattern_groups.items():
        if len(corrections) >= thresholds["min_same_pattern_corrections"]:
            triggers.append(
                f"pattern: {key} corrected {len(corrections)}x >= "
                f"{thresholds['min_same_pattern_corrections']}"
            )

    return triggers


def run_analysis(config: dict, root: Path, sessions: list[dict]):
    """执行分析并生成提案（4维度进化闭环）"""
    # 1. 语义提取（每个新会话）
    try:
        from extract_semantics import analyze_sessions
        analyze_sessions(sessions, root)
    except Exception:
        pass  # 语义提取失败不影响主流程

    # 2. 数据聚合分析
    from analyzer import aggregate_and_analyze
    analysis = aggregate_and_analyze(sessions, config, root)

    if not analysis.get("should_propose"):
        print("分析完成，当前无需提案")
        return

    # 3. 4维度分发
    try:
        from evolve_dispatcher import dispatch_evolution
        decisions = dispatch_evolution(analysis, config, root, sessions)
    except ImportError:
        decisions = []

    # 4. 执行决策
    applied_count = 0
    proposed_count = 0
    skipped_count = 0

    for decision in decisions:
        dimension = decision.get("dimension", "")
        action = decision.get("action", "")
        target = decision.get("target", "")

        try:
            if action == "auto_apply":
                _execute_auto_apply(decision, analysis, config, root)
                applied_count += 1
            elif action == "propose":
                _execute_propose(decision, analysis, config, root)
                proposed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"⚠️  [{dimension}] {target} 执行失败: {e}")

    # 更新分析状态
    state_file = root / config["paths"]["data_dir"] / "analysis_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "last_analyzed_session_id": sessions[-1]["session_id"],
        "last_analyze_time": datetime.now().isoformat(),
        "total_sessions_analyzed": len(sessions),
        "decisions_applied": applied_count,
        "decisions_proposed": proposed_count,
    }
    state_file.write_text(json.dumps(state, indent=2))

    print(f"✅ 分析完成: auto_apply={applied_count}, propose={proposed_count}, skip={skipped_count}")


def _execute_auto_apply(decision: dict, analysis: dict, config: dict, root: Path):
    """执行 auto_apply 决策"""
    dimension = decision.get("dimension", "")
    target = decision.get("target", "")
    target_file = decision.get("target_file", "")
    suggested_change = decision.get("suggested_change", "")

    if not target_file or not suggested_change:
        return

    # 各维度执行
    if dimension == "agent":
        from agent_evolution import evolve_agent
        corrections = analysis.get("correction_patterns", {}).get(f"{target}:unknown", {}).get("examples", [])
        result = evolve_agent(target, corrections, config, root)
        if result.get("success"):
            _apply_file_change(target_file, result.get("suggested_change", ""), config, root)
            print(f"✅ [Agent] {target}: {result.get('change_type')}")

    elif dimension == "instinct":
        from instinct_updater import add_pattern
        from extract_semantics import _record_to_instinct
        # instinct 已在 extract_semantics 中记录
        print(f"✅ [Instinct] {target}: 已记录")


def _execute_propose(decision: dict, analysis: dict, config: dict, root: Path):
    """执行 propose 决策"""
    dimension = decision.get("dimension", "")
    target = decision.get("target", "")
    target_file = decision.get("target_file", "")
    suggested_change = decision.get("suggested_change", "")

    from proposer import generate_proposal

    # 构建带维度的分析
    dimension_analysis = {**analysis, "dimension": dimension, "target_file": target_file, "suggested_change": suggested_change}
    proposal_path = generate_proposal(dimension_analysis, config, root)
    if proposal_path:
        print(f"📋 [{dimension}] {target}: 提案已生成")
    else:
        print(f"⚠️ [{dimension}] {target}: 提案生成失败")


def _apply_file_change(target_file: str, suggested_change: str, config: dict, root: Path):
    """将改动应用到文件"""
    from apply_change import apply_change

    decision = {
        "target_file": target_file,
        "suggested_change": suggested_change,
        "id": f"auto-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    }
    try:
        apply_change(decision, root)
    except Exception:
        # fallback: 直接追加内容
        try:
            file_path = Path(target_file)
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                content += suggested_change
                file_path.write_text(content, encoding="utf-8")
        except Exception:
            pass


def install_launchd(root: Path):
    """macOS: 生成 LaunchAgent plist 并安装"""
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-harness-kit.evolve</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{Path(__file__).resolve()}</string>
        <string>run</string>
    </array>
    <key>StartInterval</key>
    <integer>14400</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CLAUDE_PROJECT_DIR</key>
        <string>{root}</string>
    </dict>
</dict>
</plist>"""

    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.claude-harness-kit.evolve.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist)
    print(f"✅ LaunchAgent 已安装: {plist_path}")
    print(f"   加载: launchctl load {plist_path}")
    print(f"   卸载: launchctl unload {plist_path}")


def main():
    config = load_config()
    root = find_root()
    data_dir = root / config["paths"]["data_dir"]

    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    # 读取分析状态
    state_file = data_dir / "analysis_state.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    last_analyzed_id = state.get("last_analyzed_session_id")
    last_analyze_time = None
    if state.get("last_analyze_time"):
        try:
            last_analyze_time = datetime.fromisoformat(state["last_analyze_time"])
        except (ValueError, TypeError):
            pass

    sessions = load_new_sessions(data_dir, last_analyzed_id)

    if cmd == "check":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        print(json.dumps({
            "new_sessions": len(sessions),
            "last_analyze_time": str(last_analyze_time),
            "triggers": triggers,
            "should_run": len(triggers) > 0,
        }, indent=2, ensure_ascii=False))

    elif cmd == "run":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        if not triggers:
            print("无触发条件，跳过分析")
            return
        print(f"触发条件: {', '.join(triggers)}")
        run_analysis(config, root, sessions)

    elif cmd == "status":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        proposals_dir = root / config["paths"]["proposals_dir"]
        proposals = list(proposals_dir.glob("*.md")) if proposals_dir.exists() else []
        print(json.dumps({
            "total_sessions_file": str(data_dir / "sessions.jsonl"),
            "new_sessions_since_last_analyze": len(sessions),
            "pending_proposals": len(proposals),
            "will_trigger": len(triggers) > 0,
            "triggers": triggers,
        }, indent=2, ensure_ascii=False))

    elif cmd == "install-launchd":
        install_launchd(root)

    elif cmd == "start":
        # 内置调度器模式
        from scheduler import _manager
        result = _manager.start()
        if result.get("success"):
            print(f"调度器已启动")
            print(f"   模式: {result.get('mode')}")
            print(f"   间隔: {result.get('interval')} ({result.get('interval_seconds')}s)")
            if result.get("run_on_startup"):
                print(f"   启动时立即运行: 是")
            print("\n后台运行中，按 Ctrl+C 停止")
            try:
                import time as time_module
                while True:
                    time_module.sleep(60)
            except KeyboardInterrupt:
                print("\n正在停止调度器...")
                _manager.stop()
                print("已停止")
        else:
            print(f"启动失败: {result.get('error')}")
            print("提示：确保 config.yaml 中 daemon.mode 包含 'internal'")
            print("提示：确保已安装 APScheduler: pip install APScheduler")

    elif cmd == "stop":
        # 停止内置调度器
        from scheduler import _manager
        result = _manager.stop()
        if result.get("success"):
            print("调度器已停止")
        else:
            print(f"停止失败: {result.get('error')}")

    else:
        print(f"未知命令: {cmd}")
        print("用法: python3 daemon.py [check|run|start|stop|status|install-launchd]")
        print("")
        print("命令说明：")
        print("  check           - 仅检查触发条件")
        print("  run             - 检查并执行分析（外部触发模式）")
        print("  start           - 启动内置调度器（内部定时触发）")
        print("  stop            - 停止内置调度器")
        print("  status          - 查看系统状态")
        print("  install-launchd - macOS: 安装 LaunchAgent")
        print("")
        print("示例：")
        print("  python3 daemon.py check           # 检查触发条件")
        print("  python3 daemon.py start          # 启动内置调度器")


if __name__ == "__main__":
    main()
