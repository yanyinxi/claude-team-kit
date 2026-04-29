#!/usr/bin/env python3
"""
进化安全模块 — 熔断器 + 限流器 + 快照回滚 + 数据校验

原则: 进化前检查，进化后记录，异常时自动熔断。
"""

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple


# ═══════════════════════════════════════════════════════════════
# 文件快照与回滚
# ═══════════════════════════════════════════════════════════════

def snapshot_file(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def backup_file(file_path: str, backup_dir: str = ".claude/data/backups") -> str:
    src = Path(file_path)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = Path(backup_dir) / f"{src.name}.{ts}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, backup)
    return str(backup)


def rollback_file(file_path: str, backup_path: str) -> bool:
    try:
        shutil.copy2(backup_path, file_path)
        return True
    except OSError:
        return False


# ═══════════════════════════════════════════════════════════════
# 进化熔断器
# ═══════════════════════════════════════════════════════════════

class EvolutionCircuitBreaker:
    """
    连续 2 次退化 → 熔断，阻止该目标继续进化。
    状态持久化到 evolution_metrics.json。
    """

    def __init__(self, metrics_path: str = ".claude/data/evolution_metrics.json"):
        self.metrics_path = Path(metrics_path)
        self.max_consecutive_degradations = 2

    def is_open(self, dimension: str, target: str) -> bool:
        metrics = self._read_metrics()
        breaker = metrics.get("circuit_breaker", {}).get(dimension, {}).get(target)
        if not breaker:
            return False
        return breaker.get("consecutive_degradations", 0) >= self.max_consecutive_degradations

    def record_result(self, dimension: str, target: str, improved: bool):
        metrics = self._read_metrics()
        metrics.setdefault("circuit_breaker", {}).setdefault(dimension, {}).setdefault(target, {})
        breaker = metrics["circuit_breaker"][dimension][target]

        if improved:
            breaker["consecutive_degradations"] = 0
            breaker["status"] = "CLOSED"
        else:
            breaker["consecutive_degradations"] = breaker.get("consecutive_degradations", 0) + 1
            breaker["last_degradation"] = datetime.now().isoformat()

        if breaker["consecutive_degradations"] >= self.max_consecutive_degradations:
            breaker["status"] = "OPEN"
            breaker["opened_at"] = datetime.now().isoformat()
            breaker["action_required"] = "人工检查并重置熔断器"

        self._write_metrics(metrics)

    def reset(self, dimension: str, target: str):
        metrics = self._read_metrics()
        cb = metrics.get("circuit_breaker", {})
        dim = cb.get(dimension, {})
        if target in dim:
            del dim[target]
            self._write_metrics(metrics)
            return True
        return False

    def reset_all(self):
        metrics = self._read_metrics()
        if "circuit_breaker" in metrics:
            del metrics["circuit_breaker"]
            self._write_metrics(metrics)
            return True
        return False

    def get_status(self) -> dict:
        metrics = self._read_metrics()
        return metrics.get("circuit_breaker", {})

    def _read_metrics(self) -> dict:
        if self.metrics_path.exists():
            try:
                return json.loads(self.metrics_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_metrics(self, data: dict):
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.metrics_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(str(tmp), str(self.metrics_path))


# ═══════════════════════════════════════════════════════════════
# 进化限流器
# ═══════════════════════════════════════════════════════════════

class EvolutionRateLimiter:
    """
    Skill/Agent: 24h 冷却 | Rule: 48h | Memory: 无冷却
    每会话全局上限: 3 次
    """

    COOLDOWNS = {
        "skill": timedelta(hours=24),
        "agent": timedelta(hours=24),
        "rule": timedelta(hours=48),
        "memory": timedelta(hours=0),
    }
    MAX_PER_SESSION = 3

    def __init__(self, history_path: str = ".claude/data/evolution_history.jsonl"):
        self.history_path = Path(history_path)

    def can_evolve(self, dimension: str, target: str, session_id: str) -> Tuple[bool, str]:
        history = self._read_history()

        # 检查 1: 会话上限
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        session_count = sum(
            1 for h in history
            if h.get("session_id") == session_id
            and h.get("timestamp", "").startswith(today_prefix)
        )
        if session_count >= self.MAX_PER_SESSION:
            return False, f"本次会话已达进化上限 ({self.MAX_PER_SESSION}次)"

        # 检查 2: 冷却期
        cooldown = self.COOLDOWNS.get(dimension, timedelta(hours=24))
        if cooldown.total_seconds() > 0:
            for h in reversed(history):
                if h.get("dimension") == dimension and h.get("target") == target:
                    try:
                        last_time = datetime.fromisoformat(h["timestamp"])
                        # 统一为 UTC aware datetime
                        from datetime import timezone as _tz
                        if last_time.tzinfo is None:
                            last_time = last_time.replace(tzinfo=_tz.utc)
                        now = datetime.now(_tz.utc)
                        elapsed = now - last_time
                        if elapsed < cooldown:
                            remaining = cooldown - elapsed
                            hours = remaining.total_seconds() / 3600
                            return False, "冷却中，还需 {:.1f} 小时".format(hours)
                    except (ValueError, KeyError):
                        continue

        return True, "OK"

    def _read_history(self) -> list:
        if not self.history_path.exists():
            return []
        records = []
        with open(self.history_path, encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records


# ═══════════════════════════════════════════════════════════════
# 数据校验
# ═══════════════════════════════════════════════════════════════

RECORD_SCHEMAS = {
    "agent_launch": ["type", "timestamp", "session_id", "agent", "task"],
    "skill_invoked": ["type", "timestamp", "session_id", "skill"],
    "tool_failure": ["type", "timestamp", "session_id", "tool", "error_summary"],
    "rule_violation": ["type", "timestamp", "session_id", "rule", "file", "severity"],
    "session_end": ["type", "timestamp", "session_id"],
    "daily_score": ["date", "overall"],
}


def validate_record_schema(record: dict, schema_name: str) -> Tuple[bool, str]:
    """
    验证记录是否符合已知 schema。
    无 type 字段的记录（如 daily_score）跳过 schema 校验，视为有效。
    """
    rec_type = record.get("type", "")
    if not rec_type:
        # 无 type 字段的记录（如 daily_score）不做 schema 校验
        return True, "OK (无 type)"
    schema = RECORD_SCHEMAS.get(rec_type)
    if not schema:
        return False, f"未知记录类型: {rec_type}"
    for field in schema:
        if field not in record:
            return False, f"缺少必需字段: {field}"
    return True, "OK"


def validate_jsonl_file(file_path: str) -> dict:
    """验证 JSONL 文件完整性，返回 {total, corrupted, corrupted_lines}"""
    p = Path(file_path)
    if not p.exists():
        return {"total": 0, "corrupted": 0, "corrupted_lines": []}

    total, corrupted, corrupted_lines = 0, 0, []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                record = json.loads(line)
                ok, _ = validate_record_schema(record, record.get("type", ""))
                if not ok:
                    corrupted += 1
                    corrupted_lines.append(i)
            except json.JSONDecodeError:
                corrupted += 1
                corrupted_lines.append(i)

    return {"total": total, "corrupted": corrupted, "corrupted_lines": corrupted_lines}


# ═══════════════════════════════════════════════════════════════
# 敏感信息过滤
# ═══════════════════════════════════════════════════════════════

_SENSITIVE_PATTERNS = [
    (re.compile(r'(?:api[_-]?key|apikey|api_secret|secret_key|password|token|auth)\s*[:=]\s*[\S]+', re.I),
     lambda m: m.group(0).split('=')[0].split(':')[0] + '=***REDACTED***'),
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), lambda m: 'sk-***REDACTED***'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), lambda m: 'ghp_***REDACTED***'),
    (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----.*?-----END', re.DOTALL),
     lambda m: '***REDACTED PRIVATE KEY***'),
]


