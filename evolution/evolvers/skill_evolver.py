"""Skill 进化器

根据使用数据自动优化 Skill 内容。
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .base import BaseEvolver, UsageMetrics
from ..engine import EvolutionResult


class SkillEvolver(BaseEvolver):
    """
    Skill 进化器
    
    触发条件：
    - 累计调用 10 次以上
    - 错误率超过 20%
    - 用户主动反馈
    
    改进逻辑：
    - 分析成功/失败模式
    - 提取常见错误类型
    - 更新 SKILL.md 的「进化记录」章节
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.dimension = "skill"
    
    def get_all_targets(self) -> List[str]:
        """获取所有 Skill 名称"""
        skills = []
        if self.config.skills_dir.exists():
            for skill_dir in self.config.skills_dir.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    skills.append(skill_dir.name)
        return skills
    
    def check_evolution_needed(self, skill_name: str) -> bool:
        """检查 Skill 是否需要进化"""
        metrics = self._get_skill_metrics(skill_name)
        trigger = self.config.skill_trigger
        
        # 条件1: 调用次数达标
        if metrics.total_invocations < trigger.min_invocations:
            return False
        
        # 条件2: 错误率超标
        error_rate = metrics.error_count / max(metrics.total_invocations, 1)
        if error_rate >= trigger.min_error_rate:
            return True
        
        # 条件3: 性能下降（执行时间过长）
        if metrics.avg_duration_ms > 10000:  # 超过10秒
            return True
        
        return False
    
    def analyze_performance(self, skill_name: str) -> Dict[str, Any]:
        """分析 Skill 性能"""
        metrics = self._get_skill_metrics(skill_name)
        
        # 加载调用记录分析错误模式
        invocations = self._load_invocations(skill_name)
        error_patterns = self._extract_error_patterns(invocations)
        
        # 计算评分 (1-10)
        success_rate = metrics.success_count / max(metrics.total_invocations, 1)
        score = success_rate * 10
        
        # 根据执行时间扣分
        if metrics.avg_duration_ms > 5000:
            score -= 1
        if metrics.avg_duration_ms > 10000:
            score -= 2
        
        score = max(1, min(10, score))
        
        return {
            "skill_name": skill_name,
            "metrics": metrics,
            "success_rate": success_rate,
            "score": score,
            "error_patterns": error_patterns,
            "total_invocations": metrics.total_invocations,
            "improvement_areas": self._identify_improvements(skill_name, error_patterns)
        }
    
    def generate_improvements(self, skill_name: str, analysis: Dict) -> List[str]:
        """生成改进建议"""
        improvements = []
        error_patterns = analysis.get("error_patterns", [])
        
        for pattern in error_patterns:
            pattern_type = pattern.get("type")
            count = pattern.get("count", 0)
            
            if pattern_type == "missing_context":
                improvements.append(
                    f"添加更详细的上下文说明章节（{count}次反馈）"
                )
            elif pattern_type == "unclear_steps":
                improvements.append(
                    f"简化步骤说明，添加示例（{count}次执行失败）"
                )
            elif pattern_type == "outdated_info":
                improvements.append(
                    f"更新过时信息（{count}次引用失败）"
                )
            elif pattern_type == "missing_error_handling":
                improvements.append(
                    f"添加错误处理章节（{count}次异常）"
                )
        
        # 如果没有具体错误模式，添加通用优化
        if not improvements and analysis.get("score", 0) < 7:
            improvements.append("根据使用数据优化内容结构")
        
        return improvements
    
    def apply_evolution(self, skill_name: str, improvements: List[str]) -> bool:
        """应用 Skill 进化"""
        skill_file = self.config.skills_dir / skill_name / "SKILL.md"
        
        if not skill_file.exists():
            return False
        
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 更新或添加进化记录章节
            content = self._update_evolution_section(content, skill_name, improvements)
            
            # 更新使用数据区块
            content = self._update_usage_section(content, skill_name)
            
            with open(skill_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"更新 Skill 失败 {skill_name}: {e}")
            return False
    
    def _get_skill_metrics(self, skill_name: str) -> UsageMetrics:
        """获取 Skill 使用指标"""
        invocations = self._load_invocations(skill_name)
        
        if not invocations:
            return UsageMetrics()
        
        success_count = sum(1 for inv in invocations if inv.get("success", False))
        error_count = len(invocations) - success_count
        
        durations = [
            inv.get("duration_ms", 0) for inv in invocations
            if inv.get("duration_ms")
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        last_used = max(
            (inv.get("timestamp", "") for inv in invocations),
            default=None
        )
        
        return UsageMetrics(
            total_invocations=len(invocations),
            success_count=success_count,
            error_count=error_count,
            avg_duration_ms=avg_duration,
            last_used=last_used
        )
    
    def _load_invocations(self, skill_name: str) -> List[Dict]:
        """加载 Skill 调用记录"""
        # 从 agent-invocations.jsonl 中筛选
        records = self._load_jsonl(self.config.logs_dir / "agent-invocations.jsonl")
        
        return [
            r for r in records
            if r.get("skill") == skill_name or r.get("agent") == skill_name
        ]
    
    def _extract_error_patterns(self, invocations: List[Dict]) -> List[Dict]:
        """提取错误模式"""
        patterns = {}
        
        for inv in invocations:
            if not inv.get("success", False):
                error_type = inv.get("error_type", "unknown")
                error_msg = inv.get("error", "")
                
                # 分类错误
                if "not found" in error_msg.lower() or "context" in error_msg.lower():
                    key = "missing_context"
                elif "unclear" in error_msg.lower() or "confused" in error_msg.lower():
                    key = "unclear_steps"
                elif "outdated" in error_msg.lower() or "deprecated" in error_msg.lower():
                    key = "outdated_info"
                elif "error" in error_msg.lower() or "exception" in error_msg.lower():
                    key = "missing_error_handling"
                else:
                    key = error_type
                
                patterns[key] = patterns.get(key, 0) + 1
        
        return [
            {"type": k, "count": v} for k, v in sorted(
                patterns.items(), key=lambda x: -x[1]
            )[:5]  # 取前5个
        ]
    
    def _identify_improvements(self, skill_name: str, error_patterns: List[Dict]) -> List[str]:
        """识别改进领域"""
        areas = []
        for pattern in error_patterns:
            areas.append(pattern["type"])
        return areas
    
    def _update_evolution_section(self, content: str, skill_name: str, improvements: List[str]) -> str:
        """更新进化记录章节"""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        
        # 构建新的进化记录条目
        new_entry = f"""
| {timestamp} | {', '.join(improvements[:2])} | 自动分析触发 | 🔄 待验证 |
"""
        
        # 检查是否已有进化记录章节
        if "## 📈 进化记录" in content:
            # 在表格末尾添加新行
            lines = content.split('\n')
            result = []
            in_evolution_table = False
            
            for line in lines:
                result.append(line)
                if "## 📈 进化记录" in line:
                    in_evolution_table = True
                elif in_evolution_table and line.startswith('| --'):
                    # 表格分隔线后，添加新记录
                    result.append(new_entry.strip())
                    in_evolution_table = False
            
            content = '\n'.join(result)
        else:
            # 添加新的进化记录章节
            evolution_section = f"""

## 📈 进化记录（自动更新）

| 时间 | 改进点 | 触发原因 | 验证结果 |
|------|--------|----------|----------|{new_entry}

_此章节由进化系统自动维护_"""
            
            content = content.rstrip() + evolution_section
        
        return content
    
    def _update_usage_section(self, content: str, skill_name: str) -> str:
        """更新使用数据区块"""
        metrics = self._get_skill_metrics(skill_name)
        
        usage_block = f"""## 📊 使用数据（自动更新）

- **调用次数**: {metrics.total_invocations}
- **成功率**: {metrics.success_count}/{metrics.total_invocations} ({100*metrics.success_count/max(metrics.total_invocations,1):.1f}%)
- **平均执行时间**: {metrics.avg_duration_ms/1000:.1f}s
- **最后使用**: {metrics.last_used or 'N/A'}

_此章节由进化系统自动维护_
"""
        
        # 替换或添加使用数据章节
        if "## 📊 使用数据" in content:
            content = re.sub(
                r'## 📊 使用数据.*?(?=## |\Z)',
                usage_block,
                content,
                flags=re.DOTALL
            )
        else:
            # 在文件末尾添加
            content = content.rstrip() + '\n\n' + usage_block
        
        return content
