#!/usr/bin/env python3
"""
自动应用模块 — 根据 LLM 决策自动应用改动。

工作流程:
1. 读取 decision
2. 备份原文件
3. 应用改动
4. 记录提案历史
5. 进入观察期
"""
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


def find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


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
    return {
        "paths": {
            "data_dir": ".claude/data",
            "proposals_dir": ".claude/proposals",
            "skills_dir": "skills",
            "agents_dir": "agents",
            "rules_dir": "rules",
            "instinct_dir": "instinct",
            "backups_dir": ".claude/data/backups",
        },
        "observation": {
            "days": 7,
        },
        "safety": {
            "breaker": {"max_consecutive_rejects": 3, "pause_days": 30},
        },
    }


def backup_file(file_path: Path, backups_dir: Path, decision_id: str) -> Optional[Path]:
    """备份原文件到 backups_dir"""
    if not file_path.exists():
        return None

    backups_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backups_dir / f"{decision_id}_{file_path.name}"

    try:
        backup_path.write_bytes(file_path.read_bytes())
        return backup_path
    except OSError:
        return None


def restore_file(backup_path: Path, original_path: Path) -> bool:
    """从备份恢复文件"""
    if not backup_path.exists():
        return False

    try:
        original_path.write_bytes(backup_path.read_bytes())
        return True
    except OSError:
        return False


def apply_text_change(content: str, change: str) -> str:
    """
    应用文本改动。

    change 可以是：
    1. 精确替换: "old_text -> new_text"
    2. 行追加: "append: content"
    3. 行删除: "delete: pattern"
    4. 正则替换: "regex: pattern -> replacement"
    """
    change = change.strip()

    # 精确替换
    if " -> " in change and not change.startswith("append") and not change.startswith("delete") and not change.startswith("regex"):
        old, new = change.split(" -> ", 1)
        old = old.strip()
        new = new.strip()
        if old in content:
            return content.replace(old, new, 1)

    # 行追加
    if change.startswith("append:"):
        new_content = change[7:].strip()
        return content + "\n" + new_content

    # 行删除
    if change.startswith("delete:"):
        pattern = change[7:].strip()
        lines = content.split("\n")
        lines = [l for l in lines if pattern not in l]
        return "\n".join(lines)

    # 正则替换
    if change.startswith("regex:"):
        match = re.match(r"(.+?) -> (.+)", change[6:].lstrip())
        if match:
            pattern, replacement = match.groups()
            try:
                return re.sub(pattern, replacement, content)
            except re.error:
                pass

    # 兜底：如果 change 本身就是要写入的内容
    return change


def apply_change(decision: dict, root: Optional[Path] = None) -> bool:
    """
    根据 decision 自动应用改动。

    返回: True 成功，False 失败
    """
    if root is None:
        root = find_root()

    if decision.get("action") != "auto_apply":
        return False

    target_file = decision.get("target_file")
    suggested_change = decision.get("suggested_change")

    if not target_file or not suggested_change:
        return False

    # 解析文件路径
    file_path = root / target_file
    if not file_path.exists():
        print(f"Target file not found: {file_path}")
        return False

    config = load_config()
    backups_dir = root / config.get("paths", {}).get("backups_dir", ".claude/data/backups")

    # 备份
    decision_id = decision.get("id", f"auto-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    backup_path = backup_file(file_path, backups_dir, decision_id)

    # 读取当前内容
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Failed to read {file_path}: {e}")
        return False

    # 应用改动
    new_content = apply_text_change(content, suggested_change)

    # 写入
    try:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"Applied change to {target_file}")
    except OSError as e:
        # 写入失败，恢复备份
        if backup_path:
            restore_file(backup_path, file_path)
        print(f"Failed to write {file_path}: {e}")
        return False

    # 记录提案历史
    record_proposal(decision, root, backup_path)

    # 更新 instinct
    _update_instinct(decision, root)

    return True


def record_proposal(decision: dict, root: Path, backup_path: Optional[Path] = None):
    """记录提案历史到 proposal_history.json"""
    history_file = root / ".claude" / "data" / "proposal_history.json"

    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text())
        except (json.JSONDecodeError, OSError):
            history = []

    config = load_config()
    observation_days = config.get("observation", {}).get("days", 7)

    entry = {
        "id": decision.get("id", ""),
        "action": decision.get("action", ""),
        "reason": decision.get("reason", ""),
        "target_file": decision.get("target_file"),
        "suggested_change": decision.get("suggested_change"),
        "risk_level": decision.get("risk_level", "medium"),
        "confidence": decision.get("confidence", 0),
        "status": "applied",
        "applied_at": datetime.now().isoformat(),
        "observation_end": (datetime.now() + __import__("datetime").timedelta(days=observation_days)).isoformat(),
        "backup_path": str(backup_path) if backup_path else None,
        "baseline_metrics": _collect_baseline_metrics(root),
        "dimension": decision.get("dimension", "agent"),
        "linked_instinct_id": decision.get("linked_instinct_id"),
    }

    history.append(entry)

    # 保留最近 100 条
    history = history[-100:]

    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def _collect_baseline_metrics(root: Path) -> dict:
    """收集基线指标（用于后续验证对比）"""
    sessions_file = root / ".claude" / "data" / "sessions.jsonl"

    if not sessions_file.exists():
        return {}

    sessions = []
    for line in sessions_file.read_text().splitlines():
        if line.strip():
            try:
                sessions.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not sessions:
        return {}

    recent = sessions[-20:]  # 最近 20 个会话作为基线

    total = len(recent)
    total_failures = sum(s.get("tool_failures", 0) for s in recent)
    total_corrections = sum(len(s.get("corrections", [])) for s in recent)
    success_count = sum(1 for s in recent if s.get("tool_failures", 0) == 0)

    return {
        "success_rate": round(success_count / max(total, 1), 2),
        "failure_rate": round(total_failures / max(total, 1), 2),
        "correction_rate": round(total_corrections / max(total, 1), 2),
        "sample_size": total,
    }


