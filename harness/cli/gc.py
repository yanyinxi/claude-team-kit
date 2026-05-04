#!/usr/bin/env python3
"""
知识垃圾回收 CLI — kit gc 命令。

调用 GC Agent 扫描 harness/knowledge/ 目录，输出模式漂移报告。
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_gc_agent(knowledge_dir: Path, output_path: Path):
    """通过 Claude Code CLI 调用 GC Agent"""
    drift_file = knowledge_dir / "drift-report.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 构建 prompt 给 GC Agent
    gc_prompt = f"""你是知识垃圾回收 Agent。扫描 {knowledge_dir} 目录，识别以下问题：

1. **模式漂移**: 知识条目与当前代码库实践不一致
2. **死知识**: 从未被引用的条目（无 project_count 或 usage_count）
3. **过期知识**: 上次使用时间超过 6 个月的条目
4. **孤儿引用**: 被 INDEX.md 引用但文件已不存在的条目

扫描 {knowledge_dir} 中所有 .json 条目和 INDEX.md，生成 markdown 报告到 {drift_file}。

报告格式:
## 模式漂移
...

## 死知识
...

## 过期知识
...

## 孤儿引用
...

每个问题项附上: 文件路径 + 问题描述 + 建议操作。
"""

    # 通过 Claude Code 调用 gc agent
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "claude_code",
                "--print", gc_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=knowledge_dir.parent,
        )
        # 如果 Claude Code 不可用，生成基础报告
        if result.returncode != 0:
            generate_fallback_report(knowledge_dir, drift_file, timestamp)
    except FileNotFoundError:
        generate_fallback_report(knowledge_dir, drift_file, timestamp)
    except subprocess.TimeoutExpired:
        generate_fallback_report(knowledge_dir, drift_file, timestamp)

    return drift_file


def generate_fallback_report(knowledge_dir: Path, output_path: Path, timestamp: str):
    """无 Claude Code 时生成基础扫描报告"""
    issues = []
    entries = []

    for f in knowledge_dir.rglob("*.json"):
        if f.name == "INDEX.md":
            continue
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            entry["_file"] = str(f.relative_to(knowledge_dir))
            entries.append(entry)
        except (json.JSONDecodeError, OSError):
            issues.append(f"  - 无法解析: {f.name}")

    # 过期条目（超过6个月未用）
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=180)).isoformat()
    stale = [e for e in entries if e.get("last_used_at", "") < cutoff]
    if stale:
        issues.append("## 过期知识（>6个月未用）")
        for e in stale:
            issues.append(f"  - {e.get('name', e.get('id', 'unknown'))} ({e['_file']}) — 上次使用: {e.get('last_used_at', '未知')}")

    # 死条目（从未使用）
    dead = [e for e in entries if e.get("usage_count", 0) == 0 and e.get("project_count", 0) == 0]
    if dead:
        issues.append("## 死知识（从未被引用）")
        for e in dead:
            issues.append(f"  - {e.get('name', e.get('id', 'unknown'))} ({e['_file']})")

    report = f"""# 知识漂移报告 — {timestamp}

> 由 kit gc 自动生成

## 统计
- 知识条目总数: {len(entries)}
- 发现问题数: {len(issues)}

## 问题列表

{chr(10).join(issues) if issues else "* 未发现问题 *"}
"""
    output_path.write_text(report, encoding="utf-8")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    root = Path(target).resolve()
    knowledge_dir = root / "harness" / "knowledge"

    if not knowledge_dir.exists():
        print(f"错误: 找不到 {knowledge_dir} 目录")
        sys.exit(1)

    output_path = knowledge_dir / "drift-report.md"
    drift_file = run_gc_agent(knowledge_dir, output_path)

    print(f"✅ 漂移报告已生成: {drift_file}")
    if drift_file.exists():
        lines = drift_file.read_text().splitlines()
        print(f"   共 {len(lines)} 行")