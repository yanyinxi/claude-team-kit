#!/usr/bin/env python3
"""paths.py — CHK 全局路径配置服务

本模块是 CHK 系统的路径中枢，所有跨模块的路径引用都应从此处导入，
避免硬编码路径字符串导致的维护问题。

目录结构概览:
    <项目根>
    ├── .claude/                  # Claude Code 运行时数据（sessions、data 等）
    │   ├── data/
    │   └── proposals/
    └── harness/                  # CHK 插件主体
        ├── agents/              # 22 个 Agent 定义
        ├── skills/             # 35+ 个 Skill 集合
        ├── rules/              # 扩展规则
        ├── hooks/              # Hook 配置和脚本
        ├── memory/             # 记忆系统
        ├── knowledge/          # 知识推荐引擎
        ├── instinct/           # 本能记录
        ├── cli/                # 命令行入口
        ├── evolve-daemon/      # 自动进化守护进程
        └── tests/              # 测试套件

路径解析优先级（以 ROOT 为例）:
    1. 环境变量 CLAUDE_PROJECT_DIR（用于 CI/测试覆盖自定义路径）
    2. 默认推导路径（<脚本所在目录>/..）
"""
import os
from pathlib import Path

# ============================================================================
# 路径解析（解析函数，不导出常量）
# ============================================================================

# 脚本文件自身所在目录 → 项目根 = 脚本所在目录的父目录
_SCRIPT_LOCATION = Path(__file__).resolve().parent

def _project_root() -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env_root:
        return Path(env_root)
    return _SCRIPT_LOCATION.parent

def _plugin_root() -> Path:
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if env_root:
        return Path(env_root)
    return _project_root()

# ============================================================================
# 目录名常量（字符串，用于拼接，不涉及文件系统）
# ============================================================================
# 注：这些常量主要用于构造绝对路径字符串，区分不同子目录的语义用途

DIR_CLAUDE = ".claude"            # Claude Code 运行时根目录
DIR_DATA = "data"                 # 会话/错误等数据文件目录
DIR_PROPOSALS = "proposals"       # 进化提案目录（分析结果写入位置）
DIR_HOOKS = "hooks"               # Hook 配置和脚本目录
DIR_HOOKS_BIN = "bin"             # Hook 可执行脚本目录（shell/python）
DIR_SKILLS = "skills"             # Skill 定义目录
DIR_AGENTS = "agents"             # Agent 定义目录
DIR_RULES = "rules"               # 扩展规则目录
DIR_MEMORY = "memory"             # 记忆系统目录
DIR_KNOWLEDGE = "knowledge"       # 知识推荐引擎目录
DIR_TESTS = "tests"               # 测试套件目录
DIR_DOCS = "docs"                 # 设计文档目录
DIR_INSTINCT = "instinct"         # 本能记录目录
DIR_CLI = "cli"                   # CLI 工具入口目录
DIR_CLI_MODES = "modes"           # CLI 执行模式目录（如 solo/team/ultrawork）
DIR_HOMUNCULUS = "homunculus"     # Homunculus 子系统目录（观测/观察者）

# ============================================================================
# 文件名常量（字符串，用于拼接，不涉及文件系统）
# ============================================================================

FILE_SESSIONS = "sessions.jsonl"              # 会话记录（进化数据源）
FILE_ERRORS = "error.jsonl"                   # 错误记录
FILE_ERRORS_LOCK = "error.jsonl.lock"         # 错误文件锁（并发写入保护）
FILE_FAILURES = "failures.jsonl"              # 失败追踪（效果跟踪）
FILE_AGENT_CALLS = "agent_calls.jsonl"         # Agent 调用记录
FILE_SKILL_CALLS = "skill_calls.jsonl"         # Skill 调用记录
FILE_OBSERVATIONS = "observations.jsonl"       # Homunculus 观测数据
FILE_OBS_ERRORS = "observe_errors.log"        # 观测错误日志
FILE_ANALYSIS_STATE = "analysis_state.json"  # 分析状态快照（断点续分析）
FILE_INSTINCT_RECORD = "instinct-record.json" # 本能记录文件
FILE_SETTINGS_LOCAL = "settings.local.json"  # 本地覆盖配置
FILE_LIFECYCLE_YAML = "lifecycle.yaml"        # 知识生命周期配置
FILE_PROPOSAL_HISTORY = "proposal_history.json" # 进化提案历史

