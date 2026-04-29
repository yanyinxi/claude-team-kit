"""进化系统配置管理"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import json


@dataclass
class TriggerConfig:
    """进化触发器配置"""
    min_invocations: int = 10      # 最小调用次数
    min_error_rate: float = 0.2    # 最小错误率触发
    auto_update_after_confirmations: int = 10  # 自动更新前的确认次数


@dataclass
class ConfirmationConfig:
    """人工确认配置"""
    mode: str = "interactive_first_n"  # interactive_first_n | always | never
    first_n: int = 10                  # 前N次需要确认


@dataclass
class EvolutionConfig:
    """进化系统全局配置"""
    
    # 触发器配置
    skill_trigger: TriggerConfig = field(default_factory=lambda: TriggerConfig(
        min_invocations=10,
        min_error_rate=0.2,
        auto_update_after_confirmations=10
    ))
    
    agent_trigger: TriggerConfig = field(default_factory=lambda: TriggerConfig(
        min_invocations=5,
        min_error_rate=0.25,
        auto_update_after_confirmations=5
    ))
    
    rule_trigger: TriggerConfig = field(default_factory=lambda: TriggerConfig(
        min_invocations=20,
        min_error_rate=0.15,
        auto_update_after_confirmations=20
    ))
    
    memory_trigger: TriggerConfig = field(default_factory=lambda: TriggerConfig(
        min_invocations=3,
        min_error_rate=0.0,
        auto_update_after_confirmations=0
    ))
    
    # 确认配置
    confirmation: ConfirmationConfig = field(default_factory=lambda: ConfirmationConfig(
        mode="interactive_first_n",
        first_n=10
    ))
    
    # 路径配置
    project_root: Path = field(default_factory=lambda: Path("."))
    
    @property
    def claude_dir(self) -> Path:
        return self.project_root / ".claude"
    
    @property
    def logs_dir(self) -> Path:
        return self.claude_dir / "logs"
    
    @property
    def skills_dir(self) -> Path:
        return self.claude_dir / "skills"
    
    @property
    def agents_dir(self) -> Path:
        return self.claude_dir / "agents"
    
    @property
    def rules_dir(self) -> Path:
        return self.claude_dir / "rules"
    
    @property
    def memory_dir(self) -> Path:
        return self.claude_dir / "memory"
    
    @property
    def data_dir(self) -> Path:
        return self.claude_dir / "data"
    
    def save(self, path: Optional[Path] = None):
        """保存配置到文件"""
        save_path = path or self.claude_dir / "evolution" / "config.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        config_dict = {
            "skill_trigger": self.skill_trigger.__dict__,
            "agent_trigger": self.agent_trigger.__dict__,
            "rule_trigger": self.rule_trigger.__dict__,
            "memory_trigger": self.memory_trigger.__dict__,
            "confirmation": self.confirmation.__dict__,
        }
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> "EvolutionConfig":
        """从文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        config = cls()
        config.skill_trigger = TriggerConfig(**data.get("skill_trigger", {}))
        config.agent_trigger = TriggerConfig(**data.get("agent_trigger", {}))
        config.rule_trigger = TriggerConfig(**data.get("rule_trigger", {}))
        config.memory_trigger = TriggerConfig(**data.get("memory_trigger", {}))
        config.confirmation = ConfirmationConfig(**data.get("confirmation", {}))
        
        return config
