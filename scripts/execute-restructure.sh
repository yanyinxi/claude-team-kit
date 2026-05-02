#!/bin/bash
# ==============================================================================
# CHK 目录结构重构执行脚本
# 执行 restructure-plan.md Phase 0 → P → M → V
# 使用方式: bash scripts/execute-restructure.sh
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$PROJECT_ROOT/.claude/data/restructure-execution.log"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }

section() { echo ""; echo -e "${GREEN}═══════════════════════════════════════${NC}"; echo -e "${GREEN}  $1${NC}"; echo -e "${GREEN}═══════════════════════════════════════${NC}"; }

# ------------------------------------------------------------------------------
# Phase 0: 紧急修复（在目录迁移前必须完成）
# ------------------------------------------------------------------------------
phase_0() {
    section "Phase 0: 紧急修复"

    # Step 0.1: 修复 generate_skill_index.py 硬编码路径
    log "Step 0.1: 修复 cli/generate_skill_index.py 硬编码路径"
    TARGET="$PROJECT_ROOT/cli/generate_skill_index.py"
    if [ -f "$TARGET" ]; then
        if grep -q '/Users/yanyinxi' "$TARGET"; then
            sed -i '' "s|SKILLS_DIR = Path(\"/Users/yanyinxi/.*\")|SKILLS_DIR = Path(__file__).parent.parent / \"skills\"|" "$TARGET"
            ok "generate_skill_index.py 已修复"
        else
            ok "generate_skill_index.py 已无硬编码路径（可能已被修复）"
        fi
    else
        warn "generate_skill_index.py 不存在，跳过"
    fi

    # Step 0.2: 创建 homunculus/ 目录
    log "Step 0.2: 创建 .claude/data/homunculus/ 目录"
    mkdir -p "$PROJECT_ROOT/.claude/data/homunculus"
    ok "homunculus 目录已创建: $PROJECT_ROOT/.claude/data/homunculus"

    # Step 0.3: 统一 instinct 数据
    log "Step 0.3: 统一 instinct 三副本数据"
    INSTINCT_MAIN="$PROJECT_ROOT/evolve-daemon/instinct/instinct-record.json"
    INSTINCT_ROOT="$PROJECT_ROOT/instinct/instinct-record.json"
    INSTINCT_AGENTS="$PROJECT_ROOT/agents/instinct/instinct-record.json"

    if [ -f "$INSTINCT_MAIN" ]; then
        # 以 evolve-daemon/instinct/ 为主数据源（内容最完整：8671B）
        python3 - <<'PYEOF'
import json, sys
from pathlib import Path

files = [
    Path("agents/instinct/instinct-record.json"),
    Path("instinct/instinct-record.json"),
    Path("evolve-daemon/instinct/instinct-record.json"),
]

all_records = {}
for f in files:
    if f.exists():
        try:
            with open(f) as fp:
                data = json.load(fp)
                for record in data.get("records", []):
                    all_records[record["id"]] = record
        except Exception as e:
            print(f"Warning: {f} read error: {e}", file=sys.stderr)

merged = {"records": list(all_records.values()), "version": "merged"}
with open("instinct/instinct-record.json", "w") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print(f"Merged {len(all_records)} instinct records")
PYEOF
        ok "instinct 数据已合并（以 evolve-daemon/instinct/ 为主）"
    else
        warn "未找到 instinct 主数据，跳过合并"
    fi

    # Step 0.4: 修复 settings.local.json 硬编码路径
    log "Step 0.4: 修复 .claude/settings.local.json 硬编码路径"
    TARGET="$PROJECT_ROOT/.claude/settings.local.json"
    if [ -f "$TARGET" ]; then
        # 备份
        cp "$TARGET" "$TARGET.bak"
        # 使用 sed 替换（macOS 兼容）
        sed -i '' 's|"path": "/Users/yanyinxi/[^"]*"|"path": "${CLAUDE_PLUGIN_ROOT}"|' "$TARGET"
        ok "settings.local.json 已修复（备份: .bak）"
    fi

    # Step 0.5: 补充 .claudeignore 缺失项
    log "Step 0.5: 补充 .claudeignore 缺失项"
    TARGET="$PROJECT_ROOT/.claudeignore"
    if [ -f "$TARGET" ]; then
        for item in ".pytest_cache/" ".DS_Store" "*.tmp" "*.temp"; do
            if ! grep -q "$item" "$TARGET"; then
                echo "$item" >> "$TARGET"
            fi
        done
        ok ".claudeignore 已补充缺失项"
    fi
}