# ============================================================================
# API 端点
# ============================================================================

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"  # Anthropic 消息 API

# ============================================================================
# 根路径（模块级常量，供其他模块直接引用）
# ============================================================================
# ROOT: 项目根目录（包含 .claude/ 和 harness/ 的目录）
# PLUGIN_ROOT: harness/ 目录，所有 CHK 插件资产在此之下

ROOT = _project_root()
PLUGIN_ROOT = _project_root() / "harness"

# ============================================================================
# Claude 运行时路径（位于 .claude/ 下）
# ============================================================================
# 这些路径指向 Claude Code 的数据和配置目录

CLAUDE_DIR = ROOT / DIR_CLAUDE            # .claude/ 根目录
DATA_DIR = CLAUDE_DIR / DIR_DATA           # .claude/data/ — 会话和错误数据
PROPOSALS_DIR = CLAUDE_DIR / DIR_PROPOSALS # .claude/proposals/ — 进化提案
RATE_LIMITS_DIR = DATA_DIR / "rate-limits"  # 速率限制数据
WORKTREES_DIR = DATA_DIR / "worktrees"     # Git worktree 工作区数据
HOMUNCULUS_DIR = DATA_DIR / DIR_HOMUNCULUS # .claude/data/homunculus/ — 观测子系统

# ============================================================================
# 动态文件路径工厂函数（每次调用返回新 Path 对象）
# ============================================================================
# 注：使用函数而非模块级常量，避免 Path 对象被意外修改时影响全局状态

def sessions_file() -> Path: return DATA_DIR / FILE_SESSIONS
def errors_file() -> Path: return DATA_DIR / FILE_ERRORS
def errors_lock_file() -> Path: return DATA_DIR / FILE_ERRORS_LOCK
def failures_file() -> Path: return DATA_DIR / FILE_FAILURES
def agent_calls_file() -> Path: return DATA_DIR / FILE_AGENT_CALLS
def skill_calls_file() -> Path: return DATA_DIR / FILE_SKILL_CALLS
def analysis_state_file() -> Path: return DATA_DIR / FILE_ANALYSIS_STATE
def proposal_history_file() -> Path: return DATA_DIR / FILE_PROPOSAL_HISTORY
def observations_file() -> Path: return HOMUNCULUS_DIR / FILE_OBSERVATIONS
def obs_errors_file() -> Path: return HOMUNCULUS_DIR / FILE_OBS_ERRORS

# ============================================================================
# CHK 插件资产路径（位于 harness/ 下）
# ============================================================================

SKILLS_DIR = PLUGIN_ROOT / DIR_SKILLS      # harness/skills/ — 35+ Skill 定义
AGENTS_DIR = PLUGIN_ROOT / DIR_AGENTS      # harness/agents/ — 22 个 Agent 定义
RULES_DIR = PLUGIN_ROOT / DIR_RULES        # harness/rules/ — 扩展规则
HOOKS_DIR = PLUGIN_ROOT / DIR_HOOKS        # harness/hooks/ — Hook 配置
HOOKS_BIN_DIR = HOOKS_DIR / DIR_HOOKS_BIN # harness/hooks/bin/ — Hook 脚本
MEMORY_DIR = PLUGIN_ROOT / DIR_MEMORY      # harness/memory/ — 记忆系统
KNOWLEDGE_DIR = PLUGIN_ROOT / DIR_KNOWLEDGE # harness/knowledge/ — 知识推荐引擎
TESTS_DIR = PLUGIN_ROOT / DIR_TESTS        # harness/tests/ — 测试套件
DOCS_DIR = PLUGIN_ROOT / DIR_DOCS          # harness/docs/ — 设计文档
INSTINCT_DIR = PLUGIN_ROOT / DIR_INSTINCT  # harness/instinct/ — 本能记录
CLI_DIR = PLUGIN_ROOT / DIR_CLI            # harness/cli/ — CLI 入口
CLI_MODES_DIR = CLI_DIR / DIR_CLI_MODES   # harness/cli/modes/ — 7 种执行模式

