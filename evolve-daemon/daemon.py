#!/usr/bin/env python3
"""
进化守护进程入口 — 由 cron/launchd 定时触发。

用法:
  python3 daemon.py check          # 仅检查触发条件
  python3 daemon.py run            # 检查并执行分析（cron 模式）
  python3 daemon.py status         # 查看系统状态
  python3 daemon.py install-launchd  # macOS: 安装 LaunchAgent
  python3 daemon.py install-systemd   # Linux: 安装 systemd timer

触发条件（满足任一即触发）:
  - 累计 ≥ 5 个新会话未分析
  - 同一 target 被纠正 ≥ 3 次
  - 距上次分析 ≥ 6 小时
"""
import json
import os
import sys
import yaml
from pathlib import Path
from datetime import datetime, timedelta


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


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
    """执行分析并生成提案"""
    sys.path.insert(0, str(Path(__file__).parent))
    from analyzer import aggregate_and_analyze
    from proposer import generate_proposal

    analysis = aggregate_and_analyze(sessions, config, root)

    if analysis.get("should_propose"):
        proposal_path = generate_proposal(analysis, config, root)
        print(f"✅ 提案已生成: {proposal_path}")

        # 更新分析状态
        state_file = root / config["paths"]["data_dir"] / "analysis_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "last_analyzed_session_id": sessions[-1]["session_id"],
            "last_analyze_time": datetime.now().isoformat(),
            "total_sessions_analyzed": len(sessions),
        }
        state_file.write_text(json.dumps(state, indent=2))
    else:
        print("分析完成，当前无需提案")


def install_launchd(root: Path):
    """macOS: 生成 LaunchAgent plist 并安装"""
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-team-kit.evolve</string>
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

    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.claude-team-kit.evolve.plist"
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

    elif cmd == "install-systemd":
        print("systemd 安装请参考 docs/evolve-daemon-design.md 第 5.2 节")

    else:
        print(f"未知命令: {cmd}")
        print("用法: python3 daemon.py [check|run|status|install-launchd|install-systemd]")


if __name__ == "__main__":
    main()