def sanitize_prompt(text: str, max_length: int = 200) -> str:
    for pattern, replacer in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacer, text)
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text


# ═══════════════════════════════════════════════════════════════
# 进化前安全检查
# ═══════════════════════════════════════════════════════════════

def check_data_sufficiency(dimension: str, data_dir: str = ".claude/data") -> dict:
    """检查该维度的数据是否充足"""
    dp = Path(data_dir)
    file_map = {
        "skill": "skill_usage.jsonl",
        "agent": "agent_performance.jsonl",
        "rule": "rule_violations.jsonl",
        "memory": "pending_evolution.json",
    }
    f = dp / file_map.get(dimension, file_map.get("skill", ""))
    if not f.exists():
        return {"sufficient": False, "record_count": 0}

    count = sum(1 for _ in open(f, encoding="utf-8") if _.strip())
    return {"sufficient": count >= 1, "record_count": count}


def check_target_exists(dimension: str, target: str, project_root: str = ".") -> bool:
    root = Path(project_root) / ".claude"
    paths = {
        "skill": root / "skills" / f"{target}" / "SKILL.md",
        "agent": root / "agents" / f"{target}.md",
        "rule": root / "rules" / f"{target}.md",
        "memory": root / "memory" / f"{target}.md",
    }
    return paths.get(dimension, Path()).exists()