# ============================================================================
# 进化系统路径（位于 harness/evolve-daemon/ 下）
# ============================================================================
# 注：harness/knowledge/evolved/ 是符号链接，指向 evolve-daemon/knowledge/，
#     保持手工知识和进化知识的目录统一

EVOLVE_DIR = PLUGIN_ROOT / "evolve-daemon"
EVOLVE_TEMPLATES_DIR = EVOLVE_DIR / "templates"        # 进化提案模板
EVOLVE_CONFIG_FILE = EVOLVE_DIR / "config.yaml"        # 进化配置
EVOLVE_INSTINCT_DIR = EVOLVE_DIR / DIR_INSTINCT         # 进化本能目录
EVOLVE_INSTINCT_FILE = EVOLVE_INSTINCT_DIR / FILE_INSTINCT_RECORD

# ============================================================================
# 其他插件路径
# ============================================================================

INSTINCT_FILE = INSTINCT_DIR / FILE_INSTINCT_RECORD   # 本能记录文件
LIFECYCLE_YAML = KNOWLEDGE_DIR / FILE_LIFECYCLE_YAML  # 知识生命周期配置
SETTINGS_LOCAL = CLAUDE_DIR / FILE_SETTINGS_LOCAL      # 本地配置覆盖
MCP_JSON = PLUGIN_ROOT / ".mcp.json"                  # MCP 服务器配置
MARKETPLACE_JSON = PLUGIN_ROOT / "marketplace.json"    # 市场配置

# ============================================================================
# Hook 脚本映射（命令名 → 脚本路径）
# ============================================================================
# 通过名称引用而非硬编码路径，便于 Hook 配置集中管理。
# scripts.json 中引用脚本名称，运行时解析为实际路径。

HOOK_SCRIPTS = {
    # ── 安全/质量门禁 ──────────────────────────────────────────────
    "safety-check.sh": HOOKS_BIN_DIR / "safety-check.sh",       # 前置安全检查
    "quality-gate.sh": HOOKS_BIN_DIR / "quality-gate.sh",       # 质量门禁
    "tdd-check.sh": HOOKS_BIN_DIR / "tdd-check.sh",             # TDD 检查
    "rate-limiter.sh": HOOKS_BIN_DIR / "rate-limiter.sh",       # API 速率限制

    # ── 自动保存/检查点 ─────────────────────────────────────────────
    "checkpoint-auto-save.sh": HOOKS_BIN_DIR / "checkpoint-auto-save.sh",  # 自动保存

    # ── Worktree 管理 ──────────────────────────────────────────────
    "worktree-sync.sh": HOOKS_BIN_DIR / "worktree-sync.sh",     # 工作区同步
    "worktree-cleanup.sh": HOOKS_BIN_DIR / "worktree-cleanup.sh",  # 工作区清理
    "worktree-init.sh": HOOKS_BIN_DIR / "worktree-init.sh",     # 工作区初始化
    "worktree-manager.sh": HOOKS_BIN_DIR / "worktree-manager.sh",  # 工作区管理器

    # ── 观测系统 ──────────────────────────────────────────────────
    "observe.sh": HOOKS_BIN_DIR / "observe.sh",                 # 观测 Hook
    "observe.py": HOOKS_BIN_DIR / "observe.py",                 # 观测（Python 版）

    # ── 安全自动触发 ──────────────────────────────────────────────
    "security-auto-trigger.sh": HOOKS_BIN_DIR / "security-auto-trigger.sh",  # 安全扫描触发

    # ── 数据收集 ──────────────────────────────────────────────────
    "collect-failure.py": HOOKS_BIN_DIR / "collect-failure.py", # 失败收集
    "collect-agent.py": HOOKS_BIN_DIR / "collect-agent.py",       # Agent 调用收集
    "collect-skill.py": HOOKS_BIN_DIR / "collect-skill.py",     # Skill 调用收集
    "collect_session.py": HOOKS_BIN_DIR / "collect_session.py",  # 会话收集
    "collect_error.py": HOOKS_BIN_DIR / "collect_error.py",     # 错误收集

    # ── 安全过滤 ──────────────────────────────────────────────────
    "output-secret-filter.py": HOOKS_BIN_DIR / "output-secret-filter.py",  # 敏感信息过滤

    # ── 上下文注入 ────────────────────────────────────────────────
    "context-injector.py": HOOKS_BIN_DIR / "context-injector.py",  # 知识注入
    "extract_semantics.py": HOOKS_BIN_DIR / "extract_semantics.py",  # 语义提取

    # ── 进化自动触发 ──────────────────────────────────────────────
    "auto-start-evolve.py": HOOKS_BIN_DIR / "auto-start-evolve.py",  # 进化守护进程触发

    # ── 错误处理 ──────────────────────────────────────────────────
    "error_writer.py": HOOKS_BIN_DIR / "error_writer.py",       # 错误写入
}


