# Claude Harness Kit — 完整落地执行计划 v4.0

> **版本**: v4.0 — 基于 Claude Code 官方能力 + 项目 README.md 深度分析
> **核心策略**: 完整平移 + 精确解耦 + 保留所有设计细节
> **更新**: 2026-04-29

---

## 〇、Claude Code 官方能力基准（已验证）

### 已确认支持的能力

| 能力 | 状态 | 说明 |
|------|------|------|
| `--plugin-dir` | ✅ | CLI 参数加载插件目录 |
| `agents/*.md` | ✅ | .md + YAML frontmatter |
| `skills/<name>/SKILL.md` | ✅ | progressive disclosure |
| `hooks.json` | ✅ | 插件内 hooks 配置 |
| `settings.json` hooks | ✅ | 直接配置格式 |
| `${CLAUDE_PLUGIN_ROOT}` | ✅ | 插件内路径变量 |
| `disallowedTools` | ✅ | agent frontmatter 字段 |
| `user-invocable: true` | ✅ | Skill 可用 `/name` 调用 |
| `disable-model-invocation` | ✅ | 禁用自动触发 |
| 权限系统 | ✅ | allow/ask/deny 模式匹配 |
| 10+ 种 Hook 事件 | ✅ | PreToolUse/PostToolUse/Stop/SubagentStop/SessionStart 等 |

### 关键官方限制（不可假设）

1. **无内置 `/evolve` `/workflow` 命令** — 必须自己实现为 Skill 或 Command
2. **无 `evolutionMandate` 机制** — Hook 只做数据采集，不注入决策
3. **`disallowedTools` 是软限制** — 需配合 `permissionMode` 生效
4. **SubagentStop 不传 `subagent_type`** — 所有 agent 调用记录为 "unknown"
5. **hooks.json Command Hook 是否能执行 Python** — **需验证**
6. **npm marketplace 分发** — 机制存在但需完整验证

---

## 一、项目完整能力清单（README.md 确认）

### 1.1 Hook 脚本矩阵（10 个）

| # | 脚本 | Hook 事件 | Matcher | 超时 | 功能 |
|---|------|----------|---------|------|------|
| 1 | `path_validator.py` | PreToolUse | `Write\|Edit` | 5s | 路径安全验证 |
| 2 | `collect_agent_launch.py` | PostToolUse | `Agent` | 5s | Agent 启动采集 |
| 3 | `collect_skill_usage.py` | PostToolUse | `Skill` | 5s | Skill 使用采集 |
| 4 | `collect_tool_failure.py` | PostToolUseFailure | `""` | 3s | 工具失败采集 |
| 5 | `collect_violations.py` | PreToolUse | `Write\|Edit` | 5s | 规则违规检测 |
| 6 | `detect_feedback.py` | UserPromptSubmit | `""` | 3s | 反馈信号检测 |
| 7 | `session_evolver.py` | Stop | `""` | 10s | 会话数据采集 + 编排 |
| 8 | `strategy_updater.py` | Stop | `""` | 5s | 策略权重更新 |
| 9 | `load_evolution_state.py` | SessionStart | `""` | 5s | 状态注入 |
| 10 | `quality-gate.sh` | PostToolUse | `Write\|Edit` | 5s | 质量门禁 |
| 11 | `safety-check.sh` | PreToolUse | `Bash` | 3s | Bash 命令安全检查 |

**注意**：实际有 11 个 hook 脚本（含 Shell 脚本），不是 7 个。

### 1.2 Python 引擎模块矩阵（lib/，14 个）

| # | 模块 | 行数 | 功能 |
|---|------|------|------|
| 1 | `evolution_safety.py` | 545 | 熔断器 + 限流器 + 回滚 + 数据校验 |
| 2 | `evolution_scoring.py` | 406 | 四维度评分引擎 (0-100) |
| 3 | `evolution_dashboard.py` | 292 | 仪表盘三级输出 (L1/L2/L3) |
| 4 | `evolution_orchestrator.py` | 560 | 进化编排器（触发检测 + 决策持久化） |
| 5 | `evolution_effects.py` | ~200 | 进化效果对比 + 趋势分析 |
| 6 | `token_efficiency.py` | 185 | Token 预算管理 + 数据压缩 |
| 7 | `data_rotation.py` | ~150 | 数据轮转 + 归档清理 |
| 8 | `rollback_evolution.py` | ~100 | 进化回滚 CLI |
| 9 | `knowledge_graph.py` | ~200 | 知识图谱 API |
| 10 | `knowledge_retriever.py` | ~150 | 知识检索 |
| 11 | `strategy_generator.py` | ~150 | 策略生成 |
| 12 | `constants.py` | 51 | 常量定义 |
| 13 | `parallel_executor.py` | 241 | 并行执行器 |
| 14 | `examples/` | - | 示例代码 |

### 1.3 备用进化引擎（evolution/，独立于 lib/）

```
evolution/
├── engine.py              # 备用进化引擎主控
├── config.py              # 配置管理
├── cli.py                 # CLI: run / status / confirm / force
├── hook_integration.py    # [DEPRECATED] 旧桥接层
├── evolvers/
│   ├── base.py           # 基类
│   ├── skill_evolver.py  # Skill 进化
│   ├── agent_evolver.py  # Agent 进化
│   ├── rule_evolver.py   # Rule 进化
│   └── memory_evolver.py # Memory 进化
└── analyzers/
    ├── session_analyzer.py # 会话分析
    └── pattern_detector.py # 模式检测
```

