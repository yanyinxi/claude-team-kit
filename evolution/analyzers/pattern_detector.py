"""模式检测器 - 识别重复出现的问题和成功经验"""

from typing import List, Dict, Any
from collections import Counter


class PatternDetector:
    """检测数据中的模式"""
    
    def detect_error_patterns(self, invocations: List[Dict]) -> List[Dict]:
        """检测错误模式"""
        errors = [inv for inv in invocations if not inv.get("success", True)]
        
        # 按错误类型分组
        error_types = Counter(inv.get("error_type", "unknown") for inv in errors)
        
        return [
            {"pattern": error_type, "count": count, "type": "error"}
            for error_type, count in error_types.most_common(5)
        ]
    
    def detect_success_patterns(self, sessions: List[Dict]) -> List[Dict]:
        """检测成功模式"""
        patterns = []
        
        # 检测高成功率组合
        test_and_commit = [
            s for s in sessions
            if s.get("signals", {}).get("has_tests")
            and s.get("signals", {}).get("commits_in_session")
        ]
        
        if len(test_and_commit) > len(sessions) * 0.3:
            patterns.append({
                "pattern": "测试驱动开发",
                "frequency": len(test_and_commit) / max(len(sessions), 1),
                "type": "success"
            })
        
        return patterns
    
    def detect_recurring_issues(self, records: List[Dict], key_field: str) -> List[Dict]:
        """检测反复出现的问题"""
        counter = Counter(r.get(key_field, "unknown") for r in records)
        
        return [
            {"issue": key, "count": count, "severity": "high" if count > 5 else "medium"}
            for key, count in counter.most_common(5)
            if count > 2
        ]
