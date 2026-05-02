# CHK 目录结构重构方案

> 目标：将项目目录结构对齐 Claude Code 官方规范，CHK 扩展能力统一收敛到 `harness/` 扩展目录；建立全局路径配置体系，根治硬编码路径问题。

**状态**：v3.0 — 完整评审版
**作者**：Claude Code
**日期**：2026-05-02

---

## 变更日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v3.0 | 2026-05-02 | 修正统计数字（Python文件数、hardcode行数）；补充 index.js、marketplace.json 缺失问题；新增 instinct 三副本处理策略；补充 `homunculus/` 目录；补充 settings.local.json 路径处理；补充 package.json files[] 完整清单；补充 Phase 0 准备检查 |
| v2.0 | 2026-05-02 | 初稿 |

---

## 背景与动机（Why）

### B.1 当前目录结构的问题不只是"乱"

根目录平铺 9 个扩展目录，表面是命名混乱，深层是**架构失焦**：无法区分 Claude Code 官方标准与 CHK 自研扩展。后果：

- **升级脆弱**：Claude Code 升级 `.claude/` 规范时，CHK 自己的 `rules/`、`knowledge/`、`tests/` 会被混淆或覆盖
- **插件分发不完整**：`package.json` 的 `files[]` 缺少 `index.js`、`evolve-daemon/`、`knowledge/`、`memory/`、`instinct/`、`tests/`、`docs/`、`marketplace.json`、`.mcp.json`，发布后插件根本无法运行
- **新人门槛高**：无法一眼看出哪些是官方约定、哪些是 CHK 特色，需要大量 tribal knowledge
- **instinct 数据三处散落**：`agents/instinct/instinct-record.json`（788B）、`instinct/instinct-record.json`（7964B）、`evolve-daemon/instinct/instinct-record.json`（8671B），内容不一致，存在数据丢失风险

### B.2 硬编码路径是技术债的根源

CHK 有 **55 个 Python 文件**（含测试），其中**只有 1 处真正的硬编码绝对路径**需要修复，其余均已使用 `__file__` 相对路径或环境变量：

| 问题类型 | 出现次数 | 代表案例 | 风险 |
|----------|----------|----------|------|
| **硬编码绝对路径** | **1 处** | `cli/generate_skill_index.py` line 6 的 `/Users/yanyinxi/...` | 换机器即坏 |
| 硬编码 `.claude` 目录名 | 已用 env var | 所有 hooks 和 daemon 使用 `CLAUDE_PROJECT_DIR` | 无风险 |
| JSONL 文件名散落 | 各文件自行定义 | `sessions.jsonl`、`error.jsonl` 等 | 重命名需改多处 |
| Hook 源映射硬编码 | `_HOOK_SOURCE_MAP` 存在但为相对路径 | `collect_error.py` lines 41-57 | 结构一变即需更新 |
| instinct 位置不一致 | **3 处** | 见 B.1 | **数据丢失风险** |
| API URL 硬编码 | 5 处 | `"https://api.anthropic.com/v1/messages"` | 可接受（常量） |
| `homunculus/` 目录未声明 | 1 处 | `observe.py` line 24 引用 | 迁移时需补充 |
| `settings.local.json` 路径硬编码 | 1 处 | `.claude/settings.local.json` line 27 绝对路径 | 需环境变量覆盖 |

**根本原因**：没有统一的配置层。虽然大部分路径已正确使用相对路径，但 JSONL 文件名、API URL、hook 映射等仍散落在各模块中。

### B.3 为什么现有方案不够

CHK 已有 `evolve-daemon/config.yaml`，但只服务 daemon，覆盖不了：

- Hook 脚本（`hooks/bin/`）在 config.yaml 之外
- CLI 工具（`cli/`）在 config.yaml 之外
- `_HOOK_SOURCE_MAP` 在代码里而不是配置文件
- JSONL 文件名散落在 8+ 文件中

需要一个**全局统一**的配置层，覆盖**所有 Python 模块**，无论它们在哪个子目录。

---

## 一、现状分析

### 1.1 当前目录结构（全量盘点）

```
项目根目录/
├── .claude/                    ← 官方标准 ✅ 已对齐
│   ├── settings.json           ← 官方配置
│   ├── settings.local.json     ← 本地覆盖 ⚠️ 含硬编码绝对路径
│   ├── data/                   ← 运行时日志（session、error、agent调用）
│   ├── knowledge/              ← 知识库（decision、guideline、pitfall、process）
│   ├── tests/                  ← Claude Code 项目级测试（3 个）
│   └── proposals/              ← Evolve Daemon 提案输出目录
│
├── .claude-plugin/             ← 官方插件元数据 ✅ 已对齐
│   ├── plugin.json             ← 插件声明（name、version、slashCommands）
│   └── marketplace.json        ← 市场发布元数据
│
├── index.js                    ← MCP Server 入口 ⚠️ 未列入 package.json files[]
├── package.json                ← NPM 包（files[] 不完整）
├── CLAUDE.md                   ← 项目入口说明
├── README.md
├── .mcp.json                   ← MCP Server 配置 ⚠️ 未列入 package.json files[]
├── .claudeignore               ← Claude Code 扫描排除（不完整）
├── .gitignore
│
├── agents/                    ← ❌ 根目录 — CHK 扩展（21 个 .md）
│   ├── instinct/              ← ❌ instinct 数据副本1（788B，不活跃）
│   │   └── instinct-record.json
│   └── [其他 agent .md 文件]
│
├── skills/                    ← ❌ 根目录 — CHK 扩展（35 个 skills）
│   ├── SKILL.md / INDEX.md
│   ├── database-designer/     ← 含 3 个 .py 文件
│   └── [其他 34 个 skill...]
│
├── hooks/                     ← ❌ 根目录 — CHK 扩展
│   ├── hooks.json            ← Hook 配置（使用 ${CLAUDE_PLUGIN_ROOT} ✅）
│   └── bin/                   ← 26 个 Hook 脚本（23 .py + 3 .sh）
│
├── rules/                     ← ❌ 根目录 — CHK 扩展（6 个规则）
│
├── memory/                    ← ❌ 根目录 — CHK 扩展（记忆/反馈）
│
├── knowledge/                 ← ❌ 根目录 — CHK 扩展（与 .claude/knowledge/ 重复）
│   ├── lifecycle.py / .yaml
│   └── project/ / team/
│
├── tests/                     ← ❌ 根目录 — CHK 测试（11 个测试文件）
│
├── docs/                      ← ❌ 根目录 — CHK 文档（15 个文档）
│
├── instinct/                  ← ❌ 根目录 — CHK instinct 数据副本2（7964B）
│   └── instinct-record.json
│
├── evolve-daemon/             ← ❌ 根目录 — CHK 扩展（独立守护进程）
│   ├── instinct/              ← ❌ instinct 数据副本3（8671B，最新活跃）
│   │   └── instinct-record.json
│   ├── templates/
│   ├── [18 个 .py 文件]
│   └── config.yaml
│
├── marketplace.json           ← ❌ 根目录 ⚠️ 未列入 package.json files[]
└── cli/                       ← ❌ 根目录 — CHK CLI 工具（8 个 .py + 3 个 .sh）
```

