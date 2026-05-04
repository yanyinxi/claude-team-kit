#!/usr/bin/env python3
"""
instinct_cli.py — Claude Harness Kit 本能记录管理 CLI

Usage:
  python3 harness/cli/instinct_cli.py status
  python3 harness/cli/instinct_cli.py status [--domain <domain>]
  python3 harness/cli/instinct_cli.py export [--min-confidence N] [--format json|markdown]
  python3 harness/cli/instinct_cli.py import <file>
  python3 harness/cli/instinct_cli.py evolve [--dry-run]
  python3 harness/cli/instinct_cli.py add <domain> <trigger> <pattern> [--confidence N]
"""

import sys
import json
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# ── Data Path (canonical: harness/memory/) ────────────────────────

INSTINCT_ROOT = Path(__file__).parent.parent / "memory"
INSTINCT_FILE = INSTINCT_ROOT / "instinct-record.json"
INSTINCT_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Schema: {"records": [...], "meta": {...}} ──────────────────────────────────

# CHK 版本（统一从 _core/version.json 读取）
def _get_chk_version() -> str:
    try:
        version_file = Path(__file__).parent.parent / "_core" / "version.json"
        if version_file.exists():
            data = json.loads(version_file.read_text())
            return data.get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"

DEFAULT_SCHEMA = {
    "records": [],
    "meta": {
        "version": _get_chk_version(),
        "created": datetime.utcnow().isoformat() + "Z",
        "updated": datetime.utcnow().isoformat() + "Z",
    }
}

