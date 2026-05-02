#!/usr/bin/env python3
"""paths.py — CHK 全局路径配置服务"""
import os
from pathlib import Path

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

DIR_CLAUDE = ".claude"
DIR_DATA = "data"
DIR_PROPOSALS = "proposals"
DIR_HOOKS = "hooks"
DIR_HOOKS_BIN = "bin"
DIR_SKILLS = "skills"
DIR_AGENTS = "agents"
DIR_RULES = "rules"
DIR_MEMORY = "memory"
DIR_KNOWLEDGE = "knowledge"
DIR_TESTS = "tests"
DIR_DOCS = "docs"
DIR_INSTINCT = "instinct"
DIR_CLI = "cli"
DIR_CLI_MODES = "modes"
DIR_HOMUNCULUS = "homunculus"

FILE_SESSIONS = "sessions.jsonl"
FILE_ERRORS = "error.jsonl"
FILE_ERRORS_LOCK = "error.jsonl.lock"
FILE_FAILURES = "failures.jsonl"
FILE_AGENT_CALLS = "agent_calls.jsonl"
FILE_SKILL_CALLS = "skill_calls.jsonl"
FILE_OBSERVATIONS = "observations.jsonl"
FILE_OBS_ERRORS = "observe_errors.log"
FILE_ANALYSIS_STATE = "analysis_state.json"
FILE_INSTINCT_RECORD = "instinct-record.json"
FILE_SETTINGS_LOCAL = "settings.local.json"
FILE_LIFECYCLE_YAML = "lifecycle.yaml"
FILE_PROPOSAL_HISTORY = "proposal_history.json"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

ROOT = _project_root()
PLUGIN_ROOT = _project_root() / "harness"

CLAUDE_DIR = ROOT / DIR_CLAUDE
DATA_DIR = CLAUDE_DIR / DIR_DATA
PROPOSALS_DIR = CLAUDE_DIR / DIR_PROPOSALS
RATE_LIMITS_DIR = DATA_DIR / "rate-limits"
WORKTREES_DIR = DATA_DIR / "worktrees"
HOMUNCULUS_DIR = DATA_DIR / DIR_HOMUNCULUS

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

SKILLS_DIR = PLUGIN_ROOT / DIR_SKILLS
AGENTS_DIR = PLUGIN_ROOT / DIR_AGENTS
RULES_DIR = PLUGIN_ROOT / DIR_RULES
HOOKS_DIR = PLUGIN_ROOT / DIR_HOOKS
HOOKS_BIN_DIR = HOOKS_DIR / DIR_HOOKS_BIN
MEMORY_DIR = PLUGIN_ROOT / DIR_MEMORY
KNOWLEDGE_DIR = PLUGIN_ROOT / DIR_KNOWLEDGE
TESTS_DIR = PLUGIN_ROOT / DIR_TESTS
DOCS_DIR = PLUGIN_ROOT / DIR_DOCS
INSTINCT_DIR = PLUGIN_ROOT / DIR_INSTINCT
CLI_DIR = PLUGIN_ROOT / DIR_CLI
CLI_MODES_DIR = CLI_DIR / DIR_CLI_MODES
EVOLVE_DIR = PLUGIN_ROOT / "evolve-daemon"
EVOLVE_TEMPLATES_DIR = EVOLVE_DIR / "templates"
EVOLVE_CONFIG_FILE = EVOLVE_DIR / "config.yaml"
EVOLVE_INSTINCT_DIR = EVOLVE_DIR / DIR_INSTINCT
EVOLVE_INSTINCT_FILE = EVOLVE_INSTINCT_DIR / FILE_INSTINCT_RECORD
INSTINCT_FILE = INSTINCT_DIR / FILE_INSTINCT_RECORD
LIFECYCLE_YAML = KNOWLEDGE_DIR / FILE_LIFECYCLE_YAML
SETTINGS_LOCAL = CLAUDE_DIR / FILE_SETTINGS_LOCAL
MCP_JSON = PLUGIN_ROOT / ".mcp.json"
MARKETPLACE_JSON = PLUGIN_ROOT / "marketplace.json"

