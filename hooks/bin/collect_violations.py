#!/usr/bin/env python3
"""
PreToolUse[Write|Edit] Hook — 检测是否违反 rules/ 中的规则

输出: data/rule_violations.jsonl
"""
import fcntl, json, os, sys
from datetime import datetime
from pathlib import Path


def _load_violation_rules(project_root: str) -> list:
    """从 config/violation-rules.json 加载规则，无配置则用默认规则"""
    config_file = Path(project_root) / ".claude" / "config" / "violation-rules.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                rules = json.load(f)
                return [{"rule": r["name"], "check": lambda fp, p=r["pattern"]: re.match(p, fp) is not None, "severity": r["severity"]} for r in rules]
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    return _get_default_rules()


def _get_default_rules() -> list:
    return [
        {"rule": "deny-git-write", "check": lambda fp: ".git/" in fp, "severity": "critical"},
        {"rule": "deny-env-write", "check": lambda fp: fp.endswith(".env") or ".env." in fp, "severity": "high"},
        {"rule": "test-location", "check": lambda fp: ("tests/" in fp and not fp.startswith("main/backend/src/test/") and not fp.startswith("main/frontend/")), "severity": "medium"},
        {"rule": "no-lombok", "check": lambda fp: fp.endswith(".java") and "lombok" in fp.lower(), "severity": "medium"},
    ]


def main():
    try:
        raw = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        data = {}

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return

    session_id = data.get("session_id", "unknown")
    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    violation_rules = _load_violation_rules(project_root)

    violations = []
    for rule in violation_rules:
        if rule["check"](file_path):
            violations.append({"rule": rule["rule"], "file": file_path, "severity": rule["severity"]})

    if not violations:
        return

    data_dir = Path(project_root) / ".claude" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    vio_file = data_dir / "rule_violations.jsonl"
    with open(vio_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            for v in violations:
                v.update({"timestamp": datetime.now().isoformat(), "session_id": session_id})
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