def validate_paths(project_root: Path | None = None) -> dict:
    """
    验证 CHK 系统关键路径是否存在，启动时健康检查。

    检查 8 个关键目录和 3 个关键数据文件，返回详细诊断结果。
    适用于：CI 检查、启动自检、调试路径问题。

    参数:
        project_root: 项目根目录，默认为 ROOT（即 _project_root() 的返回值）。
                      传入用于测试覆盖自定义路径。

    返回值字典结构:
        all_valid (bool)       — 所有关键路径是否存在且为目录
        missing_paths (list)   — 不存在的路径列表（含用途描述）
        existing_paths (list)  — 存在的路径列表（含用途描述）
        warnings (list)         — 所有警告信息（缺失 + 非目录 + 建议）
        invalid_paths (list)   — 无效路径（缺失或非目录）

    示例:
        >>> result = validate_paths()
        >>> if not result["all_valid"]:
        ...     print("缺失:", result["missing_paths"])
    """
    from typing import Any

    root = project_root if project_root else ROOT

    # 定义关键路径及其用途说明
    critical_paths = {
        "data_dir": (DATA_DIR, "数据文件目录"),
        "skills_dir": (SKILLS_DIR, "Skill 定义目录"),
        "agents_dir": (AGENTS_DIR, "Agent 定义目录"),
        "rules_dir": (RULES_DIR, "规则文件目录"),
        "hooks_dir": (HOOKS_DIR, "Hook 脚本目录"),
        "tests_dir": (TESTS_DIR, "测试目录"),
        "evolve_dir": (EVOLVE_DIR, "进化守护进程目录"),
    }

    result: dict[str, Any] = {
        "all_valid": True,
        "missing_paths": [],
        "existing_paths": [],
        "warnings": [],
        "invalid_paths": [],
    }

    for name, (path, description) in critical_paths.items():
        # 转换相对路径为绝对路径（如果需要）
        if not path.is_absolute():
            abs_path = root / path
        else:
            abs_path = path

        if abs_path.exists():
            result["existing_paths"].append({
                "name": name,
                "path": str(abs_path),
                "description": description,
            })
            # 检查是否为目录
            if not abs_path.is_dir():
                result["warnings"].append(f"{name} ({abs_path}) 存在但不是目录")
                result["invalid_paths"].append({"name": name, "path": str(abs_path)})
                result["all_valid"] = False
        else:
            result["missing_paths"].append({
                "name": name,
                "path": str(abs_path),
                "description": description,
            })
            result["warnings"].append(f"缺失关键路径: {name} ({abs_path}) - {description}")
            result["invalid_paths"].append({"name": name, "path": str(abs_path)})
            result["all_valid"] = False

    # 检查数据文件是否存在
    data_dir_abs = root / DATA_DIR if not DATA_DIR.is_absolute() else DATA_DIR
    if data_dir_abs.exists():
        key_files = {
            "sessions": "sessions.jsonl",
            "errors": "error.jsonl",
            "failures": "failures.jsonl",
        }
        for key, filename in key_files.items():
            file_path = data_dir_abs / filename
            if file_path.exists():
                result["existing_paths"].append({
                    "name": f"data_file_{key}",
                    "path": str(file_path),
                    "description": f"数据文件: {filename}",
                })
            else:
                result["warnings"].append(f"建议创建数据文件: {filename}")

    return result


