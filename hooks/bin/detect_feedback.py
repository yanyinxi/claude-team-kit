#!/usr/bin/env python3
"""
UserPromptSubmit Hook — 检测用户消息中的反馈信号
触发 Memory 进化。

检测模式:
  - 记忆请求: (记住|记下|保存)(这个|一下)?[：:]
  - 纠正信号: (不对|错了|不是这样)[，,]?
  - 确认信号: (对的|没错|就是这样|exactly|perfect)
  - 偏好声明: (以后|下次|将来|always|never)\s

质量过滤:
  - 噪音过滤: 外来系统 Prompt 泄漏
  - 最小内容长度: 10+ 字符（确保有足够上下文创建记忆）
  - 去重: 与已有信号比较，相似度 > 0.8 则跳过

输出: data/pending_evolution.json (合并模式)
"""
import json, os, re, sys
from datetime import datetime
from pathlib import Path


MEMORY_SIGNAL = re.compile(
    r'(?:记住|记下|保存)(?:这个|一下)?[：:]\s*(.+)'
)
CORRECTION_SIGNAL = re.compile(
    r'(?:不对|错了|不是这样)[，,]?\s*(.+)'
)
CONFIRMATION_SIGNAL = re.compile(
    r'(?:对的|没错|就是这样|exactly|perfect)\b', re.IGNORECASE
)
PREFERENCE_SIGNAL = re.compile(
    r'(?:以后|下次|将来|always|never)\s+(.+)', re.IGNORECASE
)

# 噪音模式
NOISE_PATTERNS = [
    re.compile(r'<ultrawork-mode>', re.IGNORECASE),
    re.compile(r'INVOKE THE PLAN AGENT', re.IGNORECASE),
    re.compile(r'delegate_task', re.IGNORECASE),
    re.compile(r'load_skills\s*=\s*\[', re.IGNORECASE),
    re.compile(r'issues\.chromium\.org', re.IGNORECASE),
    re.compile(r'ULTRAWORK MODE ENABLED', re.IGNORECASE),
    re.compile(r'Maximum precision required', re.IGNORECASE),
    re.compile(r'submit your feedback here', re.IGNORECASE),
]

# 信号质量阈值
MIN_CONTENT_LENGTH = 10  # 最少 10 个字符才有足够上下文
MIN_SPECIFIC_WORDS = 3   # 至少 3 个汉字或单词才不算泛泛而谈


def _is_noise(text: str) -> bool:
    """检查文本是否为已知的外来系统噪音。"""
    for pattern in NOISE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _content_quality(text: str) -> bool:
    """
    检查信号内容是否足够具体，能生成有意义的记忆。
    过滤掉过于泛泛的指令（如 '你深度检查和思考一下之前的动作'）。
    """
    text = text.strip()
    if len(text) < MIN_CONTENT_LENGTH:
        return False
    # 计算有意义的词数（中文字符或英文单词）
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return (chinese_chars + english_words) >= MIN_SPECIFIC_WORDS


def _is_duplicate(new_content: str, existing_signals: list) -> bool:
    """检查是否与已有信号重复（简单 Jaccard 相似度）。"""
    if not existing_signals:
        return False
    new_chars = set(new_content)
    if len(new_chars) < 3:
        return False
    for sig in existing_signals[-20:]:  # 只检查最近 20 条
        existing_chars = set(sig.get("content", ""))
        if not existing_chars:
            continue
        intersection = len(new_chars & existing_chars)
        union = len(new_chars | existing_chars)
        if union == 0:
            continue
        similarity = intersection / union
        if similarity > 0.8:
            return True
    return False


def main():
    try:
        raw = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        return

    prompt = data.get("prompt", "")
    if not prompt:
        return

    # 噪音过滤
    if _is_noise(prompt):
        print("[detect_feedback] 跳过噪音信号", file=sys.stderr)
        return

    session_id = data.get("session_id", "unknown")
    signals = []

    # 检测记忆请求
    m = MEMORY_SIGNAL.search(prompt)
    if m:
        content = m.group(1).strip()
        if _content_quality(content) and not _is_noise(content):
            signals.append({
                "type": "memory_request",
                "content": content[:300],
            })

    # 检测纠正信号
    m = CORRECTION_SIGNAL.search(prompt)
    if m:
        content = m.group(1).strip()
        if _content_quality(content) and not _is_noise(content):
            signals.append({
                "type": "correction",
                "content": content[:300],
            })

    # 检测确认信号 (正面反馈) — 需额外质量检查
    if CONFIRMATION_SIGNAL.search(prompt) and not _is_noise(prompt[:200]):
        # 确认信号只取 prompt 前 100 字符，且需有足够内容
        content = prompt[:100].strip()
        if _content_quality(content):
            signals.append({
                "type": "confirmation",
                "content": content,
            })

    # 检测偏好声明
    m = PREFERENCE_SIGNAL.search(prompt)
    if m:
        content = m.group(1).strip()
        if _content_quality(content) and not _is_noise(content):
            signals.append({
                "type": "preference",
                "content": content[:300],
            })

    if not signals:
        return

    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    data_dir = Path(project_root) / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    pending_file = data_dir / "pending_evolution.json"
    pending_file.parent.mkdir(parents=True, exist_ok=True)

    # fcntl 锁保护的原子 read-modify-write
    with open(pending_file, "a+") as f:
        import fcntl as _fcntl
        _fcntl.flock(f.fileno(), _fcntl.LOCK_EX)
        try:
            f.seek(0)
            content = f.read()
            pending = {}
            if content.strip():
                try:
                    pending = json.loads(content)
                except (json.JSONDecodeError, OSError):
                    pending = {}

            existing = pending.get("feedback_signals", [])
            new_count = 0
            for s in signals:
                # 去重检查
                if _is_duplicate(s["content"], existing):
                    continue
                s["timestamp"] = datetime.now().isoformat()
                s["session_id"] = session_id
                existing.append(s)
                new_count += 1

            if new_count == 0:
                return

            pending["feedback_signals"] = existing
            pending["last_signal_at"] = datetime.now().isoformat()
            pending["session_id"] = session_id

            f.seek(0)
            f.truncate()
            f.write(json.dumps(pending, indent=2, ensure_ascii=False))
        finally:
            _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)

    print("detect_feedback: {} 个新信号 ({} 个跳过重复)".format(
        new_count, len(signals) - new_count
    ), file=sys.stderr)


if __name__ == "__main__":
    main()
