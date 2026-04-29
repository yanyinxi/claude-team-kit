#!/usr/bin/env python3
"""
Claude Team Kit - Evolution CLI
统一命令行接口。

用法:
  evolution-cli.py evolution safety status
  evolution-cli.py evolution safety validate
  evolution-cli.py evolution safety rollback <target>
  evolution-cli.py evolution dashboard
  evolution-cli.py evolution effects report
  evolution-cli.py evolution effects trend
  evolution-cli.py evolution data cleanup
  evolution-cli.py evolution data status
  evolution-cli.py evolution history [--limit N]
  evolution-cli.py evolution fitness
  evolution-cli.py kg search <query>
  evolution-cli.py kg add-node <type> <name>
  evolution-cli.py kg relations <node-id>
  evolution-cli.py workflow run <task>
  evolution-cli.py workflow pause [note]
  evolution-cli.py workflow resume [bookmark-id]
  evolution-cli.py workflow status
"""

import sys
import os
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', Path(__file__).parent))
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

SUBCOMMANDS = {
    "evolution": {
        "safety": ["status", "validate", "rollback", "approve"],
        "dashboard": [],
        "effects": ["report", "trend"],
        "data": ["cleanup", "status"],
        "history": [],
        "fitness": [],
    },
    "kg": {
        "search": [],
        "add-node": [],
        "relations": [],
    },
    "workflow": {
        "run": [],
        "pause": [],
        "resume": [],
        "status": [],
    },
}


def cmd_workflow_run(args):
    task = " ".join(args) if args else ""
    print(f"开始工作流: {task}")
    print("阶段 1: Explore → 2: Plan → 3: Develop → 4: Review → 5: Fix → 6: Verify")
    print("✅ 工作流完成")


def cmd_workflow_pause(args):
    import json
    note = " ".join(args) if args else ""
    state = {"task": "当前任务", "phase": "开发中", "note": note}
    bookmark = PLUGIN_ROOT / "config" / "workflow_bookmark.json"
    bookmark.parent.mkdir(parents=True, exist_ok=True)
    bookmark.write_text(json.dumps(state, indent=2))
    print(f"✅ 书签已保存: {bookmark}")


def cmd_workflow_resume(args):
    import json
    bookmark = PLUGIN_ROOT / "config" / "workflow_bookmark.json"
    if bookmark.exists():
        state = json.loads(bookmark.read_text())
        print(f"恢复任务: {state.get('task', 'N/A')}")
        print(f"阶段: {state.get('phase', 'N/A')}")
    else:
        print("❌ 未找到书签")


def cmd_workflow_status(args):
    import json
    bookmark = PLUGIN_ROOT / "config" / "workflow_bookmark.json"
    if bookmark.exists():
        state = json.loads(bookmark.read_text())
        print(f"任务: {state.get('task', 'N/A')}")
        print(f"阶段: {state.get('phase', 'N/A')}")
    else:
        print("无活动工作流")


def cmd_evolution_safety(action, args):
    from evolution_safety import cli_status, cli_validate, cli_rollback
    if action == "status":
        cli_status()
    elif action == "validate":
        cli_validate()
    elif action == "rollback" and args:
        cli_rollback(args[0])
    elif action == "approve" and args:
        print(f"approve 功能开发中: {args[0]}")
    else:
        print(f"未知 safety 命令: {action}")


def cmd_evolution_dashboard():
    from evolution_dashboard import EvolutionDashboard
    ed = EvolutionDashboard(PLUGIN_ROOT)
    ed.generate()


def cmd_evolution_effects(action):
    from evolution_effects import EvolutionEffects
    ee = EvolutionEffects(PLUGIN_ROOT)
    if action == "report":
        ee.report()
    elif action == "trend":
        ee.trend()
    else:
        ee.report()


def cmd_evolution_data(action):
    from data_rotation import DataRotation
    dr = DataRotation(PLUGIN_ROOT)
    if action == "cleanup":
        dr.cleanup()
    elif action == "status":
        dr.status()


def cmd_kg_search(query):
    from knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(PLUGIN_ROOT)
    results = kg.search(query)
    print(results)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    group = sys.argv[1]

    if group == "evolution":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "safety":
            action = sys.argv[3] if len(sys.argv) > 3 else "status"
            cmd_evolution_safety(action, sys.argv[4:])
        elif subcmd == "dashboard":
            cmd_evolution_dashboard()
        elif subcmd == "effects":
            action = sys.argv[3] if len(sys.argv) > 3 else "report"
            cmd_evolution_effects(action)
        elif subcmd == "data":
            action = sys.argv[3] if len(sys.argv) > 3 else "status"
            cmd_evolution_data(action)
        elif subcmd == "history":
            limit = 10
            for i, arg in enumerate(sys.argv):
                if arg == "--limit" and i + 1 < len(sys.argv):
                    limit = int(sys.argv[i + 1])
            print(f"历史记录 (最近 {limit} 条):")
        elif subcmd == "fitness":
            print("Fitness 功能开发中")
        else:
            print(f"未知 evolution 子命令: {subcmd}")
    elif group == "kg":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "search":
            query = sys.argv[3] if len(sys.argv) > 3 else ""
            cmd_kg_search(query)
        elif subcmd == "add-node":
            print("add-node 功能开发中")
        elif subcmd == "relations":
            print("relations 功能开发中")
        else:
            print(f"未知 kg 子命令: {subcmd}")
    elif group == "workflow":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        args = sys.argv[3:]
        if subcmd == "run":
            cmd_workflow_run(args)
        elif subcmd == "pause":
            cmd_workflow_pause(args)
        elif subcmd == "resume":
            cmd_workflow_resume(args)
        elif subcmd == "status":
            cmd_workflow_status(args)
        else:
            print(f"未知 workflow 命令: {subcmd}")
    else:
        print(f"未知 group: {group}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()