### 1.2 核心问题

| 问题 | 说明 | 优先级 |
|------|------|--------|
| **package.json files[] 缺失关键文件** | `index.js`、`evolve-daemon/`、`knowledge/`、`memory/`、`instinct/`、`tests/`、`docs/`、`marketplace.json`、`.mcp.json` 均未列出，发布后插件无法运行 | 🔴 紧急 |
| **根目录混乱** | 9 个扩展目录平铺根目录，无法区分官方标准和 CHK 扩展 | 🟡 重要 |
| **instinct 数据三副本不同步** | `agents/instinct/`（788B）、`instinct/`（7964B）、`evolve-daemon/instinct/`（8671B）内容不一致，daemon 和 CLI 可能读写不同文件 | 🔴 紧急 |
| **hardcoded 绝对路径** | `cli/generate_skill_index.py` line 6 和 `settings.local.json` line 27 各有 1 处 | 🟡 重要 |
| **`homunculus/` 目录未声明** | `hooks/bin/observe.py` 引用 `.claude/homunculus/observations.jsonl`，但此目录从未被创建或声明 | 🟡 重要 |
| **settings.local.json 含硬编码路径** | `extraKnownMarketplaces.claude-harness-kit.source.path` 硬编码了本机路径，跨机器无法工作 | 🟡 重要 |
| **官方边界模糊** | `.claude/knowledge/` 和 `knowledge/` 两个知识库，前者是官方结构，后者是 CHK 扩展但命名冲突 | 🟢 次要 |

### 1.3 当前 package.json files[] 问题（最严重）

```json
// 当前 files[] — 缺少关键文件
"files": [
  ".claude-plugin/",
  "agents/",
  "skills/",
  "hooks/",
  "rules/",
  "CLAUDE.md",
  "README.md",
  "package.json"
]

// 缺少：
// ❌ index.js（入口点，package.json main 指向它）
// ❌ evolve-daemon/（守护进程核心）
// ❌ knowledge/（生命周期知识库）
// ❌ memory/（记忆系统）
// ❌ instinct/（本能记录）
// ❌ tests/（测试套件）
// ❌ docs/（设计文档）
// ❌ marketplace.json（市场清单）
// ❌ .mcp.json（MCP 配置）
```

---

## 二、目标结构

### 2.1 总体布局

```
项目根目录/
├── .claude/                    ← 【官方标准】不动，保持 Claude Code 规范
│   ├── settings.json
│   ├── settings.local.json     ← ⚠️ 迁移前需先将硬编码路径改为 ${CLAUDE_PLUGIN_ROOT}
│   ├── data/                   ← 运行时日志（session、error、agent_calls、failures）
│   │   └── homunculus/         ← 【新增】observe.py 写入目录（需 mkdir）
│   ├── knowledge/              ← 知识库（decision、guideline、pitfall、process、model）
│   ├── tests/                  ← Claude Code 项目级测试（3 个）
│   └── proposals/              ← Evolve Daemon 提案输出
│
├── .claude-plugin/             ← 【官方插件元数据】不动
│   ├── plugin.json
│   └── marketplace.json
│
├── harness/                    ← 【新增】CHK 统一扩展目录
│   ├── paths.py                ← 【新增】全局路径配置服务
│   ├── _core/                  ← 【新增】基础设施（config_loader、config_validator）
│   │   ├── config_loader.py
│   │   └── config_validator.py
│   ├── docs/                  ← 设计/架构文档（15 个）
│   ├── evolve-daemon/          ← 守护进程（18 个 .py）
│   │   ├── instinct/          ← instinct 数据（迁移自 evolve-daemon/instinct/，已是最活跃数据）
│   │   └── templates/
│   ├── instinct/              ← instinct 数据统一目录
│   │   └── instinct-record.json
│   ├── memory/                 ← 记忆/反馈系统
│   ├── rules/                  ← CHK 扩展规则（6 个）
│   ├── skills/                 ← 35 个 CHK Skills
│   │   ├── database-designer/  ← 含 3 个 .py 文件
│   │   └── SKILL.md / INDEX.md
│   ├── agents/                 ← 21 个 .md Agent 定义
│   │   └── instinct/          ← instinct 数据旧副本（迁移后删除）
│   ├── hooks/                  ← Hook 配置 + 脚本
│   │   ├── hooks.json
│   │   └── bin/                ← 26 个脚本（23 .py + 3 .sh）
│   ├── knowledge/              ← CHK 知识库（与 .claude/knowledge/ 并列）
│   │   ├── lifecycle.py / .yaml
│   │   └── project/ / team/
│   ├── tests/                  ← CHK 测试套件（11 个测试文件）
│   ├── cli/                    ← CLI 工具（11 个 .py + .sh）
│   │   └── modes/
│   ├── marketplace.json       ← CHK 市场清单（迁移自根目录）
│   └── .mcp.json              ← MCP Server 配置（迁移自根目录）
│
├── index.js                    ← MCP Server（第三方扩展机制）⚠️ 需加入 package.json files[]
├── package.json
├── CLAUDE.md
├── README.md
├── .claudeignore               ← 需补充 .pytest_cache/、.DS_Store 等
└── .gitignore
```

