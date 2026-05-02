#!/usr/bin/env python3
"""Rule 维度进化策略"""
import json
from pathlib import Path


def _path(p):
    if p is None: return Path(".")
    if isinstance(p, str): return Path(p)
    return p


def evolve_rule(target: str, corrections: list, config: dict, root: Path) -> dict:
    rule_name = target.replace("rule:", "")
    paths = config.get("paths", {})
    rules_dir = root / paths.get("rules_dir", "rules")
    rule_file = rules_dir / f"{rule_name}.md"
    if not rule_file.exists():
        return {"success": False, "error": f"Rule file not found: {rule_file}"}
    suggested_changes = _generate_rule_change(rule_name, corrections)
    return {"success": True, "action": "propose", "target_file": str(rule_file), "change_type": "exception", "suggested_change": f"\n## [Auto-Evolved Exceptions]\n以下情况为例外：\n{suggested_changes}\n"}


def _generate_rule_change(rule_name: str, corrections: list) -> str:
    if not corrections:
        return "- 经 team-lead 口头批准后可例外\n"
    lines = []
    for c in corrections[:5]:
        ctx = c.get("context", "")
        corr = c.get("user_correction", "")
        if ctx or corr:
            lines.append(f"- 例外场景：{ctx} → {corr}")
    return "\n".join(lines) if lines else "- 经 team-lead 口头批准后可例外\n"


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    config = {"paths": {"rules_dir": "rules"}}
    result = evolve_rule("rule:security", [{"context": "紧急修复", "user_correction": "跳过 review"}], config, root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
