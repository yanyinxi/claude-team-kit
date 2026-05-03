#!/usr/bin/env python3
"""
collect-error.py — 全局错误收集 Hook

功能:
  - 捕获工具执行失败 (PostToolUseFailure)
  - 捕获 CHK 自身内部错误
  - 从 sessions.jsonl 补全上下文
  - 自动溯源到 CHK 源码文件:行号

触发: PostToolUseFailure, Stop (汇总)

设计原则:
  - 轻量采集，耗时 < 1ms
  - 失败静默 (sys.exit(0))，不阻断 Claude Code
  - 使用 flock 保护并发写入
  - 自动从 sessions.jsonl 补全上下文
"""
import json
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

# 导入共享工具模块
sys.path.insert(0, str(Path(__file__).parent))
from _session_utils import get_session_id, get_project_root, get_data_dir, load_hook_context, get_hook_event, get_current_timestamp

# 导入错误写入工具
from error_writer import (
    write_error,
    build_error_record,
    ErrorType,
    _get_recent_tools,
    _sanitize_tool_input,
)


# ── CHK 源码溯源表 ───────────────────────────────────────────────────────────

# Hook 脚本 → CHK 源码文件映射 (便于快速定位问题来源)
_HOOK_SOURCE_MAP = {
    "safety-check.sh": "hooks/bin/safety-check.sh",
    "quality-gate.sh": "hooks/bin/quality-gate.sh",
    "tdd-check.sh": "hooks/bin/tdd-check.sh",
    "rate-limiter.sh": "hooks/bin/rate-limiter.sh",
    "collect-failure.py": "hooks/bin/collect-failure.py",
    "collect-agent.py": "hooks/bin/collect-agent.py",
    "collect-skill.py": "hooks/bin/collect-skill.py",
    "collect-session.py": "hooks/bin/collect-session.py",
    "output-secret-filter.py": "hooks/bin/output-secret-filter.py",
    "observe.sh": "hooks/bin/observe.sh",
    "checkpoint-auto-save.sh": "hooks/bin/checkpoint-auto-save.sh",
    "worktree-sync.sh": "hooks/bin/worktree-sync.sh",
    "worktree-cleanup.sh": "hooks/bin/worktree-cleanup.sh",
    "context-injector.py": "hooks/bin/context-injector.py",
    "extract-semantics.py": "hooks/bin/extract_semantics.py",
}


def _infer_source_from_env() -> str:
    """从环境变量和调用栈推断错误来源"""
    # 1. 尝试从调用栈获取源文件（排除 collect_error.py 自身）
    try:
        tb = traceback.extract_stack()
        for frame in reversed(tb):
            filename = Path(frame.filename).name
            # 跳过 collect_error.py 自身和标准库
            if filename == "collect-error.py":
                continue
            if filename.endswith(".py") and "site-packages" not in frame.filename:
                return f"hooks/bin/{filename}:{frame.lineno}"
    except Exception:
        pass

    # 2. 从 CLAUDE_HOOK_SCRIPT 获取（Claude Code 传递的环境变量）
    hook_script = os.environ.get("CLAUDE_HOOK_SCRIPT", "")
    if hook_script:
        return f"hooks/bin/{hook_script}"

    # 3. 从 CLAUDE_PLUGIN_ROOT 推断
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        return f"{plugin_root}/hooks/bin/collect-error.py"

    # 4. 兜底
    return "hooks/bin/collect-error.py"


def _get_hook_script_from_path() -> str:
    """获取触发此 Hook 的脚本名"""
    # Claude Code 传递的环境变量
    return os.environ.get("CLAUDE_HOOK_SCRIPT", "unknown")


def _get_mode() -> str:
    """获取当前运行模式"""
    return os.environ.get("CLAUDE_MODE", "solo")


def _get_agents_and_skills() -> tuple:
    """获取本轮使用的 agents 和 skills"""
    root = get_project_root()
    agents = []
    skills = []

    try:
        agent_calls = root / ".claude" / "data" / "agent_calls.jsonl"
        if agent_calls.exists():
            lines = agent_calls.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-5:]:  # 最近 5 次
                try:
                    data = json.loads(line)
                    agents.append(data.get("agent", "unknown"))
                except json.JSONDecodeError:
                    pass

        skill_calls = root / ".claude" / "data" / "skill_calls.jsonl"
        if skill_calls.exists():
            lines = skill_calls.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-5:]:  # 最近 5 次
                try:
                    data = json.loads(line)
                    skills.append(data.get("skill", "unknown"))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    return list(set(agents))[:5], list(set(skills))[:5]


