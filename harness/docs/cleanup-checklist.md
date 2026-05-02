# 代码清理清单

> 目标：从 32000 行精简到 ~2000 行，减少 94%
> 定位：Claude Code 插件，团队一键安装，通用适配

---

## 0. 插件架构原则

清理必须遵循以下原则：

- **技术栈无关**：Agent/Rule 不能绑定 Java/Vue 等特定技术栈，通用模式放插件，技术细节放项目 CLAUDE.md
- **开箱即用**：`claude plugins install claude-harness-kit` 即可获得全部能力
- **模块可选**：evolve-daemon 作为可选模块，不启用则零开销
- **团队适配**：每个项目可通过自己的 CLAUDE.md 覆盖/扩展插件行为
- **最小依赖**：只依赖 Python 3 标准库 + anthropic SDK（仅在启用 evolve-daemon 时需要）

---

## 1. 删除 evolution/ 目录（第二个进化引擎）

- [ ] 删除 `evolution/engine.py`
- [ ] 删除 `evolution/config.py`
- [ ] 删除 `evolution/cli.py`
- [ ] 删除 `evolution/hook_integration.py`
- [ ] 删除 `evolution/__init__.py`
- [ ] 删除 `evolution/__main__.py`
- [ ] 删除 `evolution/evolvers/__init__.py`
- [ ] 删除 `evolution/evolvers/base.py`
- [ ] 删除 `evolution/evolvers/skill_evolver.py`
- [ ] 删除 `evolution/evolvers/agent_evolver.py`
- [ ] 删除 `evolution/evolvers/rule_evolver.py`
- [ ] 删除 `evolution/evolvers/memory_evolver.py`
- [ ] 删除 `evolution/analyzers/__init__.py`
- [ ] 删除 `evolution/analyzers/session_analyzer.py`
- [ ] 删除 `evolution/analyzers/pattern_detector.py`
- [ ] 删除 `__pycache__/`

---

## 2. 删除 evolution-cli.py

- [ ] 删除 `evolution-cli.py`（460 行 CLI 包装器）

---

## 3. 删除 lib/ 目录（进化引擎 Python 模块）

- [ ] 删除 `lib/evolution_orchestrator.py`
- [ ] 删除 `lib/evolution_safety.py`
- [ ] 删除 `lib/evolution_scoring.py`
- [ ] 删除 `lib/evolution_dashboard.py`
- [ ] 删除 `lib/evolution_effects.py`
- [ ] 删除 `lib/data_rotation.py`
- [ ] 删除 `lib/rollback_evolution.py`
- [ ] 删除 `lib/strategy_generator.py`
- [ ] 删除 `lib/token_efficiency.py`
- [ ] 删除 `lib/parallel_executor.py`
- [ ] 删除 `lib/knowledge_graph.py`
- [ ] 删除 `lib/knowledge_retriever.py`
- [ ] 删除 `lib/constants.py`
- [ ] 删除 `lib/examples/demo_knowledge_graph.py`

---

## 4. 删除 config/ 目录（进化运行时数据）

- [ ] 删除 `config/agent_performance.jsonl`
- [ ] 删除 `config/daily_scores.jsonl`
- [ ] 删除 `config/skill_usage.jsonl`
- [ ] 删除 `config/tool_failures.jsonl`
- [ ] 删除 `config/evolution_history.jsonl`
- [ ] 删除 `config/evolution_metrics.json`
- [ ] 删除 `config/pending_evolution.json`
- [ ] 删除 `config/strategy_weights.json`
- [ ] 删除 `config/strategy_variants.json`
- [ ] 删除 `config/capabilities.json`
- [ ] 删除 `config/domains.json`
- [ ] 删除 `config/knowledge_graph.json`
- [ ] 删除 `config/violation-rules.json`
- [ ] 删除 `config/path-patterns.json`
- [ ] 删除 `config/interview_answers.jsonl`
- [ ] 删除 `config/workflow_bookmark.json`

---

## 5. 精简 agents/（18 → 8）

### 5.1 删除进化相关 Agent（7 个）

- [ ] 删除 `agents/evolver.md`
- [ ] 删除 `agents/agent-evolver.md`
- [ ] 删除 `agents/skill-evolver.md`
- [ ] 删除 `agents/rule-evolver.md`
- [ ] 删除 `agents/memory-evolver.md`
- [ ] 删除 `agents/self-play-trainer.md`
- [ ] 删除 `agents/strategy-selector.md`

### 5.2 删除薄包装 Agent（3 个）