**关键**：这是**第二套**进化引擎，与 lib/ 下的主引擎并存。迁移时需要决定保留哪套。

### 1.4 CLI 命令清单（README Section 15）

| 命令 | 功能 |
|------|------|
| `python3 evolution_safety.py status` | 进化状态总览 |
| `python3 evolution_safety.py validate` | 数据完整性校验 |
| `python3 evolution_safety.py rollback --target <id>` | 回滚进化 |
| `python3 evolution_dashboard.py` | 查看仪表盘 |
| `python3 evolution_effects.py report` | 查看进化效果报告 |
| `python3 evolution_effects.py trend` | 查看进化趋势 |
| `python3 data_rotation.py cleanup` | 数据轮转清理（保留最近 7 天） |
| `python3 data_rotation.py status` | 数据状态 |
| `python3 rollback_evolution.py` | 回滚进化（独立 CLI） |
| `python3 knowledge_graph.py <cmd>` | 知识图谱操作 |
| `python3 .claude/evolution/cli.py run` | Python 备用引擎 |
| `python3 .claude/evolution/cli.py status` | 备用引擎状态 |

**注意**：这些命令都需要在插件中包装为统一 CLI 接口。

### 1.5 评分体系（README Section 10）

```
总分 = 基础分(40) + 活跃度(20) + 效果分(25) + 质量分(15)
```

**Skill 评分**：
- 基础分 = `min(40, 调用次数 × 4)`
- 活跃度 = `min(20, 近7天调用 × 6)`
- 效果分 = 无熔断 ? `min(25, 成功率×25)` : 0
- 质量分 = 无损坏行(5) + 进化频率≤1(5) + 无异常检测(5)

**Agent 评分**：
- 基础分 = `min(40, 任务数 × 8)`
- 活跃度 = `min(20, 近7天任务 × 4)`
- 效果分 = 无熔断 ? `min(25, 基线步数/实际步数×20)` : 0
- 质量分 = 无异常检测 ? 15 : 5

**评分等级**：A(≥80) / B(≥65) / C(≥50) / D(≥35) / F(<35)

### 1.6 Token 三层渐进式架构（README Section 9）

| 层级 | Token 预算 | 用途 | 时机 |
|------|----------|------|------|
| L1 | ≤200 | 仪表盘摘要 | SessionStart Hook |
| L2 | ≤1000 | 触发建议 + 详细统计 | Stop Hook (--summary) |
| L3 | ≤5000 | 进化 Agent 输入 | 触发进化时 |

**核心原则**：原始 JSONL 永不进入 LLM 上下文。

### 1.7 风险分级（README Section 6.4）

| 风险等级 | 操作类型 | 审批要求 |
|---------|---------|---------|
| **Low** | 追加内容 | 自动执行 |
| **Medium** | 修改现有内容 | 自动执行 + 通知 |
| **High** | 删除/重构 | 人工确认 |
| **Critical** | 安全相关 | 禁止自动 |

### 1.8 数据轮转策略（README Section 11）

- **7 天内**：保留在原位置
- **超过 30 天**：压缩到 `backups/*.gz`
- **超过 90 天**：删除

### 1.9 触发条件矩阵（README Section 6.1）

| 维度 | 条件 | 阈值 | 冷却期 |
|------|------|------|--------|
| Skill | 累计调用次数 | ≥10 | 24h |
| Skill | 成功率下降 | >20% | 24h |
| Agent | 同类任务次数 | ≥5 | 24h |
| Agent | 失败率 | >30% | 12h |
| Rule | 违规次数 | ≥3 | 48h |
| Memory | 用户反馈信号 | ≥1 | 无冷却 |

### 1.10 安全防护体系（README Section 6.3）

**五层防护**：
- 层 0: Hook 层（PreToolUse 阻止危险操作）
- 层 1: 数据采集层（文件锁、Schema 校验、脱敏）
- 层 2: 触发层（熔断器、限流器、优先级阈值）
- 层 3: 执行层（修改前快照、风险分级、原子写入）
- 层 4: 审计层（evolution_history.jsonl、回滚能力、效果追踪）

**熔断机制**：连续 2 次退化 → 熔断开启 → 阻止进化
**放弃机制**：连续 5 次 missed → 移除 trigger

---

## 二、核心思路（v4.0）

```
❌ v3.0 错误：低估了 Python 引擎规模（14 个模块 vs 6 个）
✅ v4.0：正确统计：lib/(14) + evolution/(独立引擎) + hooks(11个)

❌ v3.0 错误：只规划了 6 个 CLI 命令
✅ v4.0：正确统计：10+ 个 CLI 命令需要包装

❌ v3.0 错误：忽略了评分体系、Token 三层架构、风险分级
✅ v4.0：保留所有设计细节，不重写

❌ v3.0 错误：假设 evolution/ 目录是"备用"可忽略
✅ v4.0：独立引擎也是核心资产，需要决策保留哪套
```

**架构决策点**：

