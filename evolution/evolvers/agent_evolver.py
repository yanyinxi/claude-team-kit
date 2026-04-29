"""Agent 进化器

根据执行效果自动优化 Agent 提示词。
"""

import re
from typing import List, Dict, Any
from datetime import datetime

from .base import BaseEvolver


class AgentEvolver(BaseEvolver):
    """
    Agent 进化器
    
    触发条件：
    - 累计执行任务 5 次以上
    - 任务评分低于 7 分
    - 执行时间超过预期
    
    改进逻辑：
    - 分析执行轨迹
    - 识别低效环节
    - 优化提示词结构
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.dimension = "agent"
    
    def get_all_targets(self) -> List[str]:
        """获取所有 Agent"""
        agents = []
        if self.config.agents_dir.exists():
            for agent_file in self.config.agents_dir.glob("*.md"):
                agents.append(agent_file.stem)
        return agents
    
    def check_evolution_needed(self, agent_name: str) -> bool:
        """检查 Agent 是否需要进化"""
        metrics = self._get_agent_metrics(agent_name)
        trigger = self.config.agent_trigger
        
        if metrics.total_invocations < trigger.min_invocations:
            return False
        
        # 评分低于阈值
        avg_score = self._calculate_avg_score(agent_name)
        if avg_score < 7.0:
            return True
        
        # 错误率过高
        error_rate = metrics.error_count / max(metrics.total_invocations, 1)
        if error_rate >= trigger.min_error_rate:
            return True
        
        return False
    
    def analyze_performance(self, agent_name: str) -> Dict[str, Any]:
        """分析 Agent 性能"""
        metrics = self._get_agent_metrics(agent_name)
        avg_score = self._calculate_avg_score(agent_name)
        
        return {
            "agent_name": agent_name,
            "metrics": metrics,
            "avg_score": avg_score,
            "score": avg_score,
            "improvement_areas": self._identify_improvements(agent_name)
        }
    
    def generate_improvements(self, agent_name: str, analysis: Dict) -> List[str]:
        """生成改进建议"""
        improvements = []
        areas = analysis.get("improvement_areas", [])
        
        for area in areas:
            if area == "slow_execution":
                improvements.append("优化执行步骤，减少冗余操作")
            elif area == "poor_output_quality":
                improvements.append("增强输出格式要求和质量标准")
            elif area == "missing_context":
                improvements.append("添加上下文理解章节")
            elif area == "tool_misuse":
                improvements.append("优化工具使用指南")
        
        if not improvements:
            improvements.append("根据执行数据优化提示词结构")
        
        return improvements
    
    def apply_evolution(self, agent_name: str, improvements: List[str]) -> bool:
        """应用 Agent 进化"""
        agent_file = self.config.agents_dir / f"{agent_name}.md"
        
        if not agent_file.exists():
            return False
        
        try:
            with open(agent_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 添加进化元数据
            content = self._update_evolution_metadata(content, agent_name, improvements)
            
            with open(agent_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"更新 Agent 失败 {agent_name}: {e}")
            return False
    
    def _get_agent_metrics(self, agent_name: str):
        """获取 Agent 使用指标"""
        records = self._load_jsonl(self.config.logs_dir / "agent-invocations.jsonl")
        agent_records = [r for r in records if r.get("agent") == agent_name]
        
        if not agent_records:
            from .base import UsageMetrics
            return UsageMetrics()
        
        success_count = sum(1 for r in agent_records if r.get("success", False))
        
        from .base import UsageMetrics
        return UsageMetrics(
            total_invocations=len(agent_records),
            success_count=success_count,
            error_count=len(agent_records) - success_count
        )
    
    def _calculate_avg_score(self, agent_name: str) -> float:
        """计算平均任务评分"""
        # 从 sessions.jsonl 中分析包含此 agent 的会话
        sessions = self._load_jsonl(self.config.logs_dir / "sessions.jsonl")
        
        scores = []
        for session in sessions:
            agents = session.get("signals", {}).get("agents_unique", [])
            if agent_name in agents:
                # 根据会话指标估算评分
                signals = session.get("signals", {})
                score = 8.0  # 基础分
                
                # 调整分数
                if signals.get("has_tests"):
                    score += 0.5
                if signals.get("commits_in_session"):
                    score += 0.5
                
                test_ratio = signals.get("test_ratio", 0)
                score += test_ratio * 2
                
                scores.append(min(10, score))
        
        return sum(scores) / len(scores) if scores else 5.0
    
    def _identify_improvements(self, agent_name: str) -> List[str]:
        """识别改进领域"""
        # 简化实现，实际应分析执行轨迹
        return ["general_optimization"]
    
    def _update_evolution_metadata(self, content: str, agent_name: str, improvements: List[str]) -> str:
        """更新进化元数据"""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        
        # 查找或创建 evolution 区块
        evolution_entry = f"  - {timestamp}: {improvements[0]}"
        
        if "evolution:" in content:
            # 在现有 evolution 区块中添加
            pattern = r'(evolution:.*?optimization_triggers:\s*\n)'
            replacement = r'\1' + evolution_entry + '\n'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            # 在 YAML front matter 后添加 evolution 区块
            if "---" in content:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    yaml_content = parts[1]
                    rest = parts[2]
                    
                    evolution_yaml = f"""
evolution:
  version: 1
  total_tasks: 1
  avg_score: 7.0
  last_optimized: "{timestamp}"
  optimization_triggers:
{evolution_entry}
"""
                    yaml_content = yaml_content.rstrip() + evolution_yaml
                    content = f"---{yaml_content}---{rest}"
        
        return content