- [ ] 删除 `agents/workflow-orchestrator.md`
- [ ] 删除 `agents/progress-viewer.md`
- [ ] 删除 `agents/librarian.md`

### 5.3 保留并改为通用（8 个）

- [x] `agents/orchestrator.md` — 多 Agent 任务编排
- [x] `agents/product-manager.md` — PRD / 需求分析
- [x] `agents/tech-lead.md` — 架构设计 / 技术决策
- [x] `agents/backend-developer.md` — **改为通用后端开发，不绑定 Java**
- [x] `agents/frontend-developer.md` — **改为通用前端开发，不绑定 Vue**
- [x] `agents/code-reviewer.md` — 代码审查
- [x] `agents/test.md` — QA / 测试
- [x] `agents/explore.md` — 代码库探索

---

## 6. 精简 skills/（22 → 11）

### 6.1 删除进化/工作流相关（5 个）

- [ ] 删除 `skills/evolve/`
- [ ] 删除 `skills/workflow-run/`
- [ ] 删除 `skills/workflow-pause/`
- [ ] 删除 `skills/workflow-resume/`
- [ ] 删除 `skills/workflow-status/`

### 6.2 删除薄/冗余 Skill（6 个）

- [ ] 删除 `skills/knowledge-graph/`
- [ ] 删除 `skills/mermaid-diagrams/`
- [ ] 删除 `skills/docker-essentials/`
- [ ] 删除 `skills/batch-edit/`
- [ ] 删除 `skills/oracle/`

### 6.3 保留（11 个）

- [x] `skills/karpathy-guidelines/`
- [x] `skills/requirement-analysis/`
- [x] `skills/architecture-design/`
- [x] `skills/task-distribution/`
- [x] `skills/testing/`
- [x] `skills/code-quality/`
- [x] `skills/debugging/`
- [x] `skills/git-master/`
- [x] `skills/ship/`
- [x] `skills/security-audit/`
- [x] `skills/database-designer/`

---

## 7. rules/ 通用化

### 7.1 删除技术栈绑定 Rule

- [ ] 删除 `rules/backend.md`（Java/Spring Boot 特定，移到项目 CLAUDE.md）
- [ ] 删除 `rules/frontend.md`（Vue 特定，移到项目 CLAUDE.md）
- [ ] 删除 `rules/evolution-dispatch.md`
- [ ] 删除 `rules/unknown.md`（已知 bug 记录，不属于 rule）

### 7.2 保留并通用化（4 条）

- [x] `rules/general.md` — 通用开发规范（Agent 优先、Git 规范）
- [x] `rules/collaboration.md` — 多 Agent 协作契约
- [x] `rules/system-design.md` — 系统设计原则
- [x] `rules/expert-mode.md` — 专家模式激活条件

> 技术栈相关规则放入具体项目的 CLAUDE.md，不放在插件中

---

## 8. 精简 hooks/bin/（11 → 2）

### 8.1 删除进化数据收集脚本（9 个）

- [ ] 删除 `hooks/bin/auto_evolver.py`
- [ ] 删除 `hooks/bin/collect_agent_launch.py`
- [ ] 删除 `hooks/bin/collect_skill_usage.py`
- [ ] 删除 `hooks/bin/collect_tool_failure.py`
- [ ] 删除 `hooks/bin/collect_violations.py`
- [ ] 删除 `hooks/bin/detect_feedback.py`
- [ ] 删除 `hooks/bin/session_evolver.py`
- [ ] 删除 `hooks/bin/strategy_updater.py`
- [ ] 删除 `hooks/bin/load_evolution_state.py`

### 8.2 保留（2 个）

- [x] `hooks/bin/safety-check.sh` — 阻止危险命令
- [x] `hooks/bin/quality-gate.sh` — JSON/Python 语法校验

---

## 9. 清理 hooks/hooks.json → 迁移为标准 settings.json

- [ ] 删除所有进化相关 hook 配置（SessionStart / PostToolUse Agent/Skill / UserPromptSubmit / Stop）
- [ ] 保留 safety-check.sh 和 quality-gate.sh 配置
- [ ] 改为 `.claude/settings.json` 标准格式

---

## 10. 清理 docs/ 多余文档

- [ ] 删除 `docs/evolution-system-design.md`
- [ ] 删除 `docs/directory-governance.md`
- [ ] 删除 `docs/claude-code-reference.md`
- [ ] 保留 `docs/50-full-plan-v2.0.md`（历史参考）
- [ ] 保留 `docs/evolve-daemon-design.md`（新方案设计）
- [ ] 保留 `docs/cleanup-checklist.md`（本文件）