def collect_tool_failure(hook_data: dict = None) -> dict:
    """收集 PostToolUseFailure 事件

    Args:
        hook_data: 可选，已读取的 hook 数据。如果为 None，则从 stdin 读取。
    """
    if hook_data is None:
        hook_data = load_hook_context()
    root = get_project_root()

    tool = hook_data.get("tool_name", "unknown")
    error_msg = hook_data.get("error", "Unknown error")
    tool_input = hook_data.get("tool_input", {})

    # 推断来源
    source = _infer_source_from_env()

    # 获取上下文
    agents, skills = _get_agents_and_skills()

    return build_error_record(
        error_type=ErrorType.TOOL_FAILURE,
        error_message=str(error_msg)[:500],
        source=source,
        tool=tool,
        tool_input=_sanitize_tool_input(tool_input),
        hook_event="PostToolUseFailure",
        context={
            "session_id": get_session_id(root),
            "project": str(root),
            "recent_tools": _get_recent_tools(root),
            "mode": _get_mode(),
            "agents_used": agents,
            "skills_used": skills,
        },
    )


def collect_chk_internal_error(error_detail: str = None) -> dict:
    """收集 CHK 自身内部错误"""
    root = get_project_root()

    # 获取详细错误信息
    if not error_detail:
        error_detail = traceback.format_exc()

    # 获取来源
    source = _infer_source_from_env()

    # 获取上下文
    agents, skills = _get_agents_and_skills()

    return build_error_record(
        error_type=ErrorType.TOOL_FAILURE,
        error_message="CHK internal error",
        source=source,
        tool=None,
        error_detail=error_detail[:1000],
        hook_event="Stop",
        context={
            "session_id": get_session_id(root),
            "project": str(root),
            "recent_tools": _get_recent_tools(root),
            "mode": _get_mode(),
            "agents_used": agents,
            "skills_used": skills,
        },
    )


def collect_session_summary_errors() -> list[dict]:
    """从 sessions.jsonl 汇总本轮错误"""
    root = get_project_root()
    data_dir = root / ".claude" / "data"
    errors = []

    # 检查 failures.jsonl 中的未处理错误
    failures_file = data_dir / "failures.jsonl"
    if failures_file.exists():
        try:
            lines = failures_file.read_text(encoding="utf-8").strip().splitlines()
            # 只处理最近 10 条
            for line in lines[-10:]:
                try:
                    failure = json.loads(line)
                    # 检查是否已记录到 error.jsonl
                    errors.append({
                        "type": ErrorType.TOOL_FAILURE,
                        "error": failure.get("error", "Unknown"),
                        "source": "hooks/bin/collect-failure.py:0",
                        "tool": failure.get("tool", "unknown"),
                        "timestamp": failure.get("timestamp"),
                    })
                except json.JSONDecodeError:
                    pass
        except OSError:
            pass

    return errors


def main():
    """
    主入口:
    1. 解析 Hook 事件类型
    2. 构建错误记录
    3. 写入 error.jsonl
    """
    try:
        # 尝试从 stdin 读取事件数据
        hook_data = load_hook_context()

        # 判断事件类型
        hook_event = get_hook_event()

        # 如果 hook_event 为空，尝试从 hook_data 推断
        if not hook_event and hook_data:
            hook_event = hook_data.get("hook_event", "") or hook_data.get("hookName", "")

        # 跳过空事件（假阳性 - Hook 被调用但没有实际错误）
        if not hook_event:
            print(json.dumps({
                "collected": False,
                "reason": "empty_hook_event",
                "skipped": True
            }))
            return

        if "PostToolUseFailure" in hook_event:
            # PostToolUseFailure: 工具执行失败（传入已读取的 hook_data）
            record = collect_tool_failure(hook_data)
        elif "Stop" in hook_event:
            # Stop: 会话结束，汇总错误
            session_errors = collect_session_summary_errors()
            if session_errors:
                for err in session_errors:
                    record = build_error_record(
                        error_type=err["type"],
                        error_message=err["error"],
                        source=err["source"],
                        tool=err["tool"],
                        hook_event="Stop",
                    )
                    write_error(record)
                print(json.dumps({
                    "collected": True,
                    "errors_count": len(session_errors)
                }))
                return
            else:
                print(json.dumps({"collected": True, "errors_count": 0}))
                return
        else:
            # 其他事件，记录为 hook_error
            record = build_error_record(
                error_type=ErrorType.HOOK_ERROR,
                error_message=f"Hook event: {hook_event}",
                source=_infer_source_from_env(),
                hook_event=hook_event,
            )

        # 写入 error.jsonl
        success = write_error(record)

        print(json.dumps({
            "collected": True,
            "written": success,
            "type": record["type"],
            "source": record["source"],
        }))

    except Exception as e:
        # CHK 自身错误，记录到 error.jsonl（如果可能）
        try:
            internal_error = collect_chk_internal_error(traceback.format_exc())
            write_error(internal_error)
        except Exception:
            pass

        # 静默失败，不阻断 Claude Code
        print(json.dumps({
            "collected": False,
            "warning": str(e)[:100]
        }), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"collected": False, "warning": str(e)[:100]}), file=sys.stderr)
        sys.exit(0)