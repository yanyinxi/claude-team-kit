#!/usr/bin/env python3
"""
语义提取器 — 用 Haiku 从会话中提取用户纠正上下文。

触发: collect_session.py 检测到纠正时异步调用
成本: Haiku ~$0.0001/次，可忽略
超时: 5s 放弃，不影响下次会话

原则:
  - 只提取事实（用户说了什么，改了什么），不做判断
  - 失败静默，元数据已兜底
"""
import json
import os
import sys
from pathlib import Path


def find_project_root():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def get_last_session(root: Path) -> dict | None:
    sessions_file = root / ".claude" / "data" / "sessions.jsonl"
    if not sessions_file.exists():
        return None

    lines = sessions_file.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None

    return json.loads(lines[-1])


def extract_with_haiku(session: dict) -> list[dict]:
    """调用 Claude Haiku 提取纠正上下文"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    system_prompt = """你是一个对话分析器。从会话摘要中提取用户纠正 AI 的上下文。

输出 JSON 数组（仅 JSON，无其他文字）:
[
  {
    "target": "skill:xxx 或 agent:xxx",
    "context": "用户当时在做什么",
    "ai_suggestion": "AI 建议了什么",
    "user_correction": "用户纠正了什么",
    "resolution": "纠正后的结果",
    "root_cause_hint": "可能的 skill/agent 定义缺失"
  }
]

如果没有纠正，输出 []。"""

    user_message = json.dumps(session, ensure_ascii=False)

    # 方案 1: 使用 anthropic SDK
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            temperature=0.1,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text
        corrections = json.loads(text)
        return corrections if isinstance(corrections, list) else []
    except ImportError:
        pass

    # 方案 2: 标准库 REST API（零外部依赖）
    try:
        import urllib.request
        body = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 512,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            text = result["content"][0]["text"]
            corrections = json.loads(text)
            return corrections if isinstance(corrections, list) else []
    except Exception:
        return []


def main():
    root = find_project_root()
    session = get_last_session(root)
    if session is None:
        return

    corrections = extract_with_haiku(session)
    if not corrections:
        return

    # 回填 sessions.jsonl 最后一行
    sessions_file = root / ".claude" / "data" / "sessions.jsonl"
    lines = sessions_file.read_text(encoding="utf-8").strip().splitlines()
    session["corrections"] = corrections
    lines[-1] = json.dumps(session, ensure_ascii=False)
    sessions_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 记录到 instinct（待观察状态，confidence=0.3）
    _record_to_instinct(corrections)


def _record_to_instinct(corrections: list[dict]):
    """将新发现的纠正模式记录到 instinct-record.json"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "evolve-daemon"))
        from instinct_updater import add_pattern
        for c in corrections:
            add_pattern(
                pattern=c.get("target", "unknown") + ": " + c.get("context", "")[:60],
                correction=c.get("user_correction", "")[:100],
                root_cause=c.get("root_cause_hint", ""),
                confidence=0.3,
                source="extract-semantics",
            )
    except Exception:
        pass  # instinct 失败不影响主流程


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys, json
        print(json.dumps({"collected": False, "warning": str(e)[:100]}), file=sys.stderr)
        sys.exit(0)
