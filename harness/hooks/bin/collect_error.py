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

# 导入共享的错误写入工具
sys.path.insert(0, str(Path(__file__).parent))
from error_writer import (
    write_error,
    build_error_record,
    ErrorType,
    _get_session_id,
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


def _infer_source_from_env(hook_data: dict = None) -> str:
    """从环境变量和 hook_data 推断错误来源"""
    # 1. 从 CLAUDE_HOOK_SCRIPT 获取（Claude Code 传递的环境变量）
    hook_script = os.environ.get("CLAUDE_HOOK_SCRIPT", "")
    if hook_script:
        return _HOOK_SOURCE_MAP.get(hook_script, f"hooks/bin/{hook_script}")

    # 2. 从 hook_data 的 tool_name 推断（PostToolUseFailure 事件自带工具名）
    if hook_data:
        tool = hook_data.get("tool_name", "")
        if tool:
            return f"hooks/{tool.lower()}.py"

    # 3. 兜底
    return "hooks/bin/collect-error.py"

def _get_hook_script_from_path() -> str:
    """获取触发此 Hook 的脚本名"""
    # Claude Code 传递的环境变量
    return os.environ.get("CLAUDE_HOOK_SCRIPT", "unknown")


def _load_hook_context() -> dict:
    """从 stdin 加载 Hook 事件数据"""
    try:
        raw = sys.stdin.read().strip()
        if raw:
            return json.loads(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return {}


def _get_mode() -> str:
    """获取当前运行模式"""
    return os.environ.get("CLAUDE_MODE", "solo")


def _get_agents_and_skills() -> tuple:
    """获取本轮使用的 agents 和 skills"""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
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
        hook_data = _load_hook_context()
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    tool = hook_data.get("tool_name", "unknown")
    error_msg = hook_data.get("error", "Unknown error")
    tool_input = hook_data.get("tool_input", {})

    # 推断来源：从 hook_data 中的工具名
    source = _infer_source_from_env(hook_data)

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
            "session_id": _get_session_id(root),
            "project": str(root),
            "recent_tools": _get_recent_tools(root),
            "mode": _get_mode(),
            "agents_used": agents,
            "skills_used": skills,
        },
    )


def collect_chk_internal_error(error_detail: str = None) -> dict:
    """收集 CHK 自身内部错误"""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

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
            "session_id": _get_session_id(root),
            "project": str(root),
            "recent_tools": _get_recent_tools(root),
            "mode": _get_mode(),
            "agents_used": agents,
            "skills_used": skills,
        },
    )


def collect_session_summary_errors() -> list[dict]:
    """从 sessions.jsonl 汇总本轮错误"""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
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


def _detect_event_type(hook_data: dict) -> str:
    """
    从 stdin 数据结构推断事件类型。

    Claude Code 不设置 CLAUDE_HOOK_EVENT 环境变量，而是通过 hook 配置
    调用不同的脚本。我们通过数据结构本身来区分：

    - PostToolUseFailure: 包含 error 字段
    - PostToolUseSuccess: 包含 result 字段（无 error）
    - Stop: CLAUDE_HOOK_EVENT == "Stop"（会话结束事件）
    """
    if "error" in hook_data and hook_data["error"]:
        return "PostToolUseFailure"
    if "result" in hook_data or "output" in hook_data:
        return "PostToolUseSuccess"
    return "Unknown"


def main():
    """
    主入口:
    1. 从 stdin 读取 Hook 事件数据
    2. 推断事件类型（不依赖不可靠的 CLAUDE_HOOK_EVENT）
    3. 构建错误记录并写入 error.jsonl
    """
    try:
        # 从 stdin 读取事件数据（Claude Code 通过管道传递 JSON）
        hook_data = _load_hook_context()

        # 推断事件类型（从数据结构判断，而非环境变量）
        hook_event = _detect_event_type(hook_data)

        # 调试日志：帮助诊断是否有事件到达
        if not hook_data:
            print(json.dumps({
                "collected": False,
                "reason": "empty_hook_data",
                "skipped": True,
                "debug": "No stdin data received from Claude Code"
            }))
            return

        if hook_event == "PostToolUseFailure":
            # 工具执行失败：构建错误记录
            record = collect_tool_failure(hook_data)
        elif hook_event == "Stop" or os.environ.get("CLAUDE_HOOK_EVENT", "") == "Stop":
            # Stop: 会话结束，汇总 failures.jsonl 中的错误
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
        elif hook_event == "PostToolUseSuccess":
            # 成功事件不写入 error.jsonl，只记录日志
            print(json.dumps({
                "collected": False,
                "reason": "success_event",
                "skipped": True
            }))
            return
        else:
            # 未知事件：记录为 hook_error（帮助调试）
            record = build_error_record(
                error_type=ErrorType.HOOK_ERROR,
                error_message=f"Unknown hook event, data: {str(hook_data)[:200]}",
                source=_infer_source_from_env(hook_data),
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
