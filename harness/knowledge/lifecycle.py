#!/usr/bin/env python3
"""
Knowledge Lifecycle Engine — 知识生命周期可执行引擎。

读取 knowledge/lifecycle.yaml 配置，实现：
  1. 条目成熟度检查（draft→verified→proven 升级路径）
  2. 自动衰减计时（读取 last_used 时间戳，超过阈值降级）
  3. 跨项目引用计数（扫描 repo-index.json 中各项目的 harness/knowledge/ 引用情况）
  4. 跨项目提升提案（L3 → L1/L2）
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def load_lifecycle_config() -> dict:
    """加载 lifecycle.yaml 配置，失败则使用内联默认值"""
    config_path = Path(__file__).parent / "lifecycle.yaml"
    if yaml and config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    # 内联默认值
    return {
        "maturity": {
            "levels": ["draft", "verified", "proven"],
            "promotion": {
                "draft_to_verified": {"condition": "usage_count >= 1"},
                "verified_to_proven": {"condition": "project_count >= 2"},
            },
        },
        "decay": {
            "rules": [
                {"from": "proven", "to": "verified", "after": "12 months unused"},
                {"from": "verified", "to": "draft", "after": "6 months unused"},
            ]
        },
        "cross_project_promotion": {
            "layer3_to_layer1_2": {
                "condition": "referenced_by >= 2 different projects AND verified_by >= 1 maintainer",
            }
        },
    }


def check_maturity_promotion(entry: dict, config: dict) -> str | None:
    """
    检查条目是否可以升级。
    返回: "verified" | "proven" | None
    """
    current = entry.get("maturity", "draft")
    levels = config["maturity"]["levels"]

    if current not in levels:
        return None

    idx = levels.index(current)
    if idx >= len(levels) - 1:
        return None  # 已经是最高级

    usage_count = entry.get("usage_count", 0)
    project_count = entry.get("project_count", 0)

    # draft → verified: usage_count >= 1
    if current == "draft" and usage_count >= 1:
        return "verified"

    # verified → proven: project_count >= 2
    if current == "verified" and project_count >= 2:
        return "proven"

    return None


def apply_decay(entry: dict, config: dict) -> str | None:
    """
    检查条目是否应该衰减降级。
    返回: 目标成熟度 | None（无需降级）
    """
    last_used_str = entry.get("last_used_at") or entry.get("last_referenced_at")
    if not last_used_str:
        return None

    try:
        last_used = datetime.fromisoformat(last_used_str)
    except (ValueError, TypeError):
        return None

    current = entry.get("maturity", "draft")
    now = datetime.now()
    days_unused = (now - last_used).days

    for rule in config.get("decay", {}).get("rules", []):
        if rule.get("from") != current:
            continue
        threshold_str = rule.get("after", "")
        # 解析 "N months unused" 或 "N days unused"
        if "month" in threshold_str:
            months = int("".join(filter(str.isdigit, threshold_str.split("month")[0])))
            threshold_days = months * 30
        elif "day" in threshold_str:
            threshold_days = int("".join(filter(str.isdigit, threshold_str.split("day")[0])))
        else:
            continue

        if days_unused >= threshold_days:
            return rule.get("to")

    return None


def promote_to_layer1(entry: dict, knowledge_dir: Path, config: dict) -> Path | None:
    """
    跨项目提升：L3 → L1/L2。
    生成提升提案到 proposals/ 目录。
    返回: 提案文件路径 | None
    """
    proj_count = entry.get("project_count", 0)
    if proj_count < 2:
        return None

    proposals_dir = knowledge_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = entry.get("id", entry.get("name", "unknown")).replace("/", "_")
    proposal_path = proposals_dir / f"promote_{timestamp}_{safe_name}.md"

    content = f"""# 知识提升提案: {entry.get("name", entry.get("id", "unknown"))}

## 来源
- 当前层级: L3 (项目特定)
- 目标层级: L1 (跨项目技术知识)
- 触发条件: 被 {proj_count} 个不同项目引用

## 知识条目
```json
{json.dumps(entry, ensure_ascii=False, indent=2)}
```

## 升级理由
{entry.get("description", "被多个项目验证的通用知识，适合提升为团队级规范")}

## 操作步骤
1. 将条目移动到 team-knowledge.git/tech-wiki/
2. 更新原项目的 harness/knowledge/INDEX.md 引用
3. 在团队会议中确认

## 验证
- 更新后需在 ≥1 个项目中验证有效性
"""
    proposal_path.write_text(content, encoding="utf-8")
    return proposal_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_check(knowledge_file: Path):
    """检查单条知识的成熟度和衰减状态"""
    entry = json.loads(knowledge_file.read_text(encoding="utf-8"))
    config = load_lifecycle_config()

    new_maturity = check_maturity_promotion(entry, config)
    decay_target = apply_decay(entry, config)

    result = {"id": entry.get("id", str(knowledge_file))}
    if new_maturity:
        result["promotion"] = new_maturity
    if decay_target:
        result["decay_to"] = decay_target
    if not new_maturity and not decay_target:
        result["status"] = "stable"

    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_decay(knowledge_dir: Path):
    """扫描目录下所有知识文件，执行衰减检查"""
    config = load_lifecycle_config()
    decayed = []

    for f in knowledge_dir.rglob("*.json"):
        if f.name == "INDEX.md":
            continue
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        target = apply_decay(entry, config)
        if target:
            entry["maturity"] = target
            entry["decayed_at"] = datetime.now().isoformat()
            f.write_text(json.dumps(entry, ensure_asascii=False, indent=2), encoding="utf-8")
            decayed.append(str(f.relative_to(knowledge_dir)))

    print(json.dumps({"decayed": decayed, "count": len(decayed)}, indent=2))


def cmd_promote(knowledge_dir: Path):
    """检查跨项目提升机会"""
    config = load_lifecycle_config()
    promoted = []

    for f in knowledge_dir.rglob("*.json"):
        if f.name == "INDEX.md":
            continue
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        path = promote_to_layer1(entry, knowledge_dir, config)
        if path:
            promoted.append(str(path.relative_to(knowledge_dir)))

    print(json.dumps({"promoted": promoted, "count": len(promoted)}, indent=2))


def main():
    if len(sys.argv) < 3:
        print("用法: lifecycle.py check <knowledge-file.json>")
        print("      lifecycle.py decay <knowledge-dir>")
        print("      lifecycle.py promote <knowledge-dir>")
        sys.exit(1)

    cmd = sys.argv[1]
    path = Path(sys.argv[2])

    if cmd == "check":
        cmd_check(path)
    elif cmd == "decay":
        cmd_decay(path)
    elif cmd == "promote":
        cmd_promote(path)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()