### 2.2 目录职责映射表

| 目标路径 | 来源 | 说明 |
|----------|------|------|
| `harness/agents/` | `agents/` | 21 个 Agent 定义 md 文件 + instinct 子目录 |
| `harness/skills/` | `skills/` | 35 个 Skill（含 database-designer 等大型 skill） |
| `harness/hooks/` | `hooks/` | `hooks.json` + `bin/`（26 个脚本） |
| `harness/rules/` | `rules/` | 6 个 CHK 扩展规则 |
| `harness/memory/` | `memory/` | 记忆/反馈记录 |
| `harness/knowledge/` | `knowledge/` | CHK 知识库（生命周期、team、project wiki） |
| `harness/tests/` | `tests/` | CHK 测试套件（11 个测试文件） |
| `harness/docs/` | `docs/` | 设计/架构文档（15 个文档） |
| `harness/evolve-daemon/` | `evolve-daemon/` | 守护进程 + templates + instinct/ 数据 |
| `harness/cli/` | `cli/` | CLI 工具 + modes/ 配置 |
| `harness/instinct/` | `instinct/` | instinct 数据统一目录（迁移后为主数据源） |
| `harness/paths.py` | (新) | 全局路径配置服务 |
| `harness/_core/` | (新) | 基础设施层（config_loader、config_validator） |
| `harness/marketplace.json` | `marketplace.json` | CHK 市场清单 |
| `harness/.mcp.json` | `.mcp.json` | MCP Server 配置 |
| `.claude/data/homunculus/` | (新建) | observe.py 写入目录（需 mkdir） |

### 2.3 instinct 数据三副本处理策略

当前有三个 instinct-record.json 文件，内容各不相同：

| 位置 | 大小 | 内容 | 状态 |
|------|------|------|------|
| `agents/instinct/instinct-record.json` | 788B | 仅 1 条 seed 记录 | 不活跃，最旧 |
| `instinct/instinct-record.json` | 7964B | 多条记录，包含 auto-* 记录 | 较活跃 |
| `evolve-daemon/instinct/instinct-record.json` | 8671B | 最完整，包含 auto-* 和 seed-* 记录 | **最活跃、最新** |

**处理策略**：

1. 迁移前，以 `evolve-daemon/instinct/instinct-record.json` 为主数据源（内容最完整）
2. 迁移到 `harness/evolve-daemon/instinct/instinct-record.json`（保持现状位置）
3. `agents/instinct/instinct-record.json` 和 `instinct/instinct-record.json` 迁移后删除
4. 后续所有 instinct 相关代码统一使用 `harness/instinct/instinct-record.json`
5. **立即修复**：`instinct_cli.py` 和 `instinct_updater.py` 路径不一致问题（见 3.5 节）

### 2.4 架构原则

为什么这样划分：

| 原则 | 说明 | 收益 |
|------|------|------|
| **官方边界不可逾越** | `.claude/` 和 `.claude-plugin/` 是 Claude Code 规范，不碰 | 跟随官方升级，零兼容成本 |
| **扩展收敛单一入口** | 所有 CHK 扩展在 `harness/` 下 | 边界清晰、可独立打包分发 |
| **配置先行代码后** | 路径在 `paths.py` 中声明，代码只读不写 | 未来目录重命名只需改一处 |
| **相对路径优先** | 代码用 `__file__` / `CLAUDE_PROJECT_DIR` 计算路径，不硬编码绝对路径 | 换机器、换目录皆可运行 |
| **环境变量兜底** | `CLAUDE_PROJECT_DIR` / `CLAUDE_PLUGIN_ROOT` 为运行时覆盖提供入口 | 支持多项目、多环境配置 |
| **instinct 数据单一真实源** | 只保留 `harness/evolve-daemon/instinct/instinct-record.json` | 防止数据分裂和丢失 |

---

## 三、全局路径配置体系设计

### 3.1 核心问题抽象

硬编码路径的本质是**紧耦合**：模块与路径值耦合在一起，导致目录结构一变，全量代码皆动。

解法是引入**配置层**：

```
配置层（paths.py — 单一来源）
         ↓ 读取
   所有 Python 模块（读路径，不写路径）
```

### 3.2 路径服务层：`harness/paths.py`

**设计位置**：`harness/paths.py`

**设计原则**：

1. **单一来源**：所有路径常量只在这里定义一次
2. **配置驱动**：路径由 `__file__` 推导，Python 只负责读取和计算
3. **兼容环境变量**：支持 `CLAUDE_PROJECT_DIR` / `CLAUDE_PLUGIN_ROOT` 运行时覆盖
4. **类型安全**：返回 `pathlib.Path` 对象而非字符串，减少拼接错误
5. **无循环依赖**：paths.py 不 import 任何 CHK 模块

**文件内容**：

