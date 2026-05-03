#!/usr/bin/env python3
"""
_session_utils.py — Hook 脚本共享工具模块

提供:
  - get_session_id(): 生成确定性 session_id
  - get_project_root(): 获取项目根目录
  - write_log_record(): 线程安全地写入 JSONL 日志

使用方式:
  import sys
  sys.path.insert(0, str(Path(__file__).parent))
  from _session_utils import get_session_id, get_project_root, write_log_record
"""
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 项目路径
# ═══════════════════════════════════════════════════════════════════════════════

def get_project_root() -> Path:
    """
    获取项目根目录。

    优先级:
      1. CLAUDE_PROJECT_DIR 环境变量
      2. 当前工作目录
    """
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


# ═══════════════════════════════════════════════════════════════════════════════
# Session ID
# ═══════════════════════════════════════════════════════════════════════════════

def get_session_id(root: Optional[Path] = None) -> str:
    """
    生成确定性 session_id。

    优先级:
      1. CLAUDE_SESSION_ID 环境变量
      2. git commit + 当前日期 (开发中)
      3. 项目名 + 时间戳 (兜底)

    Args:
        root: 项目根目录，默认自动检测

    Returns:
        session_id 字符串

    示例:
        git-{short_hash}-{YYYY-MM-DD}  # 开发中
        {project_name}-{YYYYMMDD-HHMMSS}  # 兜底
    """
    if root is None:
        root = get_project_root()

    # 优先级 1: CLAUDE_SESSION_ID 环境变量
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if session_id and session_id != "unknown":
        return session_id

    # 优先级 2: git commit + 当前日期
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                if commit:
                    today = date.today().isoformat()
                    return f"git-{commit}-{today}"
        except Exception:
            pass

    # 优先级 3: 项目名 + 时间戳
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{root.name}-{ts}"


def get_session_id_verbose(root: Optional[Path] = None) -> str:
    """
    详细版 session_id (包含 git branch 信息)。

    适用于需要更详细会话追踪的场景。
    """
    if root is None:
        root = get_project_root()

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if session_id and session_id != "unknown":
        return session_id

    git_dir = root / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "describe", "--all", "--long"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip().replace("/", "-")
                if commit:
                    return f"git-{commit}"
        except Exception:
            pass

    return "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# 数据目录
# ═══════════════════════════════════════════════════════════════════════════════

def get_data_dir(root: Optional[Path] = None) -> Path:
    """
    获取 .claude/data 目录路径，自动创建。

    Args:
        root: 项目根目录，默认自动检测

    Returns:
        .claude/data 目录 Path
    """
    if root is None:
        root = get_project_root()

    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ═══════════════════════════════════════════════════════════════════════════════
# JSONL 写入
# ═══════════════════════════════════════════════════════════════════════════════

def write_log_record(
    record: dict,
    log_file: Path,
    use_lock: bool = True
) -> bool:
    """
    线程安全地写入 JSONL 日志。

    使用 flock 保护并发写入，多个 Hook 同时触发也不会丢数据。

    Args:
        record: 要写入的记录字典
        log_file: 日志文件路径
        use_lock: 是否使用文件锁（默认 True，生产环境推荐）

    Returns:
        True: 写入成功
        False: 写入失败（静默失败，不阻断主流程）

    示例:
        >>> record = {"timestamp": "2024-01-01T00:00:00", "event": "test"}
        >>> success = write_log_record(record, Path("logs/test.jsonl"))
    """
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        if use_lock:
            lock_file = log_file.with_suffix(".jsonl.lock")
            with open(lock_file, "w") as lock_f:
                if sys.platform == "darwin":
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
                else:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                try:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                finally:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        else:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return True

    except (IOError, OSError):
        return False
    except Exception:
        return False


def read_log_records(log_file: Path, limit: int = 10) -> list[dict]:
    """
    读取最近的 JSONL 记录。

    Args:
        log_file: 日志文件路径
        limit: 返回的最大记录数（默认 10）

    Returns:
        记录字典列表
    """
    if not log_file.exists():
        return []

    try:
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Hook 数据加载
# ═══════════════════════════════════════════════════════════════════════════════

def load_hook_context() -> dict:
    """
    从 stdin 加载 Hook 事件数据。

    Returns:
        解析后的 hook 数据字典，失败时返回空字典
    """
    try:
        raw = sys.stdin.read().strip()
        if raw:
            return json.loads(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return {}


def get_hook_event() -> str:
    """
    获取 Hook 事件类型。

    Returns:
        CLAUDE_HOOK_EVENT 环境变量值或空字符串
    """
    return os.environ.get("CLAUDE_HOOK_EVENT", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_current_timestamp() -> str:
    """获取当前 ISO 格式时间戳"""
    return datetime.now().isoformat()


def truncate_string(s: str, max_length: int = 200) -> str:
    """
    截断过长的字符串。

    Args:
        s: 原始字符串
        max_length: 最大长度（默认 200）

    Returns:
        截断后的字符串，超长会追加 "..."
    """
    if not isinstance(s, str):
        s = str(s)
    if len(s) <= max_length:
        return s
    return s[:max_length] + "...[TRUNCATED]"


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口（CLI 测试）
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(json.dumps({
        "project_root": str(get_project_root()),
        "session_id": get_session_id(),
        "data_dir": str(get_data_dir()),
        "timestamp": get_current_timestamp(),
    }))