#!/usr/bin/env python3
"""
kit migrate — 项目迁移编排器。

用法:
  kit migrate <project-dir> --playbook=migration-playbook.md
  kit migrate <project-dir> --mode=autopilot --review=required

流程:
  1. 读 playbook 或自动分析迁移需求
  2. 分阶段执行迁移
  3. 每阶段: 迁移 → 测试 → 提交
  4. 生成迁移报告
"""
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime


def validate_playbook(playbook_path: Path) -> bool:
    """验证 playbook 是否有效"""
    if not playbook_path.exists():
        print(f"❌ Playbook 不存在: {playbook_path}")
        return False

    content = playbook_path.read_text(encoding="utf-8")
    required_sections = ["迁移目标", "影响范围", "前置条件", "迁移步骤"]
    missing = [s for s in required_sections if s not in content]
    if missing:
        print(f"⚠ Playbook 缺少: {', '.join(missing)}")
    return True


def generate_report(project_dir: Path, phases: list[dict], output_path: Path):
    """生成迁移报告"""
    report = f"""# 迁移报告: {project_dir.name}
日期: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## 执行摘要

| 阶段 | 状态 | 文件变更 | 测试结果 |
|------|------|----------|----------|
"""
    for p in phases:
        report += f"| {p.get('name', '?')} | {p.get('status', '?')} | {p.get('files', 0)} | {p.get('tests', '?')} |\n"

    report += f"""
## 下一步
- 代码审查
- 集成测试验证
- 部署到预发环境
"""
    output_path.write_text(report, encoding="utf-8")
    print(f"✅ 迁移报告已生成: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="项目迁移编排")
    parser.add_argument("project_dir", nargs="?", default=".", help="目标项目目录")
    parser.add_argument("--playbook", help="迁移 playbook 路径")
    parser.add_argument("--mode", default="manual", choices=["manual", "autopilot"], help="迁移模式")
    parser.add_argument("--review", default="required", choices=["required", "optional"], help="审查策略")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"❌ 项目目录不存在: {project_dir}")
        sys.exit(1)

    print(f"kit migrate: {project_dir.name}")

    claude_md = project_dir / "CLAUDE.md"
    if not claude_md.exists():
        print(f"❌ 项目缺少 CLAUDE.md，请先运行 kit init")
        sys.exit(1)

    if args.playbook:
        if not validate_playbook(Path(args.playbook)):
            sys.exit(1)
        print(f"  使用 playbook: {args.playbook}")

    print(f"  模式: {args.mode}")
    print(f"  审查: {args.review}")
    print()
    print("迁移流程:")
    print("  1. 分析现有代码和依赖")
    print("  2. 更新构建配置")
    print("  3. 迁移 API 调用")
    print("  4. 运行测试")
    print("  5. 修复失败 → 重试")
    print("  6. 生成迁移报告")
    print()
    print("请在 Claude Code 中使用 migration-dev Agent 执行具体迁移")


if __name__ == "__main__":
    main()
