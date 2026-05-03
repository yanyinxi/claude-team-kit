#!/usr/bin/env python3
"""
CHK 进化模拟器 v5 - 详细对比版
输出每次进化的: 原始状态 → 进化后状态
"""
import random
from datetime import datetime
from pathlib import Path

class DetailedEvolutionTracker:
    """详细进化追踪器 - 记录每次变化"""

    def __init__(self):
        # 原始状态快照
        self.snapshots = {
            "agent": {
                "threshold": 3,
                "prefixes": ["agent:"],
                "prompt_templates": ["基础模板 v1"],
                "error_handling": ["基础错误处理"]
            },
            "skill": {
                "threshold": 3,
                "templates": ["默认模板 v1"],
                "context_awareness": ["简单匹配"],
                "triggers": ["keyword:v1"]
            },
            "rule": {
                "threshold": 5,
                "strictness": 0.8,
                "weights": {"security": 1.0, "quality": 1.0},
                "patterns": ["基础匹配 v1"]
            },
            "instinct": {
                "threshold": 2,
                "patterns": ["pattern_v1"],
                "confidence_threshold": 0.5,
                "learning_rate": 0.1
            }
        }

        # 进化历史
        self.evolutions = []
        self.dimensions = ["agent", "skill", "rule", "instinct"]

    def get_snapshot(self, dimension: str) -> dict:
        """获取当前快照"""
        import copy
        return copy.deepcopy(self.snapshots[dimension])

    def apply_evolution(self, dimension: str, action: str):
        """应用进化并记录"""
        snapshot_before = self.get_snapshot(dimension)

        # 根据动作更新状态
        if "调整阈值" in action or "threshold" in action.lower():
            self.snapshots[dimension]["threshold"] += 1

        if "优化提示词" in action or "模板" in action:
            current = self.snapshots[dimension].get("prompt_templates", ["v1"])[-1]
            version = int(current[-1]) + 1 if current[-1].isdigit() else 2
            new_template = current.replace("v1", f"v{version}").replace("v2", "v3").replace("v3", "v4")
            if "prompt_templates" in self.snapshots[dimension]:
                self.snapshots[dimension]["prompt_templates"].append(f"优化模板 v{version}")
            else:
                self.snapshots[dimension]["templates"] = self.snapshots[dimension].get("templates", []) + [f"v{version}"]

        if "增强" in action or "增强" in action:
            if "error_handling" in self.snapshots[dimension]:
                self.snapshots[dimension]["error_handling"].append(f"增强处理 v{len(self.snapshots[dimension]['error_handling'])+1}")

        if "更新权重" in action:
            self.snapshots[dimension]["weights"] = {k: v * 1.1 for k, v in self.snapshots[dimension]["weights"].items()}

        if "调整严格度" in action:
            self.snapshots[dimension]["strictness"] = min(1.0, self.snapshots[dimension]["strictness"] + 0.1)

        if "添加模式" in action or "模式" in action:
            self.snapshots[dimension]["patterns"] = self.snapshots[dimension].get("patterns", []) + [f"new_pattern_{len(self.evolutions)+1}"]

        if "置信度" in action:
            self.snapshots[dimension]["confidence_threshold"] = min(1.0, self.snapshots[dimension]["confidence_threshold"] + 0.1)

        snapshot_after = self.get_snapshot(dimension)

        # 记录进化
        self.evolutions.append({
            "dimension": dimension,
            "action": action,
            "before": snapshot_before,
            "after": snapshot_after,
            "timestamp": datetime.now().isoformat()
        })

        return snapshot_before, snapshot_after

def run_detailed_evolution():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║          CHK 自动化进化迭代闭环 - 详细对比版 v5                            ║
║          输出: 原始状态 → 进化后状态 (每次变化都记录)                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    tracker = DetailedEvolutionTracker()
    dimensions_config = {
        "agent": {"threshold": 3, "errors": ["架构错误", "实现不完整", "测试缺失"]},
        "skill": {"threshold": 3, "errors": ["模板错误", "上下文丢失", "超时"]},
        "rule": {"threshold": 5, "errors": ["安全违规", "质量门禁失败", "TDD违反"]},
        "instinct": {"threshold": 2, "errors": ["新模式", "低置信度", "上下文漂移"]}
    }

    # 运行每个维度 3 轮，每轮触发进化
    for dim in ["agent", "skill", "rule", "instinct"]:
        config = dimensions_config[dim]
        threshold = config["threshold"]
        errors = config["errors"]

        print(f"\n{'='*75}")
        print(f"📐 维度: {dim.upper()} | 阈值: {threshold}")
        print(f"{'='*75}")

        # 运行到触发进化
        correction_count = 0
        evolution_num = 0

        while evolution_num < 3:  # 每维度触发3次进化
            for i in range(threshold + 1):
                correction_count += 1
                error = random.choice(errors)

                if (correction_count % threshold == 0):
                    # 触发进化
                    evolution_num += 1
                    print(f"\n  ╭──────────────────────────────────────────────────────────────────╮")
                    print(f"  │ ⚡ 进化 #{evolution_num} | 纠正 #{correction_count} | 错误: {error:<15} │")
                    print(f"  ╰──────────────────────────────────────────────────────────────────╯")

                    # 生成进化动作
                    actions_map = {
                        "agent": ["调整阈值", "优化提示词", "增强错误处理"],
                        "skill": ["更新模板", "增强上下文", "优化触发"],
                        "rule": ["调整严格度", "更新权重", "优化匹配"],
                        "instinct": ["添加模式", "增强置信度", "更新库"]
                    }
                    actions = actions_map[dim][:evolution_num]

                    # 应用进化并对比
                    print(f"\n  【进化前状态】→ 【进化后状态】")
                    print(f"  {'─'*70}")

                    for action in actions:
                        before, after = tracker.apply_evolution(dim, action)
                        print(f"\n  📌 动作: {action}")
                        print(f"     原始值: {before}")
                        print(f"     进化后: {after}")

                    print(f"\n  {'─'*70}")

            print(f"\n  📊 {dim.upper()} 累计进化: {evolution_num} 次")

    # ================================================================
    # 最终详细对比报告
    # ================================================================
    print(f"\n{'='*75}")
    print(f"📊 完整进化对比报告")
    print(f"{'='*75}")

    for dim in ["agent", "skill", "rule", "instinct"]:
        dim_evolutions = [e for e in tracker.evolutions if e["dimension"] == dim]

        print(f"\n【{dim.upper()}】")
        print(f"  进化次数: {len(dim_evolutions)}")

        # 显示最终状态
        final_state = tracker.snapshots[dim]
        print(f"  最终状态:")
        for key, value in final_state.items():
            print(f"    • {key}: {value}")

    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                          详细进化对比完成                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                        ║
║  总进化次数: {len(tracker.evolutions)}                                                   ║
║  维度覆盖:   {len(set(e['dimension'] for e in tracker.evolutions))}/4                                                   ║
║                                                                        ║
║  结论: 每次进化的具体内容已详细记录并对比                                   ║
║                                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    run_detailed_evolution()