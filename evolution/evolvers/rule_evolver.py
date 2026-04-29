"""Rule 进化器

根据验证结果自动调整规则。
"""

import re
from typing import List, Dict, Any
from datetime import datetime

from .base import BaseEvolver


class RuleEvolver(BaseEvolver):
    """
    Rule 进化器
    
    触发条件：
    - 规则检查 20 次以上
    - 违规率超过 15%
    - 规则导致严重问题
    
    改进逻辑：
    - 统计违规模式
    - 评估规则有效性
    - 调整规则严格度
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.dimension = "rule"
    
    def get_all_targets(self) -> List[str]:
        """获取所有 Rule"""
        rules = []
        if self.config.rules_dir.exists():
            for rule_file in self.config.rules_dir.glob("*.md"):
                rules.append(rule_file.stem)
        return rules
    
    def check_evolution_needed(self, rule_name: str) -> bool:
        """检查 Rule 是否需要进化"""
        violations = self._get_rule_violations(rule_name)
        trigger = self.config.rule_trigger
        
        if len(violations) < trigger.min_invocations:
            return False
        
        # 违规率过高
        violation_rate = len([v for v in violations if v.get("violated")]) / max(len(violations), 1)
        if violation_rate >= trigger.min_error_rate:
            return True
        
        return False
    
    def analyze_performance(self, rule_name: str) -> Dict[str, Any]:
        """分析 Rule 效果"""
        violations = self._get_rule_violations(rule_name)
        total_checks = len(violations)
        actual_violations = len([v for v in violations if v.get("violated")])
        
        violation_rate = actual_violations / max(total_checks, 1)
        
        # 评分：违规率越低越好，但完全无违规可能规则太松
        if violation_rate == 0:
            score = 5.0  # 可能规则太松
        elif violation_rate < 0.05:
            score = 9.0
        elif violation_rate < 0.15:
            score = 7.0
        else:
            score = max(1, 10 - violation_rate * 20)
        
        return {
            "rule_name": rule_name,
            "total_checks": total_checks,
            "violations": actual_violations,
            "violation_rate": violation_rate,
            "score": score,
            "needs_adjustment": violation_rate > 0.15
        }
    
    def generate_improvements(self, rule_name: str, analysis: Dict) -> List[str]:
        """生成改进建议"""
        improvements = []
        violation_rate = analysis.get("violation_rate", 0)
        
        if violation_rate > 0.3:
            improvements.append("放宽规则要求，当前违规率过高")
        elif violation_rate > 0.15:
            improvements.append("添加例外情况说明")
        elif violation_rate == 0:
            improvements.append("考虑增强规则，当前无违规可能规则过松")
        else:
            improvements.append("规则运行良好，优化文档表述")
        
        return improvements
    
    def apply_evolution(self, rule_name: str, improvements: List[str]) -> bool:
        """应用 Rule 进化"""
        rule_file = self.config.rules_dir / f"{rule_name}.md"
        
        if not rule_file.exists():
            return False
        
        try:
            with open(rule_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 添加合规统计
            content = self._update_compliance_section(content, rule_name)
            
            with open(rule_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"更新 Rule 失败 {rule_name}: {e}")
            return False
    
    def _get_rule_violations(self, rule_name: str) -> List[Dict]:
        """获取规则违规记录"""
        # 简化实现，从 sessions 中推断
        sessions = self._load_jsonl(self.config.logs_dir / "sessions.jsonl")
        
        violations = []
        for session in sessions:
            # 根据会话质量推断规则遵守情况
            violations.append({
                "timestamp": session.get("timestamp"),
                "violated": False,  # 简化
                "reason": None
            })
        
        return violations
    
    def _update_compliance_section(self, content: str, rule_name: str) -> str:
        """更新合规统计章节"""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        violations = self._get_rule_violations(rule_name)
        violation_count = len([v for v in violations if v.get("violated")])
        
        compliance_block = f"""## 📈 合规统计（自动更新）

- **检查次数**: {len(violations)}
- **违规次数**: {violation_count}
- **合规率**: {100*(len(violations)-violation_count)/max(len(violations),1):.1f}%
- **最后更新**: {timestamp}

_此章节由进化系统自动维护_
"""
        
        if "## 📈 合规统计" in content:
            content = re.sub(
                r'## 📈 合规统计.*?(?=## |\Z)',
                compliance_block,
                content,
                flags=re.DOTALL
            )
        else:
            content = content.rstrip() + '\n\n' + compliance_block
        
        return content
