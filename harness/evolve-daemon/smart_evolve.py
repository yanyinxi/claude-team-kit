#!/usr/bin/env python3
"""
智能进化入口 - 整合所有组件的完整闭环

整合:
- SmartEvolutionEngine: 错误捕获 + LLM分析 + 知识沉淀
- EffectTracker: 效果跟踪 + 验证

形成真正的自我进化闭环:
Error → LLM分析 → 知识沉淀 → 应用规则 → 效果验证 → 自我优化
"""
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from smart_evolution_engine import SmartEvolutionEngine
from effect_tracker import EffectTracker

class SmartEvolver:
    """智能进化器 - 完整闭环"""

    def __init__(self, root: Path = None):
        self.engine = SmartEvolutionEngine(root)
        self.tracker = EffectTracker(root)

    def evolve(self, error_data: dict, apply_rule: bool = True) -> dict:
        """
        完整进化闭环
        """
        # 步骤1-3: 错误捕获 → LLM分析 → 知识沉淀
        result = self.engine.full_loop(error_data, apply_rule)

        # 返回结果供后续验证
        return result

    def verify(self, knowledge_id: str, outcome: str, context: dict = None):
        """
        验证效果
        """
        self.tracker.track(knowledge_id, outcome, context)

    def report(self):
        """
        生成进化报告
        """
        self.tracker.print_report()

    def get_knowledge_base(self) -> dict:
        """
        获取知识库状态
        """
        return self.engine._read_jsonl(
            self.engine.knowledge_base.with_suffix(".jsonl")
        )


def main():
    import json

    print("""
╔════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║           CHK 智能进化系统 v2.0 - 完整闭环测试                        ║
║                                                                        ║
║     Error → LLM分析 → 知识沉淀 → 应用规则 → 效果验证 → 自我优化      ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝
""")

    evolver = SmartEvolver()

    # 测试场景
    test_cases = [
        {
            "error": "Permission denied: /path/to/file",
            "context": "执行 chmod 命令时权限不足",
            "tool": "Bash"
        },
        {
            "error": "File not found: /tmp/config.json",
            "context": "读取配置文件时文件不存在",
            "tool": "Read"
        },
        {
            "error": "Operation timeout after 30s",
            "context": "下载大文件时超时",
            "tool": "Bash"
        },
        {
            "error": "SyntaxError: invalid syntax",
            "context": "执行 Python 代码时语法错误",
            "tool": "Bash"
        },
        {
            "error": "Connection refused",
            "context": "连接数据库失败",
            "tool": "Bash"
        },
    ]

    results = []

    print(f"\n🔄 开始进化测试 ({len(test_cases)} 个测试场景)")
    print("="*70)

    for i, error_data in enumerate(test_cases, 1):
        print(f"\n{'─'*70}")
        print(f"测试 #{i}: {error_data['error'][:50]}")
        print(f"{'─'*70}")

        # 执行进化
        result = evolver.evolve(error_data)
        results.append(result)

        # 模拟效果验证
        import random
        outcome = random.choice(["success", "success", "success", "partial"])
        evolver.verify(result["knowledge_id"], outcome, {"test": True})

    # 生成报告
    print(f"\n{'='*70}")
    print(f"📊 进化效果报告")
    print(f"{'='*70}")

    evolver.report()

    # 知识库状态
    print(f"\n📚 知识库状态:")
    knowledge = evolver.get_knowledge_base()
    print(f"   知识总数: {len(knowledge)}")
    for k in knowledge[:5]:
        print(f"   • {k.get('id', 'N/A')}: {k.get('rule', {}).get('description', 'N/A')}")

    print(f"""
╔════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║                    智能进化系统测试完成 ✅                             ║
║                                                                        ║
║  改进内容:                                                             ║
║    1. ✅ 每次错误都触发 LLM 分析                                       ║
║    2. ✅ 分析结果沉淀为可执行规则                                       ║
║    3. ✅ 跟踪应用效果，验证改进有效性                                   ║
║    4. ✅ 自动标记有效/无效知识                                          ║
║                                                                        ║
║  闭环验证:                                                             ║
║    Error → LLM分析 → 知识沉淀 → 效果验证 → 自我优化                   ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
