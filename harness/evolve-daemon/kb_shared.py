#!/usr/bin/env python3
"""
kb_shared.py — 统一知识库共享函数库

所有进化流程（会话级 + 决策级）共享的工具函数。

核心功能：
1. 知识库读写（统一 knowledge_base.jsonl）
2. 置信度管理（基于测试验证的实时更新）
3. 冷启动迁移（从 instinct-record.json 迁移）
4. 状态机（unconfirmed / active / deprecated）
5. merge abort 冷却期管理
6. LLM 失败飞书通知
7. 知识衰减与退化检测
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ── 统一模型配置 ─────────────────────────────────────────────
def get_haiku_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

def get_sonnet_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6-20250514")

def get_llm_config() -> dict:
    """统一 LLM 配置参数，所有模块引用此处"""
    model = os.environ.get("ANTHROPIC_MODEL")
    return {
        # 模型
        "extract_model": model or "claude-haiku-4-5-20251001",
        "analyze_model": model or "claude-sonnet-4-6-20250514",
        "decide_model": model or "claude-sonnet-4-6-20250514",
        # Haiku 参数（快速分类）
        "extract_max_tokens": 8192,
        "extract_temperature": 0.1,
        # Sonnet 参数（深度分析）
        "analyze_max_tokens": 4096,
        "analyze_temperature": 0.3,
        "decide_max_tokens": 2048,
        "decide_temperature": 0.2,
        # API
        "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        "api_key": os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "PROXY_MANAGED"),
    }

def create_llm_client() -> "Anthropic":
    """创建统一的 LLM 客户端"""
    from anthropic import Anthropic
    cfg = get_llm_config()
    return Anthropic(api_key=cfg["api_key"], base_url=cfg["base_url"])


# ── 路径常量 ────────────────────────────────────────────────
def _find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _evolve_dir() -> Path:
    return _find_root() / "harness" / "evolve-daemon"


def _knowledge_dir() -> Path:
    d = _evolve_dir() / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


KB_PATH = _knowledge_dir() / "knowledge_base.jsonl"
INSTINCT_PATH = _find_root() / "harness" / "instinct" / "instinct-record.json"
EFFECT_PATH = _knowledge_dir() / "effect_tracking.jsonl"
MERGE_COOLDOWN_PATH = _knowledge_dir() / "merge_cooldown.jsonl"
NOTIFY_COOLDOWN_PATH = _knowledge_dir() / "notify_cooldown.jsonl"


# ── 时间工具 ────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now().isoformat()


def hours_ago(hours: int) -> str:
    return (datetime.now() - timedelta(hours=hours)).isoformat()


def days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat()


# ── JSONL 工具 ─────────────────────────────────────────────
def read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件，返回 list[dict]"""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path: Path, entry: dict):
    """追加一条到 JSONL 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, entries: list[dict]):
    """重写整个 JSONL 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_json(path: Path) -> dict | list | None:
    """读取 JSON 文件"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_json(path: Path, data):
    """写入 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 知识库读写 ─────────────────────────────────────────────
def load_knowledge_base(root: Optional[Path] = None) -> list[dict]:
    """加载所有知识库条目"""
    if root:
        kb_file = root / "harness" / "evolve-daemon" / "knowledge" / "knowledge_base.jsonl"
    else:
        kb_file = KB_PATH
    return read_jsonl(kb_file)


def load_active_kb(root: Optional[Path] = None) -> list[dict]:
    """加载活跃知识（未被 superseded）"""
    kb = load_knowledge_base(root)
    return [e for e in kb if not e.get("superseded_by")]


def save_kb_entry(entry: dict, root: Optional[Path] = None):
    """追加一条知识到知识库"""
    if root:
        kb_file = root / "harness" / "evolve-daemon" / "knowledge" / "knowledge_base.jsonl"
    else:
        kb_file = KB_PATH
    append_jsonl(kb_file, entry)


def update_kb_all(entries: list[dict], root: Optional[Path] = None):
    """重写整个知识库"""
    if root:
        kb_file = root / "harness" / "evolve-daemon" / "knowledge" / "knowledge_base.jsonl"
    else:
        kb_file = KB_PATH
    write_jsonl(kb_file, entries)