def warn_missing_paths(project_root: Path | None = None) -> list[str]:
    """
    返回缺失路径的警告信息列表，轻量级健康检查。

    参数:
        project_root: 项目根目录，默认使用 ROOT

    返回:
        list: 警告字符串列表，如 ["缺失关键路径: skills_dir (/path/to/skills) - Skill 定义目录"]
    """
    validation = validate_paths(project_root)
    return validation.get("warnings", [])

__all__ = [
    # ── 目录名常量（字符串，语义标识）─────────────────────────────────
    "DIR_CLAUDE", "DIR_DATA", "DIR_PROPOSALS", "DIR_HOOKS", "DIR_HOOKS_BIN",
    "DIR_SKILLS", "DIR_AGENTS", "DIR_RULES", "DIR_MEMORY", "DIR_KNOWLEDGE",
    "DIR_TESTS", "DIR_DOCS", "DIR_INSTINCT", "DIR_CLI", "DIR_CLI_MODES",
    "DIR_HOMUNCULUS",
    # ── 文件名常量（字符串，语义标识）─────────────────────────────────
    "FILE_SESSIONS", "FILE_ERRORS", "FILE_ERRORS_LOCK", "FILE_FAILURES",
    "FILE_AGENT_CALLS", "FILE_SKILL_CALLS", "FILE_OBSERVATIONS",
    "FILE_OBS_ERRORS", "FILE_ANALYSIS_STATE", "FILE_INSTINCT_RECORD",
    "FILE_SETTINGS_LOCAL", "FILE_LIFECYCLE_YAML", "FILE_PROPOSAL_HISTORY",
    "ANTHROPIC_API_URL",
    # ── 根路径常量（Path 对象）───────────────────────────────────────
    "ROOT", "PLUGIN_ROOT",
    # ── .claude/ 下路径（Path 对象）──────────────────────────────────
    "CLAUDE_DIR", "DATA_DIR", "PROPOSALS_DIR", "RATE_LIMITS_DIR", "WORKTREES_DIR",
    "HOMUNCULUS_DIR",
    # ── harness/ 下路径（Path 对象）──────────────────────────────────
    "SKILLS_DIR", "AGENTS_DIR", "RULES_DIR", "HOOKS_DIR", "HOOKS_BIN_DIR",
    "MEMORY_DIR", "KNOWLEDGE_DIR", "TESTS_DIR", "DOCS_DIR", "INSTINCT_DIR",
    "CLI_DIR", "CLI_MODES_DIR", "EVOLVE_DIR", "EVOLVE_TEMPLATES_DIR",
    "EVOLVE_CONFIG_FILE", "EVOLVE_INSTINCT_DIR", "EVOLVE_INSTINCT_FILE",
    "INSTINCT_FILE", "LIFECYCLE_YAML", "SETTINGS_LOCAL",
    "MCP_JSON", "MARKETPLACE_JSON",
    # ── 动态文件路径工厂函数（返回新 Path 对象）────────────────────
    "sessions_file", "errors_file", "errors_lock_file", "failures_file",
    "agent_calls_file", "skill_calls_file", "analysis_state_file",
    "proposal_history_file", "observations_file", "obs_errors_file",
    # ── Hook 映射表（名称 → 脚本路径）──────────────────────────────
    "HOOK_SCRIPTS",
    # ── 工具函数 ────────────────────────────────────────────────────
    "validate_paths", "warn_missing_paths",
]
