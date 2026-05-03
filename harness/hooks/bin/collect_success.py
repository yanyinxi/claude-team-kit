#!/usr/bin/env python3
"""
collect_success.py — 成功工具调用收集 Hook

功能:
  - 收集 PostToolUseSuccess 事件
  - 调用 effect_tracker.track() 验证进化改进有效性
  - 与 error.jsonl 形成对比，分析成功/失败比例

触发: PostToolUseSuccess

使用方式:
  python3 collect_success.py < stdin (JSON 事件数据)
"""
import json
import os
import sys
import traceback
from pathlib import Path

# 导入共享工具模块
sys.path.insert(0, str(Path(__file__).parent))
from _session_utils import get_session_id, get_project_root, get_data_dir, load_hook_context, get_hook_event, get_current_timestamp

# ── 路径配置 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = get_project_root()
CHK_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", str(PROJECT_ROOT / "harness")))
EVOLVE_DIR = CHK_ROOT / "evolve-daemon"
DATA_DIR = get_data_dir(PROJECT_ROOT)
INSTINCT_FILE = CHK_ROOT / "instinct" / "instinct-record.json"
EFFECT_LOG = EVOLVE_DIR / "knowledge" / "effect_tracking.jsonl"


def _get_session_id_verbose() -> str:
    """
    获取详细版 session_id (包含 git branch 信息)。

    适用于需要更详细会话追踪的场景。
    """
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if session_id and session_id != "unknown":
        return session_id

    git_dir = PROJECT_ROOT / ".git"
    if git_dir.exists():
        try:
            import subprocess
            result = subprocess.run(
                ["git", "describe", "--all", "--long"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip().replace("/", "-")
                return f"git-{commit}"
        except Exception:
            pass
    return "unknown"


def track_success(tool: str, context: dict = None) -> bool:
    """跟踪成功事件，调用效果跟踪器"""
    try:
        sys.path.insert(0, str(EVOLVE_DIR))
        from effect_tracker import EffectTracker

        tracker = EffectTracker(str(PROJECT_ROOT))

        # 从 context 中提取 knowledge_id（如果关联了知识）
        knowledge_id = None
        if context:
            knowledge_id = context.get("knowledge_id")

        if knowledge_id:
            tracker.track(knowledge_id, "success", context or {})
            return True
        return False
    except Exception as e:
        # 静默失败，不阻断主流程
        return False


def collect_tool_success(hook_data: dict = None) -> dict:
    """收集 PostToolUseSuccess 事件"""
    if hook_data is None:
        hook_data = load_hook_context()

    tool = hook_data.get("tool_name", "unknown")
    tool_input = hook_data.get("tool_input", {})

    # 构建成功记录
    record = {
        "timestamp": get_current_timestamp(),
        "type": "tool_success",
        "source": "hooks/bin/collect_success.py",
        "tool": tool,
        "context": {
            "session_id": _get_session_id_verbose(),
            "project": str(PROJECT_ROOT),
        }
    }

    # 尝试跟踪效果
    has_tracked = track_success(tool, record["context"])

    record["effect_tracked"] = has_tracked

    return record


def write_success_record(record: dict) -> bool:
    """写入成功记录到 effect_tracking.jsonl"""
    try:
        EFFECT_LOG.parent.mkdir(parents=True, exist_ok=True)

        with open(EFFECT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def main():
    """主入口"""
    try:
        hook_data = load_hook_context()
        hook_event = get_hook_event()

        if not hook_event and hook_data:
            hook_event = hook_data.get("hook_event", "") or hook_data.get("hookName", "")

        if "PostToolUseSuccess" in hook_event:
            record = collect_tool_success(hook_data)
            success = write_success_record(record)

            print(json.dumps({
                "collected": True,
                "written": success,
                "effect_tracked": record.get("effect_tracked", False),
                "tool": record.get("tool", "unknown"),
            }))
        else:
            # 非 PostToolUseSuccess 事件，跳过
            print(json.dumps({
                "collected": False,
                "reason": "not_post_tool_use_success",
                "skipped": True
            }))

    except Exception as e:
        print(json.dumps({
            "collected": False,
            "warning": str(e)[:100]
        }), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()