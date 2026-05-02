# CLAUDE.md

<!-- 由 chk-init 生成于 2026-05-03 — 基于项目分析 -->

## 项目概览

**CHK (Claude Harness Kit)** — 团队级 AI 驾驭工具包，让 AI 真正"看懂"你的代码库。
Human steers, Agents execute. 多 Agent 协作、通用 Skills、持续进化。

## 技术栈
- 语言/构建: Node.js >=18 / npm
- 插件入口: `index.js`
- 配置文件: `package.json` (version: 0.4.0)

## 构建命令
```bash
npm install   # 安装依赖
npm test      # 运行测试 (69 测试)
npm run test-verbose  # 详细输出
```

## 模块结构 (harness/)

```
harness/
├── _core/          # 核心库
├── agents/         # 22 个 Agent 定义 (*.md)
├── cli/            # CLI 工具 + modes/
├── docs/           # 设计文档
├── evolve-daemon/  # 自动进化守护进程
├── hooks/          # Hook 配置和脚本 (26 个)
├── instinct/       # 本能记录系统
├── knowledge/      # 知识库
├── memory/         # 记忆系统
├── rules/          # 扩展规则
├── skills/         # 35 个 Skill 集合
└── tests/          # 测试套件
```

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

### 35 个 Skill
涵盖: testing, debugging, tdd, security-review, architecture-design, api-designer, migration, database-designer, ml-engineer, data-engineer, sre, performance, mobile-dev, iac, docker-essentials, lark-* (飞书全家桶), wechat-*, xiaohongshu-*, 等

## 入口文件
- `index.js` — 插件主入口，暴露 agents/skills/rules
- `harness/cli/` — 命令行入口

## 已知陷阱
- Hook 脚本统一在 `harness/hooks/`；repo root `hooks/` 是符号链接
- instinct 数据路径已统一到 `harness/instinct/`
- agents/ 旧路径已迁移到 `harness/agents/`

## 相关知识
- 项目知识: `.claude/knowledge/`
- 团队规范: `.claude/rules/`
- 设计文档: `harness/docs/`
- 进化数据: `harness/evolve-daemon/`
- 本能记录: `harness/instinct/`