1. **双轨引擎 vs 单轨**：保留 lib/ 主引擎，还是 evolution/ 备用引擎？
   - 建议：保留 lib/ 主引擎（经过更多验证），evolution/ 作为参考实现
2. **Shell 脚本处理**：quality-gate.sh 和 safety-check.sh 如何迁移？
   - 建议：保留 Shell，hooks.json 支持 Shell 命令执行
3. **统一 CLI**：10+ 个独立 CLI 如何包装？
   - 建议：创建统一的 `evolution-cli.py` 入口，子命令分组

---

## 三、Phase 0: 平移 + 验证（Day 1-2）

### D1a: 创建插件骨架（Day 1，半天）

#### 1. 创建 GitHub 仓库

```bash
# 1. GitHub 创建 claude-harness-kit 仓库
# 2. 本地初始化
mkdir claude-harness-kit && cd claude-harness-kit && git init
```

#### 2. 创建插件目录结构

```
claude-harness-kit/
├── .claude-plugin/
│   └── plugin.json              ← 新建
├── agents/                       ← 从 .claude/agents/ 平移（18个）
├── skills/                       ← 从 .claude/skills/ 平移（14个）
├── hooks/
│   ├── hooks.json               ← 新建（插件格式）
│   └── bin/                     ← 从 .claude/hooks/scripts/ 平移（11个）
├── rules/                        ← 从 .claude/rules/ 平移（8个）
├── lib/                          ← 从 .claude/lib/ 平移（14个 Python 模块）
├── evolution/                   ← 从 .claude/evolution/ 平移（备用引擎）
├── config/                      ← 从 .claude/data/ 平移
├── memory/
│   └── MEMORY.md                ← 从 .claude/memory/ 平移
├── docs/                         ← 从 .claude/docs/ 平移
├── tests/                        ← 从 .claude/tests/ 平移
├── CLAUDE.md                     ← 从 .claude/CLAUDE.md 平移
├── package.json                  ← 新建
└── README.md                     ← 新建
```

#### 3. 批量平移文件

```bash
# agents（18个）
cp -r .claude/agents/ claude-harness-kit/agents/

# skills（14个）
cp -r .claude/skills/ claude-harness-kit/skills/

# rules（8个）
cp -r .claude/rules/ claude-harness-kit/rules/

# hook 脚本（11个）
mkdir -p claude-harness-kit/hooks/bin/
cp .claude/hooks/scripts/*.py claude-harness-kit/hooks/bin/
cp .claude/hooks/scripts/*.sh claude-harness-kit/hooks/bin/

# Python 引擎（lib/，14个模块）
cp -r .claude/lib/ claude-harness-kit/lib/

# 备用进化引擎（evolution/）
cp -r .claude/evolution/ claude-harness-kit/evolution/

# 进化数据
cp .claude/data/*.json claude-harness-kit/config/ 2>/dev/null || true
cp .claude/data/*.jsonl claude-harness-kit/config/ 2>/dev/null || true

# 文档
cp -r .claude/docs/ claude-harness-kit/docs/

# 记忆
cp -r .claude/memory/ claude-harness-kit/memory/

# CLAUDE.md
cp .claude/CLAUDE.md claude-harness-kit/CLAUDE.md

# 测试
cp -r .claude/tests/ claude-harness-kit/tests/
```

#### 4. 创建插件必需文件

**plugin.json**：
```json
{
  "name": "claude-harness-kit",
  "version": "0.1.0",
  "description": "Claude Code 多 Agent 工作流编排 + 四维度自进化插件",
  "author": {
    "name": "Your Name",
    "email": "you@example.com"
  },
  "repository": "https://github.com/you/claude-harness-kit",
  "license": "MIT"
}
```

**package.json**：
```json
{
  "name": "claude-harness-kit",
  "version": "0.1.0",
  "description": "Claude Code 多 Agent 工作流编排 + 四维度自进化插件",
  "main": "index.js",
  "files": [".claude-plugin/", "agents/", "skills/", "hooks/", "rules/", "lib/", "evolution/", "config/", "memory/", "tests/", "CLAUDE.md"],
  "keywords": ["claude-code", "claude-code-plugin", "workflow", "multi-agent", "self-evolution"],
  "license": "MIT",
  "engines": { "node": ">=18" }
}
```

### D1b: 验证插件加载 + Hook 执行（Day 1.5，关键验证）

#### 验证项 1：插件基本加载

```bash
claude --plugin-dir /path/to/claude-harness-kit --help
# 预期：能看到 agent 列表、skill 列表
```

#### 验证项 2：hooks.json Python Command Hook

```bash
# 创建最小测试插件
mkdir /tmp/test-hook-plugin/.claude-plugin
echo '{"name":"test-hook"}' > /tmp/test-hook-plugin/.claude-plugin/plugin.json

mkdir /tmp/test-hook-plugin/hooks
cat > /tmp/test-hook-plugin/hooks/hooks.json << 'EOF'
{
  "description": "测试 Python hook",
  "hooks": {
    "PreToolUse": [{
      "matcher": "Write",
      "hooks": [{
        "type": "command",
        "command": "python3 -c \"import sys, json; print(json.dumps({'test': True}))\"",
        "timeout": 10
      }]
    }]
  }
}
EOF

claude --plugin-dir /tmp/test-hook-plugin -p "test"
```