def pre_evolution_check(dimension: str, target: str, session_id: str,
                        project_root: str = ".") -> dict:
    breaker = EvolutionCircuitBreaker(Path(project_root) / ".claude/data/evolution_metrics.json")
    limiter = EvolutionRateLimiter(Path(project_root) / ".claude/data/evolution_history.jsonl")

    can_evolve, reason = limiter.can_evolve(dimension, target, session_id)
    data_suff = check_data_sufficiency(dimension, str(Path(project_root) / ".claude/data"))

    checks = {
        "熔断器未断开": not breaker.is_open(dimension, target),
        "冷却期已过": can_evolve,
        "数据充分": data_suff["sufficient"],
        "目标文件存在": check_target_exists(dimension, target, project_root),
    }

    all_pass = all(checks.values())
    blocked = [k for k, v in checks.items() if not v]

    if not can_evolve:
        blocked.append(f"限流原因: {reason}")

    return {
        "can_proceed": all_pass,
        "checks": checks,
        "blocked_by": blocked,
        "dimension": dimension,
        "target": target,
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def _find_project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def cli_status():
    """查看进化系统安全状态"""
    root = _find_project_root()
    breaker = EvolutionCircuitBreaker(str(root / ".claude/data/evolution_metrics.json"))
    limiter = EvolutionRateLimiter(str(root / ".claude/data/evolution_history.jsonl"))

    cb_status = breaker.get_status()
    history = limiter._read_history()

    print("=" * 60)
    print("进化系统安全状态")
    print("=" * 60)

    # 数据文件
    data_dir = root / ".claude" / "data"
    print(f"\n📁 数据文件:")
    for f in sorted(data_dir.glob("*.jsonl")):
        lines = sum(1 for _ in open(f) if _.strip())
        size_kb = f.stat().st_size / 1024
        print(f"   {f.name}: {lines} 行, {size_kb:.1f} KB")

    # 熔断器
    print(f"\n🔌 熔断器状态:")
    if cb_status:
        for dim, targets in cb_status.items():
            for target, state in targets.items():
                status = state.get("status", "CLOSED")
                icon = "🔴" if status == "OPEN" else "🟢"
                deg = state.get("consecutive_degradations", 0)
                print(f"   {icon} {dim}/{target}: {status} (连续退化: {deg})")
    else:
        print("   ✅ 无熔断，所有维度正常")

    # 进化历史
    print(f"\n📊 进化历史: {len(history)} 条记录")
    if history:
        by_dim = {}
        for h in history:
            dim = h.get("dimension", "unknown")
            by_dim[dim] = by_dim.get(dim, 0) + 1
        for dim, count in by_dim.items():
            print(f"   {dim}: {count} 次")


def cli_validate():
    """验证数据文件完整性"""
    root = _find_project_root()
    data_dir = root / ".claude" / "data"

    print("=" * 60)
    print("数据完整性校验")
    print("=" * 60)

    all_ok = True
    for f in sorted(data_dir.glob("*.jsonl")):
        result = validate_jsonl_file(str(f))
        status = "✅" if result["corrupted"] == 0 else "❌"
        print(f"   {status} {f.name}: {result['total']} 行, {result['corrupted']} 损坏")
        if result["corrupted"]:
            all_ok = False
            print(f"      损坏行: {result['corrupted_lines'][:10]}")

    if all_ok:
        print("\n✅ 所有数据文件完整")


def cli_rollback(target: str, timestamp: str = None):
    """回滚指定目标的进化"""
    root = _find_project_root()
    backup_dir = root / ".claude" / "data" / "backups"

    dimension, target_name = target.split(":", 1) if ":" in target else (None, target)

    # 查找备份
    backups = sorted(backup_dir.glob(f"{target_name}*.bak"), reverse=True)
    if timestamp:
        backups = [b for b in backups if timestamp in b.name]

    if not backups:
        print(f"❌ 未找到 {target} 的备份文件")
        return

    print(f"可用备份 ({len(backups)} 个):")
    for i, b in enumerate(backups[:10]):
        print(f"   [{i}] {b.name}")

    # 使用最新的备份恢复
    latest = backups[0]
    # 按维度推断目标文件路径
    path_map = {
        "skill": root / ".claude" / "skills" / target_name / "SKILL.md",
        "agent": root / ".claude" / "agents" / f"{target_name}.md",
        "rule": root / ".claude" / "rules" / f"{target_name}.md",
    }
    target_path = path_map.get(dimension, root / ".claude" / "rules" / f"{target_name}.md")

    if rollback_file(str(target_path), str(latest)):
        print(f"✅ 已回滚 {target_path} → {latest.name}")
    else:
        print(f"❌ 回滚失败")


def cli_reset_all(confirm: bool = False):
    """重置所有进化数据（保留 memory/ 文件）"""
    if not confirm:
        print("⚠️  此操作将删除所有进化数据（保留 memory/ 文件）")
        print("   请使用 --confirm 参数确认")
        return

    root = _find_project_root()
    data_dir = root / ".claude" / "data"

    preserved = []
    removed = []

    for f in data_dir.glob("*"):
        if f.name.startswith("backup"):
            continue
        if f.name.startswith("memory"):
            preserved.append(f.name)
            continue
        try:
            f.unlink()
            removed.append(f.name)
        except OSError:
            pass

    # 重置熔断器
    breaker = EvolutionCircuitBreaker(str(data_dir / "evolution_metrics.json"))
    breaker.reset_all()

    print(f"✅ 已删除: {removed}")
    print(f"✅ 已保留: {preserved}")
    print(f"✅ 熔断器已重置")


def cli_diff(target: str):
    """对比当前版本与最近备份的差异"""
    root = _find_project_root()
    dimension, target_name = target.split(":", 1) if ":" in target else (None, target)

    path_map = {
        "skill": root / ".claude" / "skills" / target_name / "SKILL.md",
        "agent": root / ".claude" / "agents" / f"{target_name}.md",
        "rule": root / ".claude" / "rules" / f"{target_name}.md",
    }
    target_path = path_map.get(dimension)
    if not target_path or not target_path.exists():
        print(f"❌ 目标文件不存在: {target_path}")
        return

    backup_dir = root / ".claude" / "data" / "backups"
    backups = sorted(backup_dir.glob(f"{target_name}*.bak"), reverse=True)

    if not backups:
        print(f"ℹ️  无备份可对比")
        return

    latest_backup = backups[0]
    print(f"对比: {target_path} vs {latest_backup.name}")
    print(f"当前 hash: {snapshot_file(str(target_path))}")
    print(f"备份 hash: {snapshot_file(str(latest_backup))}")


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="进化安全工具")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="查看安全状态")
    sub.add_parser("validate", help="验证数据完整性")

    rollback_p = sub.add_parser("rollback", help="回滚进化")
    rollback_p.add_argument("--target", required=True, help="目标，如 skill:karpathy-guidelines")
    rollback_p.add_argument("--timestamp", help="指定时间戳版本")

    diff_p = sub.add_parser("diff", help="对比差异")
    diff_p.add_argument("--target", required=True, help="目标")

    reset_p = sub.add_parser("reset-all", help="重置所有进化数据")
    reset_p.add_argument("--confirm", action="store_true")

    args = parser.parse_args()

    if args.cmd == "status":
        cli_status()
    elif args.cmd == "validate":
        cli_validate()
    elif args.cmd == "rollback":
        cli_rollback(args.target, getattr(args, "timestamp", None))
    elif args.cmd == "diff":
        cli_diff(args.target)
    elif args.cmd == "reset-all":
        cli_reset_all(confirm=args.confirm)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