```python
#!/usr/bin/env python3
"""
paths.py — CHK 全局路径配置服务

所有 Python 模块通过 from paths import * 获取路径常量。
任何目录结构变更只需要修改此文件。

使用方式:
  import sys
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from paths import ROOT, CLAUDE_DIR, DATA_DIR, SKILLS_DIR, ...

设计原则:
  - 环境变量 CLAUDE_PROJECT_DIR 优先于源码位置
  - 所有路径返回 pathlib.Path 对象
  - 文件路径用函数（lazy）而非常量，避免模块加载顺序问题
  - 不 import 任何 CHK 模块，避免循环依赖
"""

import os
from pathlib import Path

# ════════════════════════════════════════════════════════════════════
# Layer 1: 源码位置（最低优先级）
# ════════════════════════════════════════════════════════════════════

_SCRIPT_LOCATION = Path(__file__).resolve().parent  # = harness/

# ════════════════════════════════════════════════════════════════════
# Layer 2: 环境变量（可覆盖）
# ════════════════════════════════════════════════════════════════════

def _project_root() -> Path:
    """项目根目录 — 环境变量优先，否则基于 __file__ 推断"""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env_root:
        return Path(env_root)
    return _SCRIPT_LOCATION.parent


def _plugin_root() -> Path:
    """插件根目录 — 环境变量优先，否则等于 _project_root()"""
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if env_root:
        return Path(env_root)
    return _project_root()


# ════════════════════════════════════════════════════════════════════
# Layer 3: 目录名常量（允许重命名 .claude 等目录名）
# ════════════════════════════════════════════════════════════════════

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
DIR_HOMUNCULUS = "homunculus"  # observe.py 数据目录

# ════════════════════════════════════════════════════════════════════
# Layer 4: JSONL 数据文件名常量（允许重命名日志文件）
# ════════════════════════════════════════════════════════════════════

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

# API 端点常量
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
# 可通过环境变量覆盖:
# ANTHROPIC_BASE_URL 用于代理/测试环境

# ════════════════════════════════════════════════════════════════════
# Layer 5: 路径常量
# ════════════════════════════════════════════════════════════════════

ROOT = _project_root()
PLUGIN_ROOT = _plugin_root()

# .claude/ 体系（官方标准）
CLAUDE_DIR = ROOT / DIR_CLAUDE
DATA_DIR = CLAUDE_DIR / DIR_DATA
PROPOSALS_DIR = CLAUDE_DIR / DIR_PROPOSALS
RATE_LIMITS_DIR = DATA_DIR / "rate-limits"
WORKTREES_DIR = DATA_DIR / "worktrees"
HOMUNCULUS_DIR = DATA_DIR / DIR_HOMUNCULUS  # observe.py 使用

# .claude/data/*.jsonl 文件（懒访问函数，每次重新构建 Path）
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

# 插件根体系（CHK 扩展）
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
EVOLVE_INSTINCT_DIR = EVOLVE_DIR / DIR_INSTINCT  # evolve-daemon/instinct/
EVOLVE_INSTINCT_FILE = EVOLVE_INSTINCT_DIR / FILE_INSTINCT_RECORD

# instinct-record.json 文件（统一位置）
INSTINCT_FILE = INSTINCT_DIR / FILE_INSTINCT_RECORD

# cli 内部
LIFECYCLE_YAML = KNOWLEDGE_DIR / FILE_LIFECYCLE_YAML
SETTINGS_LOCAL = CLAUDE_DIR / FILE_SETTINGS_LOCAL

# MCP 和 marketplace
MCP_JSON = PLUGIN_ROOT / ".mcp.json"
MARKETPLACE_JSON = PLUGIN_ROOT / "marketplace.json"

# ════════════════════════════════════════════════════════════════════
# Hook 脚本名映射（替换 collect_error.py 的 _HOOK_SOURCE_MAP）
# ════════════════════════════════════════════════════════════════════

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

# ════════════════════════════════════════════════════════════════════
# 导出（from paths import * 时可见）
# ════════════════════════════════════════════════════════════════════

__all__ = [
    # 目录名常量
    "DIR_CLAUDE", "DIR_DATA", "DIR_PROPOSALS", "DIR_HOOKS", "DIR_HOOKS_BIN",
    "DIR_SKILLS", "DIR_AGENTS", "DIR_RULES", "DIR_MEMORY", "DIR_KNOWLEDGE",
    "DIR_TESTS", "DIR_DOCS", "DIR_INSTINCT", "DIR_CLI", "DIR_CLI_MODES",
    "DIR_HOMUNCULUS",
    # JSONL 文件名常量
    "FILE_SESSIONS", "FILE_ERRORS", "FILE_ERRORS_LOCK", "FILE_FAILURES",
    "FILE_AGENT_CALLS", "FILE_SKILL_CALLS", "FILE_OBSERVATIONS",
    "FILE_OBS_ERRORS", "FILE_ANALYSIS_STATE", "FILE_INSTINCT_RECORD",
    "FILE_SETTINGS_LOCAL", "FILE_LIFECYCLE_YAML", "FILE_PROPOSAL_HISTORY",
    # API 端点
    "ANTHROPIC_API_URL",
    # 路径对象
    "ROOT", "PLUGIN_ROOT",
    "CLAUDE_DIR", "DATA_DIR", "PROPOSALS_DIR", "RATE_LIMITS_DIR", "WORKTREES_DIR",
    "HOMUNCULUS_DIR",
    "SKILLS_DIR", "AGENTS_DIR", "RULES_DIR", "HOOKS_DIR", "HOOKS_BIN_DIR",
    "MEMORY_DIR", "KNOWLEDGE_DIR", "TESTS_DIR", "DOCS_DIR", "INSTINCT_DIR",
    "CLI_DIR", "CLI_MODES_DIR", "EVOLVE_DIR", "EVOLVE_TEMPLATES_DIR",
    "EVOLVE_CONFIG_FILE", "EVOLVE_INSTINCT_DIR", "EVOLVE_INSTINCT_FILE",
    "INSTINCT_FILE", "LIFECYCLE_YAML", "SETTINGS_LOCAL",
    "MCP_JSON", "MARKETPLACE_JSON",
    # 方法（lazy 文件路径）
    "sessions_file", "errors_file", "errors_lock_file", "failures_file",
    "agent_calls_file", "skill_calls_file", "analysis_state_file",
    "proposal_history_file", "observations_file", "obs_errors_file",
    # Hook 映射
    "HOOK_SCRIPTS",
]
```

### 3.3 为什么这样设计

