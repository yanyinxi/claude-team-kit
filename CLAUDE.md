# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Claude Harness Kit — Claude Code 团队级 AI 驾驭工具包。借鉴 OpenAI Harness Engineering 方法论 (Human steers, Agents execute)，提供多 Agent 协作、通用化 Skills/Rules、知识生命周期管理、持续进化能力，支持 20+ 人团队和 100+ 存量代码库的全流程 AI 化。

## 当前状态（v0.4）

```
claude-harness-kit/
├── .claude-plugin/plugin.json
├── package.json
├── agents/                      # 22 个通用 Agent
│   ├── orchestrator.md          # 多 Agent 编排中心
│   ├── architect.md             # 架构设计 (Opus)
│   ├── tech-lead.md             # 技术负责人
│   ├── product-manager.md       # 产品经理 / PRD
│   ├── backend-dev.md           # 通用后端
│   ├── frontend-dev.md          # 通用前端
│   ├── database-dev.md          # 数据库开发
│   ├── devops.md                # DevOps / CI-CD
│   ├── migration-dev.md         # 迁移工程
│   ├── executor.md              # 通用执行器
│   ├── code-reviewer.md         # 代码审查 (5轴)
│   ├── security-auditor.md      # 安全审计 (Opus, 只读)
│   ├── qa-tester.md             # QA / 测试
│   ├── test.md                  # 测试工程
│   ├── ralph.md                 # Ralph 自修复循环
│   ├── verifier.md              # 验证器 (PASS/FAIL)
│   ├── learner.md               # Instinct 学习
│   ├── gc.md                    # 知识垃圾回收
│   ├── explore.md               # 代码探索 (Haiku)
│   ├── codebase-analyzer.md     # 模块结构分析 (Haiku)
│   ├── impact-analyzer.md       # 影响范围评估 (Haiku)
│   └── oracle.md                # 高级咨询 (Opus, 只读)
├── skills/                      # 19 个通用 Skill
│   ├── karpathy-guidelines/     ├── requirement-analysis/
│   ├── architecture-design/     ├── task-distribution/
│   ├── testing/                 ├── code-quality/
│   ├── debugging/               ├── git-master/
│   ├── ship/                    ├── security-audit/
│   ├── database-designer/       ├── api-designer/
│   ├── tdd/                     ├── performance/
│   ├── migration/               ├── docker-compose/
│   ├── multi-model-review/      ├── context-compaction/
│   └── parallel-dispatch/
├── rules/                       # 6 条通用规则
│   ├── general.md               ├── collaboration.md
│   ├── system-design.md         ├── expert-mode.md
│   ├── quality-gates.md         └── security.md
├── hooks/
│   ├── hooks.json               # 7 个 Hook 事件
│   └── bin/                     # 8 个脚本
├── knowledge/                   # 知识生命周期系统
│   └── lifecycle.yaml
├── evolve-daemon/               # 进化守护进程
│   ├── daemon.py                ├── analyzer.py
│   ├── proposer.py              ├── rollback.py
│   └── intent_detector.py
├── cli/                         # 命令行工具
│   ├── chk.sh                   # 统一入口（主推）
│   ├── kit.sh                   # 兼容旧入口
│   ├── install.sh               # 一键安装到终端
│   ├── init.py                  ├── mode.py
│   ├── sync.py                  ├── scan.py
│   ├── migrate.py               ├── status.py
│   ├── gc.py                    └── modes/
│       └── modes/               # 7 种模式 hook 配置
│           ├── solo.json        ├── auto.json
│           ├── team.json        ├── ultra.json
│           ├── pipeline.json    ├── ralph.json
│           └── ccg.json
└── docs/                        # 设计文档
    ├── architecture-v2.md
    ├── research-claude-code-internals.md
    ├── evolve-daemon-design.md
    ├── harness-engineering-proposal.md
    └── cleanup-checklist.md
```

## 设计原则

- **技术栈无关**：Agent/Rule 不绑定特定技术栈，通用模式放插件，技术细节放项目 CLAUDE.md
- **Harness 驾驭模式**：Human steers, Agents execute — 人是骑手，Agent 是马，Rule/Skill 是缰绳
- **按需加载**：Skill 采用 Progressive Disclosure (30-50 tokens 描述)，Rule 采用 path-scoped frontmatter
- **最小依赖**：不引入 npm 依赖，Hook 脚本只用 bash/python3 标准库

## 核心架构

参阅 [docs/architecture-v2.md](docs/architecture-v2.md) — 4 层架构：
- **Layer 1 上下文层**：4 级 CLAUDE.md 分层 + kit init 自动注入 + path-scoped rules
- **Layer 2 能力层**：22 Agents + 19 Skills + 6 Rules
- **Layer 3 编排层**：5 阶段执行流 + 冲突检测矩阵 + TaskFile/Mailbox/Checkpoint 协议
- **Layer 4 进化层**：Instinct System + Learner Agent + evolve-daemon + 知识生命周期 + GC Agent

## 多 Agent 并行协议

详见 [agents/orchestrator.md](agents/orchestrator.md) 和 [rules/collaboration.md](rules/collaboration.md)：
- 冲突检测：A ∩ B = ∅ → 可并行
- TaskFile 协议：阶段间文件交接
- Mailbox 机制：Agent 间直接通信
- Checkpoint 系统：/compact 安全恢复

## /chk-xxx 快速上手

一句话：在 Claude Code 或终端输入 `/chk-xxx` 或 `chk xxx`，切换到对应的工作模式。

### 安装（两步搞定）

**Step 1：克隆项目**

```bash
git clone https://github.com/yanyinxi/claude-harness-kit.git
cd claude-harness-kit
```

**Step 2：安装到 Claude Code**

```bash
claude plugins marketplace add --scope local $(pwd)
claude plugins install claude-harness-kit
```

### 11 个命令，对号入座

在 Claude Code 或 VS 插件聊天框中输入 `/chk-xxx`：

| 你想做什么 | 斜杠命令 |
|------------|----------|
| 初始化新项目 | `/chk-init` |
| 快速修复一个 Bug | `/chk-auto` |
| 日常功能开发 | `/chk-team` |
| 批量改造 20 个文件 | `/chk-ultra` |
| 做数据库迁移 | `/chk-pipeline` |
| 写支付/安全代码 | `/chk-ralph` |
| 做一个架构决策 | `/chk-ccg` |
| 简单问答一下 | `/chk-solo` |
| 查看当前状态 | `/chk-status` |
| 清理过期知识 | `/chk-gc` |
| 查看所有命令 | `/chk-help` |

### 场景对照（闭眼选）

```text
不知道问什么       → /chk-solo
线上有个 Bug      → /chk-auto
新功能要从零做    → /chk-team
代码要全面重构     → /chk-ultra
要迁数据库表      → /chk-pipeline
写转账/加密代码   → /chk-ralph
系统要怎么改      → /chk-ccg
接手一个新项目   → /chk-init
```

## 安全边界

- Deny-First 原则：安全拦截优先于功能放行
- 审查类 Agent 禁止 Write/Edit/Bash 工具
- GC Agent 只生成报告，不直接修改定义文件