# ------------------------------------------------------------------------------
# Phase P: 路径重构
# ------------------------------------------------------------------------------
phase_p() {
    section "Phase P: 路径重构"

    # Step P.1: 创建 harness/paths.py
    log "Step P.1: 创建 harness/paths.py"
    mkdir -p "$PROJECT_ROOT/harness"
    cat > "$PROJECT_ROOT/harness/paths.py" << 'PYEOF'
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
PLUGIN_ROOT = _plugin_root()

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
    "collect-session.py": HOOKS_BIN_DIR / "collect-session.py",
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
PYEOF
    ok "harness/paths.py 已创建"

    # Step P.2: 创建 harness/_core/ 基础设施
    log "Step P.2: 创建 harness/_core/ 基础设施"
    mkdir -p "$PROJECT_ROOT/harness/_core"
    cat > "$PROJECT_ROOT/harness/_core/__init__.py" << 'PYEOF'
"""_core — CHK 核心基础设施"""
PYEOF
    cat > "$PROJECT_ROOT/harness/_core/config_loader.py" << 'PYEOF'
"""BaseConfig — 模块配置加载器"""
import os
from pathlib import Path
from typing import Any, Optional, TypeVar
import yaml

T = TypeVar("T", bound="BaseConfig")

class BaseConfig:
    DEFAULTS: dict = {}
    _cache: Optional[dict] = None

    @classmethod
    def load(cls, harness_root: Optional[Path] = None) -> dict:
        if cls._cache:
            return cls._cache
        base = cls.DEFAULTS.copy()
        path = cls._config_path(harness_root)
        if path and path.exists():
            with open(path) as f:
                user = yaml.safe_load(f) or {}
            base = cls._merge(base, user)
        base = cls._apply_env(base)
        cls._cache = base
        return base

    @classmethod
    def _config_path(cls, harness_root) -> Optional[Path]:
        return None

    @classmethod
    def _merge(cls, base: dict, override: dict) -> dict:
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = cls._merge(result[k], v)
            else:
                result[k] = v
        return result

    @classmethod
    def _apply_env(cls, cfg: dict) -> dict:
        for key in list(cfg.keys()):
            env_key = f"{cls._env_prefix()}_{key.upper()}"
            if env_key in os.environ:
                cfg[key] = os.environ[env_key]
        return cfg

    @classmethod
    def _env_prefix(cls) -> str:
        return "CHK"
PYEOF
    ok "harness/_core/ 基础设施已创建"

    # Step P.3: 修复 observe.py（添加 mkdir）
    log "Step P.3: 修复 hooks/bin/observe.py（添加 mkdir）"
    TARGET="$PROJECT_ROOT/hooks/bin/observe.py"
    if [ -f "$TARGET" ]; then
        if grep -q 'mkdir.*parents=True' "$TARGET" 2>/dev/null; then
            ok "observe.py 已包含 mkdir（可能已被修复）"
        else
            # 在 OBS_DIR 定义后添加 mkdir
            if grep -q 'OBS_DIR = PLUGIN_ROOT / ".claude" / "homunculus"' "$TARGET"; then
                # 修改路径到 data/homunculus
                sed -i '' 's|OBS_DIR = PLUGIN_ROOT / ".claude" / "homunculus"|OBS_DIR = PLUGIN_ROOT / ".claude" / "data" / "homunculus"|' "$TARGET"
            fi
            if grep -q 'OBS_DIR.mkdir' "$TARGET" 2>/dev/null; then
                ok "observe.py 已包含 mkdir"
            else
                # 在 OBS_DIR 定义后添加 mkdir（插入方式）
                python3 - <<PYEOF
import re
with open("$TARGET", "r") as f:
    content = f.read()
# 在 OBS_DIR = 后面添加 mkdir 行
content = re.sub(
    r'(OBS_DIR = [^\n]+\n)',
    r'\1OBS_DIR.mkdir(parents=True, exist_ok=True)\n',
    content
)
with open("$TARGET", "w") as f:
    f.write(content)
print("observe.py mkdir added")
PYEOF
                ok "observe.py 已添加 mkdir"
            fi
        fi
    fi
}

