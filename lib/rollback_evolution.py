#!/usr/bin/env python3
"""
进化回滚工具 — 回滚指定目标的最近一次进化

用法:
  python3 .claude/lib/rollback_evolution.py --target skill:karpathy-guidelines
  python3 .claude/lib/rollback_evolution.py --target agent:backend-developer
  python3 .claude/lib/rollback_evolution.py --list  # 列出所有可回滚目标
"""
import sys
from pathlib import Path

_lib_dir = Path(__file__).parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

from evolution_safety import (
    cli_rollback, cli_diff, cli_status,
    EvolutionCircuitBreaker, snapshot_file,
    backup_file, rollback_file,
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="进化回滚工具")
    parser.add_argument("--target", help="回滚目标，格式: dimension:name")
    parser.add_argument("--timestamp", help="指定回滚到的时间戳版本")
    parser.add_argument("--diff", action="store_true", help="对比当前与备份")
    parser.add_argument("--list", action="store_true", help="列出所有可回滚目标")
    args = parser.parse_args()

    if args.list:
        # 列出所有有备份的目标
        import os
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
        backup_dir = root / ".claude" / "data" / "backups"
        if not backup_dir.exists():
            print("(无备份文件)")
            return
        backups = sorted(backup_dir.glob("*.bak"))
        if not backups:
            print("(无备份文件)")
            return
        print(f"可回滚目标 ({len(backups)} 个备份):")
        for b in backups:
            import datetime
            mtime = datetime.datetime.fromtimestamp(b.stat().st_mtime)
            print(f"  {b.stem} — {mtime.strftime('%Y-%m-%d %H:%M')}")
        return

    if not args.target:
        parser.print_help()
        return

    if args.diff:
        cli_diff(args.target)
    else:
        cli_rollback(args.target, args.timestamp)


if __name__ == "__main__":
    main()