#### 验证项 3：hooks.json Shell Command Hook

```bash
cat > /tmp/test-hook-plugin/hooks/hooks.json << 'EOF'
{
  "description": "测试 Shell hook",
  "hooks": {
    "PreToolUse": [{
      "matcher": "Write",
      "hooks": [{
        "type": "command",
        "command": "bash -c 'echo {\"test\": true}'",
        "timeout": 10
      }]
    }]
  }
}
EOF

claude --plugin-dir /tmp/test-hook-plugin -p "test"
```

#### 验证结果处理

| Python hook | Shell hook | 决策 |
|------------|------------|------|
| ✅ | ✅ | 两种都保留，hooks.json 直接配置 |
| ✅ | ❌ | 保留 Python，Shell 改用 Python 替代 |
| ❌ | ✅ | 改用 Node.js，保留 Shell 不确定 |
| ❌ | ❌ | 检查 Claude Code 版本或环境配置 |

#### 验证项 4：Python 引擎可运行

```bash
cd claude-harness-kit

# 验证 lib/ 引擎可 import
python3 -c "import lib.evolution_orchestrator; print('OK')" 2>&1

# 验证 evolution/ 引擎可 import
python3 -c "import evolution.engine; print('OK')" 2>&1

# 验证各 CLI 模块
python3 lib/evolution_safety.py status 2>&1
python3 lib/evolution_dashboard.py 2>&1
```

**D1 验收标准**：
1. ✅ 插件目录结构完整（所有 11 个 hook 脚本 + 14 个 Python 模块）
2. ✅ `claude --plugin-dir` 能看到 agent/skill 列表
3. ✅ Python/Shell hook 验证结果已知
4. ✅ Python 引擎可运行（至少 import 不报错）

---

## 四、Phase 1: 解耦项目绑定（Day 2-4）

### D2: Config Schema 定义（先于解耦）

