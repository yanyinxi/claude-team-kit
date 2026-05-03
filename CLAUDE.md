# CLAUDE.md

<!-- 由 chk-init 生成于 2026-05-03 — 基于项目分析 -->
<!-- CHK Version: 0.6.1 -->

## 项目概览

**CHK (Claude Harness Kit)** — 团队级 AI 驾驭工具包，让 AI 真正"看懂"你的代码库。
Human steers, Agents execute. 多 Agent 协作、通用 Skills、持续进化。

## 技术栈
- 语言/构建: Node.js >=18 / npm
- 插件入口: `index.js`
- 配置文件: `package.json` (version: 0.6.1)

## 构建命令
```bash
npm install   # 安装依赖
npm test      # 运行测试 (69 测试)
```

## 模块结构 (harness/)

```
harness/
├── _core/          # 核心库 (版本管理、配置加载)
├── agents/         # 22 个 Agent 定义 (*.md)
├── cli/            # CLI 工具 + modes/
├── docs/           # 设计文档
├── evolve-daemon/  # 自动进化守护进程
│   ├── analyzer.py         # 会话聚合分析
│   ├── evolve_dispatcher.py # 4+4 维度决策
│   ├── smart_evolution_engine.py # 智能进化引擎
│   ├── rollback.py         # 自动回滚机制
│   ├── effect_tracker.py   # 效果跟踪
│   ├── knowledge/          # 符号链接 → ../knowledge/evolved
│   └── monitor-rollback.sh # 回滚监控
├── hooks/          # Hook 配置和脚本 (33 个)
│   ├── bin/
│   │   ├── collect_error.py    # 错误收集
│   │   ├── collect_success.py  # 成功跟踪 ← NEW
│   │   ├── context-injector.py # 上下文注入
│   │   └── ...
│   └── hooks.json
├── instinct/       # 本能记录系统
├── knowledge/      # 知识推荐引擎
│   ├── knowledge_recommender.py # 双知识库推荐
│   ├── lifecycle.py            # 知识生命周期
│   ├── evolved/                # 进化知识 (原 evolve-daemon/knowledge/)
│   └── manual/                 # 手工知识 (符号链接 → .claude/knowledge/)
├── memory/         # 记忆系统
├── rules/          # 扩展规则 (6 个)
├── skills/         # 35+ 个 Skill 集合
└── tests/          # 测试套件
```

## 进化系统架构 (双知识库闭环)

```
sessions.jsonl
       ↓
analyzer.py (会话聚合分析)
       ↓
daemon.py (调度 + 执行)
       ↓
┌──────────────────────────────────────────────────────────┐
│  知识生成流                                              │
│  integrated_evolution.py → knowledge_base.jsonl         │
│                                    ↓                    │
│                              进化知识库 (45 条) ←────────┤
└──────────────────────────────────────────────────────────┘
                                    ↓
                      knowledge_recommender.py
                     (双知识库合并: 手工 + 进化)
                                    ↓
                      context-injector.py (注入上下文)
                                    ↓
                         ← 推荐给用户

┌──────────────────────────────────────────────────────────┐
│  效果跟踪流                                              │
│  PostToolUseSuccess → collect_success.py → effect_tracker│
│                                                      ↓   │
│  effect_tracking.jsonl ←───────────── 验证改进有效性     │
└──────────────────────────────────────────────────────────┘
```

### 8 分析维度
- 基础 4 维: agent, skill, rule, instinct
- 扩展 4 维: performance, interaction, security, context

### 双知识库
| 知识库 | 路径 | 内容 |
|--------|------|------|
| 手工维护 | `.claude/knowledge/` 或 `harness/knowledge/manual/` | 专家知识 |
| 进化生成 | `harness/knowledge/evolved/` | 学习知识 |

> 注: `harness/evolve-daemon/knowledge/` 已符号链接到 `harness/knowledge/evolved/` 保持向后兼容

## 核心功能

### 7 种执行模式 (通过 /chk 调用)
- `solo` — 直接对话，零开销
- `team` — 多 Agent 协作开发
- `ultrawork` — 极限并行 (3-5 Agent)
- `ralph` — TDD 强制模式
- `ccg` — Claude + Codex + Gemini 三方审查
- `auto` — 全自动端到端
- `gc` — 知识垃圾回收

### 22 个 Agent
architect, backend-dev, code-reviewer, codebase-analyzer, database-dev, debugger, developer, devops, documentation, elicitor, executor, expert, frontend-dev, generalist, infrastructure, ml-engineer, planner, qa-tester, researcher, reviewer, security-auditor, tester

### 35+ 个 Skill
涵盖: testing, debugging, tdd, security-review, architecture-design, api-designer, migration, database-designer, ml-engineer, data-engineer, sre, performance, mobile-dev, iac, docker-essentials, lark-* (飞书全家桶), wechat-*, xiaohongshu-*, 等

## 入口文件
- `index.js` — 插件主入口，暴露 agents/skills/rules
- `harness/cli/` — 命令行入口

## 已知陷阱
- Hook 脚本统一在 `harness/hooks/`；repo root `hooks/` 是符号链接
- instinct 数据路径已统一到 `harness/instinct/`
- agents/ 旧路径已迁移到 `harness/agents/`

## 相关知识
- 项目知识: `.claude/knowledge/` 或 `harness/knowledge/manual/`
- 团队规范: `.claude/rules/`
- 设计文档: `harness/docs/`
- 进化数据: `harness/knowledge/evolved/` (原 `harness/evolve-daemon/knowledge/`)
- 本能记录: `harness/instinct/`