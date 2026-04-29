"""Memory 进化器

自动提炼和归档关键经验。
"""

import re
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path

from .base import BaseEvolver


class MemoryEvolver(BaseEvolver):
    """
    Memory 进化器
    
    触发条件：
    - 发现新的成功/失败模式
    - 重复出现相同问题
    - 用户标记重要经验
    
    改进逻辑：
    - 分析会话成功因子
    - 提炼通用经验
    - 创建 Memory 文档
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.dimension = "memory"
    
    def get_all_targets(self) -> List[str]:
        """获取可提炼的经验主题"""
        # 从会话数据中识别主题
        sessions = self._load_jsonl(self.config.logs_dir / "sessions.jsonl")
        
        themes = set()
        for session in sessions:
            domain = session.get("primary_domain", "general")
            themes.add(f"{domain}_best_practices")
        
        return list(themes)
    
    def check_evolution_needed(self, theme: str) -> bool:
        """检查是否需要创建/更新 Memory"""
        # 检查是否已有相关 memory
        memory_file = self.config.memory_dir / f"auto_{theme}.md"
        
        sessions = self._load_jsonl(self.config.logs_dir / "sessions.jsonl")
        domain = theme.replace("_best_practices", "")
        
        related_sessions = [
            s for s in sessions
            if s.get("primary_domain") == domain
        ]
        
        # 3次以上相关会话即触发
        if len(related_sessions) >= 3:
            # 如果 memory 已存在且较新，不触发
            if memory_file.exists():
                mtime = memory_file.stat().st_mtime
                from time import time
                if time() - mtime < 86400 * 7:  # 一周内不重复更新
                    return False
            return True
        
        return False
    
    def analyze_performance(self, theme: str) -> Dict[str, Any]:
        """分析主题相关会话"""
        domain = theme.replace("_best_practices", "")
        sessions = self._load_jsonl(self.config.logs_dir / "sessions.jsonl")
        
        related = [s for s in sessions if s.get("primary_domain") == domain]
        
        success_patterns = []
        failure_patterns = []
        
        for session in related:
            signals = session.get("signals", {})
            
            if signals.get("has_tests") and signals.get("commits_in_session"):
                success_patterns.append("测试+提交组合")
            
            if not signals.get("has_tests") and session.get("files_changed", 0) > 10:
                failure_patterns.append("大量改动无测试")
        
        return {
            "theme": theme,
            "domain": domain,
            "session_count": len(related),
            "success_patterns": list(set(success_patterns)),
            "failure_patterns": list(set(failure_patterns)),
            "score": 8.0 if success_patterns else 5.0
        }
    
    def generate_improvements(self, theme: str, analysis: Dict) -> List[str]:
        """生成经验总结"""
        improvements = []
        
        for pattern in analysis.get("success_patterns", []):
            improvements.append(f"成功模式: {pattern}")
        
        for pattern in analysis.get("failure_patterns", []):
            improvements.append(f"避坑指南: {pattern}")
        
        return improvements
    
    def apply_evolution(self, theme: str, improvements: List[str]) -> bool:
        """创建/更新 Memory 文档"""
        memory_file = self.config.memory_dir / f"auto_{theme}.md"
        
        domain = theme.replace("_best_practices", "")
        timestamp = datetime.now().strftime("%Y-%m-%d")
        
        content = f"""# {domain.title()} 领域经验总结

> 由进化系统自动生成于 {timestamp}

## 🎯 成功模式

{chr(10).join(['- ' + imp for imp in improvements if '成功' in imp]) or '- 待积累更多数据'}

## ⚠️ 避坑指南

{chr(10).join(['- ' + imp for imp in improvements if '避坑' in imp]) or '- 待积累更多数据'}

## 📊 数据来源

- 分析会话数: 3+
- 最后更新: {timestamp}

---

_此文档由进化系统自动维护_
"""
        
        try:
            with open(memory_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 同时更新 MEMORY.md 索引
            self._update_memory_index(theme, memory_file.name)
            
            return True
        except Exception as e:
            print(f"创建 Memory 失败 {theme}: {e}")
            return False
    
    def _update_memory_index(self, theme: str, filename: str):
        """更新 Memory 索引"""
        index_file = self.config.memory_dir / "MEMORY.md"
        
        new_entry = f"- [{theme}]({filename}) — 自动生成的{theme.replace('_', ' ')}"
        
        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if filename not in content:
                content = content.rstrip() + f"\n{new_entry}\n"
                with open(index_file, 'w', encoding='utf-8') as f:
                    f.write(content)
        else:
            content = f"""# Memory Index

{new_entry}
"""
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(content)
