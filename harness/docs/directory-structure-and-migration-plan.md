# CHK 目录结构规范与迁移方案

> 本文档定义 CHK 项目的目录架构规范，以及现状改造的执行计划。

---

## 第一部分：目标目录结构规范

### 一、`.claude/` — Claude Code 运行时空间（Claude Code 自管）

**核心原则：`.claude/` 下只存放运行时数据，不存放任何代码文件（.py / .sh / .js）。**

#### 允许的子目录

| 子目录 | 存放内容 | 文件格式 | 生命周期 |
|--------|---------|---------|---------|
| `data/` | Claude Code / Hooks 运行产生的原始数据 | `.jsonl`（append-only）或 `.json`（全量状态） | 运行期产生，CI 不追踪 |
| `proposals/` | Daemon 进化提案输出（Markdown） | `.md` + frontmatter | Daemon 写入，人工审核 |

#### 允许的文件（直接放在 `.claude/` 根目录）

| 文件 | 说明 | 生命周期 |
|------|------|---------|
| `settings.json` | Claude Code 全局权限配置 | Claude Code 写入，勿动 |
| `settings.local.json` | 本地权限覆盖配置 | 本地维护 |

#### 禁止事项

- ❌ `.claude/` 下禁止创建子目录存放 `.py` / `.sh` / `.md` 代码文件
- ❌ 禁止存放 `.lock` / `.bak` / `.tmp` 等临时文件（锁文件由代码自动管理，不手动提交）
- ❌ 禁止存放空目录占位

#### `data/` 文件清单

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `sessions.jsonl` | jsonl | 会话摘要，冷数据 |
| `error.jsonl` | jsonl | 工具失败记录，冷数据 |
| `agent_calls.jsonl` | jsonl | Agent 调用记录，冷数据 |
| `skill_calls.jsonl` | jsonl | Skill 调用记录，冷数据 |
| `analysis_state.json` | json | 进化分析进度（Daemon 热数据） |
| `proposal_history.json` | json | 进化提案历史（Daemon 热数据） |
| `knowledge_recommendations.json` | json | 知识推荐结果（Daemon 热数据） |

#### 归档策略

当 `.jsonl` 文件超过 500 行时，压缩归档到 `data/archive/`：

```
data/
├── sessions.jsonl
├── error.jsonl
├── ...
└── archive/
    ├── sessions_202605.jsonl.gz
    └── error_202605.jsonl.gz
```

---

### 二、`harness/` — CHK 插件主体（Git 追踪）

#### 子目录规范

| 子目录 | 存放内容 | 约束 |
|--------|---------|------|
| `_core/` | 版本管理、配置加载、核心异常 | 禁止放业务逻辑 |
| `agents/` | 22 个 Agent 定义（`.md`） | 每个文件一个 Agent |
| `skills/` | 35+ 个 Skill（每个 Skill 一个子目录） | 禁止在根目录放 `.md` |
| `rules/` | 6 个 Rule 定义（`.md`） | 每个文件一个 Rule |
| `hooks/` | Hook 系统配置和脚本 | 详见下方 |
| `evolve-daemon/` | 进化守护进程（Python 模块） | 禁止嵌套 harness/ |
| `knowledge/` | 知识推荐引擎（Python 模块）+ 知识文件 | 详见下方 |
| `memory/` | 本能记录 + 反馈积累（JSON / JSONL） | 详见下方 |
| `cli/` | CLI 工具（Python 模块） | 禁止在根目录放 `.sh` |
| `docs/` | 设计文档（`.md`） | 仅文档，不放代码 |
| `tests/` | 测试套件 | 仅测试文件 |

#### 子目录命名规则

- ✅ 全小写 + hyphen 连接（`evolve-daemon`、`skill-factory`、`rate-limits`）
- ❌ 禁止用 `_` 作为子目录名的连接符（与 Python 包名区分）
- ✅ 每个子目录必须有代码引用（零引用的目录必须删除）

#### `hooks/` 结构

```
hooks/
├── hooks.json              # Hook 配置（所有 hook 触发规则）
└── bin/
    ├── _session_utils.py   # ✅ 共享工具（多个 hook 共同依赖）
    ├── collect_session.py  # underscore ✅
    ├── collect_success.py  # underscore ✅
    ├── collect_agent.py    # underscore ✅
    ├── collect_failure.py # underscore ✅
    ├── collect_skill.py    # underscore ✅
    ├── collect_error.py   # underscore ✅
    ├── error_writer.py    # 共享写入工具
    ├── context-injector.py
    ├── extract_semantics.py
    └── *.sh               # Shell hook（所有 shell 脚本）
```