def load_records() -> dict:
    if not INSTINCT_FILE.exists():
        return DEFAULT_SCHEMA.copy()
    try:
        with open(INSTINCT_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return DEFAULT_SCHEMA.copy()

def save_records(data: dict):
    data["meta"]["updated"] = datetime.utcnow().isoformat() + "Z"
    with open(INSTINCT_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Confidence helpers ───────────────────────────────────────────────────────────

CONFIDENCE_LABELS = {
    (0.9, 1.1):  ("🟢 AUTO",  "已验证本能"),
    (0.5, 0.9):   ("🟡 PROPOSAL", "提案本能"),
    (0.0, 0.5):   ("🔴 OBSERVE",  "观测本能"),
}

def confidence_label(confidence: float) -> str:
    for (low, high), (emoji, label) in CONFIDENCE_LABELS.items():
        if low <= confidence < high:
            return f"{emoji} {label}"
    return f"🔴 OBSERVE"

def confidence_bar(confidence: float, width: int = 10) -> str:
    filled = int(confidence * width)
    return "█" * filled + "░" * (width - filled)

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_status(args):
    data = load_records()
    records = data.get("records", [])

    if not records:
        print("📭 No instincts recorded yet.")
        print("  Run: instinct_cli.py add <domain> <trigger> <pattern>")
        return 0

    # Filter by domain if specified
    if args.domain:
        records = [r for r in records if r.get("domain", "").lower() == args.domain.lower()]

    # Group by domain
    by_domain = defaultdict(list)
    for r in records:
        by_domain[r.get("domain", "unknown")].append(r)

    # Summary stats
    total = len(records)
    auto = sum(1 for r in records if r.get("confidence", 0) >= 0.9)
    proposal = sum(1 for r in records if 0.5 <= r.get("confidence", 0) < 0.9)
    observe = sum(1 for r in records if r.get("confidence", 0) < 0.5)

    print(f"🦁 Instinct System — {total} records")
    print(f"   🟢 AUTO (≥0.9):      {auto}")
    print(f"   🟡 PROPOSAL (≥0.5): {proposal}")
    print(f"   🔴 OBSERVE (<0.5):   {observe}")
    print()

    if args.domain:
        print(f"📂 Domain: {args.domain}")

    for domain, recs in sorted(by_domain.items()):
        print(f"\n  ┌─ {domain.upper()} ({len(recs)} records)")
        for r in recs:
            conf = r.get("confidence", 0)
            bar = confidence_bar(conf)
            label = confidence_label(conf)
            age = r.get("last_triggered", r.get("created", ""))
            if age:
                try:
                    age_str = _time_ago(age)
                except Exception:
                    age_str = age
            else:
                age_str = "never"
            print(f"  │ {bar} {conf:.2f} {label}")
            print(f"  │   Trigger: {r.get('trigger', '?')}")
            if r.get("pattern"):
                print(f"  │   Pattern: {r.get('pattern', '')[:60]}")
            print(f"  │   Age: {age_str} | Evals: {r.get('eval_count', 0)}")
            print(f"  │   ID: {r.get('id', '?')}")
        print(f"  └{'─' * max(len(d) for d in by_domain)}")

    return 0

def _time_ago(iso_str: str) -> str:
    try:
        if iso_str.endswith("Z"):
            dt = datetime.fromisoformat(iso_str[:-1]).replace(tzinfo=None)
        else:
            dt = datetime.fromisoformat(iso_str)
        delta = datetime.utcnow() - dt
        if delta.days > 30:
            return f"{delta.days // 30}mo ago"
        if delta.days > 0:
            return f"{delta.days}d ago"
        if delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        return f"{delta.seconds // 60}m ago"
    except Exception:
        return iso_str

def cmd_export(args):
    data = load_records()
    records = data.get("records", [])

    # Filter by min-confidence
    if args.min_confidence is not None:
        records = [r for r in records if r.get("confidence", 0) >= args.min_confidence]

    if not records:
        print("📭 No instincts match the criteria." if args.min_confidence else "📭 No instincts recorded.")
        return 0

    if args.format == "json":
        print(json.dumps({"records": records, "meta": data.get("meta", {})}, ensure_ascii=False, indent=2))
    else:
        # Markdown format
        print("# Instinct Export")
        print(f"Exported: {datetime.utcnow().isoformat()}Z")
        print(f"Total: {len(records)} instincts")
        print()
        for r in records:
            conf = r.get("confidence", 0)
            print(f"## {r.get('trigger', '?')} (ID: {r.get('id', '?')})")
            print(f"- Domain: {r.get('domain', '?')}")
            print(f"- Confidence: {conf:.2f} {confidence_label(conf)}")
            print(f"- Pattern: {r.get('pattern', 'N/A')}")
            print(f"- Created: {r.get('created', '?')}")
            print(f"- Eval count: {r.get('eval_count', 0)}")
            print()

    return 0

def cmd_import(args):
    filepath = Path(args.file)
    if not filepath.exists():
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        return 1

    try:
        with open(filepath) as f:
            imported = json.load(f)
    except json.JSONDecodeError:
        print("❌ Invalid JSON file.", file=sys.stderr)
        return 1

    records = imported if isinstance(imported, list) else imported.get("records", [])
    if not records:
        print("❌ No records found in file.", file=sys.stderr)
        return 1

    data = load_records()
    existing_ids = {r["id"] for r in data.get("records", []) if "id" in r}
    new_records = [r for r in records if r.get("id") not in existing_ids]

    data.setdefault("records", []).extend(new_records)
    save_records(data)

    print(f"✅ Imported {len(new_records)} new instincts (skipped {len(records)-len(new_records)} duplicates)")
    return 0

def cmd_evolve(args):
    data = load_records()
    records = data.get("records", [])

    if not records:
        print("📭 No instincts to evolve.")
        return 0

    # Cluster by domain
    by_domain = defaultdict(list)
    for r in records:
        by_domain[r.get("domain", "unknown")].append(r)

    proposals = []
    for domain, recs in by_domain.items():
        if len(recs) >= 2:
            avg_conf = sum(r.get("confidence", 0) for r in recs) / len(recs)
            auto_count = sum(1 for r in recs if r.get("confidence", 0) >= 0.9)
            if args.dry_run:
                proposals.append({
                    "type": "CREATE_SKILL",
                    "domain": domain,
                    "record_count": len(recs),
                    "avg_confidence": avg_conf,
                    "auto_count": auto_count,
                    "status": "PROPOSED",
                })

    if args.dry_run:
        print("🔬 Instinct Evolution — Dry Run")
        print(f"   Analyzing {len(records)} instincts across {len(by_domain)} domains")
        print()
        if not proposals:
            print("  No evolution proposals found.")
            print("  (Need ≥2 records in same domain with high confidence)")
            return 0
        for p in proposals:
            status = "🟢 READY" if p["avg_confidence"] >= 0.7 and p["auto_count"] >= 1 else "🟡 NEEDS_VALIDATION"
            print(f"  {status} CREATE_SKILL: {p['domain']}")
            print(f"    Records: {p['record_count']}, Avg confidence: {p['avg_confidence']:.2f}, AUTO: {p['auto_count']}")
        print()
        print(f"  → {len(proposals)} proposal(s) ready for implementation")
        return 0

    # Real evolution: upgrade confidence for repeated patterns
    for domain, recs in by_domain.items():
        for r in recs:
            if r.get("eval_count", 0) >= 3:
                old = r.get("confidence", 0)
                new = min(1.0, old + 0.1)
                r["confidence"] = new
                print(f"  🔼 {domain}: confidence {old:.2f} → {new:.2f} (eval_count ≥ 3)")

    save_records(data)
    print("✅ Evolution complete.")
    return 0

def cmd_add(args):
    import uuid
    data = load_records()
    record = {
        "id": str(uuid.uuid4())[:8],
        "domain": args.domain,
        "trigger": args.trigger,
        "pattern": args.pattern,
        "confidence": args.confidence or 0.3,
        "eval_count": 0,
        "created": datetime.utcnow().isoformat() + "Z",
        "last_triggered": datetime.utcnow().isoformat() + "Z",
        "source": "manual",
    }
    data.setdefault("records", []).append(record)
    save_records(data)
    conf = record["confidence"]
    print(f"✅ Added instinct: [{record['id']}] {args.trigger}")
    print(f"   Domain: {args.domain} | Confidence: {conf:.2f} {confidence_label(conf)}")
    return 0

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="instinct_cli",
        description="🦁 Claude Harness Kit — Instinct System CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # status
    p_status = sub.add_parser("status", help="显示本能记录状态")
    p_status.add_argument("--domain", help="按领域过滤")

    # export
    p_export = sub.add_parser("export", help="导出本能记录")
    p_export.add_argument("--min-confidence", type=float, default=None, help="最低置信度阈值")
    p_export.add_argument("--format", choices=["json", "markdown"], default="markdown", help="输出格式")

    # import
    p_import = sub.add_parser("import", help="从文件导入本能记录")
    p_import.add_argument("file", help="JSON 文件路径")

    # evolve
    p_evolve = sub.add_parser("evolve", help="执行本能进化（聚类 + 置信度升级）")
    p_evolve.add_argument("--dry-run", action="store_true", help="仅分析，不修改")

    # add
    p_add = sub.add_parser("add", help="手动添加本能记录")
    p_add.add_argument("domain", help="领域（如: testing, security）")
    p_add.add_argument("trigger", help="触发条件描述")
    p_add.add_argument("pattern", help="代码/行为模式")
    p_add.add_argument("--confidence", type=float, default=None, help="初始置信度（默认 0.3）")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "status": cmd_status,
        "export": cmd_export,
        "import": cmd_import,
        "evolve": cmd_evolve,
        "add": cmd_add,
    }

    return commands[args.command](args) or 0

if __name__ == "__main__":
    sys.exit(main())
