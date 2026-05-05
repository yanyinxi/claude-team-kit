#!/usr/bin/env python3
"""Agent 维度进化策略"""
import json
from pathlib import Path


def evolve_agent(target: str, corrections: list, config: dict, root: Path) -> dict:
    agent_name = target.replace("agent:", "")
    paths = config.get("paths", {})
    agents_dir = root / paths.get("agents_dir", "agents")
    agent_file = agents_dir / f"{agent_name}.md"
    if not agent_file.exists():
        return {"success": False, "error": f"Agent file not found: {agent_file}"}
    content = agent_file.read_text(encoding="utf-8")
    suggested_changes = _generate_agent_change(agent_name, corrections)
    if not suggested_changes:
        return {"success": False, "error": "No clear change pattern"}
    if "[auto-evolved]" in content or "[Auto-Evolved]" in content:
        return {"success": True, "action": "replace", "target_file": str(agent_file), "change_type": "replace", "suggested_change": suggested_changes}
    return {"success": True, "action": "append", "target_file": str(agent_file), "change_type": "append", "suggested_change": f"\n## [Auto-Evolved]\n{suggested_changes}\n"}


def _generate_agent_change(agent_name: str, corrections: list) -> str:
    if not corrections:
        return ""
    patterns = {}
    for c in corrections:
        hint = c.get("root_cause_hint", "")
        correction = c.get("user_correction", "")
        if hint:
            patterns.setdefault(hint, []).append(correction)
    if not patterns:
        return "- 根据用户反馈自动优化\n"
    lines = []
    for hint, examples in patterns.items():
        lines.append(f"- {hint}: {examples[0] if examples else ''}")
    return "\n".join(lines)


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    config = {"paths": {"agents_dir": "agents"}}
    result = evolve_agent("agent:backend-dev", [{"root_cause_hint": "避免 print 调试", "user_correction": "用 logging"}], config, root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
