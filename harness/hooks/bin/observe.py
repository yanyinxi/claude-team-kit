#!/usr/bin/env python3
"""
observe.py — Claude Code Hook 观测事件采集器

处理 PreToolUse + PostToolUse + UserPromptSubmit 三种 Hook 类型：
  - 解析 JSON hook 数据（native tool + MCP tool 全兼容）
  - 提取 session/tool/content 字段（带三段式 fallback）
  - 行为分析：用户反馈检测 + 工具使用模式识别
  - 写入 observations.jsonl（never raise，零阻塞）

Author: Claude Code CHK v2
"""
import os
import sys
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── 环境 ──────────────────────────────────────────────────────────────────────

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
OBS_DIR = PLUGIN_ROOT / ".claude" / "homunculus"
OBS_LOG = OBS_DIR / "observations.jsonl"
ERROR_LOG = OBS_DIR / "observe_errors.log"

# ── 反馈关键词（多语言）────────────────────────────────────────────────────────

CORRECTION_KEYWORDS = {
    "不对", "not right", "wrong", "错了", "incorrect",
    "should be", "应该", "改成", "change to", "fix", "修正",
    "不是", "差", "有问题", "bug", "error", "fail", "broken",
    "再改", "再试", "重写", "重新", "重试", "again", "retry",
    "不对不对", "no no", "nope", "nah", "not quite",
}
APPROVAL_KEYWORDS = {
    "好", "good", "correct", "可以", "ok", "okk", "okay", "perfect",
    "很好", "棒", "厉害", "不错", "就这样", "对了", "yes", "yep",
    "可以可以", "完美", "ideal", "exactly", "that works", "done",
}
REJECTION_KEYWORDS = {
    "no", "don't", "stop", "别", "不要", "不行", "不对",
    "wrong", "not that", "cancel", "forget it", "算了", "算了算了",
}

# ── 工具模式识别 ─────────────────────────────────────────────────────────────

READ_EXTENSIONS = {"js", "ts", "tsx", "jsx", "py", "go", "rs", "java",
                   "c", "cpp", "h", "hpp", "cs", "rb", "php", "swift",
                   "kt", "sh", "bash", "zsh", "json", "yaml", "yml",
                   "toml", "xml", "html", "css", "scss", "md", "txt",
                   "sql", "r", "R", "lua", "pl", "ps1", "vue", "svelte"}