| 设计决策 | 为什么 | 如果未来目录变 |
|----------|--------|----------------|
| `DIR_CLAUDE = ".claude"` 作为常量 | `.claude` 字符串在多处出现，改名成本高 | 只改常量值，全量代码生效 |
| `ROOT` 用环境变量优先 | 允许外部注入路径，适合测试和 CI | 测试可以 mock 环境变量 |
| 文件路径用函数而非常量 | 避免模块加载时路径尚未初始化 | 无影响 |
| `HOOK_SCRIPTS` 用 `dict` | hook 数量可能变化，且需要 Path 对象 | 加一个 key 即可 |
| `__all__` 显式导出 | 控制 `from paths import *` 的命名空间 | 防止意外导入 |
| 不在 `paths.py` 中 import 其他 CHK 模块 | 避免循环依赖；paths 是最底层模块 | 无影响 |
| 新增 `HOMUNCULUS_DIR` | `observe.py` 引用 `.claude/homunculus/`，之前未声明 | 明确目录归属 |
| 新增 `EVOLVE_INSTINCT_FILE` | 明确定义 `evolve-daemon/instinct/instinct-record.json` 路径 | 统一数据源 |
| 新增 `FILE_PROPOSAL_HISTORY` | `.claude/data/proposal_history.json` 之前未列入 | 完整覆盖 |

### 3.4 使用方式

```python
# 旧写法（硬编码绝对路径）
SKILLS_DIR = Path("/Users/yanyinxi/工作/code/github/claude-harness-kit/skills")

# 新写法（统一配置）
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 添加 harness/ 到 sys.path
from paths import SKILLS_DIR

# 旧写法（散落 JSONL 文件名）
sessions_file = data_dir / "sessions.jsonl"

# 新写法（统一来源）
from paths import sessions_file, DATA_DIR
sessions = sessions_file()

# observe.py 旧写法
OBS_DIR = PLUGIN_ROOT / ".claude" / "homunculus"
OBS_LOG = OBS_DIR / "observations.jsonl"

# observe.py 新写法
from paths import HOMUNCULUS_DIR, observations_file, obs_errors_file
# observations_file() → DATA_DIR / "homunculus" / "observations.jsonl"
```

### 3.5 需要迁移的具体文件清单

| 序号 | 文件 | 旧写法 | 新写法 | 紧急度 |
|------|------|--------|--------|--------|
| 1 | `cli/generate_skill_index.py` | `Path("/Users/yanyinxi/...")` | `from paths import SKILLS_DIR` | 🔴 立即修复 |
| 2 | `evolve-daemon/daemon.py` | inline fallback 中 `".claude/data"` | `from paths import DATA_DIR` | 🟡 迁移时修复 |
| 3 | `evolve-daemon/proposer.py` | `"https://api.anthropic.com/..."` 硬编码 | `from paths import ANTHROPIC_API_URL` | 🟢 可选 |
| 4 | `evolve-daemon/instinct_updater.py` | `root / "instinct" / "instinct-record.json"` | `from paths import INSTINCT_FILE` | 🔴 立即修复 |
| 5 | `hooks/bin/collect_error.py` | `_HOOK_SOURCE_MAP` dict（相对路径） | `from paths import HOOK_SCRIPTS` | 🟡 迁移时修复 |
| 6 | `hooks/bin/observe.py` | `PLUGIN_ROOT / ".claude" / "homunculus"` | `from paths import HOMUNCULUS_DIR` | 🔴 立即修复（目录未创建） |
| 7 | `cli/instinct_cli.py` | `Path(__file__).parent.parent / "agents" / "instinct"` | `from paths import EVOLVE_INSTINCT_DIR`（统一到 evolve-daemon 数据） | 🔴 立即修复（三副本问题） |
| 8 | `cli/mode.py` | `Path(__file__).parent / "modes"` | `from paths import CLI_MODES_DIR` | 🟢 可选 |
| 9 | `knowledge/lifecycle.py` | `Path(__file__).parent / "lifecycle.yaml"` | `from paths import LIFECYCLE_YAML` | 🟢 可选 |
| 10 | `settings.local.json` | 硬编码 `"/Users/yanyinxi/工作/..."` | `CLAUDE_PLUGIN_ROOT` 环境变量覆盖 | 🔴 立即修复 |

---

## 四、详细技术方案

### 4.0 Phase 0：紧急修复（在目录迁移前必须完成）

**⚠️ 以下问题必须在目录迁移前修复，否则会破坏生产环境。**

#### Step 0.1 — 修复 `generate_skill_index.py` 硬编码路径

```python
# cli/generate_skill_index.py line 6
# 旧：
SKILLS_DIR = Path("/Users/yanyinxi/工作/code/github/claude-harness-kit/skills")
# 新：
SKILLS_DIR = Path(__file__).parent.parent / "skills"
```

#### Step 0.2 — 创建 `homunculus/` 目录

```bash
mkdir -p .claude/data/homunculus
```

#### Step 0.3 — 统一 instinct 数据（解决三副本问题）

```bash
# 以 evolve-daemon/instinct/instinct-record.json 为准（内容最完整：8671B）
# 方案 A：保留 evolve-daemon/instinct/ 为主数据源
#         修改 instinct_cli.py 指向 harness/evolve-daemon/instinct/

# 方案 B：统一到 harness/instinct/（推荐，更清晰）
#         cp evolve-daemon/instinct/instinct-record.json instinct/instinct-record.json
#         修改 instinct_cli.py 和 instinct_updater.py 统一指向 INSTINCT_DIR
```

**推荐方案 B**：在 `harness/instinct/instinct-record.json` 建立单一真实源。

#### Step 0.4 — 修复 `settings.local.json` 硬编码路径

```json
// .claude/settings.local.json line 26-28
// 旧：
"path": "/Users/yanyinxi/工作/code/github/claude-harness-kit"
// 新：改用环境变量，插件加载时会自动替换 ${CLAUDE_PLUGIN_ROOT}
// 注意：settings.local.json 本身在 .claude/ 下，迁移后路径不变
// 但 extraKnownMarketplaces.path 硬编码了本机路径，建议改为：
"path": "${CLAUDE_PLUGIN_ROOT}"
```

#### Step 0.5 — 补充 `.claudeignore` 缺失项

