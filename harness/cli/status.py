#!/usr/bin/env python3
"""
kit status — 查看 Claude Harness Kit 当前状态。

输出 5 个信息板块:
  1. 当前模式
  2. 活跃 Hooks 数量和名称
  3. sessions.jsonl 最近 10 条摘要
  4. instinct 记录总数和置信度分布
  5. 待处理 proposal 数量
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter


def load_settings(root: Path) -> dict:
    settings_path = root / ".claude" / "settings.local.json"
    if settings_path.exists():
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def count_files(pattern: Path) -> int:
    return len(list(pattern.glob("*"))) if pattern.exists() else 0


def main():
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()
    claude_dir = root / ".claude"
    data_dir = claude_dir / "data"

    print(f"Claude Harness Kit — 项目: {root.name}")
    print("=" * 50)

    # 1. 当前模式
    settings = load_settings(root)
    mode = settings.get("mode", "default (未配置)")
    print(f"\n1️⃣  当前模式: {mode}")

    # 2. 活跃 Hooks
    hooks = settings.get("hooks", {})
    if hooks:
        print(f"\n2️⃣  活跃 Hooks ({len(hooks)} 个事件):")
        for event, configs in hooks.items():
            if configs:
                names = [c.get("hooks", [{}])[0].get("command", "").split()[-1]
                         if isinstance(c, dict) else str(c)
                         for c in configs]
                print(f"   {event}: {len(configs)} 个配置")
    else:
        print("\n2️⃣  Hooks: 未配置（运行 kit mode 启用）")

    # 3. sessions.jsonl 摘要
    sessions_file = data_dir / "sessions.jsonl"
    if sessions_file.exists():
        lines = sessions_file.read_text().strip().splitlines()
        total = len(lines)
        print(f"\n3️⃣  Sessions ({total} 条记录):")
        recent = lines[-10:] if len(lines) > 10 else lines
        for line in recent:
            try:
                s = json.loads(line)
                ts = s.get("timestamp", "")[:16]
                agents = s.get("agents_used", [])
                corrections = len(s.get("corrections", []))
                print(f"   {ts} | agents:{len(agents)} corrections:{corrections}")
            except json.JSONDecodeError:
                pass
    else:
        print("\n3️⃣  Sessions: 无记录（首次使用中）")

    # 4. instinct 分布
    instinct_file = root / "memory" / "instinct-record.json"
    if instinct_file.exists():
        try:
            data = json.loads(instinct_file.read_text(encoding="utf-8"))
            records = data.get("records", [])
            print(f"\n4️⃣  Instinct ({len(records)} 条记录):")
            if records:
                conf_dist = Counter()
                for r in records:
                    conf = r.get("confidence", 0)
                    bucket = f"{int(conf*10)*10}-{(int(conf*10)+1)*10}%"
                    conf_dist[bucket] += 1
                for bucket in sorted(conf_dist.keys()):
                    print(f"   confidence {bucket}: {conf_dist[bucket]} 条")
            else:
                print("   无记录（正在学习）")
        except (json.JSONDecodeError, OSError):
            print("\n4️⃣  Instinct: 读取失败")
    else:
        print("\n4️⃣  Instinct: 无记录")

    # 5. 待处理 proposals
    proposals_dir = root / ".claude" / "proposals"
    if proposals_dir.exists():
        pending = list(proposals_dir.glob("*.md"))
        print(f"\n5️⃣  待处理 Proposals: {len(pending)} 个")
        for p in pending[:5]:
            print(f"   - {p.name}")
    else:
        print("\n5️⃣  Proposals: 无待处理")

    print(f"\n{'='*50}")
    print(f"运行 kit mode 查看/切换模式 | kit gc 运行知识回收")


if __name__ == "__main__":
    main()