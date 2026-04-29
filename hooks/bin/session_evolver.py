#!/usr/bin/env python3
"""
Session Evolver - Stop Hook

会话结束时采集真实执行数据，这是整个自进化系统的数据源。
原则：只采集可验证的真实信号，不编造数据。

数据来源：
- git diff --stat: 真实的文件变更统计
- git log: 真实的 commit 记录
- 本次会话内 SubagentStop 累积记录：被调用过的 agent 列表
- 文件类型分布：推断活动领域
"""

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 进化引擎集成
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
from evolution_orchestrator import run_orchestrator


def run_git(args: List[str], cwd: str) -> str:
    """运行 git 命令，失败时返回空字符串而不抛异常。"""
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, timeout=5, check=False
        )
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _load_domains_config(project_root: str) -> Dict[str, Any]:
    """从 config/domains.json 加载领域配置"""
    config_file = Path(project_root) / ".claude" / "config" / "domains.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _detect_domain_from_path(file_path: str, domains_config: Dict[str, Any]) -> str:
    """根据配置检测文件所属领域"""
    for domain, config in domains_config.items():
        for pattern in config.get("source_paths", []):
            # 支持通配符模式
            if pattern.endswith("/"):
                if file_path.startswith(pattern) or file_path.startswith(pattern.rstrip("/")):
                    return domain
            elif pattern in file_path:
                return domain
    # 默认检测逻辑
    if "backend" in file_path.lower() or "/api/" in file_path or "/service/" in file_path:
        return "backend"
    if "frontend" in file_path.lower() or "/pages/" in file_path or "/components/" in file_path:
        return "frontend"
    if "test" in file_path.lower() or "/tests/" in file_path:
        return "tests"
    if file_path.endswith(".md"):
        return "docs"
    if ".claude" in file_path or file_path.endswith(".json"):
        return "config"
    return "other"


def collect_git_metrics(project_root: str) -> Dict[str, Any]:
    """
    采集真实的 git 指标。这是进化系统的真正数据来源。
    """
    diff_stat = run_git(["diff", "--stat", "HEAD"], project_root)
    status_short = run_git(["status", "--short"], project_root)
    last_commits = run_git(["log", "-5", "--oneline"], project_root)
    name_only = run_git(["diff", "--name-only", "HEAD"], project_root)

    # 解析文件列表
    files = [f for f in name_only.splitlines() if f.strip()]

    # 加载领域配置
    domains_config = _load_domains_config(project_root)

    # 文件类型分布（使用配置，无配置时使用默认检测）
    if domains_config:
        categorize = {}
        for domain in domains_config.keys():
            categorize[domain] = sum(1 for f in files if _detect_domain_from_path(f, {domain: domains_config.get(domain, {})}))
        # 确保所有配置的领域都在结果中
        for domain in domains_config.keys():
            if domain not in categorize:
                categorize[domain] = 0
    else:
        # 默认检测逻辑（保持向后兼容）
        categorize = {
            "backend": sum(1 for f in files if f.startswith("main/backend/")),
            "frontend": sum(1 for f in files if f.startswith("main/frontend/")),
            "tests": sum(1 for f in files if f.startswith("main/tests/") or "/tests/" in f),
            "docs": sum(1 for f in files if f.startswith("main/docs/") or f.endswith(".md")),
            "config": sum(1 for f in files if f.startswith(".claude/") or f.endswith(".json")),
        }

    # 解析 diff --stat 的最后一行，形如 " 5 files changed, 30 insertions(+), 10 deletions(-)"
    lines_added = 0
    lines_removed = 0
    if diff_stat:
        last = diff_stat.splitlines()[-1] if diff_stat.splitlines() else ""
        for part in last.split(","):
            part = part.strip()
            if "insertion" in part:
                lines_added = int(part.split()[0]) if part.split()[0].isdigit() else 0
            elif "deletion" in part:
                lines_removed = int(part.split()[0]) if part.split()[0].isdigit() else 0

    return {
        "files_changed": len(files),
        "files_by_domain": categorize,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "file_list": files[:20],  # 只保留前 20 个文件名
        "recent_commits": last_commits.splitlines()[:5],
        "has_uncommitted": bool(status_short),
    }


