"""会话数据分析器"""

import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict


class SessionAnalyzer:
    """分析会话日志，提取有价值的洞察"""
    
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
    
    def analyze_trends(self, days: int = 30) -> Dict[str, Any]:
        """分析最近趋势"""
        sessions = self._load_sessions()
        
        # 按时间过滤
        cutoff = datetime.now().timestamp() - days * 86400
        recent = [
            s for s in sessions
            if self._parse_timestamp(s.get("timestamp", "")) > cutoff
        ]
        
        # 按领域统计
        domain_stats = defaultdict(lambda: {"count": 0, "success": 0})
        for session in recent:
            domain = session.get("primary_domain", "unknown")
            domain_stats[domain]["count"] += 1
            signals = session.get("signals", {})
            if signals.get("has_tests") or signals.get("commits_in_session"):
                domain_stats[domain]["success"] += 1
        
        return {
            "total_sessions": len(recent),
            "domain_breakdown": dict(domain_stats),
            "avg_quality_score": self._calculate_quality_score(recent)
        }
    
    def find_success_patterns(self) -> List[Dict]:
        """发现成功模式"""
        sessions = self._load_sessions()
        
        patterns = []
        
        # 分析高成功率组合
        for session in sessions:
            signals = session.get("signals", {})
            
            if signals.get("has_tests") and signals.get("commits_in_session"):
                patterns.append({
                    "pattern": "test_driven_commit",
                    "frequency": patterns.count({"pattern": "test_driven_commit"}) + 1
                })
        
        return patterns
    
    def _load_sessions(self) -> List[Dict]:
        """加载会话记录"""
        sessions_file = self.logs_dir / "sessions.jsonl"
        if not sessions_file.exists():
            return []
        
        sessions = []
        with open(sessions_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    sessions.append(json.loads(line))
                except:
                    continue
        
        return sessions
    
    def _parse_timestamp(self, ts: str) -> float:
        """解析时间戳"""
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return dt.timestamp()
        except:
            return 0
    
    def _calculate_quality_score(self, sessions: List[Dict]) -> float:
        """计算平均质量分"""
        if not sessions:
            return 0.0
        
        total = 0
        for session in sessions:
            signals = session.get("signals", {})
            score = 5.0
            
            if signals.get("has_tests"):
                score += 2
            if signals.get("commits_in_session"):
                score += 2
            
            total += min(10, score)
        
        return total / len(sessions)