**命名规则：所有 Python hook 脚本统一用 underscore 命名（`collect_session.py`），所有 shell 脚本统一用 hyphen 命名（`safety-check.sh`）。**

#### `knowledge/` 结构

```
knowledge/
├── knowledge_recommender.py  # 知识推荐引擎（唯一读入口）
├── lifecycle.py             # 知识生命周期管理
├── lifecycle.yaml           # 生命周期配置
├── INDEX.md                 # 知识库入口索引
│
├── decision/               # 架构决策记录（ADR）
│   └── *.json
├── guideline/               # 开发规范、编码风格
│   └── *.json
├── pitfall/                # 已知陷阱、常见错误
│   └── *.json
├── process/                # 操作流程、检查清单
│   └── *.json
├── model/                  # 配置模型、数据结构定义
│   └── *.json
│
└── evolved/                # 进化生成的知识（Daemon 写入）
    ├── effect_tracking.jsonl
    ├── evolution_history.jsonl
    ├── knowledge_base.jsonl
    ├── merge_cooldown.jsonl
    ├── effect_summary.json
    └── stress_test_summary.json
```

**命名规则：知识文件统一用 `slug-type.json` 格式（例：`coding-style.json`、`json-encoding-pitfall.json`）。每个 JSON 文件必须包含标准 frontmatter：**

```json
{
  "id": "guideline-001",
  "type": "guideline | pitfall | decision | process | model | feedback",
  "name": "简短名称",
  "description": "一句话描述",
  "maturity": "draft | verified | proven | archived",
  "content": { ... },
  "created_at": "ISO 时间戳",
  "updated_at": "ISO 时间戳",
  "usage_count": 0,
  "last_used_at": null
}
```

#### `memory/` 结构

```
memory/
├── instinct-record.json     # 本能记录（置信度进化数据）
├── MEMORY.md               # memory 索引
├── chk-hidden-issues.json  # CHK 隐蔽问题（pitfall）
├── feedback_*.json         # 用户反馈积累（feedback type）
└── reference_*.json       # 参考知识
```

---

### 三、根目录文件规范

| 文件 | 说明 | 约束 |
|------|------|------|
| `index.js` | 插件入口（Node.js） | 唯一入口 |
| `package.json` | npm 包配置 | version 与 `harness/_core/version.json` 同步 |
| `CLAUDE.md` | 项目说明（由 `_core/version.json` 读取版本） | 核心文档 |
| `README.md` | 用户文档 | 由 CLAUDE.md 生成 |
| `hooks` → `harness/hooks` | 便利符号链接 | 仅开发便利，包发布时排除 |

---

### 四、防乱建规则（写在 CLAUDE.md "Known Traps" 下）

```
规范 1：.claude/ 只允许 2 个子目录：data/, proposals/
规范 2：harness/ 下只允许以下子目录（白名单）：
  _core, agents, skills, rules, hooks, evolve-daemon,
  knowledge, memory, cli, docs, tests
规范 3：所有子目录用 hyphen 连接（evolve-daemon，非 evolve_daemon）
规范 4：每个子目录必须有代码引用，无引用的空目录必须删除
规范 5：禁止嵌套 harness/（如 evolve-daemon/harness/）
规范 6：插件配置文件只放 .claude-plugin/ 下，harness/ 下禁止重复
规范 7：知识统一放 harness/knowledge/，.claude/knowledge/ 废除
规范 8：本能记录统一放 harness/memory/，harness/instinct/ 废除
规范 9：Python hook 脚本统一 underscore 命名，Shell hook 统一 hyphen 命名
```

---

## 第二部分：现状改造

### 一、清理清单（按优先级）

#### P0 — 必须立即清理（无代码引用，幽灵目录）

| # | 操作 | 路径 |
|---|------|------|
| 1 | `rm -rf harness/agents/instinct/` | 空目录，0 处代码引用 |
| 2 | `rm -rf harness/evolve-daemon/harness/` | 幽灵嵌套，内含空 `evolve-daemon/` |
| 3 | `rm harness/marketplace.json` | 与 `.claude-plugin/marketplace.json` 完全重复 |
| 4 | `rm -rf .claude/knowledge/` | 知识迁移到 `harness/knowledge/` |
| 5 | `rm -rf .claude/tests/` | 测试迁移到 `harness/tests/` |
| 6 | `rm -rf harness/instinct/` | 本能迁移到 `harness/memory/` |
| 7 | `rm harness/knowledge/manual` | 死链接（指向 `.claude/knowledge/`） |