---

## 11. 清理 tests/ 进化相关测试

- [ ] 删除 `tests/test_evolution.py`
- [ ] 删除 `tests/test_evolution_e2e.py`
- [ ] 删除 `tests/test_evolution_regression.py`
- [ ] 删除 `tests/test_evolution_system.py`
- [ ] 删除 `tests/test_evolution_30_rounds.py`
- [ ] 删除 `tests/test_evolution_full_120.py`
- [ ] 删除 `tests/test-alphazero.sh`
- [ ] 删除 `tests/test-hooks.sh`
- [ ] 删除 `tests/test-all-hooks.sh`
- [ ] 删除 `tests/test-stop-hook.sh`
- [ ] 删除 `tests/test_auto_feedback.sh`
- [ ] 删除 `tests/validate-config.sh`
- [ ] 删除 `tests/verify_capabilities.py`
- [ ] 删除 `tests/verify_hook_references.py`
- [ ] 删除 `tests/verify_standards.py`

### 11.1 保留

- [x] `tests/cleanup-claude-artifacts.sh`

---

## 12. 更新 package.json

- [ ] 更新 `files` 字段，移除已删除目录
- [ ] 移除进化相关的 scripts

---

## 13. 清理 CLAUDE.md

- [ ] 移除进化系统相关描述
- [ ] 更新项目概述为精简版

---

## 清理后目录结构

```
claude-harness-kit/                       # 插件根目录
├── .claude-plugin/
│   └── plugin.json                   # 插件元数据
├── package.json                      # npm 包配置
├── README.md                         # 团队使用说明
├── CLAUDE.md                         # 插件自身开发说明
├── .gitignore
│
├── agents/                           # 8 个通用 Agent
│   ├── orchestrator.md
│   ├── product-manager.md
│   ├── tech-lead.md
│   ├── backend-developer.md          # 通用后端
│   ├── frontend-developer.md         # 通用前端
│   ├── code-reviewer.md
│   ├── test.md
│   └── explore.md
│
├── skills/                           # 11 个 Skill
│   ├── karpathy-guidelines/
│   ├── requirement-analysis/
│   ├── architecture-design/
│   ├── task-distribution/
│   ├── testing/
│   ├── code-quality/
│   ├── debugging/
│   ├── git-master/
│   ├── ship/
│   ├── security-audit/
│   └── database-designer/
│
├── rules/                            # 4 条通用规则
│   ├── general.md
│   ├── collaboration.md
│   ├── system-design.md
│   └── expert-mode.md
│
├── hooks/
│   └── bin/
│       ├── safety-check.sh           # 危险命令拦截
│       └── quality-gate.sh           # 文件质量校验
│
├── settings.json                     # Hook 配置（标准格式）
│
├── evolve-daemon/                    # [可选] 自进化守护进程
│   ├── daemon.py
│   ├── analyzer.py
│   ├── proposer.py
│   ├── extract_semantics.py
│   ├── config.yaml
│   └── templates/
│
└── docs/
    ├── evolve-daemon-design.md       # 进化架构设计
    └── cleanup-checklist.md          # 本文件

使用方项目结构（团队在自己的项目中）:
项目根/
├── .claude/                          # 项目自己的配置
│   ├── CLAUDE.md                     # 项目技术栈 + 规范（覆盖/补充插件）
│   └── settings.local.json          # 本地覆盖
├── CLAUDE.md                         # 项目上下文
└── src/...

插件安装方式:
  claude plugins install claude-harness-kit
  # 或在 package.json 中声明依赖后 npm install

evolve-daemon 启用方式（可选）:
  cd .claude/evolve-daemon
  pip install anthropic pyyaml
  python3 daemon.py install-launchd   # macOS
  python3 daemon.py install-systemd   # Linux
```

删除: evolution/ evolution-cli.py lib/ config/
精简: agents/18→8 skills/22→11 hooks/11→2 rules/8→4

---

## 14. 插件发布准备

- [ ] 更新 `.claude-plugin/plugin.json`（描述、作者、仓库）
- [ ] 更新 `package.json`（files 字段对齐清理后结构）
- [ ] 写 README.md（安装说明、Agent/Skill 列表、evolve-daemon 可选启用）
- [ ] 配置 `.gitignore`（排除 data/、logs/、__pycache__/）
- [ ] npm publish（或团队内部 registry）

---

> 完成后提交并推送，提交信息: "插件化重构：删除进化冗余，精简为通用 Claude Code 团队插件"
