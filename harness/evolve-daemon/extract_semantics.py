#!/usr/bin/env python3
"""
语义提取器封装 — 为 daemon.py 提供 analyze_session() API。

职责：
  1. 封装 hooks/bin/extract_semantics.py 的逻辑
  2. 提供 analyze_session(session) 接口供 daemon 内部调用
  3. 对新会话进行语义提取，回填 corrections 字段

使用方式：
  from extract_semantics import analyze_session
  analyze_session(session, root)
"""
import json
import os
import sys
from pathlib import Path

# 添加同级的 kb_shared 到 Python path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from kb_shared import get_haiku_model, create_llm_client, get_llm_config, read_jsonl
from _find_root import find_root as get_project_root


def extract_with_haiku(session: dict) -> list[dict]:
    """
    调用 Claude Haiku 提取纠正上下文（统一 LLM 配置）。

    底层使用 kb_shared.get_llm_config()，所有 LLM 调用路径统一。
    """
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

    # 方案 1: 使用统一 SDK 客户端
    try:
        client = create_llm_client()
        response = client.messages.create(
            model=get_haiku_model(),
            max_tokens=512,
            temperature=0.1,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = ""
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                text = block.text.strip()
                break
        if not text:
            return []
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        corrections = json.loads(text)
        return corrections if isinstance(corrections, list) else []
    except ImportError:
        pass

    # 方案 2: 标准库 REST API（零外部依赖，降级）
    try:
        import urllib.request
        cfg = get_llm_config()
        body = json.dumps({
            "model": get_haiku_model(),
            "max_tokens": 512,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{cfg['base_url']}/v1/messages",
            data=body,
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            text = result["content"][0]["text"]
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                text = text.rsplit("```", 1)[0].strip()
            corrections = json.loads(text)
            return corrections if isinstance(corrections, list) else []
    except Exception:
        return []


def analyze_session(session: dict, root: Path | None = None) -> dict:
    """
    分析单个会话，提取语义并回填。

    Args:
        session: 会话 dict（必须包含 session_id）
        root: 项目根目录

    Returns:
        {
            "success": True/False,
            "session_id": str,
            "corrections_count": int,
            "corrections": [...] or [],
            "error": str or None,
        }
    """
    if root is None:
        root = get_project_root()

    session_id = session.get("session_id", "unknown")
    data_dir = root / ".claude" / "data"
    sessions_file = data_dir / "sessions.jsonl"

    # 跳过已有 corrections 的会话
    if session.get("corrections") and len(session.get("corrections", [])) > 0:
        return {
            "success": True,
            "session_id": session_id,
            "corrections_count": len(session["corrections"]),
            "corrections": session["corrections"],
            "error": None,
            "skipped": True,
        }

    # 调用 Haiku 提取
    try:
        corrections = extract_with_haiku(session)
    except EnvironmentError as e:
        raise EnvironmentError(str(e))

    # 回填 sessions.jsonl
    try:
        if sessions_file.exists():
            sessions = read_jsonl(sessions_file)
            updated = False
            for s in sessions:
                if s.get("session_id") == session_id:
                    s["corrections"] = corrections
                    updated = True
            if updated:
                sessions_file.write_text(
                    "\n".join(json.dumps(s, ensure_ascii=False) for s in sessions) + "\n",
                    encoding="utf-8"
                )
    except Exception:
        pass  # 回填失败不影响主流程

    # 记录到 instinct（待观察状态，confidence=0.3）
    instinct_ids = _record_to_instinct(corrections, root)

    return {
        "success": True,
        "session_id": session_id,
        "corrections_count": len(corrections),
        "corrections": corrections,
        "error": None,
        "instinct_record_ids": instinct_ids,
    }


def analyze_sessions(sessions: list[dict], root: Path | None = None) -> list[dict]:
    """
    批量分析多个会话。

    Returns: 每个会话的分析结果列表
    """
    results = []
    for session in sessions:
        result = analyze_session(session, root)
        results.append(result)
    return results


def _record_to_instinct(corrections: list[dict], root: Path) -> list[str]:
    """将新发现的纠正模式记录到 instinct-record.json，返回 record_ids"""
    record_ids = []
    try:
        from instinct_updater import add_pattern
        for c in corrections:
            target = c.get("target", "unknown")
            pattern = f"{target}: {c.get('context', '')[:60]}"
            record_id = add_pattern(
                pattern=pattern,
                correction=c.get("user_correction", "")[:100],
                root_cause=c.get("root_cause_hint", ""),
                confidence=0.3,
                source="extract-semantics",
                root=root,
            )
            if record_id:
                record_ids.append(record_id)
    except Exception:
        pass
    return record_ids


def main():
    """CLI 测试入口"""
    root = get_project_root()
    sessions_file = root / ".claude" / "data" / "sessions.jsonl"

    if not sessions_file.exists():
        print("sessions.jsonl not found")
        return

    sessions = read_jsonl(sessions_file)
    if not sessions:
        print("No sessions found")
        return

    # 分析最后一个会话
    session = sessions[-1]
    result = analyze_session(session, root)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()