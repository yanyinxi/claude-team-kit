#!/usr/bin/env python3
"""
Stop Hook: 收集会话数据，触发进化分析。

Phase 1 核心功能:
  1. 收集会话元数据（duration, agents, failures, git changes）
  2. 从 failures.jsonl 提取失败模式（不需要用户纠正）
  3. 触发异步分析（不阻塞主流程）

为什么不用 corrections：
  - 用户纠正信号难以可靠获取
  - failures.jsonl 是客观的、可测量的信号
  - 高频失败 → 提示/文档需要改进
  - 这是真正全自动进化的基础
"""
import json
import os
import subprocess
import sys
from datetime import datetime, date
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


def aggregate_agent_calls(root: Path, session_id: str = None) -> dict:
    """从 agent_calls.jsonl 汇总 agent 使用情况

    Args:
        root: 项目根目录
        session_id: 如果提供，只统计匹配此 session_id 的记录
    """
    agent_calls_file = root / ".claude" / "data" / "agent_calls.jsonl"
    result = {
        "agents": [],
        "agent_count": 0,
        "agent_distribution": {},
        "success_count": 0,
        "failure_count": 0,
    }
    if not agent_calls_file.exists():
        return result

    try:
        content = agent_calls_file.read_text().strip()
        if not content:
            return result

        agent_list = []
        success_count = 0
        failure_count = 0
        for line in content.splitlines():
            try:
                call = json.loads(line)
                # 如果指定了 session_id，只统计匹配的记录
                if session_id and call.get("session_id") != session_id:
                    continue

                agent = call.get("agent", "")
                if agent:
                    agent_list.append(agent)
                if call.get("success") is True:
                    success_count += 1
                elif call.get("success") is False:
                    failure_count += 1
            except json.JSONDecodeError:
                continue

        if agent_list:
            counter = Counter(agent_list)
            result["agents"] = list(counter.keys())
            result["agent_count"] = len(agent_list)
            result["agent_distribution"] = dict(counter)
            result["success_count"] = success_count
            result["failure_count"] = failure_count

    except OSError:
        pass

    return result


def aggregate_failures(root: Path, session_id: str = None) -> dict:
    """从 error.jsonl 提取失败模式（替代旧的 failures.jsonl）

    迁移说明:
      - v1: 写入 failures.jsonl (collect-failure.py)
      - v2: 写入 error.jsonl (collect_error.py)
      - 此函数同时兼容两种格式，过渡期后移除 failures.jsonl 支持

    Args:
        root: 项目根目录
        session_id: 如果提供，只统计匹配此 session_id 的记录
    """
    error_file = root / ".claude" / "data" / "error.jsonl"
    failures_file = root / ".claude" / "data" / "failures.jsonl"

    result = {
        "total": 0,
        "failure_types": {},
        "failure_tools": {},
        "recent_failures": [],
    }

    # 优先读取 error.jsonl (新格式)
    if error_file.exists():
        _read_error_jsonl(error_file, session_id, result)

    # 补充读取 failures.jsonl (旧格式，向后兼容)
    if failures_file.exists():
        _read_failures_jsonl(failures_file, session_id, result)

    return result


def _read_error_jsonl(error_file: Path, session_id: str, result: dict) -> None:
    """从 error.jsonl 读取错误记录"""
    try:
        content = error_file.read_text(encoding="utf-8").strip()
        if not content:
            return

        type_counter = Counter(result.get("failure_types", {}))
        tool_counter = Counter(result.get("failure_tools", {}))
        recent = list(result.get("recent_failures", []))

        for line in content.splitlines():
            try:
                f = json.loads(line)
                # 只处理 tool_failure 类型
                if f.get("type") != "tool_failure":
                    continue
                # session_id 过滤
                ctx = f.get("context", {})
                if session_id and ctx.get("session_id") != session_id:
                    continue

                error_type = f.get("type", "unknown_error")
                tool = f.get("tool", "unknown")
                type_counter[error_type] += 1
                tool_counter[tool] += 1
                recent.append({
                    "tool": tool,
                    "error_type": error_type,
                    "error": f.get("error", "")[:200],
                    "timestamp": f.get("timestamp", ""),
                    "source": f.get("source", ""),
                })
            except json.JSONDecodeError:
                continue

        result["failure_types"] = dict(type_counter)
        result["failure_tools"] = dict(tool_counter)
        result["recent_failures"] = recent[-20:]
        result["total"] = len(recent)

    except OSError:
        pass


def _read_failures_jsonl(failures_file: Path, session_id: str, result: dict) -> None:
    """从 failures.jsonl 读取旧格式记录（向后兼容）"""
    try:
        content = failures_file.read_text(encoding="utf-8").strip()
        if not content:
            return

        type_counter = Counter(result.get("failure_types", {}))
        tool_counter = Counter(result.get("failure_tools", {}))
        recent = list(result.get("recent_failures", []))

        for line in content.splitlines():
            try:
                f = json.loads(line)
                # session_id 过滤
                if session_id and f.get("session_id") != session_id:
                    continue

                error_type = f.get("error_type", classify_error_type(f.get("error", "")))
                tool = f.get("tool", "unknown")
                type_counter[error_type] += 1
                tool_counter[tool] += 1
                recent.append({
                    "tool": tool,
                    "error_type": error_type,
                    "error": f.get("error", "")[:200],
                    "timestamp": f.get("timestamp", ""),
                })
            except json.JSONDecodeError:
                continue

        result["failure_types"] = dict(type_counter)
        result["failure_tools"] = dict(tool_counter)
        result["recent_failures"] = recent[-20:]
        result["total"] = len(recent)

    except OSError:
        pass


