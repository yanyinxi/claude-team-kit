#!/usr/bin/env python3
"""
效果跟踪器 - 跟踪进化改进的有效性

核心功能：
1. 跟踪每条知识的应用次数和成功率
2. 验证改进是否真正有效
3. 自动标记有效/无效知识
4. 支持 8 维度效果跟踪：
   - 核心4维: agent, skill, rule, instinct
   - 扩展4维: performance, interaction, security, context
5. 提供优化建议
6. 成功验证后自动恢复本能记录的置信度（修复衰减不可逆问题）
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

# 导入本能更新器，用于置信度恢复
EVOLVE_DIR = Path(__file__).parent
import importlib.util
spec = importlib.util.spec_from_file_location("instinct_updater", EVOLVE_DIR / "instinct_updater.py")
instinct_mod = importlib.util.module_from_spec(spec)
sys.modules["instinct_updater"] = instinct_mod
spec.loader.exec_module(instinct_mod)

# 支持的维度列表
SUPPORTED_DIMENSIONS = [
    "agent", "skill", "rule", "instinct",
    "performance", "interaction", "security", "context"
]

class EffectTracker:
    """效果跟踪器"""

    def __init__(self, root: Optional[Path] = None):
        import os
        self.root = root or Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
        self.knowledge_dir = self.root / "harness" / "evolve-daemon" / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        self.effects_file = self.knowledge_dir / "effect_tracking.jsonl"
        self.summary_file = self.knowledge_dir / "effect_summary.json"

    def track(self, knowledge_id: str, outcome: str, context: dict = None):
        """
        跟踪一次应用效果。

        成功时自动提升对应本能记录的置信度，打破"只衰减不恢复"的不可逆问题。
        """
        effect = {
            "knowledge_id": knowledge_id,
            "outcome": outcome,  # success | failure | partial
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
        }

        with open(self.effects_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(effect, ensure_ascii=False) + "\n")

        # 实时更新摘要
        self._update_summary(knowledge_id, outcome)

        # 成功时自动恢复本能记录的置信度
        if outcome == "success":
            self._promote_instinct_confidence(knowledge_id)

    def _promote_instinct_confidence(self, knowledge_id: str, boost: float = 0.1):
        """
        当效果跟踪为 success 时，自动提升对应本能记录的置信度。

        这修复了置信度衰减不可逆的问题：验证成功后置信度可以恢复。

        Args:
            knowledge_id: 知识 ID（通常对应 instinct 记录的 id）
            boost: 提升幅度，默认 0.1
        """
        try:
            instinct_mod.promote_confidence(knowledge_id, delta=boost, root=self.root)
        except Exception:
            # 提升失败不阻塞主流程（本能记录可能不存在）
            pass

    def _update_summary(self, knowledge_id: str, outcome: str):
        """更新效果摘要"""
        # 读取现有摘要
        if self.summary_file.exists():
            summary = json.loads(self.summary_file.read_text())
        else:
            summary = {"knowledge_stats": {}, "updated": ""}

        # 初始化或更新统计
        if knowledge_id not in summary["knowledge_stats"]:
            summary["knowledge_stats"][knowledge_id] = {
                "apply_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "partial_count": 0,
            }

        stats = summary["knowledge_stats"][knowledge_id]
        stats["apply_count"] += 1

        if outcome == "success":
            stats["success_count"] += 1
        elif outcome == "failure":
            stats["failure_count"] += 1
        else:
            stats["partial_count"] += 1

        # 计算成功率
        stats["success_rate"] = stats["success_count"] / stats["apply_count"] if stats["apply_count"] > 0 else 0

        # 判断状态
        if stats["apply_count"] >= 3:
            if stats["success_rate"] >= 0.8:
                stats["status"] = "verified"  # 已验证有效
            elif stats["success_rate"] < 0.3:
                stats["status"] = "failed"  # 需要回滚
            else:
                stats["status"] = "active"  # 持续观察
        else:
            stats["status"] = "testing"  # 测试中

        summary["updated"] = datetime.now().isoformat()

        self.summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    def get_summary(self) -> dict:
        """获取效果摘要"""
        if not self.summary_file.exists():
            return {"knowledge_stats": {}}

        return json.loads(self.summary_file.read_text())

    def get_knowledge_status(self, knowledge_id: str) -> dict:
        """获取单条知识的状态"""
        summary = self.get_summary()
        return summary.get("knowledge_stats", {}).get(knowledge_id, {})

    def get_all_verified(self) -> List[str]:
        """获取所有已验证有效的知识ID"""
        summary = self.get_summary()
        return [
            k for k, v in summary.get("knowledge_stats", {}).items()
            if v.get("status") == "verified"
        ]

    def get_all_failed(self) -> List[str]:
        """获取所有验证失败的知识ID"""
        summary = self.get_summary()
        return [
            k for k, v in summary.get("knowledge_stats", {}).items()
            if v.get("status") == "failed"
        ]

    def generate_report(self) -> dict:
        """生成效果报告"""
        summary = self.get_summary()
        stats = summary.get("knowledge_stats", {})

        total_knowledge = len(stats)
        verified = len(self.get_all_verified())
        failed = len(self.get_all_failed())
        testing = len([k for k, v in stats.items() if v.get("status") == "testing"])

        total_applies = sum(v.get("apply_count", 0) for v in stats.values())
        total_successes = sum(v.get("success_count", 0) for v in stats.values())
        overall_rate = total_successes / total_applies if total_applies > 0 else 0

        return {
            "generated_at": datetime.now().isoformat(),
            "total_knowledge": total_knowledge,
            "verified": verified,
            "failed": failed,
            "testing": testing,
            "total_applies": total_applies,
            "total_successes": total_successes,
            "overall_success_rate": round(overall_rate * 100, 1),
            "top_performers": self._get_top_performers(stats, limit=5),
            "needs_attention": self._get_needs_attention(stats),
        }

    def _get_top_performers(self, stats: dict, limit: int = 5) -> List[dict]:
        """获取最佳表现知识"""
        sorted_stats = sorted(
            stats.items(),
            key=lambda x: x[1].get("success_rate", 0),
            reverse=True
        )
        return [
            {
                "knowledge_id": k,
                "success_rate": round(v.get("success_rate", 0) * 100, 1),
                "apply_count": v.get("apply_count", 0),
            }
            for k, v in sorted_stats[:limit]
        ]

    def _get_needs_attention(self, stats: dict) -> List[dict]:
        """获取需要关注的知识"""
        return [
            {
                "knowledge_id": k,
                "status": v.get("status"),
                "success_rate": round(v.get("success_rate", 0) * 100, 1),
                "apply_count": v.get("apply_count", 0),
            }
            for k, v in stats.items()
            if v.get("status") in ["failed", "testing"] and v.get("apply_count", 0) >= 3
        ]

    def print_report(self):
        """打印效果报告"""
        report = self.generate_report()

        print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                  进化效果跟踪报告                              ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  📊 总体统计                                                     ║
║     知识总数:      {report['total_knowledge']:>4}                                      ║
║     已验证有效:    {report['verified']:>4}                                      ║
║     验证失败:      {report['failed']:>4}                                      ║
║     测试中:        {report['testing']:>4}                                      ║
║                                                                  ║
║  📈 应用统计                                                     ║
║     总应用次数:    {report['total_applies']:>4}                                      ║
║     成功次数:      {report['total_successes']:>4}                                      ║
║     整体成功率:    {report['overall_success_rate']:>5.1f}%                                     ║
║                                                                  ║
║  🏆 最佳表现知识                                                 ║""")

        for i, performer in enumerate(report.get("top_performers", [])[:5], 1):
            print(f"║     {i}. {performer['knowledge_id']:<8} 成功率: {performer['success_rate']:>5.1f}%  应用: {performer['apply_count']:>3}次   ║")

        print(f"""║                                                                  ║
║  ⚠️  需要关注                                                    ║""")

        for item in report.get("needs_attention", [])[:5]:
            print(f"║     • {item['knowledge_id']:<8} 状态: {item['status']:<8} 成功率: {item['success_rate']:>5.1f}%  ║")

        print(f"""║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")


def main():
    """测试效果跟踪器"""
    tracker = EffectTracker()

    # 模拟跟踪数据
    test_cases = [
        ("k001", "success"),
        ("k001", "success"),
        ("k001", "failure"),
        ("k002", "success"),
        ("k002", "success"),
        ("k002", "success"),
        ("k003", "failure"),
        ("k003", "failure"),
        ("k003", "failure"),
        ("k001", "success"),
    ]

    print("📊 模拟跟踪效果...")
    for knowledge_id, outcome in test_cases:
        tracker.track(knowledge_id, outcome, {"context": "test"})
        print(f"   跟踪: {knowledge_id} → {outcome}")

    # 生成报告
    tracker.print_report()


if __name__ == "__main__":
    main()