def _mkdir_for(path: Path) -> None:
    """确保目录存在，失败不抛异常"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _write_log(path: Path, line: str) -> None:
    """写日志，失败静默跳过"""
    try:
        _mkdir_for(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── 核心解析 ──────────────────────────────────────────────────────────────────

def parse_hook_data(raw: str) -> Optional[dict]:
    """解析 hook JSON data，三段式 fallback"""
    # 阶段1：标准 JSON
    try:
        return json.loads(raw)
    except Exception:
        pass

    # 阶段2：尝试修复（多行 JSON 包裹）
    stripped = raw.strip()
    if stripped.startswith("{") and not stripped.endswith("}"):
        # 尝试截取到最后一个 }
        candidate = stripped[:stripped.rfind("}") + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # 阶段3：记录解析失败，返回 None
    _write_log(ERROR_LOG, f"[{_ts()}] PARSE_FAILED: {raw[:200]!r}")
    return None


def infer_hook_type(data: dict) -> str:
    """
    推断 Hook 类型，兼容 native tool + MCP tool + 各种 Claude Code 版本格式
    """
    # 优先从顶层字段推断（某些版本直接暴露）
    msg = data.get("message", {})

    if isinstance(msg, dict):
        msg_type = msg.get("type", "")
        if msg_type == "user":
            return "UserPromptSubmit"
        if msg_type == "assistant":
            return "AssistantGenerate"

        # message.name 存在 → ToolCall
        name = msg.get("name", "")
        if name:
            return f"ToolCall:{name}"

    # 顶层字段兜底
    if "tool_name" in data:
        return f"ToolCall:{data.get('tool_name', '')}"
    if "output" in data:
        return "PostToolUse"
    if "error" in data:
        return "PostToolUseFailure"

    # 新格式兜底：某些版本用 hook_type 字段
    if "hook_type" in data:
        return data["hook_type"]

    return "Unknown"


def extract_tool_name(data: dict, hook_type: str) -> str:
    """
    跨格式提取 tool name
    """
    # 方式1：从 hook_type 解析（"ToolCall:xxx"）
    if ":" in hook_type:
        return hook_type.split(":", 1)[1]

    # 方式2：从 message.name
    msg = data.get("message", {})
    if isinstance(msg, dict):
        name = msg.get("name", "")
        if name:
            return name

    # 方式3：从顶层 tool_name
    tn = data.get("tool_name", "")
    if tn:
        return tn

    return "unknown"


def extract_content(data: dict, hook_type: str) -> str:
    """
    提取用户 prompt 或工具输入内容
    """
    msg = data.get("message", {})
    if not isinstance(msg, dict):
        msg = {}

    content = msg.get("content", "")

    # content 可能是字符串或 Block[]
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                for key in ("text", "input", "content"):
                    val = block.get(key, "")
                    if isinstance(val, str) and val:
                        parts.append(val)
                    elif isinstance(val, list):
                        for sub in val:
                            if isinstance(sub, dict) and sub.get("text"):
                                parts.append(sub["text"])
        content = " ".join(parts)
    elif not isinstance(content, str):
        content = str(content) if content else ""

    return content[:600]  # 截断防止过大


def extract_tool_input(data: dict, tool_name: str) -> dict:
    """
    提取工具输入参数（用于模式识别）
    """
    msg = data.get("message", {})
    if not isinstance(msg, dict):
        msg = {}

    # 方式1：message.content[].inputs（Claude Code 标准格式）
    content = msg.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "input":
                inputs = block.get("inputs", [])
                if isinstance(inputs, list):
                    return {inp.get("name", ""): inp.get(inp.get("name", ""), "")
                            for inp in inputs if isinstance(inp, dict)}

    # 方式2：顶层 tool_input
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        return ti

    # 方式3：从 message 直接取
    if tool_name in ("Read", "Write", "Edit", "Bash"):
        result = {}
        for key in ("file_path", "command", "old_string", "new_string", "path"):
            if key in msg:
                result[key] = msg[key]
        return result

    return {}


def analyze_feedback(content: str) -> str:
    """检测用户反馈类型"""
    content_lower = content.lower()

    # 纠正反馈（最高优先级）
    for kw in CORRECTION_KEYWORDS:
        if kw.lower() in content_lower:
            return "correction"

    # 批准反馈
    for kw in APPROVAL_KEYWORDS:
        if kw.lower() in content_lower:
            return "approval"

    # 拒绝反馈
    for kw in REJECTION_KEYWORDS:
        if kw.lower() in content_lower:
            return "rejection"

    return ""


def _combined_lower(tool_input: dict, content: str) -> str:
    """合并 file_path/command 和 content，供模式匹配使用"""
    parts = []
    for key in ("file_path", "path", "command"):
        val = tool_input.get(key, "")
        if isinstance(val, str) and val:
            parts.append(val.lower())
    parts.append(content.lower())
    return " ".join(parts)


def analyze_tool_pattern(tool_name: str, tool_input: dict, content: str) -> str:
    """识别工具使用模式"""
    base = tool_name.split("__")[-1]  # MCP tool → 去掉前缀
    combined = _combined_lower(tool_input, content)

    if base in ("Read", "Read__非"):
        fp = tool_input.get("file_path", "")
        if fp:
            ext = fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
            if ext in READ_EXTENSIONS:
                return f"read:{ext}"
            return "read:other"

    if base in ("Write", "Edit") or tool_name in ("Write", "Edit"):
        if re.search(r"\b(test|spec|__test__|spec\.)\w*", combined):
            return "test_write"
        if re.search(r"\b(config|setup|settings|manifest)\w*", combined):
            return "config_write"
        if re.search(r"\b(readme|doc|changelog|license)\w*", combined):
            return "docs_write"
        return "code_write"

    if base in ("Bash", "Command"):
        cmd = tool_input.get("command", "")
        if re.search(r"\b(git|hg|svn)\b", cmd):
            return "vcs_command"
        if re.search(r"\b(python|node|ruby|java|go|rust)\b", cmd):
            return "run_script"
        if re.search(r"\b(curl|wget|http)\b", cmd):
            return "network_request"
        return "shell_command"

    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            return f"mcp_{parts[2]}"
        return "mcp_tool"

    return ""


def build_observation(
    session_id: str,
    hook_type: str,
    tool_name: str,
    feedback: str,
    patterns: str,
) -> dict:
    """构造观测记录"""
    return {
        "timestamp": _ts(),
        "session_id": session_id,
        "hook_type": hook_type,
        "tool": tool_name,
        "feedback": feedback,
        "patterns": patterns,
    }


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 主逻辑 ───────────────────────────────────────────────────────────────────

def main() -> int:
    """
    入口：读取 stdin → 解析 → 分析 → 写入
    永远返回 0，不抛异常
    """
    # 1. 读取 hook 数据
    try:
        raw = sys.stdin.read()
    except Exception as e:
        _write_log(ERROR_LOG, f"[{_ts()}] STDIN_READ_ERROR: {e}")
        return 0

    if not raw or not raw.strip():
        return 0

    # 2. 解析 JSON
    data = parse_hook_data(raw)
    if data is None:
        # 解析失败是正常的（MCP 工具有时格式不同），静默跳过
        return 0

    # 3. 推断 hook 类型
    hook_type = infer_hook_type(data)

    # 4. 提取核心字段（均有 fallback）
    session_id = data.get("sessionId") or data.get("session_id") or "unknown"
    tool_name = extract_tool_name(data, hook_type)
    content = extract_content(data, hook_type)

    # 5. 行为分析
    feedback = ""
    patterns = ""

    if hook_type == "UserPromptSubmit":
        feedback = analyze_feedback(content)
    else:
        tool_input = extract_tool_input(data, tool_name)
        patterns = analyze_tool_pattern(tool_name, tool_input, content)

    # 6. 仅在有意义时才写入
    if not (feedback or patterns):
        return 0

    # 7. 构造并写入观测记录
    obs = build_observation(session_id, hook_type, tool_name, feedback, patterns)
    try:
        _mkdir_for(OBS_LOG)
        with open(OBS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    except Exception as e:
        _write_log(ERROR_LOG, f"[{_ts()}] WRITE_ERROR: {e}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        _write_log(ERROR_LOG, f"[{_ts()}] UNHANDLED: {e}")
        sys.exit(0)