#### P1 — 脏数据清理

| # | 操作 | 说明 |
|---|------|------|
| 8 | `rm -rf .claude/data/backups/` | 3 个 config 备份，不应追踪 |
| 9 | `rm -rf .claude/data/homunculus/` | 废弃子系统，空目录 |
| 10 | `rm -rf .claude/data/rate-limits/` | 只有空 `state.json: {}` |
| 11 | `rm -rf .claude/data/worktrees/` | 只有空 `.worktree-map.json: {}` |
| 12 | `rm .claude/data/.session_start` | 会话结束后无意义 |
| 13 | `mv .claude/data/failures.jsonl .claude/data/failures.legacy.jsonl` | 旧格式（3 行），已迁移到 error.jsonl |

#### P2 — Hook 脚本命名统一

| # | 操作 | 说明 |
|---|------|------|
| 14 | `mv harness/hooks/bin/collect-agent.py harness/hooks/bin/collect_agent.py` | hooks.json 用 underscore |
| 15 | `mv harness/hooks/bin/collect-failure.py harness/hooks/bin/collect_failure.py` | 同上 |
| 16 | `mv harness/hooks/bin/collect-skill.py harness/hooks/bin/collect_skill.py` | 同上 |

#### P3 — 代码引用更新

##### P3-1：`knowledge_recommender.py` — 路径常量（2 处）

```
文件：harness/knowledge/knowledge_recommender.py

第 37-38 行：
  # 知识库 1: 手工维护的知识 (.claude/knowledge/)
  KNOWLEDGE_DIR = PROJECT_ROOT / ".claude" / "knowledge"
→ 改为：
  # 知识库 1: 手工维护的知识 (harness/knowledge/)
  KNOWLEDGE_DIR = PROJECT_ROOT / "harness" / "knowledge"

第 170 行注释：
  知识库 1: .claude/knowledge/ — 手工维护的专家知识 (通过 harness/knowledge/manual 符号链接访问)
→ 改为：
  知识库 1: harness/knowledge/ — 手工维护的专家知识
```

##### P3-2：`gc.py` — 路径常量（2 处）

```
文件：harness/cli/gc.py

第 5 行 docstring：
  调用 GC Agent 扫描 .claude/knowledge/ 目录
→ 改为：
  调用 GC Agent 扫描 harness/knowledge/ 目录

第 117 行：
  knowledge_dir = root / ".claude" / "knowledge"
→ 改为：
  knowledge_dir = root / "harness" / "knowledge"
```

##### P3-3：`init.py` — 骨架创建路径（3 处）

```
文件：harness/cli/init.py

第 261 行：
  claude_dir / "knowledge",
→ 改为：
  harness_dir / "knowledge",

第 245 行注释：
  "- 项目知识: `.claude/knowledge/INDEX.md`"
→ 改为：
  "- 项目知识: `harness/knowledge/INDEX.md`"

第 426 行：
  print(f"  🔍 [dry-run] 会创建骨架: .claude/rules/, .claude/knowledge/, .claude/data/")
→ 改为：
  print(f"  🔍 [dry-run] 会创建骨架: .claude/data/, .claude/proposals/")
  （knowledge/ 不再在 .claude/ 下，改为 harness/ 下已有）
```

##### P3-4：`test_cli.py` — 测试路径（3 处）

```
文件：harness/tests/test_cli.py

第 164 行：
  idx = tmp / ".claude" / "knowledge" / "INDEX.md"
→ 改为：
  idx = tmp / "harness" / "knowledge" / "INDEX.md"

第 169 行：
  print("  ✅ kit init: 生成 .claude/knowledge/INDEX.md")
→ 改为：
  print("  ✅ kit init: 生成 harness/knowledge/INDEX.md")

第 256 行：
  Path(tmp / ".claude" / "knowledge" / "drift-report.md").exists()
→ 改为：
  Path(tmp / "harness" / "knowledge" / "drift-report.md").exists()
```

##### P3-5：`test_knowledge.py` — 测试路径（2 处）

