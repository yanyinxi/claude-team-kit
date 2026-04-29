"""进化器基类"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import json
from pathlib import Path

from ..config import EvolutionConfig
from ..engine import EvolutionResult


@dataclass
class UsageMetrics:
    """使用指标数据"""
    total_invocations: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_duration_ms: float = 0.0
    last_used: Optional[str] = None


class BaseEvolver(ABC):
    """
    进化器基类
    
    定义所有进化器的通用接口和共享逻辑。
    """
    
    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.dimension: str = "base"
    
    @abstractmethod
    def check_evolution_needed(self, target_id: str) -> bool:
        """检查是否需要进化"""
        pass
    
    @abstractmethod
    def analyze_performance(self, target_id: str) -> Dict[str, Any]:
        """分析性能数据"""
        pass
    
    @abstractmethod
    def generate_improvements(self, target_id: str, analysis: Dict) -> List[str]:
        """生成改进建议"""
        pass
    
    @abstractmethod
    def apply_evolution(self, target_id: str, improvements: List[str]) -> bool:
        """应用进化"""
        pass
    
    @abstractmethod
    def get_all_targets(self) -> List[str]:
        """获取所有可进化目标"""
        pass
    
    def evolve_all(self) -> List[EvolutionResult]:
        """进化所有符合条件的对象"""
        results = []
        
        for target_id in self.get_all_targets():
            if self.check_evolution_needed(target_id):
                result = self._evolve_single(target_id)
                if result:
                    results.append(result)
        
        return results
    
    def force_evolve(self, target_id: str) -> Optional[EvolutionResult]:
        """强制进化指定对象"""
        return self._evolve_single(target_id, force=True)
    
    def _evolve_single(self, target_id: str, force: bool = False) -> Optional[EvolutionResult]:
        """进化单个对象"""
        # 分析性能
        analysis = self.analyze_performance(target_id)
        score_before = analysis.get("score", 5.0)
        
        # 生成改进
        improvements = self.generate_improvements(target_id, analysis)
        
        if not improvements:
            return None
        
        # 检查是否需要人工确认
        needs_confirmation = self._needs_confirmation()
        
        if needs_confirmation and not force:
            # 等待确认，先记录待处理
            return EvolutionResult(
                dimension=self.dimension,
                target_id=target_id,
                success=True,
                changes_made=improvements,
                score_before=score_before,
                score_after=score_before * 1.1,  # 预期提升
                timestamp=datetime.now().isoformat(),
                needs_confirmation=True,
                confirmation_result=None
            )
        
        # 应用进化
        success = self.apply_evolution(target_id, improvements)
        
        return EvolutionResult(
            dimension=self.dimension,
            target_id=target_id,
            success=success,
            changes_made=improvements,
            score_before=score_before,
            score_after=score_before * 1.1 if success else score_before,
            timestamp=datetime.now().isoformat(),
            needs_confirmation=needs_confirmation,
            confirmation_result=True if not needs_confirmation else None
        )
    
    def _needs_confirmation(self) -> bool:
        """判断当前进化是否需要人工确认"""
        # 获取已确认的进化次数
        history_file = self.config.data_dir / "evolution_history.jsonl"
        confirmed_count = 0
        
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    confirmed_count = sum(
                        1 for item in data
                        if item.get("confirmation_result") is not None
                    )
            except:
                pass
        
        # 根据配置判断
        if self.config.confirmation.mode == "never":
            return False
        elif self.config.confirmation.mode == "always":
            return True
        else:  # interactive_first_n
            return confirmed_count < self.config.confirmation.first_n
    
    def _load_jsonl(self, file_path: Path) -> List[Dict]:
        """加载 JSONL 文件"""
        records = []
        if not file_path.exists():
            return records
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"读取文件失败 {file_path}: {e}")
        
        return records