def _update_instinct(decision: dict, root: Path):
    """更新 instinct 记录"""
    try:
        from instinct_updater import add_pattern, increment_applied_count

        target = decision.get("target_file", "")
        pattern = f"auto-applied: {target}"
        correction = decision.get("suggested_change", "")[:200]
        reason = decision.get("reason", "")

        record_id = add_pattern(
            pattern=pattern,
            correction=correction,
            root_cause=reason,
            confidence=decision.get("confidence", 0.5),
            source="auto-applied",
        )

        increment_applied_count(record_id, root)

    except Exception as e:
        print(f"Failed to update instinct: {e}")


def rollback_proposal(proposal_id: str, root: Optional[Path] = None, reason: str = "") -> bool:
    """
    回滚指定提案。

    返回: True 成功，False 失败
    """
    if root is None:
        root = find_root()

    history_file = root / ".claude" / "data" / "proposal_history.json"

    if not history_file.exists():
        return False

    try:
        history = json.loads(history_file.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    # 找到提案
    proposal = None
    for p in history:
        if p.get("id") == proposal_id:
            proposal = p
            break

    if not proposal:
        return False

    # 恢复备份
    backup_path_str = proposal.get("backup_path")
    target_file = proposal.get("target_file")

    if backup_path_str and target_file:
        backup_path = Path(backup_path_str)
        file_path = root / target_file

        if restore_file(backup_path, file_path):
            # 更新状态
            proposal["status"] = "rolled_back"
            proposal["rolled_back_at"] = datetime.now().isoformat()
            proposal["rollback_reason"] = reason

            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2))

            # 更新 instinct
            try:
                from instinct_updater import demote_confidence
                # 找到对应的 instinct 记录并降低置信度
            except Exception:
                pass

            print(f"Rolled back {proposal_id}: {reason}")
            return True

    return False


def consolidate_proposal(proposal_id: str, root: Optional[Path] = None):
    """固化提案（观察期通过）"""
    if root is None:
        root = find_root()

    history_file = root / ".claude" / "data" / "proposal_history.json"

    if not history_file.exists():
        return

    try:
        history = json.loads(history_file.read_text())
    except (json.JSONDecodeError, OSError):
        return

    for p in history:
        if p.get("id") == proposal_id:
            p["status"] = "consolidated"
            p["consolidated_at"] = datetime.now().isoformat()
            break

    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def get_proposal_status(proposal_id: str, root: Optional[Path] = None) -> Optional[dict]:
    """获取提案状态"""
    if root is None:
        root = find_root()

    history_file = root / ".claude" / "data" / "proposal_history.json"

    if not history_file.exists():
        return None

    try:
        history = json.loads(history_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    for p in history:
        if p.get("id") == proposal_id:
            return p

    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="自动应用模块")
    parser.add_argument("action", choices=["apply", "rollback", "status", "list"])
    parser.add_argument("--id", help="提案 ID")
    parser.add_argument("--target", help="目标文件")
    parser.add_argument("--change", help="改动内容")
    parser.add_argument("--reason", help="回滚原因")

    args = parser.parse_args()

    root = find_root()

    if args.action == "apply":
        decision = {
            "action": "auto_apply",
            "id": f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "target_file": args.target,
            "suggested_change": args.change,
            "confidence": 0.8,
            "risk_level": "low",
        }
        result = apply_change(decision, root)
        print(f"Apply result: {result}")

    elif args.action == "rollback":
        if not args.id:
            print("Error: --id required for rollback")
            sys.exit(1)
        result = rollback_proposal(args.id, root, args.reason or "Manual rollback")
        print(f"Rollback result: {result}")

    elif args.action == "status":
        if not args.id:
            print("Error: --id required for status")
            sys.exit(1)
        status = get_proposal_status(args.id, root)
        print(json.dumps(status, indent=2))

    elif args.action == "list":
        history_file = root / ".claude" / "data" / "proposal_history.json"
        if history_file.exists():
            history = json.loads(history_file.read_text())
            for p in history[-10:]:
                print(f"{p['id']} | {p['status']} | {p.get('target_file', 'unknown')}")