def classify_error_type(error: str) -> str:
    """分类错误类型"""
    error_lower = error.lower()
    if "permission" in error_lower or "denied" in error_lower:
        return "permission_error"
    if "not found" in error_lower or "no such" in error_lower:
        return "not_found_error"
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout_error"
    if "syntax" in error_lower or "parse" in error_lower:
        return "syntax_error"
    if "connection" in error_lower or "network" in error_lower:
        return "network_error"
    if "read" in error_lower or "write" in error_lower or "io" in error_lower:
        return "io_error"
    return "unknown_error"


def get_git_changes(root: Path) -> dict:
    """执行 git diff 统计变更"""
    result = {
        "files_changed": 0,
        "lines_added": 0,
        "lines_deleted": 0,
    }
    try:
        # 统计未缓存的变更
        r = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=root, capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            stat = r.stdout.strip()
            if stat:
                parts = stat.split(",")
                for p in parts:
                    p = p.strip()
                    if "file" in p and "changed" in p:
                        result["files_changed"] = int(p.split()[0])
                    if "insertion" in p:
                        result["lines_added"] = int(p.split()[0])
                    if "deletion" in p:
                        result["lines_deleted"] = int(p.split()[0])

        # 也检查缓存的变更
        r2 = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=root, capture_output=True, text=True, timeout=10
        )
        if r2.returncode == 0:
            stat2 = r2.stdout.strip()
            if stat2 and stat2 != stat:
                parts = stat2.split(",")
                for p in parts:
                    p = p.strip()
                    if "file" in p and "changed" in p:
                        result["files_changed"] += int(p.split()[0])
    except Exception:
        pass
    return result


def build_session(root: Path) -> dict:
    """从所有数据源构建完整的会话摘要"""
    session_start = read_session_start(root)
    hook_data = {}
    try:
        raw = sys.stdin.read().strip()
        if raw:
            hook_data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        pass

    session_id = hook_data.get("session_id", os.environ.get("CLAUDE_SESSION_ID"))
    if not session_id or session_id == "unknown":
        session_id = get_session_id_fallback(root)

    mode = session_start.get("mode", os.environ.get("CLAUDE_MODE", "solo"))
    duration = calculate_duration(session_start)
    # 传递 session_id 以过滤只属于当前会话的数据
    agent_stats = aggregate_agent_calls(root, session_id=session_id)
    failure_stats = aggregate_failures(root, session_id=session_id)
    git_stats = get_git_changes(root)

    return {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "duration_minutes": duration,
        "agents_used": agent_stats["agents"],
        "agent_count": agent_stats["agent_count"],
        "agent_distribution": agent_stats["agent_distribution"],
        "agent_success_rate": (
            agent_stats["success_count"] /
            max(agent_stats["success_count"] + agent_stats["failure_count"], 1)
        ),
        "tool_failures": failure_stats["total"],
        "failure_types": failure_stats["failure_types"],
        "failure_tools": failure_stats["failure_tools"],
        "git_files_changed": git_stats["files_changed"],
        "git_lines_added": git_stats["lines_added"],
        "git_lines_deleted": git_stats["lines_deleted"],
        "corrections": hook_data.get("corrections", []),
        "rich_context": {
            "agent_stats": agent_stats,
            "failure_stats": failure_stats,
            "git_stats": git_stats,
        },
    }


def append_session(root: Path, session: dict) -> Path:
    """追加一行到 sessions.jsonl"""
    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    log_file = data_dir / "sessions.jsonl"
    line = json.dumps(session, ensure_ascii=False) + "\n"
    with open(log_file, "a") as f:
        f.write(line)

    return log_file


def should_trigger_analysis(session: dict, config: dict) -> bool:
    """判断是否需要立即触发分析"""
    if session.get("tool_failures", 0) >= 5:
        return True
    success_rate = session.get("agent_success_rate", 1.0)
    if success_rate < 0.5:
        return True
    failure_types = session.get("failure_types", {})
    for error_type, count in failure_types.items():
        if count >= 3:
            return True
    return False


def main():
    root = find_project_root()
    session = build_session(root)
    append_session(root, session)

    result = {
        "collected": True,
        "session_id": session["session_id"],
        "duration_minutes": session["duration_minutes"],
        "agents_used": session["agents_used"],
        "agent_count": session["agent_count"],
        "tool_failures": session["tool_failures"],
        "git_files_changed": session["git_files_changed"],
        "timestamp": session["timestamp"],
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({
            "collected": False,
            "error": str(e)[:200]
        }), file=sys.stderr)
        sys.exit(0)