```
文件：harness/tests/test_knowledge.py

第 36 行：
  knowledge_dir = tmp_path / ".claude" / "knowledge"
→ 改为：
  knowledge_dir = tmp_path / "harness" / "knowledge"

第 54 行：
  knowledge_dir = temp_project / ".claude" / "knowledge"
→ 改为：
  knowledge_dir = temp_project / "harness" / "knowledge"
```

##### P3-6：`lifecycle.py` — 注释路径（2 处）

```
文件：harness/knowledge/lifecycle.py

第 8 行：
  3. 跨项目引用计数（扫描 repo-index.json 中各项目的 .claude/knowledge/ 引用情况）
→ 改为：
  3. 跨项目引用计数（扫描 repo-index.json 中各项目的 harness/knowledge/ 引用情况）

第 151 行：
  2. 更新原项目的 .claude/knowledge/INDEX.md 引用
→ 改为：
  2. 更新原项目的 harness/knowledge/INDEX.md 引用
```

##### P3-7：`collect_error.py` — `_HOOK_SOURCE_MAP` 键名（3 处）

```
文件：harness/hooks/bin/collect_error.py

_HOOK_SOURCE_MAP（第 46-48 行）：
  "collect-failure.py": "hooks/bin/collect-failure.py",
  "collect-agent.py": "hooks/bin/collect-agent.py",
  "collect-skill.py": "hooks/bin/collect-skill.py",
→ 改为：
  "collect_failure.py": "hooks/bin/collect_failure.py",
  "collect_agent.py": "hooks/bin/collect_agent.py",
  "collect_skill.py": "hooks/bin/collect_skill.py",
```

##### P3-8：`extract_semantics.py` — 注释（1 处）

```
文件：harness/hooks/bin/extract_semantics.py

第 5 行：
  触发: collect-session.py 检测到纠正时异步调用
→ 改为：
  触发: collect_session.py 检测到纠正时异步调用
```

##### P3-9：`llm_decision.py` — 去除重复的 instinct 路径定义（合并到 instinct_updater.py）

```
文件：harness/evolve-daemon/llm_decision.py

删除第 22-25 行：
  # ── Data Path (canonical: harness/instinct/) ────────────────────────
  INSTINCT_ROOT = Path(__file__).parent.parent / "instinct"
  INSTINCT_FILE = INSTINCT_ROOT / "instinct-record.json"
  INSTINCT_FILE.parent.mkdir(parents=True, exist_ok=True)

在文件顶部 import 区添加：
  from instinct_updater import load_instinct

删除第 75-83 行自身的 load_instinct 函数：
  def load_instinct(root: Path) -> dict:  ← 删除整段

修改第 77 行的调用点（load_instinct 调用处），
  确保从 import 来的版本工作正常：
  第 126 行、第 376 行：load_instinct(root) ← 已通过 import 获得，无需改动
```

##### P3-10：`paths.py` — instinct 路径常量（5 处）

```
文件：harness/paths.py

第 67 行：
  DIR_INSTINCT = "instinct"
→ 删除此常量（不再有 harness/instinct/ 目录）

第 85 行：
  FILE_INSTINCT_RECORD = "instinct-record.json"
→ 删除此常量

第 19 行注释（目录树）：
  └── instinct/           # 本能记录
→ 删除此行

第 146 行：
  INSTINCT_DIR = PLUGIN_ROOT / DIR_INSTINCT  # harness/instinct/ — 本能记录
→ 删除

第 159-160 行：
  EVOLVE_INSTINCT_DIR = INSTINCT_DIR         # 统一到 harness/instinct/（evolve-daemon/instinct/ 已废弃）
  EVOLVE_INSTINCT_FILE = EVOLVE_INSTINCT_DIR / FILE_INSTINCT_RECORD
→ 删除

第 166 行：
  INSTINCT_FILE = INSTINCT_DIR / FILE_INSTINCT_RECORD   # 本能记录文件
→ 删除

第 336 行 __all__ 导出：
  删除 "DIR_INSTINCT", "FILE_INSTINCT_RECORD"

第 341 行 __all__ 导出：
  删除 "FILE_INSTINCT_RECORD"

第 351-354 行 __all__ 导出：
  删除 "INSTINCT_DIR", "EVOLVE_INSTINCT_DIR", "EVOLVE_INSTINCT_FILE", "INSTINCT_FILE"

并在文件顶部注释（第 27-28 行附近）添加 MEMORY_DIR 引用说明：
  DIR_MEMORY = "memory"         # 本能记录 + 反馈积累目录
```

##### P3-11：`knowledge_recommender.py` — instinct 路径常量（1 处）