def collect_agent_invocations(data_dir: Path, session_id: str) -> List[str]:
    """
    从 data/agent_performance.jsonl 收集本次会话被调用的 agent 列表。
    PostToolUse[Agent] hook 写入 agent_performance.jsonl。
    """
    invocations_file = data_dir / "agent_performance.jsonl"
    if not invocations_file.exists():
        return []

    agents = []
    with open(invocations_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                if record.get("session_id") == session_id:
                    agents.append(record.get("agent", "unknown"))
            except json.JSONDecodeError:
                continue
    return agents


def infer_primary_domain(metrics: Dict[str, Any]) -> str:
    """根据真实的文件分布推断主要活动领域。"""
    domains = metrics.get("files_by_domain", {})
    if not domains or sum(domains.values()) == 0:
        return "idle"
    return max(domains.items(), key=lambda x: x[1])[0]


def compute_quality_signals(metrics: Dict[str, Any], agents: List[str]) -> Dict[str, Any]:
    """
    基于真实数据计算质量信号（不是编造的评分）。
    每个信号都是可验证的事实，而不是拍脑袋的数字。
    """
    files_changed = metrics.get("files_changed", 0)
    lines_changed = metrics.get("lines_added", 0) + metrics.get("lines_removed", 0)
    test_files = metrics.get("files_by_domain", {}).get("tests", 0)

    return {
        "productivity": "none" if files_changed == 0
                        else "focused" if files_changed <= 5
                        else "broad" if files_changed <= 15
                        else "sprawling",
        "has_tests": test_files > 0,
        "test_ratio": round(test_files / files_changed, 2) if files_changed else 0.0,
        "volume_lines": lines_changed,
        "agents_used_count": len(set(agents)),
        "agents_unique": sorted(set(agents)),
        "commits_in_session": any(c for c in metrics.get("recent_commits", [])),
    }


def main():
    """
    Stop Hook 入口：采集真实会话数据并写入 sessions.jsonl。
    """
    try:
        raw = sys.stdin.read().strip()
        hook_data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        hook_data = {}

    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    logs_dir = Path(project_root) / ".claude" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    data_dir = Path(project_root) / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    session_id = hook_data.get("session_id", f"session-{datetime.now().strftime('%Y%m%d%H%M%S')}")

    # 采集真实指标
    git_metrics = collect_git_metrics(project_root)
    agents_used = collect_agent_invocations(data_dir, session_id)
    signals = compute_quality_signals(git_metrics, agents_used)
    primary_domain = infer_primary_domain(git_metrics)

    record = {
        "type": "session_end",
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "stop_reason": hook_data.get("stop_reason", "end_turn"),
        "primary_domain": primary_domain,
        "git_metrics": git_metrics,
        "signals": signals,
    }

    # 写入会话日志（追加式，带文件锁保护）
    sessions_file = logs_dir / "sessions.jsonl"
    with open(sessions_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # 人类可读摘要输出到 stderr
    print(
        f"📊 会话记录: domain={primary_domain}, "
        f"files={git_metrics['files_changed']}, "
        f"lines=+{git_metrics['lines_added']}/-{git_metrics['lines_removed']}, "
        f"agents={len(agents_used)}",
        file=sys.stderr
    )

    # 保存每日评分快照
    try:
        from evolution_scoring import save_daily_score
        save_daily_score(project_root)
    except Exception:
        pass

    # 触发进化编排（聚合数据 → 检查触发条件 → 安全门禁 → 持久化决策）
    # 决策写入 data/pending_evolution.json，下次会话由 Claude 主 Agent 调度 Agent 进化器执行
    decision = run_orchestrator(project_root, execute=True)
    if decision.get("should_evolve"):
        triggers = decision.get("triggers", [])
        dims = set(t["dimension"] for t in triggers)
        print(
            f"🎯 进化触发: {len(triggers)} 项 ({', '.join(dims)}) "
            f"→ 已持久化到 data/pending_evolution.json，下次会话处理",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