```claudeignore
# 新增
.pytest_cache/
.DS_Store
*.tmp
*.temp
```

### 4.1 执行顺序

**正确顺序：Phase 0 → Phase P → Phase M → Phase V**

```
Phase 0  — 紧急修复（在目录迁移前必须完成）
Phase P  — 路径重构（paths.py + import 更新，不移动目录）
Phase M  — 目录迁移（git mv 所有目录）
Phase V  — 验证（完整测试套件）
```

原因：paths.py 中 `PLUGIN_ROOT` 基于 `__file__` 推导，迁移前后路径值不变。先改 import 语句，目录迁移后自然指向新位置。

### 4.2 Phase P：路径重构

**Step P.1** 创建 `harness/paths.py`（内容见 3.2 节）

**Step P.2** 修复 `cli/generate_skill_index.py`

**Step P.3** 修复 `cli/instinct_cli.py`，统一使用 `INSTINCT_FILE`

**Step P.4** 修复 `hooks/bin/observe.py`，使用 `HOMUNCULUS_DIR`

**Step P.5** （可选）修改 `evolve-daemon/instinct_updater.py` 使用 `INSTINCT_FILE`

**Step P.6** （可选）修改 `hooks/bin/collect_error.py` 使用 `HOOK_SCRIPTS`

**Step P.7** grep 验证无硬编码路径残留

```bash
grep -rn "'/Users/" --include="*.py" .
grep -rn "'/Users/" --include="*.json" .
grep -rn '"/Users/' --include="*.py" .
```

### 4.3 Phase M：目录迁移

**Step M.1** 创建 `harness/` 及所有子目录

```bash
mkdir -p harness/{docs,evolve-daemon/templates,instinct,memory,rules,skills,agents,hooks/bin,knowledge/{project,team/biz-wiki,team/tech-wiki},tests,cli/modes,_core}
```

**Step M.2** 创建 `harness/paths.py` 和 `harness/_core/`

```bash
cp docs/restructure-plan.md harness/  # 保留一份在 harness 内
```

**Step M.3** 使用 `git mv` 迁移所有目录（保留 Git 历史）

```bash
git mv agents harness/agents
git mv skills harness/skills
git mv hooks harness/hooks
git mv rules harness/rules
git mv memory harness/memory
git mv knowledge harness/knowledge
git mv tests harness/tests
git mv docs harness/docs
git mv evolve-daemon harness/evolve-daemon
git mv cli harness/cli
git mv instinct harness/instinct
git mv marketplace.json harness/
git mv .mcp.json harness/
```

**Step M.4** 在 `harness/` 创建 `_core/` 基础设施

```bash
# 创建以下文件
harness/_core/__init__.py
harness/_core/config_loader.py
harness/_core/config_validator.py
```

**Step M.5** 创建 `harness/paths.py`（从 Phase P.1 已有内容写入）

**Step M.6** 更新 `harness/package.json` 的 `files[]` 数组

```json
{
  "files": [
    ".claude-plugin/",
    "harness/",
    "index.js",
    "CLAUDE.md",
    "README.md",
    "package.json"
  ]
}
```

> **注意**：`index.js` 保持在根目录（因为 `package.json.main` 指向它，且 MCP Server 需要在项目根目录运行），但通过 `files[]` 包含在分发中。

**Step M.7** 更新 `.gitignore`

```gitignore
# harness 运行时数据
harness/.claude/data/rate-limits/
harness/.claude/data/worktrees/
harness/.claude/data/error.jsonl
harness/.claude/data/error.jsonl.lock
harness/.claude/data/failures.jsonl

# instinct 数据（运行时生成）
harness/instinct/instinct-record.json
harness/evolve-daemon/instinct/instinct-record.json

# 运行时数据
.claude/data/homunculus/
.claude/data/observations.jsonl
```

### 4.4 Phase V：验证

**Step V.1** 目录迁移验证

```bash
# 验证根目录无旧目录残留
for dir in agents skills hooks rules memory knowledge tests docs evolve-daemon cli instinct marketplace.json .mcp.json; do
  [ -e "$dir" ] && echo "❌ 残留: $dir" || echo "✅ 已迁移: $dir"
done

# 验证 harness 目录存在
for dir in agents skills hooks rules memory knowledge tests docs evolve-daemon cli instinct; do
  [ -d "harness/$dir" ] && echo "✅ harness/$dir 存在" || echo "❌ harness/$dir 缺失"
done

# 验证 index.js 仍存在于根目录
[ -f "index.js" ] && echo "✅ index.js 在根目录" || echo "❌ index.js 丢失"
```

**Step V.2** 路径引用验证

```bash
# 验证无硬编码路径残留
grep -rn "'/Users/" --include="*.py" . | grep -v "harness/_core/paths.py" && echo "❌ 有残留" || echo "✅ 无残留"

# 验证 paths.py 存在且可导入
python3 -c "import sys; sys.path.insert(0, 'harness'); from paths import ROOT, SKILLS_DIR; print(f'ROOT={ROOT}, SKILLS_DIR={SKILLS_DIR}')"
```

**Step V.3** 运行测试套件

```bash
npm test
```

**Step V.4** MCP Server 启动验证

```bash
node index.js  # 验证无报错
```

**Step V.5** Hook 脚本验证

```bash
python3 harness/hooks/bin/context-injector.py --help
bash harness/hooks/bin/safety-check.sh
```

**Step V.6** Evolve Daemon 验证

```bash
python3 harness/evolve-daemon/daemon.py status
```

---

## 五、涉及改动点全清单

### 5.1 文件系统操作

