"""进化系统 CLI 工具

Usage:
    python -m evolution.cli run          # 运行完整进化周期
    python -m evolution.cli status       # 查看进化状态
    python -m evolution.cli confirm <id> # 确认进化
    python -m evolution.cli force <dim> <id>  # 强制进化
"""

import sys
import argparse
from pathlib import Path

# 确保能导入 evolution 模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.engine import EvolutionEngine
from evolution.config import EvolutionConfig


def run_evolution(args):
    """运行进化周期"""
    print("🔄 启动进化引擎...")
    
    config = EvolutionConfig()
    engine = EvolutionEngine(config)
    
    results = engine.run_full_cycle()
    
    print("\n" + "=" * 50)
    print("进化结果汇总")
    print("=" * 50)
    
    total = 0
    for dimension, dim_results in results.items():
        if dim_results:
            print(f"\n[{dimension.upper()}]")
            for r in dim_results:
                status = "✅" if r.success else "❌"
                confirm = "[待确认]" if r.needs_confirmation else ""
                print(f"  {status} {r.target_id} {confirm}")
                for change in r.changes_made[:2]:
                    print(f"     → {change}")
                total += 1
    
    if total == 0:
        print("\n📭 暂无可进化的对象")
    else:
        print(f"\n📊 总计: {total} 项进化建议")


def show_status(args):
    """显示进化状态"""
    config = EvolutionConfig()
    engine = EvolutionEngine(config)
    
    stats = engine.get_evolution_stats()
    pending = engine.get_pending_confirmations()
    
    print("=" * 50)
    print("进化系统状态")
    print("=" * 50)
    
    print(f"\n📈 总体统计")
    print(f"  总进化次数: {stats['total_evolutions']}")
    print(f"  成功率: {stats['success_rate']*100:.1f}%")
    print(f"  待确认: {stats['pending_confirmations']}")
    
    if stats['by_dimension']:
        print(f"\n📊 各维度统计")
        for dim, dim_stats in stats['by_dimension'].items():
            print(f"  [{dim}]")
            print(f"    总数: {dim_stats['total']}")
            print(f"    成功: {dim_stats['success']}")
            print(f"    待确认: {dim_stats['pending']}")
    
    if pending:
        print(f"\n⏳ 待确认列表")
        for p in pending[:5]:
            print(f"  - {p.dimension}/{p.target_id}")
            for change in p.changes_made[:1]:
                print(f"    {change}")


def confirm_evolution(args):
    """确认进化"""
    config = EvolutionConfig()
    engine = EvolutionEngine(config)
    
    target_id = args.target_id
    approved = not args.reject
    
    if engine.confirm_evolution(target_id, approved):
        action = "确认" if approved else "拒绝"
        print(f"✅ 已{action}: {target_id}")
    else:
        print(f"❌ 未找到待确认的进化: {target_id}")


def force_evolve(args):
    """强制进化"""
    config = EvolutionConfig()
    engine = EvolutionEngine(config)
    
    result = engine.force_evolve(args.dimension, args.target_id)
    
    if result:
        print(f"✅ 强制进化完成: {args.dimension}/{args.target_id}")
        print(f"   改动: {result.changes_made}")
    else:
        print(f"❌ 进化失败: {args.dimension}/{args.target_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Claude 自我进化系统 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m evolution.cli run                    # 运行进化
  python -m evolution.cli status                 # 查看状态
  python -m evolution.cli confirm skill_001      # 确认进化
  python -m evolution.cli force skill debugging  # 强制进化
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # run 命令
    run_parser = subparsers.add_parser("run", help="运行完整进化周期")
    
    # status 命令
    status_parser = subparsers.add_parser("status", help="查看进化状态")
    
    # confirm 命令
    confirm_parser = subparsers.add_parser("confirm", help="确认或拒绝进化")
    confirm_parser.add_argument("target_id", help="进化目标ID")
    confirm_parser.add_argument("--reject", action="store_true", help="拒绝而非确认")
    
    # force 命令
    force_parser = subparsers.add_parser("force", help="强制进化指定对象")
    force_parser.add_argument("dimension", choices=["skill", "agent", "rule", "memory"],
                             help="进化维度")
    force_parser.add_argument("target_id", help="目标ID")
    
    args = parser.parse_args()
    
    if args.command == "run":
        run_evolution(args)
    elif args.command == "status":
        show_status(args)
    elif args.command == "confirm":
        confirm_evolution(args)
    elif args.command == "force":
        force_evolve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