```
文件：harness/knowledge/knowledge_recommender.py

第 41 行：
  INSTINCT_DIR = PROJECT_ROOT / "harness" / "instinct"
→ 改为：
  INSTINCT_DIR = PROJECT_ROOT / "harness" / "memory"
```

##### P3-12：`instinct_updater.py` — instinct 路径（2 处）

```
文件：harness/evolve-daemon/instinct_updater.py

第 67 行（load_instinct 函数）：
  path = root / "harness" / "instinct" / "instinct-record.json"
→ 改为：
  path = root / "harness" / "memory" / "instinct-record.json"

第 80 行（save_instinct 函数）：
  path = root / "harness" / "instinct" / "instinct-record.json"
→ 改为：
  path = root / "harness" / "memory" / "instinct-record.json"
```

##### P3-13：`llm_decision.py`（再次）— instinct 路径（已在 P3-9 中删除了重复定义，无需额外改动）

##### P3-14：`kb_shared.py` — instinct 路径常量（1 处）

```
文件：harness/evolve-daemon/kb_shared.py

第 75 行：
  INSTINCT_PATH = _find_root() / "harness" / "instinct" / "instinct-record.json"
→ 改为：
  INSTINCT_PATH = _find_root() / "harness" / "memory" / "instinct-record.json"

第 567 行（migrate_from_instinct 函数）：
  instinct_file = root / "harness" / "instinct" / "instinct-record.json"
→ 改为：
  instinct_file = root / "harness" / "memory" / "instinct-record.json"
```

##### P3-15：`status.py` — instinct 路径（1 处）

```
文件：harness/cli/status.py

第 80 行：
  instinct_file = root / "instinct" / "instinct-record.json"
→ 改为：
  instinct_file = root / "memory" / "instinct-record.json"
```

##### P3-16：`collect_success.py` — instinct 路径（1 处）

```
文件：harness/hooks/bin/collect_success.py

第 30 行：
  INSTINCT_FILE = CHK_ROOT / "instinct" / "instinct-record.json"
→ 改为：
  INSTINCT_FILE = CHK_ROOT / "memory" / "instinct-record.json"
```

##### P3-17：`daemon.py` — instinct 注释和路径（2 处）

```
文件：harness/evolve-daemon/daemon.py

第 31 行注释：
  - 回滚事件会记录到 instinct-record.json
→ 不变（文件名不变，只是目录变了）

第 213 行 config：
  "paths": {..., "instinct_dir": "instinct"}
→ 改为：
  "paths": {..., "instinct_dir": "memory"}
```

##### P3-18：`apply_change.py` — instinct 注释（1 处）

```
文件：harness/evolve-daemon/apply_change.py

第 47 行 config：
  "instinct_dir": "instinct"
→ 改为：
  "instinct_dir": "memory"
```

##### P3-19：`llm_decision.py`（再次）— instinct 路径注释（1 处）

```
文件：harness/evolve-daemon/llm_decision.py

第 67 行：
  "instinct_dir": "instinct",
→ 改为：
  "instinct_dir": "memory",
```

##### P3-20：`instinct_cli.py` — instinct 路径（3 处）

```
文件：harness/cli/instinct_cli.py

第 22 行注释：
  # ── Data Path (canonical: harness/instinct/) ────────────────────────
→ 改为：
  # ── Data Path (canonical: harness/memory/) ────────────────────────

第 24 行：
  INSTINCT_ROOT = Path(__file__).parent.parent / "instinct"
→ 改为：
  INSTINCT_ROOT = Path(__file__).parent.parent / "memory"

第 25 行：
  INSTINCT_FILE = INSTINCT_ROOT / "instinct-record.json"
→ 不变（文件名不变）
```

##### P3-21：测试文件注释和断言 — instinct 路径