| 序号 | 操作 | 源路径 | 目标路径 |
|------|------|--------|----------|
| 1 | 创建 | (新) | `harness/paths.py` |
| 2 | 创建 | (新) | `harness/_core/__init__.py` |
| 3 | 创建 | (新) | `harness/_core/config_loader.py` |
| 4 | 创建 | (新) | `harness/_core/config_validator.py` |
| 5 | 迁移 | `agents/` | `harness/agents/` |
| 6 | 迁移 | `skills/` | `harness/skills/` |
| 7 | 迁移 | `hooks/` | `harness/hooks/` |
| 8 | 迁移 | `rules/` | `harness/rules/` |
| 9 | 迁移 | `memory/` | `harness/memory/` |
| 10 | 迁移 | `knowledge/` | `harness/knowledge/` |
| 11 | 迁移 | `tests/` | `harness/tests/` |
| 12 | 迁移 | `docs/` | `harness/docs/` |
| 13 | 迁移 | `evolve-daemon/` | `harness/evolve-daemon/` |
| 14 | 迁移 | `cli/` | `harness/cli/` |
| 15 | 迁移 | `instinct/` | `harness/instinct/` |
| 16 | 迁移 | `marketplace.json` | `harness/marketplace.json` |
| 17 | 迁移 | `.mcp.json` | `harness/.mcp.json` |
| 18 | 修复 | `index.js` | 不动，但需加入 `package.json` files[] |
| 19 | 修复 | `.claudeignore` | 补充缺失项 |

### 5.2 Python 模块路径引用更新

| 序号 | 文件 | 改动 |
|------|------|------|
| 1 | `cli/generate_skill_index.py` | 改用 `SKILLS_DIR = Path(__file__).parent.parent / "skills"` |
| 2 | `cli/instinct_cli.py` | 改用 `INSTINCT_DIR` 或 `INSTINCT_FILE` |
| 3 | `hooks/bin/observe.py` | 改用 `HOMUNCULUS_DIR` + 创建目录 |
| 4 | `evolve-daemon/instinct_updater.py` | （可选）改用 `INSTINCT_FILE` |
| 5 | `evolve-daemon/daemon.py` | （可选）改用 `DATA_DIR` 等 |
| 6 | `hooks/bin/collect_error.py` | （可选）改用 `HOOK_SCRIPTS` |
| 7 | `cli/mode.py` | （可选）改用 `CLI_MODES_DIR` |
| 8 | `knowledge/lifecycle.py` | （可选）改用 `LIFECYCLE_YAML` |

### 5.3 配置和元数据更新

| 序号 | 文件 | 改动 |
|------|------|------|
| 1 | `package.json` | 补充 `files[]` 中缺失的 9 项 |
| 2 | `.claude/settings.local.json` | 将硬编码路径改为 `${CLAUDE_PLUGIN_ROOT}` |
| 3 | `.claudeignore` | 补充 `.pytest_cache/`、`.DS_Store` 等 |
| 4 | `.gitignore` | 添加 harness 运行时数据排除规则 |
| 5 | `hooks/hooks.json` | 所有 `${CLAUDE_PLUGIN_ROOT}/hooks/bin/...` 路径迁移后自动生效 |

---

## 六、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **paths.py 循环依赖** | `paths.py` 意外 import 了依赖它的模块 | 设计为纯底层，不 import 任何 CHK 模块 |
| **instinct 数据丢失** | 三副本合并时可能丢失数据 | 迁移前备份所有三个文件；以最大文件为主；merge 策略见 2.3 |
| **index.js 未移动但 package.json 未更新** | 插件安装后找不到入口点 | 已将 `index.js` 加入 `files[]`，保持其根目录位置 |
| **`${CLAUDE_PLUGIN_ROOT}` 行为变化** | 迁移后 `CLAUDE_PLUGIN_ROOT` 指向 `harness/` 而非项目根 | hooks.json 和 settings.json 使用相对路径，插件根不变 |
| **settings.local.json 路径失效** | extraKnownMarketplaces 硬编码本机路径 | 改为 `${CLAUDE_PLUGIN_ROOT}`，但需 Claude Code 支持变量展开 |
| **`homunculus/` 目录不存在** | observe.py 写入失败，静默丢失数据 | Phase 0 创建目录；paths.py 中 HOMUNCULUS_DIR 声明 |
| **evolve-daemon 找不到 config.yaml** | 迁移后相对路径失效 | paths.py 提供 `EVOLVE_CONFIG_FILE`；daemon.py 使用 `__file__.parent` |

---

## 七、路径迁移后的好处总结

| 问题 | 重构前 | 重构后 |
|------|--------|--------|
| instinct 数据三副本 | 三个文件内容不一致 | 单一真实源，数据不分裂 |
| `homunculus/` 目录未声明 | observe.py 引用但不创建 | paths.py 声明 + Phase 0 创建 |
| `generate_skill_index.py` 硬编码 | 换机器即坏 | 基于 `__file__` 计算 |
| settings.local.json 硬编码 | 跨机器无法工作 | 环境变量覆盖 |
| `sessions.jsonl` 散落 8+ 文件 | 每个文件自己定义字符串 | `paths.py` 的 `FILE_SESSIONS` 常量 |
| package.json files[] 不完整 | 发布后插件无法运行 | 完整清单，插件可正常安装 |
| `.claudeignore` 不完整 | `__pycache__` 等未排除 | 补充缺失项 |
| Hook 源映射硬编码 | `_HOOK_SOURCE_MAP` 字典在代码里 | `paths.py` 的 `HOOK_SCRIPTS` 字典 |
| 未来目录重命名 | 需改多个文件 | 只需改 `paths.py` 一个文件 |

### 核心收益

- **可演进性**：目录结构变更从"灾难性变更"变成"配置文件修改"
- **可测试性**：测试可以 mock `CLAUDE_PROJECT_DIR` 环境变量，用临时目录运行测试
- **可发现性**：新贡献者想知道"数据文件存在哪里"，看 `paths.py` 即可
- **可迁移性**：每次目录迁移只需改 `paths.py` 一个文件 + `git mv`
- **插件可分发**：package.json files[] 完整，npm 发布后插件可正常运行

---

## 八、执行检查清单

