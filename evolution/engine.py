"""进化引擎主控

负责协调所有维度的进化过程：
- Skills 进化（使用反馈驱动）
- Agents 进化（执行效果驱动）  
- Rules 进化（验证结果驱动）
- Memory 进化（经验提炼驱动）
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from .config import EvolutionConfig


@dataclass
class EvolutionResult:
    """进化结果记录"""
    dimension: str           # skill/agent/rule/memory
    target_id: str           # 被进化的对象ID
    success: bool            # 是否成功
    changes_made: List[str]  # 具体改动
    score_before: float      # 进化前评分
    score_after: float       # 进化后评分（预期）
    timestamp: str
    needs_confirmation: bool # 是否需要人工确认
    confirmation_result: Optional[bool] = None  # 人工确认结果


class EvolutionEngine:
    """
    进化引擎主控类
    
    职责：
    1. 协调各维度进化器的执行
    2. 管理进化历史记录
    3. 提供进化状态查询
    4. 触发进化流程
    """
    
    def __init__(self, config: Optional[EvolutionConfig] = None):
        self.config = config or EvolutionConfig()
        self.logger = self._setup_logger()
        
        # 延迟导入以避免循环依赖
        from .evolvers.skill_evolver import SkillEvolver
        from .evolvers.agent_evolver import AgentEvolver
        from .evolvers.rule_evolver import RuleEvolver
        from .evolvers.memory_evolver import MemoryEvolver
        
        # 初始化各维度进化器
        self.skill_evolver = SkillEvolver(self.config)
        self.agent_evolver = AgentEvolver(self.config)
        self.rule_evolver = RuleEvolver(self.config)
        self.memory_evolver = MemoryEvolver(self.config)
        
        self._evolution_history: List[EvolutionResult] = []
        self._load_history()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger("evolution")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _load_history(self):
        """加载进化历史"""
        history_file = self.config.data_dir / "evolution_history.jsonl"
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._evolution_history = [
                        EvolutionResult(**item) for item in data
                    ]
            except Exception as e:
                self.logger.warning(f"无法加载进化历史: {e}")
    
    def _save_history(self):
        """保存进化历史"""
        history_file = self.config.data_dir / "evolution_history.jsonl"
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(
                    [asdict(r) for r in self._evolution_history],
                    f, indent=2, ensure_ascii=False
                )
        except Exception as e:
            self.logger.error(f"保存进化历史失败: {e}")
    
    def run_full_cycle(self) -> Dict[str, List[EvolutionResult]]:
        """
        运行完整进化周期
        
        依次检查并触发：
        1. Skill 进化
        2. Agent 进化
        3. Rule 进化
        4. Memory 进化
        
        Returns:
            各维度的进化结果字典
        """
        self.logger.info("=" * 50)
        self.logger.info("开始完整进化周期")
        self.logger.info("=" * 50)
        
        results = {
            "skills": self._evolve_skills(),
            "agents": self._evolve_agents(),
            "rules": self._evolve_rules(),
            "memories": self._evolve_memories()
        }
        
        # 保存历史记录
        all_results = []
        for dim_results in results.values():
            all_results.extend(dim_results)
            self._evolution_history.extend(dim_results)
        
        if all_results:
            self._save_history()
        
        self.logger.info("=" * 50)
        self.logger.info(f"进化周期完成: {len(all_results)} 项进化")
        self.logger.info("=" * 50)
        
        return results
    
    def _evolve_skills(self) -> List[EvolutionResult]:
        """执行 Skill 进化"""
        self.logger.info("[Skills] 检查进化条件...")
        return self.skill_evolver.evolve_all()
    
    def _evolve_agents(self) -> List[EvolutionResult]:
        """执行 Agent 进化"""
        self.logger.info("[Agents] 检查进化条件...")
        return self.agent_evolver.evolve_all()
    
    def _evolve_rules(self) -> List[EvolutionResult]:
        """执行 Rule 进化"""
        self.logger.info("[Rules] 检查进化条件...")
        return self.rule_evolver.evolve_all()
    
    def _evolve_memories(self) -> List[EvolutionResult]:
        """执行 Memory 进化"""
        self.logger.info("[Memory] 检查进化条件...")
        return self.memory_evolver.evolve_all()
    
    def get_evolution_stats(self) -> Dict[str, Any]:
        """获取进化统计信息"""
        stats = {
            "total_evolutions": len(self._evolution_history),
            "by_dimension": {},
            "success_rate": 0.0,
            "pending_confirmations": 0
        }
        
        for result in self._evolution_history:
            dim = result.dimension
            if dim not in stats["by_dimension"]:
                stats["by_dimension"][dim] = {
                    "total": 0, "success": 0, "pending": 0
                }
            
            stats["by_dimension"][dim]["total"] += 1
            if result.success:
                stats["by_dimension"][dim]["success"] += 1
            if result.needs_confirmation and result.confirmation_result is None:
                stats["by_dimension"][dim]["pending"] += 1
                stats["pending_confirmations"] += 1
        
        if stats["total_evolutions"] > 0:
            success_count = sum(
                1 for r in self._evolution_history if r.success
            )
            stats["success_rate"] = success_count / stats["total_evolutions"]
        
        return stats
    
    def get_pending_confirmations(self) -> List[EvolutionResult]:
        """获取待确认进化列表"""
        return [
            r for r in self._evolution_history
            if r.needs_confirmation and r.confirmation_result is None
        ]
    
    def confirm_evolution(self, target_id: str, approved: bool) -> bool:
        """确认或拒绝进化"""
        for result in self._evolution_history:
            if result.target_id == target_id and result.confirmation_result is None:
                result.confirmation_result = approved
                self._save_history()
                
                if approved:
                    self.logger.info(f"✅ 进化已确认: {target_id}")
                else:
                    self.logger.info(f"❌ 进化已拒绝: {target_id}")
                
                return True
        
        return False
    
    def force_evolve(self, dimension: str, target_id: str) -> Optional[EvolutionResult]:
        """强制触发指定对象的进化"""
        evolvers = {
            "skill": self.skill_evolver,
            "agent": self.agent_evolver,
            "rule": self.rule_evolver,
            "memory": self.memory_evolver
        }
        
        evolver = evolvers.get(dimension)
        if not evolver:
            self.logger.error(f"未知维度: {dimension}")
            return None
        
        return evolver.force_evolve(target_id)
