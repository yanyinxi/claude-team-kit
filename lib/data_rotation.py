#!/usr/bin/env python3
"""
数据轮转清理 — JSONL 归档压缩 + 过期备份清理

原则:
  - 最近 7 天原始记录保留
  - 更早的压缩为统计摘要（100:1 压缩比）
  - 备份保留 30 天
  - 总数据 < 2MB 安全阈值

用法:
  python3 .claude/lib/data_rotation.py cleanup       # 常规清理（每日 cron）
  python3 .claude/lib/data_rotation.py status         # 查看数据状态
  python3 .claude/lib/data_rotation.py force-compact  # 强制压缩所有数据
"""
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _find_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _safe_read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def get_data_status(project_root: str = None) -> dict:
    """获取数据目录状态"""
    root = _find_root() if project_root is None else Path(project_root)
    data_dir = root / ".claude" / "data"

    if not data_dir.exists():
        return {"status": "empty", "total_size_kb": 0, "total_lines": 0, "files": []}

    files_info = []
    total_size = 0
    total_lines = 0

    for f in sorted(data_dir.glob("*")):
        if f.is_file() and not f.name.startswith("."):
            size_kb = f.stat().st_size / 1024
            lines = sum(1 for _ in open(f, encoding="utf-8") if _.strip()) if f.suffix in (".jsonl", ".json") else 0
            total_size += size_kb
            total_lines += lines
            files_info.append({
                "name": f.name,
                "size_kb": round(size_kb, 2),
                "lines": lines,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })

    backup_dir = root / ".claude" / "data" / "backups"
    backup_count = len(list(backup_dir.glob("*.bak"))) if backup_dir.exists() else 0

    return {
        "status": "healthy" if total_size < 2048 else "warning",
        "total_size_kb": round(total_size, 2),
        "total_size_limit_kb": 2048,
        "total_lines": total_lines,
        "backup_count": backup_count,
        "files": files_info,
    }


def cleanup_old_data(project_root: str = None, keep_days: int = 7):
    """压缩旧数据：保留最近 N 天原始记录，更早的只保留统计摘要"""
    root = _find_root() if project_root is None else Path(project_root)
    data_dir = root / ".claude" / "data"

    if not data_dir.exists():
        return {"message": "数据目录不存在，无需清理"}

    cutoff = datetime.now() - timedelta(days=keep_days)
    compacted = []
    cleaned = []

    for jsonl_file in sorted(data_dir.glob("*.jsonl")):
        records = _safe_read_jsonl(jsonl_file)
        if len(records) <= 100:  # 小文件跳过
            continue

        recent, old = [], []
        for r in records:
            ts_str = r.get("timestamp", "2000-01-01")
            try:
                ts = datetime.fromisoformat(ts_str[:19])
            except (ValueError, TypeError):
                ts = datetime(2000, 1, 1)
            if ts > cutoff:
                recent.append(r)
            else:
                old.append(r)

        if old:
            # 生成摘要
            summary = {
                "compacted_at": datetime.now().isoformat(),
                "original_count": len(old),
                "date_range": [
                    min((r.get("timestamp", "?") for r in old), default="?"),
                    max((r.get("timestamp", "?") for r in old), default="?"),
                ],
                "stats": _basic_stats(old),
            }
            summary_file = data_dir / f"{jsonl_file.stem}_archive_summary.json"
            # 合并已有摘要
            existing = {}
            if summary_file.exists():
                try:
                    existing = json.loads(summary_file.read_text())
                except json.JSONDecodeError:
                    pass
            existing.update(summary)
            summary_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

            # 重写文件只保留最近的记录
            tmp = jsonl_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for r in recent:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(str(tmp), str(jsonl_file))

            compacted.append({
                "file": jsonl_file.name,
                "removed": len(old),
                "kept": len(recent),
                "ratio": f"{len(old) + len(recent)}:{len(recent)}" if recent else "all_compacted",
            })

    # 清理过期备份 (>30 天)
    backup_dir = data_dir / "backups"
    if backup_dir.exists():
        cutoff_backup = datetime.now() - timedelta(days=30)
        for bak in backup_dir.glob("*.bak"):
            mtime = datetime.fromtimestamp(bak.stat().st_mtime)
            if mtime < cutoff_backup:
                bak.unlink()
                cleaned.append(bak.name)

    return {
        "compacted_files": compacted,
        "cleaned_backups": cleaned,
        "message": f"压缩了 {len(compacted)} 个文件，清理了 {len(cleaned)} 个过期备份",
    }


def force_compact_all(project_root: str = None):
    """强制压缩所有数据（无论新旧）"""
    return cleanup_old_data(project_root, keep_days=0)


def _basic_stats(records: list) -> dict:
    return {
        "count": len(records),
        "types": _count_by(records, "type"),
    }


def _count_by(records: list, key: str) -> dict:
    result = {}
    for r in records:
        v = r.get(key, "unknown")
        result[v] = result.get(v, 0) + 1
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="数据轮转清理工具")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="查看数据状态")
    sub.add_parser("cleanup", help="常规清理（保留7天原始数据）")
    sub.add_parser("force-compact", help="强制压缩所有数据")

    args = parser.parse_args()

    if args.cmd == "status":
        status = get_data_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif args.cmd == "cleanup":
        result = cleanup_old_data()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == "force-compact":
        result = force_compact_all()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
