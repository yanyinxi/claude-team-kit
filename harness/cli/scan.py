#!/usr/bin/env python3
"""
kit scan — 扫描多代码库目录，评估改造量。

用法:
  kit scan --group=backend-services
  kit scan --target=java17-sb3

输出每个项目的:
  - 技术栈
  - CLAUDE.md 状态（有/无/过期）
  - 迁移优先级（低/中/高）
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime


IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".idea", "dist", "build", "target", "vendor"}
PROJECT_FILES = {"pom.xml", "package.json", "go.mod", "Cargo.toml", "pyproject.toml"}


def scan_directory(base: Path) -> list[dict]:
    """扫描目录下所有项目"""
    results = []

    for item in sorted(base.iterdir()):
        if item.name.startswith(".") or item.name in IGNORE_DIRS:
            continue
        if not item.is_dir():
            continue

        # 检测是否为项目目录
        proj_files = list(item.glob("*"))
        has_project_file = any(
            pf.name in PROJECT_FILES for pf in proj_files if pf.is_file()
        )

        if has_project_file:
            claude_md = item / "CLAUDE.md"
            claude_status = "present" if claude_md.exists() else "missing"

            # 检查 CLAUDE.md 是否过期（90天未更新）
            if claude_status == "present":
                mtime = datetime.fromtimestamp(claude_md.stat().st_mtime)
                days_old = (datetime.now() - mtime).days
                if days_old > 90:
                    claude_status = "stale"

            results.append({
                "name": item.name,
                "path": str(item),
                "claude_md": claude_status,
                "tech_files": [pf.name for pf in proj_files if pf.name in PROJECT_FILES],
            })

    return results


def main():
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.getcwd()).parent
    print(f"扫描目录: {base}")
    print(f"{'='*60}")

    projects = scan_directory(base)

    has_claude = [p for p in projects if p["claude_md"] == "present"]
    no_claude = [p for p in projects if p["claude_md"] == "missing"]
    stale_claude = [p for p in projects if p["claude_md"] == "stale"]

    print(f"\n总计: {len(projects)} 个项目")
    print(f"  有 CLAUDE.md:  {len(has_claude)}")
    print(f"  无 CLAUDE.md:  {len(no_claude)}")
    print(f"  过期(>90天):   {len(stale_claude)}")

    if no_claude:
        print(f"\n需要 kit init 的项目:")
        for p in no_claude:
            print(f"  - {p['name']} ({', '.join(p['tech_files'])})")

    if stale_claude:
        print(f"\nCLAUDE.md 过期的项目:")
        for p in stale_claude:
            print(f"  - {p['name']}")

    # 输出 JSON 报告
    report_path = base / ".claude" / "scan-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "scanned_at": datetime.now().isoformat(),
        "total": len(projects),
        "with_claude": len(has_claude),
        "without_claude": len(no_claude),
        "stale": len(stale_claude),
        "projects": projects,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()