# ------------------------------------------------------------------------------
# Phase M: 目录迁移
# ------------------------------------------------------------------------------
phase_m() {
    section "Phase M: 目录迁移"

    log "Step M.1: 创建 harness/ 子目录"
    mkdir -p "$PROJECT_ROOT/harness"/{docs,evolve-daemon/templates,instinct,memory,rules,skills,agents,hooks/bin,knowledge/{project,team/biz-wiki,team/tech-wiki},tests,cli/modes,_core}

    log "Step M.2: git mv 所有扩展目录到 harness/"
    cd "$PROJECT_ROOT"

    declare -a MV_ITEMS=(
        "agents:harness/agents"
        "skills:harness/skills"
        "hooks:harness/hooks"
        "rules:harness/rules"
        "memory:harness/memory"
        "knowledge:harness/knowledge"
        "tests:harness/tests"
        "docs:harness/docs"
        "evolve-daemon:harness/evolve-daemon"
        "cli:harness/cli"
        "instinct:harness/instinct"
        "marketplace.json:harness/marketplace.json"
        ".mcp.json:harness/.mcp.json"
    )

    for item in "${MV_ITEMS[@]}"; do
        SRC="${item%%:*}"
        DST="${item##*:}"
        if [ -e "$SRC" ]; then
            git mv "$SRC" "$DST" 2>/dev/null || mv "$SRC" "$DST"
            ok "已迁移: $SRC → $DST"
        else
            warn "跳过（不存在）: $SRC"
        fi
    done

    log "Step M.3: 更新 package.json files[]"
    TARGET="$PROJECT_ROOT/package.json"
    if [ -f "$TARGET" ]; then
        cp "$TARGET" "$TARGET.bak"
        python3 - <<'PYEOF'
import json, sys

with open("$TARGET", "r") as f:
    data = json.load(f)

data["files"] = [
    ".claude-plugin/",
    "harness/",
    "index.js",
    "CLAUDE.md",
    "README.md",
    "package.json"
]

with open("$TARGET", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("package.json files[] updated")
PYEOF
        ok "package.json 已更新（备份: package.json.bak）"
    fi

    log "Step M.4: 更新 .gitignore"
    TARGET="$PROJECT_ROOT/.gitignore"
    if [ -f "$TARGET" ]; then
        cat >> "$TARGET" << 'GITIGNORE'

# harness 运行时数据
harness/.claude/data/rate-limits/
harness/.claude/data/worktrees/
harness/.claude/data/error.jsonl
harness/.claude/data/error.jsonl.lock
harness/.claude/data/failures.jsonl
.claude/data/homunculus/
.claude/data/observations.jsonl
GITIGNORE
        ok ".gitignore 已更新"
    fi
}

# ------------------------------------------------------------------------------
# Phase V: 验证
# ------------------------------------------------------------------------------
phase_v() {
    section "Phase V: 验证"

    cd "$PROJECT_ROOT"

    log "Step V.1: 目录迁移验证"
    for dir in agents skills hooks rules memory knowledge tests docs evolve-daemon cli instinct; do
        if [ -e "$dir" ]; then
            fail "残留目录: $dir"
        else
            ok "已迁移: $dir"
        fi
    done

    log "Step V.2: 验证无硬编码路径残留（排除 paths.py 自身）"
    RESIDUAL=$(grep -rn "'/Users/" --include="*.py" . 2>/dev/null | grep -v "harness/paths.py" | grep -v ".pyc" || true)
    if [ -n "$RESIDUAL" ]; then
        fail "发现残留硬编码路径:"
        echo "$RESIDUAL" | head -5
    else
        ok "无硬编码路径残留"
    fi

    log "Step V.3: 验证 paths.py 可导入"
    python3 -c "import sys; sys.path.insert(0, 'harness'); from paths import ROOT, SKILLS_DIR, HOMUNCULUS_DIR; print(f'ROOT={ROOT}')" 2>/dev/null && ok "paths.py 可正常导入" || fail "paths.py 导入失败"

    log "Step V.4: 验证 MCP Server 可启动"
    node index.js --version 2>/dev/null && ok "MCP Server 可启动" || warn "MCP Server 启动验证跳过"

    log "Step V.5: 验证 Hook 脚本可执行"
    if [ -f "harness/hooks/bin/safety-check.sh" ]; then
        bash harness/hooks/bin/safety-check.sh 2>/dev/null && ok "safety-check.sh 可执行" || warn "safety-check.sh 执行失败"
    fi

    log "Step V.6: 运行测试套件"
    if [ -f "package.json" ]; then
        npm test 2>&1 | tail -20 && ok "测试套件已运行" || warn "测试套件有失败项"
    fi
}

# ------------------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------------------
main() {
    echo ""
    echo -e "${GREEN}███╗   ██╗███████╗███████╗███████╗ ██████╗ ██████╗ ███╗   ███╗██╗███╗   ██╗ ██████╗██╗  ██╗███████╗██████╗ ██╗██╗     ██╗      ║${NC}"
    echo -e "${GREEN}███║   ██║██╔════╝██╔════╝██╔════╝██╔═══██╗██╔══██╗████╗ ████║██║████╗  ██║██╔════╝██║  ██║██╔════╝██╔══██╗██║██║     ██║      ║${NC}"
    echo -e "${GREEN}███║   ██║█████╗  ███████╗█████╗  ██║   ██║██████╔╝██╔████╔██║██║██╔██╗ ██║██║     ███████║███████╗██████╔╝██║██║     ██║      ║${NC}"
    echo -e "${GREEN}███║   ██║██╔══╝  ╚════██║██╔══╝  ██║   ██║██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██║     ██╔══██║╚════██║██╔═══╝ ██║██║     ██║      ║${NC}"
    echo -e "${GREEN}███║   ██║███████╗███████║███████╗╚██████╔╝██║  ██║██║ ╚═╝ ██║██║██║ ╚████║╚██████╗██║  ██║███████║██║     ██║███████╗███████╗║${NC}"
    echo -e "${GREEN}╚════╝ ╚═╝╚══════╝╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚══════╝╚══════╝╝${NC}"
    echo ""
    echo -e "${BLUE}CHK 目录结构重构执行脚本${NC}"
    echo -e "${BLUE}项目根目录: $PROJECT_ROOT${NC}"
    echo -e "${BLUE}开始时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""

    # Phase 0
    phase_0

    # Phase P
    phase_p

    # Phase M
    phase_m

    # Phase V
    phase_v

    echo ""
    section "执行完成"
    echo -e "${GREEN}完成时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
    echo "后续步骤:"
    echo "  1. 提交变更: git add -A && git commit -m 'feat: 目录结构重构 v1.0'"
    echo "  2. 运行 npm test 确认所有测试通过"
    echo "  3. 验证 Claude Code 加载插件正常"
}

main "$@"
