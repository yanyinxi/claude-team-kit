#!/usr/bin/env python3
"""Skill 维度进化策略"""
import json
from pathlib import Path


def _path(p):
    if p is None: return Path(".")
    if isinstance(p, str): return Path(p)
    return p


def evolve_skill(target: str, corrections: list, config: dict, root: Path) -> dict:
    skill_name = target.replace("skill:", "")
    paths = config.get("paths", {})
    skills_dir = root / paths.get("skills_dir", "skills")
    skill_file = skills_dir / skill_name / "SKILL.md"
    if not skill_file.exists():
        return {"success": False, "error": f"Skill file not found: {skill_file}"}
    suggested_changes = _generate_skill_change(skill_name, corrections)
    return {"success": True, "action": "propose", "target_file": str(skill_file), "change_type": "supplement", "suggested_change": f"\n## [Auto-Evolved]\n补充场景：\n{suggested_changes}\n"}


def _generate_skill_change(skill_name: str, corrections: list) -> str:
    if not corrections:
        return "- 根据用户反馈补充最佳实践\n"
    lines = []
    for c in corrections[:5]:
        ctx = c.get("context", "")
        corr = c.get("user_correction", "")
        if ctx or corr:
            lines.append(f"- 场景：{ctx} → {corr}")
    return "\n".join(lines) if lines else "- 根据用户反馈补充最佳实践\n"


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    config = {"paths": {"skills_dir": "skills"}}
    result = evolve_skill("skill:testing", [{"context": "数据库测试", "user_correction": "跳过 mock 建议"}], config, root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