```
文件：harness/tests/test_evolve.py

第 45-46 行（test_knowledge 模块 fixture）：
  instinct_dir = tmp_path / "harness" / "instinct"
  instinct_dir.mkdir(parents=True)
→ 改为：
  instinct_dir = tmp_path / "harness" / "memory"
  instinct_dir.mkdir(parents=True)

第 147 行（mock_instinct_record fixture）：
  instinct_file = temp_project / "harness" / "instinct" / "instinct-record.json"
→ 改为：
  instinct_file = temp_project / "harness" / "memory" / "instinct-record.json"

文件：harness/tests/evolve-daemon/test_instinct_updater.py

第 14 行 docstring：
  """验证 load_instinct 使用 harness/instinct/ 路径"""
→ 改为：
  """验证 load_instinct 使用 harness/memory/ 路径"""

第 17 行注释：
  # INSTINCT_ROOT 应为 harness/instinct/
→ 改为：
  # INSTINCT_ROOT 应为 harness/memory/

文件：harness/cli/instinct_cli.test.py

第 14 行 docstring：
  """验证 instinct_cli 使用 harness/instinct/ 路径"""
→ 改为：
  """验证 instinct_cli 使用 harness/memory/ 路径"""

第 17-20 行断言：
  assert INSTINCT_ROOT.parts[-2] == expected_parent  # 应为 harness
  assert INSTINCT_ROOT.parts[-1] == "instinct"      # 应为 memory
→ 不变（只改路径定义常量，不改测试断言逻辑）
```

---

### 二、文件迁移操作

```
# 1. 迁移知识文件到 harness/knowledge/
mv .claude/knowledge/decision/       harness/knowledge/decision/
mv .claude/knowledge/guideline/     harness/knowledge/guideline/
mv .claude/knowledge/pitfall/       harness/knowledge/pitfall/
mv .claude/knowledge/model/        harness/knowledge/model/
mv .claude/knowledge/process/      harness/knowledge/process/
mv .claude/knowledge/INDEX.md      harness/knowledge/INDEX.md

# 2. 迁移 instinct-record.json 到 harness/memory/
mv harness/instinct/instinct-record.json  harness/memory/instinct-record.json

# 3. 迁移测试文件到 harness/tests/
mv .claude/tests/test_evolution_triggers.py    harness/tests/
mv .claude/tests/test_full_link_evolution.py    harness/tests/
mv .claude/tests/test_parallelism_protocol.py   harness/tests/
```

---

### 三、执行顺序

```
Step 1: 迁移文件（mv 命令）→ 确保数据已到新位置
Step 2: 更新代码路径（P3-1 ~ P3-21）→ 确保所有引用指向新位置
Step 3: 删除旧目录（rm -rf）→ 确认无残留
Step 4: 运行 npm test → 验证无破坏
```

---

### 四、改造完成后的目标结构

```
.claude/
├── settings.json
├── settings.local.json
├── data/
│   ├── sessions.jsonl
│   ├── error.jsonl
│   ├── agent_calls.jsonl
│   ├── skill_calls.jsonl
│   ├── analysis_state.json
│   ├── proposal_history.json
│   └── knowledge_recommendations.json
└── proposals/

harness/
├── _core/
├── agents/
├── skills/
├── rules/
├── hooks/bin/
├── evolve-daemon/
│   ├── daemon.py, analyzer.py, ...
│   ├── templates/
│   └── knowledge → ../knowledge/evolved  # 符号链接
├── knowledge/
│   ├── knowledge_recommender.py
│   ├── lifecycle.py, lifecycle.yaml
│   ├── INDEX.md
│   ├── decision/, guideline/, pitfall/, process/, model/  # 手工知识
│   └── evolved/  # 进化知识
├── memory/
│   ├── instinct-record.json  # 本能记录（合并后）
│   ├── MEMORY.md
│   └── *.json  # 反馈积累
├── cli/
├── docs/
└── tests/
```

---

### 五、注意事项

1. **`llm_decision.py` 有两个 instinct 路径定义**：`INSTINCT_ROOT/INSTINCT_FILE` 常量（第 22-25 行）和 `load_instinct()` 函数（第 75-83 行）。两者都要删除/合并，只需保留 import 语句，让 `llm_decision.py` 使用 `instinct_updater.py` 的 `load_instinct`。

2. **`instinct_cli.py` 与 `llm_decision.py` 各自独立定义了 INSTINCT_FILE 路径**。两者都要改，都指向 `harness/memory/instinct-record.json`。

3. **`collect_success.py` 和 `kb_shared.py` 各自硬编码了 instinct 路径**。都要改。

4. **迁移知识文件时**，`harness/knowledge/` 下可能已有同名空子目录（`decision/`、`guideline/` 等），迁移前先检查，如果有空目录则先 `rmdir`。

5. **`.gitignore` 需更新**：确认以下已被忽略：
   - `.claude/data/backups/`（新增）
   - `.claude/data/homunculus/`（新增）
   - `.claude/data/rate-limits/`（新增）
   - `.claude/data/worktrees/`（新增）
   - `harness/instinct/`（已迁移，目录已删除）