def find_kb_by_id(kb_id: str, root: Optional[Path] = None) -> dict | None:
    """根据 ID 查找知识"""
    kb = load_knowledge_base(root)
    for e in kb:
        if e.get("id") == kb_id:
            return e
    return None


def find_kb_by_pattern(pattern: str, root: Optional[Path] = None) -> list[dict]:
    """根据 error_type 查找知识"""
    kb = load_active_kb(root)
    return [e for e in kb if pattern.lower() in e.get("error_type", "").lower()]


def find_kb_by_dimension(
    dimension: str, target: str = "", root: Optional[Path] = None
) -> dict | None:
    """根据维度 + target 查找知识"""
    kb = load_active_kb(root)
    for e in kb:
        if e.get("dimension") == dimension:
            et = e.get("error_type", "")
            if not target or target.lower() in et.lower():
                return e
    return None


# ── 置信度更新 ─────────────────────────────────────────────
def update_kb_confidence(
    kb_id: str,
    outcome: str,  # "success" | "failure"
    root: Optional[Path] = None,
):
    """
    根据测试结果更新知识置信度。
    唯一来源：自动化测试。
    """
    kb = load_knowledge_base(root)

    for entry in kb:
        if entry.get("id") != kb_id:
            continue

        entry["validation_count"] = entry.get("validation_count", 0) + 1
        entry["updated_at"] = now_iso()

        if outcome == "success":
            entry["success_count"] = entry.get("success_count", 0) + 1
            entry["confidence"] = min(1.0, entry.get("confidence", 0.5) + 0.02)
            _track_effect(kb_id, "success", root)

            # 升级状态：unconfirmed → active
            if entry.get("status") == "unconfirmed":
                vc = entry.get("validation_count", 0)
                sc = entry.get("success_count", 0)
                if vc >= 3 and sc / vc >= 0.8:
                    entry["status"] = "active"
                    print(f"  [KB] {kb_id} 升级为 active")

        elif outcome == "failure":
            entry["failure_count"] = entry.get("failure_count", 0) + 1
            entry["confidence"] = max(0.0, entry.get("confidence", 0.5) - 0.15)
            _track_effect(kb_id, "failure", root)

            # 降级状态：连续 3 次失败 → rollback_pending
            fc = entry.get("failure_count", 0)
            if fc >= 3:
                entry["status"] = "rollback_pending"

        # 失效退级：成功率 < 50% 且 validation_count >= 3
        vc = entry.get("validation_count", 0)
        sc = entry.get("success_count", 0)
        if vc >= 3 and sc / vc < 0.5:
            entry["status"] = "deprecated"
            print(f"  [KB] {kb_id} 降级为 deprecated")

        break

    update_kb_all(kb, root)


def _track_effect(kb_id: str, outcome: str, root: Optional[Path]):
    """写入 effect_tracking.jsonl"""
    if root:
        effect_file = root / "harness" / "evolve-daemon" / "knowledge" / "effect_tracking.jsonl"
    else:
        effect_file = EFFECT_PATH
    append_jsonl(effect_file, {
        "knowledge_id": kb_id,
        "outcome": outcome,
        "timestamp": now_iso(),
    })


# ── 状态判断 ───────────────────────────────────────────────
def should_auto_apply(entry: dict) -> tuple[bool, str]:
    """
    判断知识是否应该自动应用。
    返回: (should_apply, reason)
    """
    status = entry.get("status", "unconfirmed")

    # 只有 active 状态才能 auto_apply
    if status == "deprecated":
        return False, "deprecated"

    # 置信度阈值
    conf = entry.get("confidence", 0)
    if conf < 0.7:
        return False, f"confidence {conf:.2f} < 0.7"

    # 验证次数阈值
    vc = entry.get("validation_count", 0)
    if vc < 3:
        return False, f"validation_count {vc} < 3"

    # 失败率阈值
    fc = entry.get("failure_count", 0)
    if vc > 0 and fc / vc > 0.2:
        return False, f"failure_rate {fc/vc:.0%} > 20%"

    return True, "ok"