```
[ ] Step 0.1 — 修复 cli/generate_skill_index.py 硬编码路径
[ ] Step 0.2 — 创建 .claude/data/homunculus/ 目录
[ ] Step 0.3 — 统一 instinct 数据（选方案 B，以 evolve-daemon/instinct/ 为主）
[ ] Step 0.4 — 修复 .claude/settings.local.json 硬编码路径
[ ] Step 0.5 — 补充 .claudeignore 缺失项
[ ] Step P.1 — 创建 harness/paths.py
[ ] Step P.2 — 修复 cli/generate_skill_index.py import
[ ] Step P.3 — 修复 cli/instinct_cli.py 路径
[ ] Step P.4 — 修复 hooks/bin/observe.py 路径
[ ] Step P.5 — (可选) 修复 evolve-daemon/instinct_updater.py
[ ] Step P.6 — (可选) 修复 hooks/bin/collect_error.py
[ ] Step P.7 — grep 验证无硬编码路径残留
[ ] Step M.1 — 创建 harness/ 及其子目录
[ ] Step M.2 — 创建 harness/_core/ 基础设施
[ ] Step M.3 — git mv 所有扩展目录到 harness/
[ ] Step M.4 — 更新 package.json files[]
[ ] Step M.5 — 更新 .gitignore
[ ] Step V.1 — 目录迁移验证
[ ] Step V.2 — 路径引用验证
[ ] Step V.3 — npm test
[ ] Step V.4 — MCP Server 启动验证
[ ] Step V.5 — Hook 脚本验证
[ ] Step V.6 — Evolve Daemon 验证
```

---

## 附录 A：Grep 验证命令

```bash
# 验证根目录无旧目录残留
for dir in agents skills hooks rules memory knowledge tests docs evolve-daemon cli instinct marketplace.json .mcp.json; do
  [ -e "$dir" ] && echo "❌ 残留目录: $dir" || echo "✅ 已迁移: $dir"
done

# 验证 harness 目录存在
for dir in agents skills hooks rules memory knowledge tests docs evolve-daemon cli instinct _core; do
  [ -d "harness/$dir" ] && echo "✅ harness/$dir 存在" || echo "❌ harness/$dir 缺失"
done

# 验证 index.js 仍在根目录
[ -f "index.js" ] && echo "✅ index.js 在根目录" || echo "❌ index.js 丢失"

# 验证无硬编码路径残留（排除 paths.py 自身）
grep -rn "'/Users/" --include="*.py" . | grep -v "harness/paths.py" && echo "❌ 有残留" || echo "✅ 无残留"

# 验证 paths.py 可正常导入
cd /Users/yanyinxi/工作/code/github/claude-harness-kit && python3 -c "import sys; sys.path.insert(0, 'harness'); from paths import ROOT, SKILLS_DIR, HOMUNCULUS_DIR; print(f'✅ paths.py OK: ROOT={ROOT}')"
```

## 附录 B：Git mv 推荐操作

```bash
# 使用 git mv 保留文件历史
git mv agents harness/agents
git mv skills harness/skills
git mv hooks harness/hooks
git mv rules harness/rules
git mv memory harness/memory
git mv knowledge harness/knowledge
git mv tests harness/tests
git mv docs harness/docs
git mv evolve-daemon harness/evolve-daemon
git mv cli harness/cli
git mv instinct harness/instinct
git mv marketplace.json harness/
git mv .mcp.json harness/
```

## 附录 C：Phase 0 紧急修复详解

### C.1 `generate_skill_index.py` 硬编码路径修复

```python
# cli/generate_skill_index.py line 6
# 当前（会换机器坏掉）:
SKILLS_DIR = Path("/Users/yanyinxi/工作/code/github/claude-harness-kit/skills")

# 修复为（相对路径，可移植）:
SKILLS_DIR = Path(__file__).parent.parent / "skills"
```

### C.2 `observe.py` 路径和目录创建

```python
# hooks/bin/observe.py lines 23-26
# 当前（目录不存在）:
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
OBS_DIR = PLUGIN_ROOT / ".claude" / "homunculus"
OBS_LOG = OBS_DIR / "observations.jsonl"

# 修复为（同时确保目录存在）:
import os
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
OBS_DIR = PLUGIN_ROOT / ".claude" / "data" / "homunculus"
OBS_DIR.mkdir(parents=True, exist_ok=True)  # 自动创建目录
OBS_LOG = OBS_DIR / "observations.jsonl"
```

### C.3 instinct 三副本合并

```python
# instinct_merge.py（临时脚本，用于 Phase 0）
import json
from pathlib import Path

files = [
    Path("agents/instinct/instinct-record.json"),  # 788B
    Path("instinct/instinct-record.json"),          # 7964B
    Path("evolve-daemon/instinct/instinct-record.json"),  # 8671B
]

# 读取所有记录
all_records = {}
for f in files:
    if f.exists():
        with open(f) as fp:
            data = json.load(fp)
            for record in data.get("records", []):
                all_records[record["id"]] = record

# 合并（以最新最大文件为准，时间戳优先）
merged = {"records": list(all_records.values()), "version": "merged"}

# 写入统一位置
output = Path("instinct/instinct-record.json")
output.parent.mkdir(exist_ok=True)
with open(output, "w") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print(f"✅ Merged {len(all_records)} records into {output}")
```

### C.4 `settings.local.json` 路径修复

```json
// .claude/settings.local.json
// 当前（含硬编码本机路径）:
{
  "extraKnownMarketplaces": {
    "claude-harness-kit": {
      "source": {
        "source": "directory",
        "path": "/Users/yanyinxi/工作/code/github/claude-harness-kit"
      }
    }
  }
}

// 修复为（使用环境变量）:
{
  "extraKnownMarketplaces": {
    "claude-harness-kit": {
      "source": {
        "source": "directory",
        "path": "${CLAUDE_PLUGIN_ROOT}"
      }
    }
  }
}
```

> **注意**：Claude Code 是否支持 `${CLAUDE_PLUGIN_ROOT}` 变量展开需要验证。如不支持，可改为相对路径 `"."`（相对于项目根目录）。

---

## 附录 D：Per-Module Config YAML 体系设计

（与 v2.0 一致，此处略。详见原文档 Section D）