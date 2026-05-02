#!/usr/bin/env python3
"""
Stop Hook: 聚合本轮会话摘要，触发语义提取。

阶段 1: 元数据收集
  读取本轮所有临时 jsonl → 构建会话摘要行 → 写入 sessions.jsonl

阶段 2: 触发 extract_semantics.py（异步，不阻塞）
  如果检测到用户纠正，异步触发语义提取

设计原则:
  - Hook 只采集元数据，不做 AI 调用
  - 非阻塞：写入一行 JSONL 后立即返回
  - 语义提取异步触发，失败不影响主流程
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter


def find_project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def get_session_id_fallback(root: Path) -> str:
    """生成确定性的 session_id"""
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                if commit:
                    from datetime import date
                    today = date.today().isoformat()
                    return f"git-{commit}-{today}"
        except Exception:
            pass

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{root.name}-{ts}"


def read_session_start(root: Path) -> dict:
    """读取 .session_start 文件"""
    session_start_file = root / ".claude" / "data" / ".session_start"
    if session_start_file.exists():
        try:
            return json.loads(session_start_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def calculate_duration(session_start: dict) -> int:
    """从 session_start 计算 duration_minutes"""
    if not session_start:
        return 0
    try:
        start_time = datetime.fromisoformat(session_start.get("timestamp", ""))
        duration = datetime.now() - start_time
        return max(0, int(duration.total_seconds() / 60))
    except (ValueError, TypeError):
        return 0


def aggregate_agent_calls(root: Path) -> list:
    """从 agent_calls.jsonl 汇总 agents_used"""
    agent_calls_file = root / ".claude" / "data" / "agent_calls.jsonl"
    if not agent_calls_file.exists():
        return []

    agents = set()
    try:
        content = agent_calls_file.read_text().strip()
        if content:
            for line in content.splitlines():
                try:
                    call = json.loads(line)
                    agent = call.get("agent", "")
                    if agent:
                        agents.add(agent)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    return sorted(list(agents))


def aggregate_failures(root: Path) -> int:
    """从 failures.jsonl 统计 tool_failures"""
    failures_file = root / ".claude" / "data" / "failures.jsonl"
    if not failures_file.exists():
        return 0

    try:
        content = failures_file.read_text().strip()
        if content:
            return len(content.splitlines())
    except OSError:
        pass

    return 0


def get_git_files_changed(root: Path) -> int:
    """执行 git diff --stat 统计 git_files_changed"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=root, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            files = result.stdout.strip()
            if files:
                return len(files.splitlines())

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=root, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            files = result.stdout.strip()
            if files:
                return len(files.splitlines())
    except Exception:
        pass

    return 0


def build_rich_context(root: Path) -> dict:
    """从 agent_calls 提取 rich_context（工具使用分布等）"""
    agent_calls_file = root / ".claude" / "data" / "agent_calls.jsonl"
    context = {
        "agent_count": 0,
        "agents": [],
    }

    if agent_calls_file.exists():
        try:
            content = agent_calls_file.read_text().strip()
            if content:
                agent_list = []
                for line in content.splitlines():
                    try:
                        call = json.loads(line)
                        agent = call.get("agent", "")
                        if agent:
                            agent_list.append(agent)
                    except json.JSONDecodeError:
                        continue

                if agent_list:
                    counter = Counter(agent_list)
                    context["agent_count"] = len(agent_list)
                    context["agents"] = list(counter.keys())
                    context["agent_distribution"] = dict(counter)
        except OSError:
            pass

    return context


def build_session_summary(root: Path) -> dict:
    """从所有数据源构建完整的会话摘要"""
    try:
        raw = sys.stdin.read().strip()
        hook_data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    session_start = read_session_start(root)

    session_id = hook_data.get("session_id", os.environ.get("CLAUDE_SESSION_ID"))
    if not session_id or session_id == "unknown":
        session_id = get_session_id_fallback(root)

    mode = session_start.get("mode", os.environ.get("CLAUDE_MODE", "solo"))

    agents_used = aggregate_agent_calls(root)
    tool_failures = aggregate_failures(root)
    duration_minutes = calculate_duration(session_start)
    git_files_changed = get_git_files_changed(root)
    rich_context = build_rich_context(root)

    return {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "duration_minutes": duration_minutes,
        "agents_used": agents_used,
        "skills_used": hook_data.get("skills_used", []),
        "tool_failures": tool_failures,
        "git_files_changed": git_files_changed,
        "corrections": [],
        "rich_context": rich_context,
    }


def append_session(root: Path, session: dict) -> int:
    """追加一行到 sessions.jsonl"""
    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    log_file = data_dir / "sessions.jsonl"
    line = json.dumps(session, ensure_ascii=False) + "\n"
    with open(log_file, "a") as f:
        f.write(line)

    return 0


def trigger_semantic_extraction(root: Path):
    """异步触发语义提取"""
    daemon_dir = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", root)) / "hooks" / "bin"
    extract_script = daemon_dir / "extract_semantics.py"
    if not extract_script.exists():
        return False

    subprocess.Popen(
        [sys.executable, str(extract_script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def main():
    root = find_project_root()

    session = build_session_summary(root)
    append_session(root, session)

    corrections = session.get("corrections", [])
    has_corrections = bool(corrections) or bool(os.environ.get("CLAUDE_HAS_CORRECTIONS"))

    if not has_corrections:
        data_dir = root / ".claude" / "data"
        failures_file = data_dir / "failures.jsonl"
        if failures_file.exists():
            try:
                failures = failures_file.read_text().strip()
                if failures and len(failures.splitlines()) > 0:
                    has_corrections = True
            except OSError:
                pass

    extraction_triggered = False
    if has_corrections:
        extraction_triggered = trigger_semantic_extraction(root)

    result = {
        "collected": True,
        "session_id": session["session_id"],
        "extraction_triggered": extraction_triggered,
        "duration_minutes": session["duration_minutes"],
        "agents_used": len(session["agents_used"]),
        "tool_failures": session["tool_failures"],
        "git_files_changed": session["git_files_changed"],
    }
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"collected": False, "warning": str(e)[:100]}), file=sys.stderr)
        sys.exit(0)