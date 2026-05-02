#!/usr/bin/env python3
"""
Instinct 自动更新器 — 管理本能记录的完整生命周期。

核心功能:
1. 添加新 pattern
2. 置信度动态调整（时间衰减 + 验证增强）
3. 模式优先级管理

时间衰减算法:
  - 90 天半衰期
  - 多次验证的记录半衰期延长
  - 置信度不低于 0.1
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def load_config():
    """加载配置"""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        return _default_config()
    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    except ImportError:
        return _default_config()


def _default_config():
    """默认配置（当 yaml 不可用时）"""
    return {
        "decay": {
            "half_life_days": 90,
            "decay_floor": 0.1,
            "min_reinforcement": 3,
            "reinforcement_bonus": 0.05,
            "max_confidence": 0.95,
        }
    }


def find_root():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def load_instinct(root: Optional[Path] = None) -> dict:
    """加载或初始化 instinct-record.json"""
    if root is None:
        root = find_root()
    path = root / "instinct" / "instinct-record.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"description": "Instinct System", "version": 1, "records": []}


def save_instinct(instinct: dict, root: Optional[Path] = None):
    """保存 instinct-record.json"""
    if root is None:
        root = find_root()
    path = root / "instinct" / "instinct-record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(instinct, ensure_ascii=False, indent=2), encoding="utf-8")


def time_decay_weight(
    created_at: str,
    last_reinforced: Optional[str],
    half_life_days: int = 90
) -> float:
    """
    计算时间衰减权重。

    公式: weight = 0.5 ^ (age_days / half_life_days)

    例如: 90 天后权重为 0.5, 180 天后权重为 0.25
    """
    if not created_at:
        return 1.0

    try:
        reference_time = last_reinforced if last_reinforced else created_at
        ref_dt = datetime.fromisoformat(reference_time)
    except (ValueError, TypeError):
        return 1.0

    age_seconds = (datetime.now() - ref_dt).total_seconds()
    age_days = age_seconds / 86400
    return 0.5 ** (age_days / half_life_days)


def apply_decay_to_all(instinct: dict, config: Optional[dict] = None) -> dict:
    """
    对所有非 seed 记录应用时间衰减。

    规则:
    - seed 记录不衰减
    - reinforcement_count >= 3 的记录半衰期延长 50%
    - reinforcement_count >= 5 的记录半衰期延长 100%
    - 衰减后置信度不低于 decay_floor
    """
    if config is None:
        config = _default_config()

    decay_config = config.get("decay", {})
    half_life_days = decay_config.get("half_life_days", 90)
    decay_floor = decay_config.get("decay_floor", 0.1)

    if "records" not in instinct:
        instinct["records"] = []

    for i, record in enumerate(instinct["records"]):
        # seed 记录不衰减
        if record.get("source") == "seed":
            continue

        # 计算半衰期调整
        reinforcement_count = record.get("reinforcement_count", 0)
        effective_half_life = half_life_days
        if reinforcement_count >= 5:
            effective_half_life = int(half_life_days * 2)
        elif reinforcement_count >= 3:
            effective_half_life = int(half_life_days * 1.5)

        # 计算衰减权重
        weight = time_decay_weight(
            record.get("created_at", ""),
            record.get("last_reinforced_at"),
            effective_half_life
        )

        # 应用衰减，但不低于 floor
        current_confidence = record.get("confidence", 0.3)
        new_confidence = max(decay_floor, current_confidence * weight)

        instinct["records"][i]["confidence"] = round(new_confidence, 3)
        instinct["records"][i]["decay_status"] = "decaying" if weight < 0.8 else "active"
        instinct["records"][i]["updated_at"] = datetime.now().isoformat()
        instinct["records"][i]["decay_weight"] = round(weight, 4)

    # 清理已衰减到 floor 且超过 180 天的记录
    instinct["records"] = [
        r for r in instinct["records"]
        if not (
            r.get("confidence", 1) > decay_floor
            and r.get("decay_status") == "decaying"
            and (datetime.now() - datetime.fromisoformat(
                r.get("last_reinforced_at", r.get("created_at", "2000-01-01"))
            )).days > 180
        )
    ]

    return instinct


def add_pattern(
    pattern: str,
    correction: str,
    root_cause: str = "",
    confidence: float = 0.3,
    source: str = "auto-detected",
    context: str = "",
    root: Optional[Path] = None
) -> str:
    """
    向 instinct-record.json 添加一条记录，返回记录 ID。
    """
    if root is None:
        root = find_root()

    instinct = load_instinct(root)

    import uuid
    record_id = f"auto-{uuid.uuid4().hex[:8]}"
    record = {
        "id": record_id,
        "pattern": pattern,
        "context": context,
        "correction": correction,
        "root_cause": root_cause,
        "confidence": confidence,
        "applied_count": 0,
        "reinforcement_count": 0,
        "source": source,
        "created_at": datetime.now().isoformat(),
        "last_reinforced_at": None,
        "decay_status": "active",
        "decay_weight": 1.0,
        "updated_at": datetime.now().isoformat(),
    }

    instinct.setdefault("records", []).append(record)
    save_instinct(instinct, root)
    return record_id


def promote_confidence(record_id: str, delta: float = 0.1, root: Optional[Path] = None):
    """
    增加已有记录的置信度（用于观察期后的升级）。
    同时增加 reinforcement_count 和 last_reinforced_at。
    """
    if root is None:
        root = find_root()

    instinct = load_instinct(root)
    config = load_config()
    max_conf = config.get("decay", {}).get("max_confidence", 0.95)

    for rec in instinct.get("records", []):
        if rec.get("id") == record_id:
            old_conf = rec.get("confidence", 0.3)
            new_conf = min(max_conf, old_conf + delta)
            rec["confidence"] = round(new_conf, 3)
            rec["reinforcement_count"] = rec.get("reinforcement_count", 0) + 1
            rec["last_reinforced_at"] = datetime.now().isoformat()
            rec["decay_status"] = "active"
            rec["updated_at"] = datetime.now().isoformat()
            save_instinct(instinct, root)
            return


def demote_confidence(record_id: str, delta: float = 0.1, root: Optional[Path] = None):
    """
    降低已有记录的置信度（用于回滚场景）。
    """
    if root is None:
        root = find_root()

    instinct = load_instinct(root)
    config = load_config()
    decay_floor = config.get("decay", {}).get("decay_floor", 0.1)

    for rec in instinct.get("records", []):
        if rec.get("id") == record_id:
            old_conf = rec.get("confidence", 0.3)
            new_conf = max(decay_floor, old_conf - delta)
            rec["confidence"] = round(new_conf, 3)
            rec["reinforcement_count"] = max(0, rec.get("reinforcement_count", 0) - 1)
            rec["updated_at"] = datetime.now().isoformat()
            save_instinct(instinct, root)
            return


def reinforce_pattern(pattern_id: str, delta: float = 0.1, root: Optional[Path] = None):
    """
    验证成功后增强置信度（alias for promote_confidence）。
    """
    promote_confidence(pattern_id, delta, root)


def get_patterns_by_source(source: str, root: Optional[Path] = None) -> list:
    """获取指定来源的所有 pattern"""
    if root is None:
        root = find_root()

    instinct = load_instinct(root)
    return [r for r in instinct.get("records", []) if r.get("source") == source]


def get_high_confidence_patterns(threshold: float = 0.7, root: Optional[Path] = None) -> list:
    """获取高置信度的 pattern（用于指导决策）"""
    if root is None:
        root = find_root()

    instinct = load_instinct(root)
    return [
        r for r in instinct.get("records", [])
        if r.get("confidence", 0) >= threshold and r.get("decay_status") != "decaying"
    ]


def increment_applied_count(record_id: str, root: Optional[Path] = None):
    """增加 applied_count 计数"""
    if root is None:
        root = find_root()

    instinct = load_instinct(root)
    for rec in instinct.get("records", []):
        if rec.get("id") == record_id:
            rec["applied_count"] = rec.get("applied_count", 0) + 1
            rec["updated_at"] = datetime.now().isoformat()
            save_instinct(instinct, root)
            return


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Instinct 自动更新器")
    parser.add_argument("action", choices=["add", "promote", "demote", "decay", "list", "stats"])
    parser.add_argument("--pattern", help="Pattern 描述")
    parser.add_argument("--correction", help="纠正措施")
    parser.add_argument("--root-cause", help="根本原因")
    parser.add_argument("--confidence", type=float, default=0.3)
    parser.add_argument("--id", help="记录 ID")
    parser.add_argument("--delta", type=float, default=0.1)

    args = parser.parse_args()

    if args.action == "add":
        if not args.pattern or not args.correction:
            print("Error: --pattern and --correction required for add")
            sys.exit(1)
        record_id = add_pattern(args.pattern, args.correction, args.root_cause or "", args.confidence)
        print(f"Added pattern: {record_id}")

    elif args.action == "promote":
        if not args.id:
            print("Error: --id required for promote")
            sys.exit(1)
        promote_confidence(args.id, args.delta)
        print(f"Promoted: {args.id}")

    elif args.action == "demote":
        if not args.id:
            print("Error: --id required for demote")
            sys.exit(1)
        demote_confidence(args.id, args.delta)
        print(f"Demoted: {args.id}")

    elif args.action == "decay":
        instinct = load_instinct()
        instinct = apply_decay_to_all(instinct)
        save_instinct(instinct)
        print("Applied decay to all records")

    elif args.action == "list":
        instinct = load_instinct()
        for rec in instinct.get("records", []):
            print(f"{rec['id']} | {rec['source']} | conf={rec['confidence']:.2f} | {rec['pattern'][:50]}")

    elif args.action == "stats":
        instinct = load_instinct()
        records = instinct.get("records", [])
        total = len(records)
        high_conf = sum(1 for r in records if r.get("confidence", 0) >= 0.7)
        active = sum(1 for r in records if r.get("decay_status") != "decaying")
        print(f"Total: {total}, High confidence: {high_conf}, Active: {active}")