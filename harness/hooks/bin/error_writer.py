#!/usr/bin/env python3
"""
error_writer.py — 线程安全的 error.jsonl 写入工具

功能:
  - 使用 flock 保护并发写入，多个 Hook 同时触发也不会丢数据
  - 自动创建 .claude/data 目录
  - 统一的错误记录格式

使用方式:
  from error_writer import write_error
  write_error(error_record, project_dir)
"""
import json
import os
import sys
import time
import fcntl
import errno
from pathlib import Path
from datetime import datetime
from typing import Optional


# 错误类型枚举
class ErrorType:
    TOOL_FAILURE = "tool_failure"        # 工具执行失败 (PostToolUseFailure)
    HOOK_ERROR = "hook_error"            # Hook 脚本内部错误
    CHK_INTERNAL_ERROR = "chk_internal_error"  # CHK 自身逻辑错误
    API_ERROR = "api_error"              # API 调用错误
    VALIDATION_ERROR = "validation_error"  # 验证失败


# CHK 版本（统一从 version.json 读取）
def get_chk_version() -> str:
    try:
        root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
        version_file = root / "_core" / "version.json"
        if version_file.exists():
            data = json.loads(version_file.read_text(encoding="utf-8"))
            return data.get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"


def _get_lock_file(log_file: Path) -> Path:
    """获取与 log_file 对应的锁文件"""
    return log_file.with_suffix(".jsonl.lock")


def _get_session_id(root: Path) -> str:
    """生成确定性 session_id，与 collect-failure.py 保持一致"""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")

    if not session_id or session_id == "unknown":
        git_dir = root / ".git"
        if git_dir.exists():
            try:
                import subprocess
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

    if not session_id or session_id == "unknown":
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{root.name}-{ts}"

    return session_id


def _get_recent_tools(root: Path, limit: int = 5) -> list:
    """从 sessions.jsonl 补全最近的操作上下文"""
    sessions_file = root / ".claude" / "data" / "sessions.jsonl"
    try:
        if not sessions_file.exists():
            return []
    except (OSError, PermissionError):
        return []

    try:
        if not os.access(sessions_file, os.R_OK):
            return []
        lines = sessions_file.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return []
        last = json.loads(lines[-1])
        return last.get("recent_tools", [])[-limit:]
    except (OSError, PermissionError):
        return []
    except Exception:
        return []


def _ensure_data_dir(root: Path) -> Path:
    """确保 .claude/data 目录存在"""
    data_dir = root / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _sanitize_tool_input(tool_input: dict) -> dict:
    """脱敏工具输入，移除敏感字段"""
    if not tool_input:
        return {}

    sanitized = {}
    sensitive_keys = {
        "password", "secret", "token", "key", "api_key", "auth",
        "credential", "private", "secret_key", "access_token",
        "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
    }

    for k, v in tool_input.items():
        key_lower = k.lower()
        if any(s in key_lower for s in sensitive_keys):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 500:
            sanitized[k] = v[:500] + "...[TRUNCATED]"
        else:
            sanitized[k] = v

    return sanitized


def build_error_record(
    error_type: str,
    error_message: str,
    source: str,
    tool: Optional[str] = None,
    tool_input: Optional[dict] = None,
    error_detail: Optional[str] = None,
    context: Optional[dict] = None,
    hook_event: Optional[str] = None,
) -> dict:
    """构建标准错误记录"""
    # 截断超长错误消息（防止 JSONL 文件过大）
    if isinstance(error_message, str) and len(error_message) > 500:
        error_message = error_message[:500] + "...[TRUNCATED]"

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    # 合并 context
    merged_context = {
        "session_id": _get_session_id(root),
        "project": str(root),
        "tool_input": _sanitize_tool_input(tool_input) if tool_input else {},
        "recent_tools": _get_recent_tools(root),
        "mode": os.environ.get("CLAUDE_MODE", "solo"),
        "agents_used": [],
        "skills_used": [],
    }
    if context:
        merged_context.update(context)
        # caller 通过 context 传入的 recent_tools 有更高优先级
        if "recent_tools" in context:
            merged_context["recent_tools"] = context["recent_tools"]

    record = {
        "timestamp": datetime.now().isoformat(),
        "type": error_type,
        "source": source,
        "tool": tool,
        "error": error_message,
        "error_detail": error_detail,
        "context": merged_context,
        "metadata": {
            "chk_version": get_chk_version(),
            "hook_event": hook_event,
            "collector": "collect-error.py",
        },
    }

    return record


def _is_macos() -> bool:
    """检测是否为 macOS"""
    import platform
    return platform.system() == "Darwin"


def write_error(
    error_record: dict,
    project_dir: Optional[str] = None,
) -> bool:
    """
    线程安全的 JSONL 写入

    Args:
        error_record: 错误记录字典
        project_dir: 项目目录，默认从环境变量获取

    Returns:
        True: 写入成功
        False: 写入失败（不阻断主流程）
    """
    if project_dir:
        root = Path(project_dir)
    else:
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    data_dir = _ensure_data_dir(root)
    log_file = data_dir / "error.jsonl"
    lock_file = _get_lock_file(log_file)

    try:
        with open(lock_file, "w") as lock_f:
            # macOS 使用阻塞锁（等待释放），Linux 使用非阻塞锁
            if sys.platform == "darwin":
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            else:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            try:
                with open(log_file, "a") as f:
                    f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
            finally:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

        return True

    except (IOError, OSError) as e:
        # 锁冲突或其他 IO 错误，静默失败
        if e.errno == errno.EWOULDBLOCK:
            # 锁冲突，等下次再写
            return False
        print(
            json.dumps({"writer_error": str(e)[:100]}, ensure_ascii=False),
            file=sys.stderr
        )
        return False
    except Exception as e:
        print(
            json.dumps({"writer_error": str(e)[:100]}, ensure_ascii=False),
            file=sys.stderr
        )
        return False


# ── CLI 接口 ─────────────────────────────────────────────────────────────────

def main():
    """
    支持两种调用方式:
    1. 管道输入 JSON: cat error_data.json | python3 error_writer.py
    2. 直接传参: python3 error_writer.py tool_failure "error msg" hooks/bin/collect-error.py:42
    """
    raw = sys.stdin.read().strip()

    if raw:
        # 方式 1: 管道输入
        try:
            error_record = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            print(
                json.dumps({"error": "Invalid JSON input", "input": raw[:100]}),
                file=sys.stderr
            )
            sys.exit(0)

        success = write_error(error_record)
        print(json.dumps({"written": success}))
    else:
        # 方式 2: 命令行参数
        if len(sys.argv) < 4:
            print(json.dumps({
                "usage": "error_writer.py <type> <error> <source> [tool] [detail]"
            }))
            sys.exit(0)

        error_type = sys.argv[1]
        error_message = sys.argv[2]
        source = sys.argv[3]
        tool = sys.argv[4] if len(sys.argv) > 4 else None
        error_detail = sys.argv[5] if len(sys.argv) > 5 else None

        record = build_error_record(
            error_type=error_type,
            error_message=error_message,
            source=source,
            tool=tool,
            error_detail=error_detail,
        )

        success = write_error(record)
        print(json.dumps({"written": success}))


if __name__ == "__main__":
    main()
