# CLAUDE.md

本文件为 Claude Code 提供项目上下文指导。

<!-- 由 kit init 生成于 2026-05-01 — 人工补充 TODO 项 -->

## 技术栈
- 语言/构建: Node.js / npm/yarn/pnpm

## 构建命令
```bash
npm install   # 安装依赖
npm test      # 运行测试
npm build     # 构建
```

## 关键路径
- `harness/tests/` — 测试目录

### 入口文件
- `index.js`

### 模块（统一在 harness/ 下）
- `harness/agents/` — Agent 定义（22 个）
- `harness/cli/` — CLI 工具（11 个 + modes/）
- `harness/docs/` — 设计文档
- `harness/evolve-daemon/` — 自动进化守护进程
- `harness/hooks/` — Hook 配置和脚本（26 个）
- `harness/instinct/` — 本能记录
- `harness/knowledge/` — 知识库
- `harness/memory/` — 记忆系统
- `harness/rules/` — 扩展规则
- `harness/skills/` — Skill 集合（36 个）
- `harness/tests/` — 测试套件

## 架构约定
<!-- TODO: 补充项目架构模式、分层约定、命名规范 -->

## 已知陷阱
- Hook 脚本通过 `hooks/` → `harness/hooks/` 符号链接访问

## 相关知识
- 项目知识: `.claude/knowledge/INDEX.md`
- 团队规范: `.claude/rules/`
- 设计文档: `harness/docs/`