HOOK_SCRIPTS = {
    "safety-check.sh": HOOKS_BIN_DIR / "safety-check.sh",
    "quality-gate.sh": HOOKS_BIN_DIR / "quality-gate.sh",
    "tdd-check.sh": HOOKS_BIN_DIR / "tdd-check.sh",
    "rate-limiter.sh": HOOKS_BIN_DIR / "rate-limiter.sh",
    "checkpoint-auto-save.sh": HOOKS_BIN_DIR / "checkpoint-auto-save.sh",
    "worktree-sync.sh": HOOKS_BIN_DIR / "worktree-sync.sh",
    "worktree-cleanup.sh": HOOKS_BIN_DIR / "worktree-cleanup.sh",
    "worktree-init.sh": HOOKS_BIN_DIR / "worktree-init.sh",
    "worktree-manager.sh": HOOKS_BIN_DIR / "worktree-manager.sh",
    "observe.sh": HOOKS_BIN_DIR / "observe.sh",
    "security-auto-trigger.sh": HOOKS_BIN_DIR / "security-auto-trigger.sh",
    "collect-failure.py": HOOKS_BIN_DIR / "collect-failure.py",
    "collect-agent.py": HOOKS_BIN_DIR / "collect-agent.py",
    "collect-skill.py": HOOKS_BIN_DIR / "collect-skill.py",
    "collect_session.py": HOOKS_BIN_DIR / "collect_session.py",
    "collect_error.py": HOOKS_BIN_DIR / "collect_error.py",
    "output-secret-filter.py": HOOKS_BIN_DIR / "output-secret-filter.py",
    "context-injector.py": HOOKS_BIN_DIR / "context-injector.py",
    "extract_semantics.py": HOOKS_BIN_DIR / "extract_semantics.py",
    "observe.py": HOOKS_BIN_DIR / "observe.py",
    "auto-start-evolve.py": HOOKS_BIN_DIR / "auto-start-evolve.py",
    "error_writer.py": HOOKS_BIN_DIR / "error_writer.py",
}

__all__ = [
    "DIR_CLAUDE", "DIR_DATA", "DIR_PROPOSALS", "DIR_HOOKS", "DIR_HOOKS_BIN",
    "DIR_SKILLS", "DIR_AGENTS", "DIR_RULES", "DIR_MEMORY", "DIR_KNOWLEDGE",
    "DIR_TESTS", "DIR_DOCS", "DIR_INSTINCT", "DIR_CLI", "DIR_CLI_MODES",
    "DIR_HOMUNCULUS",
    "FILE_SESSIONS", "FILE_ERRORS", "FILE_ERRORS_LOCK", "FILE_FAILURES",
    "FILE_AGENT_CALLS", "FILE_SKILL_CALLS", "FILE_OBSERVATIONS",
    "FILE_OBS_ERRORS", "FILE_ANALYSIS_STATE", "FILE_INSTINCT_RECORD",
    "FILE_SETTINGS_LOCAL", "FILE_LIFECYCLE_YAML", "FILE_PROPOSAL_HISTORY",
    "ANTHROPIC_API_URL",
    "ROOT", "PLUGIN_ROOT",
    "CLAUDE_DIR", "DATA_DIR", "PROPOSALS_DIR", "RATE_LIMITS_DIR", "WORKTREES_DIR",
    "HOMUNCULUS_DIR",
    "SKILLS_DIR", "AGENTS_DIR", "RULES_DIR", "HOOKS_DIR", "HOOKS_BIN_DIR",
    "MEMORY_DIR", "KNOWLEDGE_DIR", "TESTS_DIR", "DOCS_DIR", "INSTINCT_DIR",
    "CLI_DIR", "CLI_MODES_DIR", "EVOLVE_DIR", "EVOLVE_TEMPLATES_DIR",
    "EVOLVE_CONFIG_FILE", "EVOLVE_INSTINCT_DIR", "EVOLVE_INSTINCT_FILE",
    "INSTINCT_FILE", "LIFECYCLE_YAML", "SETTINGS_LOCAL",
    "MCP_JSON", "MARKETPLACE_JSON",
    "sessions_file", "errors_file", "errors_lock_file", "failures_file",
    "agent_calls_file", "skill_calls_file", "analysis_state_file",
    "proposal_history_file", "observations_file", "obs_errors_file",
    "HOOK_SCRIPTS",
]