def is_covered_by_kb(correction_text: str, root: Optional[Path] = None) -> tuple[bool, str | None]:
    """
    检查纠正是否已被知识库覆盖（语义相似度检查）。
    优先用 LLM 做语义匹配，fallback 到字符串包含匹配。
    返回: (is_covered, matched_kb_id)
    """
    import os as _os
    kb = load_active_kb(root)
    correction_lower = correction_text.lower()

    # 先做快速字符串匹配
    for entry in kb:
        for example in entry.get("specific_examples", []):
            if example.lower() in correction_lower or correction_lower in example.lower():
                return True, entry.get("id")

    # 语义匹配（调用 LLM）
    if _os.environ.get("ANTHROPIC_BASE_URL") or _os.environ.get("ANTHROPIC_API_KEY") or _os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        matched_id = _semantic_match(correction_text, kb)
        if matched_id:
            return True, matched_id

    return False, None


def _semantic_match(text: str, kb: list[dict]) -> str | None:
    """
    用 LLM 做语义相似度匹配。
    返回匹配的 KB 条目 ID，或 None。
    """
    if not kb:
        return None

    try:
        client = create_llm_client()

        # 最多对比 10 条
        sample_kb = kb[:10]
        kb_text = "\n".join([
            f"- id={e['id']} type={e.get('error_type','')[:40]} root={e.get('root_cause','')[:60]}"
            for e in sample_kb
        ])

        system = """你是一个代码库知识匹配专家。判断新错误是否和已有知识相似。

规则：
- 如果根因相同或非常相似，返回匹配的 id
- 如果完全不相关，返回 null
- 宁可保守，不要误匹配

输出 JSON：
{"matched_id": "kb-xxxx" | null, "confidence": 0.0-1.0, "reason": "简短理由"}"""

        user = f"""已有知识：
{kb_text}

待匹配错误：{text}

判断是否已有相似知识？"""

        response = client.messages.create(
            model=get_haiku_model(),
            max_tokens=512,
            temperature=0.1,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # 提取文本内容（跳过 thinking block，处理 ```json 包裹）
        content = ""
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                content = block.text.strip()
                break
        if not content:
            return None
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0].strip()
        result = json.loads(content) if content else {}
        matched_id = result.get("matched_id")
        if matched_id:
            print(f"  [KB] 语义匹配: {text[:40]} → {matched_id} (conf={result.get('confidence', 0):.2f})")
        return matched_id
    except Exception:
        return None


def should_activate(entry: dict) -> bool:
    """判断 unconfirmed 知识是否可以激活"""
    vc = entry.get("validation_count", 0)
    sc = entry.get("success_count", 0)
    fc = entry.get("failure_count", 0)

    if vc < 3:
        return False
    if sc + fc == 0:
        return False

    success_rate = sc / (sc + fc)
    return success_rate >= 0.8


# ── 知识降级 ─────────────────────────────────────────────
def deprecate_knowledge(kb_id: str, reason: str = "", root: Optional[Path] = None):
    """将知识降级为 deprecated"""
    kb = load_knowledge_base(root)
    for entry in kb:
        if entry.get("id") == kb_id:
            entry["status"] = "deprecated"
            entry["deprecated_reason"] = reason
            entry["deprecated_at"] = now_iso()
            entry["updated_at"] = now_iso()
            break
    update_kb_all(kb, root)


def reactivate_knowledge(kb_id: str, root: Optional[Path] = None):
    """将 deprecated 知识重新激活（用新证据）"""
    kb = load_knowledge_base(root)
    for entry in kb:
        if entry.get("id") == kb_id:
            entry["status"] = "unconfirmed"
            entry["reactivated_at"] = now_iso()
            entry["updated_at"] = now_iso()
            entry["failure_count"] = 0
            entry["validation_count"] = 0
            entry["success_count"] = 0
            break
    update_kb_all(kb, root)


# ── merge 冷却期管理 ───────────────────────────────────────
def check_merge_cooldown(
    kb_ids: list[str], hours: int = 6
) -> bool:
    """
    检查这组 kb_ids 是否处于 merge abort 冷却期。
    返回: True = 在冷却期内，不能 merge；False = 可以 merge
    """
    if not kb_ids:
        return False

    records = read_jsonl(MERGE_COOLDOWN_PATH)
    cutoff = hours_ago(hours)

    for rec in records:
        if rec.get("aborted_at", "") < cutoff:
            continue
        # 检查是否有交集
        aborted_ids = set(rec.get("kb_ids", []))
        current_ids = set(kb_ids)
        if aborted_ids & current_ids:  # 有交集
            return True

    return False