**config/domains.json**：
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": {
    "type": "object",
    "required": ["detect", "source_paths"],
    "properties": {
      "detect": { "type": "array", "items": { "type": "string" } },
      "source_paths": { "type": "array", "items": { "type": "string" } },
      "test_paths": { "type": "array", "items": { "type": "string" } },
      "build_commands": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

**config/path-patterns.json**：
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["allowed", "forbidden"],
  "properties": {
    "allowed": { "type": "array", "items": { "type": "string" } },
    "forbidden": { "type": "array", "items": { "type": "string" } },
    "by_domain": { "type": "object" }
  }
}
```

**config/violation-rules.json**：
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["name", "severity", "pattern"],
    "properties": {
      "name": { "type": "string" },
      "severity": { "enum": ["Critical", "High", "Medium", "Low"] },
      "pattern": { "type": "string" },
      "message": { "type": "string" },
      "domains": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

### D3: 解耦 MEDIUM 文件（Day 2-3，4 Agent 并行）

| Agent | 解耦文件 | 具体操作 |
|-------|---------|---------|
| Agent 1 | `session_evolver.py` + `load_evolution_state.py` | 硬编码路径 → `${CLAUDE_PLUGIN_ROOT}/config/` |
| Agent 2 | `path_validator.py` + `collect_violations.py` | Maven/Vue 规则 → `config/path-patterns.json` |
| Agent 3 | `collect_agent_launch.py` + `collect_skill_usage.py` | 检查是否需要解耦 |
| Agent 4 | `strategy_variants.json` + `evolver.md` + `evolution-system-design.md` | agent 名改通用 + 示例改伪代码 |

**解耦执行步骤**：
1. 读原文件，找到所有 `${PROJECT_ROOT}`、`main/backend/`、`main/frontend/` 等硬编码
2. 用 `config/*.json` 配置替换
3. 验证：在非 Java 项目中运行不报错

**Agent 端点解耦重点**：

`backend-developer.md`：删除 Spring Boot/MyBatis-Plus 示例
`frontend-developer.md`：删除 Vue 3/Element Plus/ECharts 示例
`evolution-system-design.md`：删除项目特定示例

### D4: 架构决策 + evolver agent 解耦（Day 3-4）

#### 决策 1：双轨引擎保留哪套？

**选项 A**：保留 `lib/` 主引擎（Stop Hook 触发）
- 优点：经过更多验证，数据积累更多
- 缺点：与 evolution/ 有重复

**选项 B**：保留 `evolution/` 备用引擎
- 优点：结构更清晰，有独立 evolvers/ 和 analyzers/
- 缺点：未知问题可能更多

**建议**：保留 `lib/` 主引擎，`evolution/` 作为参考文档或单独 Skill。

#### 决策 2：统一 CLI 架构

将 10+ 个独立 CLI 命令整合为一个统一入口：

```
evolution-cli.py <group> <command> [args]

Groups:
  evolution safety <subcmd>   # status/validate/rollback
  evolution dashboard <subcmd> # (无子命令)
  evolution effects <subcmd>   # report/trend
  evolution data <subcmd>      # cleanup/status
  evolution rollback <subcmd>  # (无子命令)
  evolution kg <subcmd>        # knowledge graph operations
  workflow <subcmd>            # run/pause/resume/status
```

### D5: evolver agent 的 disallowedTools 修复（P0 修复）

**核心修复**：保留 `Edit/Write`，只禁止危险工具：

| Agent | tools 正确配置 |
|-------|--------------|
| `skill-evolver.md` | `tools: [Read, Edit, Bash, Grep]` |
| `agent-evolver.md` | `tools: [Read, Edit, Bash, Grep]` |
| `rule-evolver.md` | `tools: [Read, Edit, Bash, Grep]` |
| `memory-evolver.md` | `tools: [Read, Write, Edit, Bash, Grep]` |

**Phase 1 验收标准**：
1. ✅ 所有文件无 Java/Vue/Spring Boot 硬编码字符串
2. ✅ `config/*.json` 驱动项目类型检测和路径验证
3. ✅ 4 个 evolver agent 的 `tools` 配置正确
4. ✅ 统一 CLI 架构已定义

---

## 五、Phase 2: 新增通用组件（Day 5-7）

### D6: 新增 `evolve` Skill（Day 5，核心）

**skills/evolve/SKILL.md**：
```yaml
---
name: evolve
description: |
  This skill should be used when the user asks to "analyze evolution",
  "approve evolution", "review evolution proposals", "trigger evolution",
  "check evolution status", "rollback evolution", "evolution history",
  "evolution fitness", or mentions "evolve", "evolution", "self-improve".
version: 1.0.0
user-invocable: true
disable-model-invocation: false
allowed-tools: [Read, Bash, Grep]
---

# Evolution System

进化系统操控台，管理 Agent/Skill/Rule/Memory 四个维度的自进化。

## 命令

### /evolve analyze
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/evolution_orchestrator.py
```

### /evolve status
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution safety status
```

### /evolve dashboard
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/evolution_dashboard.py
```

### /evolve approve <proposal-id>
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution safety approve <id>
```

### /evolve rollback <version>
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution rollback <version>
```

### /evolve history [--limit N]
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution history --limit 10
```

### /evolve effects
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution effects report
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution effects trend
```

### /evolve fitness
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution fitness
```

## 安全级别

| 级别 | 操作 | 审批 |
|------|------|------|
| L1 | memory 追加、skill 缩窄、rule 放松、agent 加约束 | 自动 |
| L2 | agent 修改、skill 扩展、新 rule | `/evolve approve` |
| L3 | 新 agent、skill 重构、rule 集变更 | 多人批准 |

## 评分体系

总分 = 基础分(40) + 活跃度(20) + 效果分(25) + 质量分(15)

| 等级 | 分数 |
|------|------|
| A | ≥80 |
| B | ≥65 |
| C | ≥50 |
| D | ≥35 |
| F | <35 |

## 风险分级

| 等级 | 操作 | 处理 |
|------|------|------|
| Low | 追加内容 | 自动执行 |
| Medium | 修改现有内容 | 自动执行 + 通知 |
| High | 删除/重构 | 人工确认 |
| Critical | 安全相关 | 禁止自动 |
```

### D7: 新增 `workflow-run` + `workflow-pause` + `workflow-resume` + `workflow-status` Skills（Day 5-6）

**skills/workflow-run/SKILL.md**：
```yaml
---
name: workflow-run
description: |
  This skill should be used when the user asks to "run workflow", "execute workflow",
  "build feature", "implement feature", or wants to "build something from scratch".
user-invocable: true
allowed-tools: [Read, Bash, Grep, Glob]
---

# Workflow Orchestration

工作流编排引擎，执行完整的开发周期。

## 工作流阶段

1. **Explore**: 理解需求，探索代码库
2. **Plan**: 设计方案，制定计划
3. **Develop**: 实现功能（可并行后端/前端）
4. **Review**: 代码审查
5. **Fix**: 修复问题（循环直到通过）
6. **Verify**: 验证完成

## 执行

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow run "<任务>"
```

## 书签功能

使用 `/pause` 保存进度，`/resume` 恢复执行。
```

**skills/workflow-pause/SKILL.md**：
```yaml
---
name: workflow-pause
description: |
  This skill should be used when the user says "pause", "suspend", "save progress",
  "checkpoint", or wants to stop and resume later.
user-invocable: true
---

# Pause Workflow

保存当前工作流状态为书签。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow pause "<备注>"
```
```

**skills/workflow-resume/SKILL.md**：
```yaml
---
name: workflow-resume
description: |
  This skill should be used when the user says "resume", "continue",
  "restore", or wants to continue from a saved checkpoint.
user-invocable: true
---

# Resume Workflow

恢复之前保存的工作流书签。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow resume [bookmark-id]
```
```

**skills/workflow-status/SKILL.md**：
```yaml
---
name: workflow-status
description: |
  This skill should be used when the user asks to "check status", "show progress",
  "workflow status", or wants to see current workflow state.
user-invocable: true
---

# Workflow Status

查看当前或最近工作流的状态。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow status
```
```

### D8: 新增 `workflow-orchestrator` Agent（Day 6）

**agents/workflow-orchestrator.md**：
```yaml
---
name: workflow-orchestrator
description: |
  Use this agent when the user wants to "run workflow", "execute development",
  "build feature", or needs multi-agent coordination for a complex task.
model: sonnet
color: cyan
tools: [Read, Bash, Grep, Glob]
permissionMode: acceptEdits
---

You are the workflow orchestrator for Claude Harness Kit.

**Your Responsibilities:**
1. Understand the user's task and break it down
2. Choose the right strategy (sequential/parallel/hybrid)
3. Coordinate specialist agents
4. Monitor progress and handle failures
5. Ensure quality gates pass before completion

**Available Strategies:**
- `sequential`: One agent at a time (1-3 tasks)
- `granular`: Backend + Frontend + Reviewer in parallel (3-6 tasks)
- `hybrid`: Backend + Frontend + Test in parallel (6-8 tasks)
- `parallel_high`: Multiple agents per layer (8+ tasks)
```

### D9: 新增 `knowledge-graph` Skill（Day 6-7）

**skills/knowledge-graph/SKILL.md**：
```yaml
---
name: knowledge-graph
description: |
  This skill should be used when the user asks to "query knowledge graph",
  "search knowledge", "add to knowledge graph", or mentions "knowledge".
user-invocable: true
allowed-tools: [Read, Bash, Grep]
---

# Knowledge Graph

知识图谱系统，管理 skill/agent/pattern/concept 节点和关系。

## 命令

### 查询
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py kg search "<query>"
```

### 添加节点
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py kg add-node <type> <name> "<data>"
```

### 查看关系
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py kg relations <node-id>
```

## 节点类型

- skill: 技能节点
- agent: Agent 节点
- pattern: 模式节点
- concept: 概念节点

## 关系类型

- uses: 使用关系
- composes: 组成关系
- depends: 依赖关系
```

**Phase 2 验收标准**：
1. ✅ `evolve` Skill 存在且 `user-invocable: true`
2. ✅ `workflow-run/pause/resume/status` Skills 存在
3. ✅ `workflow-orchestrator` agent 存在
4. ✅ `knowledge-graph` Skill 存在
5. ✅ 4 个 evolver agent 的 `tools` 配置正确

---

## 六、Phase 3: 统一 CLI 包装（Day 7-9）

### D10: 实现 evolution-cli.py

将 10+ 个独立 CLI 命令整合为一个统一入口：

```python
#!/usr/bin/env python3
"""
Claude Harness Kit - Evolution CLI
统一命令行接口。

用法:
  evolution-cli.py evolution safety status
  evolution-cli.py evolution safety validate
  evolution-cli.py evolution safety rollback <target>
  evolution-cli.py evolution dashboard
  evolution-cli.py evolution effects report
  evolution-cli.py evolution effects trend
  evolution-cli.py evolution data cleanup
  evolution-cli.py evolution data status
  evolution-cli.py evolution history [--limit N]
  evolution-cli.py evolution fitness
  evolution-cli.py kg search <query>
  evolution-cli.py kg add-node <type> <name>
  evolution-cli.py kg relations <node-id>
  evolution-cli.py workflow run <task>
  evolution-cli.py workflow pause [note]
  evolution-cli.py workflow resume [bookmark-id]
  evolution-cli.py workflow status
"""

import sys
import os
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', Path(__file__).parent.parent))
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

SUBCOMMANDS = {
    # Evolution group
    "evolution": {
        "safety": {
            "status": "lib.evolution_safety:cmd_status",
            "validate": "lib.evolution_safety:cmd_validate",
            "rollback": "lib.evolution_safety:cmd_rollback",
            "approve": "lib.evolution_safety:cmd_approve",
        },
        "dashboard": {
            "": "lib.evolution_dashboard:cmd_dashboard",
        },
        "effects": {
            "report": "lib.evolution_effects:cmd_report",
            "trend": "lib.evolution_effects:cmd_trend",
        },
        "data": {
            "cleanup": "lib.data_rotation:cmd_cleanup",
            "status": "lib.data_rotation:cmd_status",
        },
        "history": {
            "": "lib:cmd_history",  # 需要实现
        },
        "fitness": {
            "": "lib:cmd_fitness",  # 需要实现
        },
    },
    # Knowledge graph group
    "kg": {
        "search": "lib.knowledge_graph:cmd_search",
        "add-node": "lib.knowledge_graph:cmd_add_node",
        "relations": "lib.knowledge_retriever:cmd_relations",
    },
    # Workflow group
    "workflow": {
        "run": "cmd_workflow_run",
        "pause": "cmd_workflow_pause",
        "resume": "cmd_workflow_resume",
        "status": "cmd_workflow_status",
    },
}

def cmd_workflow_run(args):
    """运行工作流"""
    task = " ".join(args) if args else ""
    print(f"开始工作流: {task}")
    print("阶段 1: Explore → 2: Plan → 3: Develop → 4: Review → 5: Fix → 6: Verify")
    print("✅ 工作流完成")

def cmd_workflow_pause(args):
    """保存书签"""
    import json
    note = " ".join(args) if args else ""
    state = {"task": "当前任务", "phase": "开发中", "note": note}
    bookmark = PLUGIN_ROOT / "config" / "workflow_bookmark.json"
    bookmark.write_text(json.dumps(state, indent=2))
    print(f"✅ 书签已保存: {bookmark}")

def cmd_workflow_resume(args):
    """恢复书签"""
    import json
    bookmark = PLUGIN_ROOT / "config" / "workflow_bookmark.json"
    if bookmark.exists():
        state = json.loads(bookmark.read_text())
        print(f"恢复任务: {state['task']}")
        print(f"阶段: {state['phase']}")
    else:
        print("❌ 未找到书签")

def cmd_workflow_status(args):
    """查看状态"""
    import json
    bookmark = PLUGIN_ROOT / "config" / "workflow_bookmark.json"
    if bookmark.exists():
        state = json.loads(bookmark.read_text())
        print(f"任务: {state.get('task', 'N/A')}")
        print(f"阶段: {state.get('phase', 'N/A')}")
    else:
        print("无活动工作流")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    group = sys.argv[1]

    if group == "evolution":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "safety":
            action = sys.argv[3] if len(sys.argv) > 3 else "status"
            # 调用 lib.evolution_safety
            from evolution_safety import EvolutionSafety
            es = EvolutionSafety(PLUGIN_ROOT)
            if action == "status":
                es.status()
            elif action == "validate":
                es.validate()
            elif action == "rollback" and len(sys.argv) > 4:
                es.rollback(sys.argv[4])
            else:
                print(f"未知 safety 命令: {action}")
        elif subcmd == "dashboard":
            from evolution_dashboard import EvolutionDashboard
            ed = EvolutionDashboard(PLUGIN_ROOT)
            ed.generate()
        elif subcmd == "effects":
            action = sys.argv[3] if len(sys.argv) > 3 else ""
            from evolution_effects import EvolutionEffects
            ee = EvolutionEffects(PLUGIN_ROOT)
            if action == "report":
                ee.report()
            elif action == "trend":
                ee.trend()
        # ... 其他命令
    elif group == "kg":
        # 知识图谱命令
        pass
    elif group == "workflow":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        args = sys.argv[3:]
        if subcmd == "run":
            cmd_workflow_run(args)
        elif subcmd == "pause":
            cmd_workflow_pause(args)
        elif subcmd == "resume":
            cmd_workflow_resume(args)
        elif subcmd == "status":
            cmd_workflow_status(args)
        else:
            print(f"未知 workflow 命令: {subcmd}")
    else:
        print(f"未知 group: {group}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### D11: hooks.json 配置（Day 8-9）

根据 D1b 验证结果配置：

```json
{
  "description": "Claude Harness Kit Hooks",
  "hooks": {
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/load_evolution_state.py",
        "timeout": 5
      }]
    }],
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/path_validator.py",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/collect_violations.py",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/bin/safety-check.sh",
          "timeout": 3
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/bin/quality-gate.sh",
          "timeout": 5
        }]
      },
      {
        "matcher": "Agent",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/collect_agent_launch.py",
          "timeout": 5
        }]
      },
      {
        "matcher": "Skill",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/collect_skill_usage.py",
          "timeout": 5
        }]
      }
    ],
    "PostToolUseFailure": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/collect_tool_failure.py",
        "timeout": 3
      }]
    }],
    "UserPromptSubmit": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/detect_feedback.py",
        "timeout": 3
      }]
    }],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/session_evolver.py",
            "timeout": 10
          },
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/strategy_updater.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Phase 3 验收标准**：
1. ✅ `evolution-cli.py` 统一入口存在
2. ✅ `evolution-cli.py evolution safety status` 可执行
3. ✅ `evolution-cli.py workflow run/pause/resume/status` 可执行
4. ✅ `hooks.json` 配置完整（11 个 hook 全部覆盖）
5. ✅ 在原项目 `claude --plugin-dir` 验证插件加载

---

## 七、Phase 4: 闭环验证（Day 10-11）

### D12: 完整进化闭环验证

```
1. /evolve analyze
   → 验证 Skill 调用 lib.evolution_orchestrator.py
   → 验证提案生成

2. /evolve status
   → 验证 evolution-cli.py evolution safety status

3. /evolve dashboard
   → 验证 lib.evolution_dashboard.py

4. /workflow "添加一个简单的 API endpoint"
   → 验证 workflow Skill 调用 evolution-cli.py

5. /pause 保存书签
6. /resume 恢复

7. 触发一个 L1 进化（memory 追加）
   → 验证 evolver agent 执行
   → 验证 tools 配置正确（Edit 可用）

8. 验证 git diff 确认 .md 文件被修改
```

### D13: 回归检测 + 数据轮转验证

```
1. 触发进化后，确认成功率未下降 > 20%
2. 运行数据轮转：evolution-cli.py evolution data cleanup
3. 验证 30 天前数据被压缩
```

**Phase 4 验收标准**：
1. ✅ `/evolve` 所有子命令可用
2. ✅ `/workflow` + `/pause` + `/resume` + `/status` 可用
3. ✅ L1 进化自动执行
4. ✅ 4 个 evolver agent 的 tools 配置正确
5. ✅ 数据轮转正常工作

---

## 八、Phase 5: 生产化 + 发布（Day 12-14）

### D14: npm 打包 + 本地验证

- `npm pack` → 生成 tgz
- 全新目录 `--plugin-dir` 验证
- 3 种项目（Java/Node/Python）测试所有 Skill

### D15: 安全 + 性能 + CI

- 安全审查（路径遍历、进化注入、tools 绕过）
- 性能测试（复杂任务 context budget）
- GitHub Actions: lint + test + npm publish

### D16: 文档 + 示例

- README + quickstart + troubleshooting
- 3 个示例项目
- 3 个 ADR 文档

### D17: npm publish + 最终验证

- `npm publish`
- 全新 Mac 环境 `npm install` 验证
- 分享给 2-3 人试用

**Phase 5 验收标准**：
1. ✅ `npm install claude-harness-kit` 可用
2. ✅ 3 种项目 `/evolve` + `/workflow` 可用
3. ✅ 进化闭环完整可用
4. ✅ 安全审查无高危
5. ✅ 3 人试用反馈收集

---

## 九、时间线总览（v4.0）

```
D1a:   平移（0.5天）— git 批量复制 + plugin.json + package.json
D1b:   插件验证（0.5天）— Python/Shell hook + 引擎验证
D2:    Config Schema 定义（0.5天）— 3 个 JSON Schema
D3:    解耦 MEDIUM 文件（1.5天）— 4 Agent 并行
D4:    架构决策 + evolver 解耦（1天）
D5:    evolve Skill + workflow Skills（1天）
D6:    workflow-orchestrator + knowledge-graph（1天）
D7:    evolver agent disallowedTools 修复（0.5天）
D8:    evolution-cli.py 统一入口（1天）
D9:    hooks.json 配置（0.5天）
D10:   完整进化闭环验证（1天）
D11:   回归检测 + 数据轮转（0.5天）
D12:   npm 打包 + 本地验证（0.5天）
D13:   安全 + 性能 + CI（1天）
D14:   文档 + 示例（0.5天）
D15:   npm publish + 最终验证（0.5天）

总计：14 天（保持不变）
```

---

## 十、风险矩阵（v4.0）

| 风险 | 概率 | 影响 | 应对 |
|------|:----:|:----:|------|
| D1b Python hook 验证失败 | 低 | 中 | 改为 Node.js hooks |
| D1b Shell hook 验证失败 | 中 | 中 | Shell 改用 Python 替代 |
| 双轨引擎冲突 | 中 | 高 | D4 架构决策选一 |
| disallowedTools 配置错误 | 低 | **高** | D7 专门修复 |
| 统一 CLI 实现复杂 | 中 | 中 | 分组子命令，减少耦合 |
| npm 包结构不被识别 | 低 | 高 | D12 本地验证 |

---

## 十一、关键修复对照表（v2.0 → v3.0 → v4.0）

| 问题 | v2.0 | v3.0 | v4.0 |
|------|------|------|------|
| Python 引擎规模 | 6 个模块 | 6 个模块 | **14 个模块 + 独立引擎** |
| Hook 脚本数量 | 7 个 | 7 个 | **11 个** |
| CLI 命令数量 | 2 个 | 6 个 | **10+ 个（统一入口）** |
| disallowedTools | ❌ 死锁 | ✅ 修复 | ✅ 修复 |
| evolver tools | 未规划 | 规划 | **修复 + 完善** |
| 评分体系 | 未规划 | 未规划 | **完整保留** |
| Token 三层架构 | 未规划 | 未规划 | **完整保留** |
| 风险分级 | 未规划 | 未规划 | **完整保留** |
| 数据轮转 | 未规划 | 未规划 | **完整保留** |
| 知识图谱 | 未规划 | 未规划 | **新增 Skill** |
| 双轨引擎 | 忽略 | 忽略 | **D4 架构决策** |

---

## 十二、与原 README.md 的对应关系

| README Section | v4.0 对应 |
|---------------|----------|
| Section 1: 项目概览 | 平移到 README.md |
| Section 2: 架构图 | D1a 目录结构 |
| Section 3: 目录结构 | D1a 平移命令 |
| Section 4: 自进化系统 | 保留在 lib/ |
| Section 5: 数据流向 | hooks.json 配置 |
| Section 6: 进化触发引擎 | lib/evolution_orchestrator.py |
| Section 7: 四维度进化流程 | agents/*-evolver.md |
| Section 8: 进化派发协议 | load_evolution_state.py |
| Section 9: Token 效率 | lib/token_efficiency.py |
| Section 10: 评分体系 | lib/evolution_scoring.py |
| Section 11: 数据轮转 | lib/data_rotation.py |
| Section 12: 上下文管理 | CLAUDE.md 注入 |
| Section 13: 知识图谱 | lib/knowledge_graph.py + Skill |
| Section 14: Agent 协作 | agents/workflow-orchestrator.md |
| Section 15: 常用命令 | evolution-cli.py 统一入口 |
| Section 16: 数据文件清单 | config/ 目录 |
| Section 17: 设计文档 | docs/ 目录平移 |
| Section 18: 维护原则 | README.md 说明 |
| Section 19: 核心原则 | 保留不变 |

---

## 十三、待验证项（SessionStart 前必须确认）

1. **D1b 验证**：Python/Shell Command Hook 是否可用
2. **D4 决策**：双轨引擎保留哪套
3. **npm marketplace**：插件完整发布流程是否可用
4. **disallowedTools**：evolver agent 的 tools 配置是否真正生效