def record_merge_abort(kb_ids: list[str], reason: str = ""):
    """记录 merge abort"""
    append_jsonl(MERGE_COOLDOWN_PATH, {
        "kb_ids": kb_ids,
        "reason": reason,
        "aborted_at": now_iso(),
    })


def clear_expired_cooldown(hours: int = 6):
    """清理过期的 abort 记录"""
    records = read_jsonl(MERGE_COOLDOWN_PATH)
    cutoff = hours_ago(hours)
    active = [r for r in records if r.get("aborted_at", "") >= cutoff]
    write_jsonl(MERGE_COOLDOWN_PATH, active)


# ── LLM 失败通知 ───────────────────────────────────────────
def notify_llm_failure(
    error: str,
    context: str = "",
    notify_url: str = "",
):
    """
    LLM 调用失败时发送飞书通知。
    通知后系统继续自动运行（零人工）。
    """
    if not notify_url:
        # 从环境变量读取
        notify_url = os.environ.get("FEISHU_WEBHOOK_URL", "")

    if not notify_url:
        print(f"  [通知] LLM 失败但未配置飞书通知: {error[:100]}")
        return

    import urllib.request
    import urllib.error

    message = {
        "msg_type": "text",
        "content": {
            "text": (
                f"[CHK 进化系统] LLM 调用失败\n"
                f"时间: {now_iso()}\n"
                f"错误: {error[:200]}\n"
                f"上下文: {context[:100] if context else '无'}\n"
                f"系统将继续自动运行，下次触发时重试。"
            )
        },
    }

    try:
        body = json.dumps(message).encode("utf-8")
        req = urllib.request.Request(
            notify_url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print(f"  [通知] 飞书通知已发送")
    except Exception as e:
        print(f"  [通知] 飞书通知发送失败: {e}")


# ── 知识衰减 ───────────────────────────────────────────────
def decay_knowledge(root: Optional[Path] = None):
    """
    定期知识衰减。
    - 30 天未验证的知识：置信度缓慢下降
    - 衰退后成功率 < 70%：标记为 deprecated
    """
    kb = load_knowledge_base(root)
    now = datetime.now()
    changed = False

    for entry in kb:
        if entry.get("status") in ("deprecated", "pending"):
            continue

        last_validated = entry.get("updated_at", entry.get("created_at", ""))
        if not last_validated:
            continue

        try:
            last_dt = datetime.fromisoformat(last_validated)
            days_since = (now - last_dt).days
        except (ValueError, TypeError):
            continue

        if days_since > 30:
            # 每超过 30 天，置信度下降 10%
            decay_steps = (days_since - 30) // 30
            decay = decay_steps * 0.10
            old_conf = entry.get("confidence", 0.5)
            entry["confidence"] = max(0.1, old_conf - decay)
            entry["updated_at"] = now_iso()
            entry["decayed"] = True
            changed = True

            if entry.get("confidence", 0) < 0.3:
                entry["status"] = "deprecated"
                entry["deprecated_reason"] = "confidence too low after decay"

            print(f"  [衰减] {entry['id']} confidence: {old_conf:.2f} → {entry['confidence']:.2f}")

    if changed:
        update_kb_all(kb, root)


# ── 冷启动迁移 ─────────────────────────────────────────────
def migrate_from_instinct(root: Optional[Path] = None):
    """
    从 instinct-record.json 迁移数据到 knowledge_base.jsonl。
    只迁移活跃的（source != seed）记录。
    """
    if root:
        instinct_file = root / "harness" / "instinct" / "instinct-record.json"
    else:
        instinct_file = INSTINCT_PATH

    instinct_data = read_json(instinct_file)
    if not instinct_data:
        return 0

    existing_kb = load_knowledge_base(root)
    existing_ids = {e.get("id") for e in existing_kb}

    records = instinct_data.get("records", [])
    migrated = 0

    for rec in records:
        # 跳过 seed 记录和已存在的
        if rec.get("source") == "seed":
            continue
        if rec.get("id") in existing_ids:
            continue

        kb_entry = {
            "id": rec.get("id", f"mig-{uuid.uuid4().hex[:8]}"),
            "created_at": rec.get("created", rec.get("created_at", now_iso())),
            "updated_at": now_iso(),
            "status": "unconfirmed",
            "error_type": rec.get("pattern", rec.get("trigger", "unknown")),
            "error_type_detail": rec.get("context", ""),
            "root_cause": rec.get("root_cause", ""),
            "solution": rec.get("correction", ""),
            "specific_examples": [rec.get("pattern", "")],
            "generalized_from": [],
            "superseded_by": None,
            "confidence": rec.get("confidence", 0.5),
            "validation_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "source": "instinct_migration",
            "dimension": "instinct",
            "target_file": rec.get("target_file"),
            "linked_instinct_id": rec.get("id"),
        }

        save_kb_entry(kb_entry, root)
        migrated += 1

    if migrated > 0:
        print(f"  [迁移] 从 instinct-record 迁移了 {migrated} 条记录到 knowledge_base")

    return migrated


# ── 辅助工具 ───────────────────────────────────────────────
def generate_kb_id() -> str:
    """生成知识库 ID"""
    return f"kb-{uuid.uuid4().hex[:8]}"


def create_new_knowledge(
    error: dict,
    analysis: dict,
    reasoning_chain: list[str] | None = None,
    root_cause_category: str = "unknown",
    abstraction_level: int = 3,
    solution: dict | None = None,
    root: Optional[Path] = None,
) -> dict:
    """创建新知识条目"""
    return {
        "id": generate_kb_id(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "unconfirmed",
        "error_type": analysis.get("error_type", "unknown"),
        "error_type_detail": analysis.get("error_type_detail", ""),
        "root_cause": analysis.get("root_cause", ""),
        "solution": analysis.get("solution", ""),
        "specific_examples": [error.get("error", "")],
        "generalized_from": [],
        "superseded_by": None,
        "confidence": 0.5,  # 新知识从 0.5 开始
        "validation_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "source": "llm",
        "dimension": analysis.get("dimension", "instinct"),
        "target_file": analysis.get("target_file"),
        "root_cause_category": root_cause_category,
        "abstraction_level": abstraction_level,
        "reasoning_chain": reasoning_chain or [],
        "solution_details": solution or {},
    }


def get_kb_stats(root: Optional[Path] = None) -> dict:
    """获取知识库统计"""
    kb = load_knowledge_base(root)
    active = [e for e in kb if e.get("status") == "active"]
    unconfirmed = [e for e in kb if e.get("status") == "unconfirmed"]
    deprecated = [e for e in kb if e.get("status") in ("deprecated", "rollback_pending")]
    superseded = [e for e in kb if e.get("superseded_by")]

    return {
        "total": len(kb),
        "active": len(active),
        "unconfirmed": len(unconfirmed),
        "deprecated": len(deprecated),
        "superseded": len(superseded),
        "avg_confidence": round(sum(e.get("confidence", 0) for e in kb) / max(len(kb), 1), 3),
    }


def print_kb_stats(root: Optional[Path] = None):
    """打印知识库统计"""
    stats = get_kb_stats(root)
    print(f"""
╔══════════════════════════════════════╗
║         知识库统计                    ║
╠══════════════════════════════════════╣
║  总计:       {stats['total']:>4}                       ║
║  active:    {stats['active']:>4}                       ║
║  unconfirmed: {stats['unconfirmed']:>3}                       ║
║  deprecated: {stats['deprecated']:>4}                       ║
║  superseded: {stats['superseded']:>4}                       ║
║  平均置信度: {stats['avg_confidence']:.3f}                    ║
╚══════════════════════════════════════╝
""")


# ── CLI ───────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="知识库共享工具")
    parser.add_argument("action", choices=[
        "stats", "migrate", "decay", "cooldown_clear"
    ])
    args = parser.parse_args()

    if args.action == "stats":
        print_kb_stats()

    elif args.action == "migrate":
        migrated = migrate_from_instinct()
        print(f"迁移完成: {migrated} 条")

    elif args.action == "decay":
        decay_knowledge()

    elif args.action == "cooldown_clear":
        clear_expired_cooldown()
        print("冷却期记录已清理")
