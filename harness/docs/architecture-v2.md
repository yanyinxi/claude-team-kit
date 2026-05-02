# Claude Harness Kit v2 — 团队级智能研发插件架构设计

> **目标**: 20+ 人研发团队，100+ 存量代码库，AI 覆盖需求→开发→测试→上线全流程，自动化持续进化

---

## 0. 学习总结：从标杆到超越

### 0.1 对比标杆：我们的 V2 在哪

| 维度 | everything-claude-code | oh-my-claudecode | Superpowers | Claude Code 源码 | **我们的 V2** |
|------|:--:|:--:|:--:|:--:|:--:|
| **Agent 数量** | 47 | 32 | — | 6 内置 | **20**（按模型 4 组） |
| **Skill 数量** | 181 | 40+ | — | — | **20**（5 组） |
| **执行模式** | 5 阶段流水线 | 7 种 | 7 阶段 | — | **7 种** |
| **TDD 强制** | ❌ | ✅ Ralph | ✅ 铁律 | ❌ | **Ralph Loop + tdd skill** |
| **跨模型路由** | ✅ | ✅ | ❌ | ❌ | **Haiku→Sonnet→Opus** |
| **后台 Agent 管理** | ✅ ECC 2.0 | ✅ | ❌ | ❌ | **evolve-daemon** |
| **自动学习** | ✅ Instinct v2 | ✅ Learner | ❌ | ❌ | **Instinct + Learner** |
| **持续进化** | ✅ | ✅ | ❌ | KAIROS(未发布) | **evolve-daemon 守护进程** |
| **大代码库策略** | ❌ | ❌ | ✅ Worktree | ✅ `/add-dir` | **kit init + repo-context + path-scoped rules** |
| **团队共享** | ✅ 插件市场 | ✅ NPM | ✅ 插件市场 | — | **claude plugins install** |
| | | | | | |
| **上下文分层** | CLAUDE.md | CLAUDE.md | CLAUDE.md | 4 级分层 | **4 级分层 + 自动注入** |
| **Prompt 缓存优化** | ❓ | ❓ | ❓ | ✅ 92% 复用率 | **字母序确定性排序** |
| **Rich Context 数据** | shared_memory.json | — | — | corrections 数组 | **corrections 含 root_cause** |
| **记忆合并** | ❓ | ❓ | ❓ | AutoDream(≥24h+≥5会话) | **evolve-daemon 合并 + 冲突消除** |
| **路径作用域规则** | ❓ | ❓ | ❓ | ✅ paths frontmatter | **paths 按需加载** |
| **Worktree 隔离** | ❌ | ❌ | ✅ | ✅ 实验性 | **Pipeline + Ultrawork 模式** |
| **多 Agent 编排** | Fork+92%缓存复用 | Director→EM→Worker | 文件交接制 | Coordinator+TaskList | **7 模式 + 文件交接 + 并行 fork** |
| **安全架构** | ✅ AgentShield | ✅ 断路器 | ✅ | ✅ 7 层独立 | **5 层安全边界 + Deny-First** |
| **CLI 工具链** | — | — | — | — | **kit init/sync/migrate/scan** |

### 0.2 V2 的核心差异

对比标杆项目，V2 不是"又一个 Agent/Skill 集合"，而是解决了三个他们没有完全解决的问题：

**1. 100+ 存量代码库的上下文注入**
- everything-claude-code 和 oh-my-claudecode 假设你在一个项目里工作
- Superpowers 有 Worktree 但没有系统化的上下文注入
- V2：`kit init` 自动分析项目生成 CLAUDE.md，SessionStart 自动注入项目上下文，path-scoped rules 按需加载

**2. 进化的闭环（不只是"建议"）**
- 大多数项目的"进化"其实是统计+建议
- KAIROS/AutoDream 在 Claude Code 源码中存在但未公开发布
- V2：collect → extract semantics → Learner → instinct → evolve-daemon → 验证 → 固化，完整闭环

**3. 团队规模下的上下文管理**
- 20 人 × 100+ 代码库 = 每个人每天切换 3-5 个项目
- 没有系统化的上下文管理，AI 每次都要"重新认识"项目
- V2：中央配置仓库 + kit sync + repo-index.json + LOCAL_SUMMARY.md

### 0.3 关键洞察

1. **瓶颈不是写代码速度，而是 AI 对项目的理解深度**。100+ 代码库的核心挑战是让 AI 快速"看懂"每个项目
2. **上下文工程是真正的核心能力**。CLAUDE.md 分层、Progressive Disclosure、Path-Scoped Rules
3. **验证循环 > 一次生成**。Ralph Loop：发现问题→分析→修复→测试→审查→重复，直到通过
4. **跨模型路由不是噱头**。Haiku 探索 → Sonnet 编码 → Opus 审查，按任务选模型，成本降 50%+
5. **进化需要闭环**。不是"提出建议"，而是"发现 → 学习 → 应用 → 验证效果 → 固化"
6. **Prompt 缓存是规模化的经济基础**。确定性前缀（字母序）→ 92% 缓存复用 → 并行 Agent 边际成本趋零

---

## 1. 插件整体架构

### 1.1 四层架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Layer 4: 进化层 (Evolution)                         │
│                    evolve-daemon + instinct-learning                       │
│                 自动发现 → 学习 → 应用 → 验证 → 固化                          │
├──────────────────────────────────────────────────────────────────────────┤
│                        Layer 3: 编排层 (Orchestration)                      │
│                  7 种执行模式 + 多 Agent 并行调度                             │
│         Team / Autopilot / Ultrawork / Ralph / Pipeline / CCG / Solo       │
├──────────────────────────────────────────────────────────────────────────┤
│                        Layer 2: 能力层 (Capabilities)                       │
│          Agents (8→20)  +  Skills (11→20)  +  Rules (4→6)                 │
│                    按领域分组，按模型分层，按场景激活                           │
├──────────────────────────────────────────────────────────────────────────┤
│                        Layer 1: 上下文层 (Context)                          │
│         CLAUDE.md 分层体系 + Repo-Context 自动注入 + Progressive Disclosure   │
│                    让 AI 快速看懂任何一个代码库                                │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 安装与使用

```bash
# 团队安装（一次性）
claude plugins install claude-harness-kit

# 存量项目适配（每个项目执行一次）
cd legacy-project
kit init                    # 自动分析项目，生成 CLAUDE.md + .claude/
kit sync --from=central     # 从中央仓库同步团队共享配置

# 日常使用
kit dev "实现用户登录功能"    # 标准开发流水线
kit review                  # 代码审查模式
kit migrate "升级 Spring Boot 2.x → 3.x"  # 迁移模式
```

---

## 2. Layer 1: 上下文层 — AI 看懂代码库的核心

### 2.1 核心问题

> 20 人团队 × 100+ 代码库 = AI 每次切换项目都需要重新理解上下文。没有系统化的上下文注入，AI 就是在瞎猜。

### 2.2 CLAUDE.md 四层分级体系

```
层级 1: 全局 (~/.claude/CLAUDE.md)
  └─ 个人偏好：语言、提交风格、工具链
     例: "我习惯用中文写提交记录，后端偏好 Spring Boot"

层级 2: 团队共享 (中央配置仓库 synced)
  └─ 团队规范：代码风格、安全策略、Agent 使用约定
     例: "所有 API 接口需要 RateLimitFilter，SQL 操作用 MyBatis-Plus"

层级 3: 项目级 (./CLAUDE.md, 自动生成 + 人工维护)
  └─ 项目上下文：技术栈、架构、关键路径、领域术语
     例: "这是一个视频素材查询服务，PostgreSQL + Spring Boot + Vue 3"

层级 4: 模块级 (./subdir/CLAUDE.md, 按需)
  └─ 模块细节：特定模块的业务逻辑、边界条件、已知陷阱
     例: "src/auth/: JWT token 有效期 24h，续期逻辑在 AuthService.refresh()"
```

### 2.3 kit init — 自动项目分析

```bash
kit init
```

做的事情：

```
1. 扫描项目结构
   ├─ 识别技术栈（pom.xml → Java/Maven, package.json → Node/Vue, go.mod → Go...）
   ├─ 识别目录结构（src/main/java, src/components, ...）
   └─ 识别关键配置（application.yml, docker-compose.yml, ...）

2. 生成初始 CLAUDE.md
   ├─ 技术栈描述（自动推断）
   ├─ 构建命令（从配置文件提取）
   ├─ 关键路径标注
   └─ 模块边界描述

3. 创建 .claude/ 目录
   ├─ settings.json（hook 配置）
   ├─ CLAUDE.md（项目上下文，人工补充）
   └─ 链接团队共享的 agents/skills/rules
```

### 2.4 Repo-Context 自动注入

每次新会话启动时（SessionStart Hook），自动注入：

```
┌─────────────────────────────────────────────────┐
│  kit context injector                            │
│                                                  │
│  1. 读取项目 CLAUDE.md（层级 3）                   │
│  2. 读取当前目录最近的 CLAUDE.md（层级 4）          │
│  3. 读取团队共享 rules（层级 2）                    │
│  4. 分析 git log 最近变更（当前分支热点）            │
│  5. 分析当前目录文件结构（上下文感知）               │
│                                                  │
│  → 注入到 system prompt 前 200 tokens             │
│  → AI 在对话开始就"知道"当前项目的基本情况           │
└─────────────────────────────────────────────────┘
```

### 2.5 100+ 代码库管理策略

```
中央配置仓库 (claude-team-standards)
├── rules/           # 团队通用规则（CI/CD 同步到所有项目）
├── CLAUDE.md        # 团队级模板
├── repo-index.json  # 所有代码库索引
└── migration/       # 大规模改造任务追踪

每个项目仓库
├── CLAUDE.md        # 项目特有（自动生成 + 人工维护）
└── .claude/
    ├── memory/      # 项目特定的 AI 学习积累
    └── settings.local.json

同步机制：
  kit sync --from=central
  # → 拉取最新团队 rules，保留项目级 CLAUDE.md 不动
  # → 可在 CI/CD 中配置为自动执行
```

---

## 3. Layer 2: 能力层 — Agents, Skills, Rules

### 3.1 Agent 体系（8 → 20，按模型三层分组）

#### 架构组（Opus/Sonnet — 高推理）

| Agent | 模型 | 角色 |
|-------|------|------|
| **architect** | Opus | 系统架构设计，技术决策，跨模块影响评估 |
| **tech-lead** | Opus | 技术方案评审，代码审查最终签字 |
| **product-manager** | Sonnet | PRD 生成，需求澄清，验收标准 |

#### 执行组（Sonnet — 日常编码）

| Agent | 模型 | 角色 |
|-------|------|------|
| **executor** | Sonnet | 通用代码编写（默认执行者） |
| **backend-dev** | Sonnet | 后端开发（适配 Java/Python/Go/Node） |
| **frontend-dev** | Sonnet | 前端开发（适配 React/Vue/Angular） |
| **database-dev** | Sonnet | 数据库变更、迁移、索引优化 |
| **devops** | Sonnet | CI/CD、Docker、K8s 配置 |
| **migration-dev** | Sonnet | 框架升级、代码迁移专项 |

#### 审查组（Opus/Sonnet — 质量保障）

| Agent | 模型 | 角色 |
|-------|------|------|
| **code-reviewer** | Sonnet | 5 维度代码审查（正确性/可读性/架构/安全/性能） |
| **security-auditor** | Opus | 安全漏洞检测，OWASP 审查 |
| **qa-tester** | Sonnet | 测试用例生成，边界条件覆盖 |

#### 探索组（Haiku — 快速只读）

| Agent | 模型 | 角色 |
|-------|------|------|
| **explore** | Haiku | 代码库搜索，依赖分析 |
| **codebase-analyzer** | Haiku | 快速分析项目结构，生成 CLAUDE.md |
| **impact-analyzer** | Haiku | 变更影响范围评估 |

#### 特殊 Agent

| Agent | 模型 | 角色 |
|-------|------|------|
| **orchestrator** | Sonnet | 多 Agent 任务编排和调度 |
| **ralph** | Sonnet | 持久化执行循环（不通过不停止） |
| **learner** | Sonnet | 从对话中提取可复用知识 |
| **verifier** | Sonnet | 专项验证（功能/性能/兼容性） |

### 3.2 Skill 体系（11 → 20）

#### 需求分析组

| Skill | 功能 |
|-------|------|
| **requirement-analysis** | PRD 生成，用户故事分解 |
| **architecture-design** | 系统架构设计，技术选型 |
| **task-distribution** | 任务拆分，并行计划 |

#### 开发执行组

| Skill | 功能 |
|-------|------|
| **karpathy-guidelines** | LLM 编码最佳实践 |
| **tdd** | 测试驱动开发（RED → GREEN → REFACTOR） |
| **database-designer** | 数据库设计、迁移、索引优化 |
| **api-designer** | RESTful API 设计规范 |

#### 审查测试组

| Skill | 功能 |
|-------|------|
| **code-quality** | 代码审查流程 |
| **testing** | 测试策略和模板 |
| **security-audit** | 安全审计清单 |
| **performance** | 性能分析和优化建议 |

#### 运维交付组

| Skill | 功能 |
|-------|------|
| **git-master** | Git 工作流管理 |
| **ship** | 发布检查清单 |
| **debugging** | 系统化根因分析 |
| **migration** | 框架/依赖升级指南 |
| **docker-compose** | 容器化部署 |

#### 跨模型组

| Skill | 功能 |
|-------|------|
| **multi-model-review** | 多模型交叉审查 |
| **context-compaction** | 上下文压缩策略 |
| **parallel-dispatch** | 并行任务分派 |

### 3.3 Rules 体系（4 → 6）

| Rule | 覆盖范围 | 内容 |
|------|----------|------|
| **general.md** | 全局 | Agent 优先、Git 规范、目录标准 |
| **collaboration.md** | 全局 | 多 Agent 协作契约，反模式 |
| **system-design.md** | 架构 | 技术选型决策树，安全三层防护 |
| **expert-mode.md** | 全局 | 专家模式激活条件 |
| **quality-gates.md** | 全局 | 每个阶段的退出条件 |
| **security.md** | 全局 | 安全底线（不做的事 + 必须做的事） |

---

## 4. Layer 3: 编排层 — 7 种执行模式

### 4.1 模式全景图

```
                    复杂度 ↑
                        │
    Ralph (持久循环)      │          Team (多Agent流水线)
    "不通过不停止"        │          "Plan→Exec→Verify→Fix"
           ┌──────────────┼──────────────┐
           │              │              │
           │         Autopilot           │
           │      "全自动端到端"          │
           │              │              │
    ------+--------------+--------------+-------→ 任务规模
           │              │              │
           │         Pipeline            │
           │     "上一步输出喂下一步"     │
           │                             │
      Ultrawork                    CCG (三模型审查)
    "极限并行加速"                "Claude+Codex+Gemini"
```

### 4.2 模式详解

#### Team Mode（默认，大多数场景）

```
Plan → PRD → Execute → Verify → Fix → Review → Merge

阶段间用 /clear 清理上下文，中间产物存文件：
  plan.md → prd.md → implementation/ → test-report.md → review-comments.md
```

#### Autopilot Mode（快速原型、简单任务）

```
全自动端到端，单一 Agent 自主完成
适用：简单 CRUD、Bug 修复、配置变更
```

#### Ultrawork Mode（批量改造、并行加速）

```
自动拆解任务 → 派发 3-5 个并行 Subagent → 汇总结果 → 冲突解决
适用：跨模块重构、代码风格统一、依赖升级
```

#### Ralph Mode（零容忍质量）

```
执行 → 验证 → 失败 → 自动修复 → 再验证 → ... → 通过或超时放弃
适用：安全相关代码、核心支付逻辑、认证模块
命名来源：Ralph Wiggum "I'm helping!"
```

#### Pipeline Mode（严格顺序）

```
Step 1 输出 → Step 2 输入 → Step 3 输入 → ...
适用：数据库迁移、API 版本升级、多步骤部署
```

#### CCG Mode（多模型交叉审查）

```
同时发给 Claude + Codex + Gemini
→ 三个独立审查结果
→ 对比差异，高亮不一致 → 人工决策
适用：安全审计、关键架构决策
```

#### Solo Mode（直接对话）

```
不使用 Agent，直接和 Claude 对话
适用：问答、探索、文档编写
```

---

## 5. Layer 4: 进化层 — 持续学习系统

### 5.1 核心设计

```
进化 = 发现 + 学习 + 应用 + 验证 + 固化
       │      │      │      │      │
       │      │      │      │      └─ instinct-record.json
       │      │      │      │         (置信度 > 0.8 自动应用)
       │      │      │      │         (置信度 0.5-0.8 → 提案)
       │      │      │      │         (置信度 < 0.5 → 丢弃)
       │      │      │      │
       │      │      │      └─ 下一个同场景验证
       │      │      │         (用户是否再次纠正？)
       │      │      │
       │      │      └─ 应用到 skills/rules/CLAUDE.md
       │      │         (低风险自动，高风险提案)
       │      │
       │      └─ extract_semantics.py (Haiku 提取)
       │         用户纠正了什么？为什么纠正？
       │
       └─ collect_session.py (Stop Hook)
          元数据 + 对话上下文摘要
```

### 5.2 本能系统（Instinct System）

借鉴 everything-claude-code 的 Instinct v2：

```json
// .claude/instinct/instinct-record.json
{
  "id": "instinct_042",
  "type": "pattern_correction",
  "context": {
    "trigger": "testing skill 建议 mock 数据库事务",
    "domain": "testing",
    "tech_stack": ["Spring Boot", "JPA", "PostgreSQL"]
  },
  "correction": "涉及 @Transactional 的测试需用集成测试而非 mock",
  "source": {
    "session_id": "sess_abc123",
    "user_confirmed": true,
    "times_observed": 3
  },
  "confidence": 0.85,
  "applied_to": "skills/testing/SKILL.md",
  "verified_at": "2026-05-03T10:00:00",
  "verified_result": "用户不再纠正"
}
```

**置信度升级路径**:

| 次数 | 置信度 | 行为 |
|------|--------|------|
| 第 1 次观察到 | 0.3 | 仅记录 |
| 第 2 次同一模式 | 0.5 | 生成观察报告 |
| 第 3 次同一模式 | 0.7 | 生成改进提案 |
| 提案被 Accept + 验证通过 | 0.9 | 固化为本能（自动应用） |
| 提案被 Reject | → 0.1 | 标记为误报，暂停 30 天 |

### 5.3 Learner Agent

```
Stop Hook → 触发 Learner Agent
  ├─ 输入: 本轮对话摘要 + 用户纠正记录
  ├─ 分析: 是否有可复用的模式？
  ├─ 输出: 新的 instinct 记录 或 更新已有记录
  └─ 成本: Sonnet 1 次调用，约 $0.01/会话

触发条件:
  - 出现用户纠正
  - 出现新的问题-解决方案对
  - Agent 失败后用户手动完成
```

### 5.4 evolve-daemon（守护进程）

```
cron 每 4 小时 / 累积 5+ 会话触发
  ├─ 读取 sessions.jsonl + instinct-records
  ├─ 聚合分析（同一模式出现次数、置信度变化）
  ├─ 调用 Claude Opus 深度分析（独立 API Key）
  │   └─ 输入: 多个会话的纠正故事 + 现有 skill/rule/agent 定义
  │   └─ 输出: 结构化改进提案
  ├─ 生成 proposals/YYYY-MM-DD_description.md
  ├─ 可选: 自动创建 GitHub Issue/PR
  └─ 退出
```

---

## 6. 完整执行流程

### 6.1 一次标准开发的完整链路

```
用户: kit dev "实现素材标签过滤功能"

  [SessionStart Hook]
    ├─ context-injector: 注入项目 CLAUDE.md (200 tokens)
    └─ 项目概要: "视频素材查询服务，PostgreSQL，Spring Boot，Vue 3"

  [Phase 1: 需求澄清] (product-manager Agent, Sonnet)
    ├─ 分析现有代码（素材查询接口、标签字段结构）
    ├─ 提出 3 个问题:
    │   Q1: "过滤支持多标签并交/并/差？"
    │   Q2: "是否需要权限校验？"
    │   Q3: "前端展示分页还是无限滚动？"
    ├─ 用户回答 → 生成 PRD → prd.md
    └─ /clear

  [Phase 2: 架构设计] (architect Agent, Opus)
    ├─ 读 prd.md
    ├─ 分析影响范围:
    │   - AssetController: 新增 filter 参数
    │   - AssetService: 新增 filterByTags()
    │   - AssetMapper: 新增动态 SQL
    │   - AssetTag.vue: 新增标签选择器
    ├─ 输出 plan.md（含文件路径、接口签名、测试策略）
    └─ /clear

  [Phase 3: 任务拆分] (orchestrator Agent)
    ├─ 拆分为 5 个独立任务:
    │   Task 1: 后端 DTO 扩展 (3 min)
    │   Task 2: Service 层过滤逻辑 (5 min)
    │   Task 3: Mapper 动态 SQL (5 min)
    │   Task 4: Controller 接口扩展 (2 min)
    │   Task 5: 前端标签选择器组件 (10 min)
    ├─ 识别依赖: Task 2 → Task 3, Task 1+2+3 → Task 4
    └─ 并行组: Task 1 || Task 5

  [Phase 4: 并行执行] (Team Mode)
    ├─ Batch 1 (并行): Task 1 + Task 5
    │   ├─ backend-dev Agent (Sonnet): DTO 扩展
    │   └─ frontend-dev Agent (Sonnet): 标签选择器
    ├─ Batch 2: Task 2 (底层，Task 3 依赖它)
    ├─ Batch 3: Task 3 + Task 4
    │   ├─ backend-dev Agent: Mapper SQL
    │   └─ backend-dev Agent: Controller
    └─ 每完成一个 Task → code-reviewer Agent 自动审查

  [Phase 5: 测试] (qa-tester Agent)
    ├─ 生成单元测试: AssetServiceTest.filterByTags()
    ├─ 生成集成测试: AssetControllerIT.filterApi()
    ├─ 运行测试: mvn test
    └─ 失败 → Ralph Mode: 自动修复 → 再运行 → 通过

  [Phase 6: 代码审查] (code-reviewer + security-auditor)
    ├─ code-reviewer (5 维度):
    │   ✅ 正确性: 标签过滤逻辑正确，NULL 处理到位
    │   ⚠️ 性能: 多标签查询无索引，建议加 GIN 索引
    │   ✅ 安全性: XSS 过滤正常
    ├─ security-auditor: SQL 注入白名单检查 ✅
    └─ 输出 review-comments.md

  [Phase 7: 完成交付] (ship Skill)
    ├─ 全量测试通过 ✅
    ├─ 代码审查通过 ✅
    ├─ 生成 commit message
    ├─ git commit + git push
    └─ 清理临时文件

  [Stop Hook]
    ├─ collect_session.py: 写入 sessions.jsonl
    ├─ Learner Agent: 检查是否有新 instinct
    │   (本次无用户纠正，跳过学习)
    └─ extract_semantics.py: 未触发（无纠正）
```

### 6.2 大规模迁移的完整链路（100+ 代码库场景）

```
场景: 将 30 个 Java 8 项目升级到 Java 17 + Spring Boot 3.x

  [准备阶段]
    kit scan --group="backend-services" --target="java17-sb3"
    → 扫描 30 个项目，评估改动量，排序优先级

  [试点阶段]
    选 1 个最简单项目跑一遍完整流程
    → 记录所有的坑和解决方案 → 生成 migration-playbook.md

  [批量阶段]
    for project in priority_order:
      kit migrate project \
        --playbook=migration-playbook.md \
        --mode=autopilot \
        --review=required   # 每个项目必审
      
      # autopilot 自动执行:
      # 1. 分析项目 pom.xml/build.gradle
      # 2. 更新依赖版本
      # 3. 迁移 javax.* → jakarta.*
      # 4. 迁移 Spring Security 配置
      # 5. 运行测试 → 修复 → 再运行
      # 6. 代码审查 Agent 审核
      # 7. 生成迁移报告

  [进化反馈]
    每完成一个项目 → Learner Agent 提取新的迁移模式
    → 更新 migration-playbook.md
    → 下一个项目受益于前面所有项目的经验
```

---

## 7. Hook 系统设计

### 7.1 精简而精准的 Hook 配置

```json
// .claude/settings.json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/context-injector.py"
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/bin/safety-check.sh"
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/bin/quality-gate.sh"
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/bin/collect-session.py"
        }]
      }
    ]
  }
}
```

5 个 Hook，精确定位：
- **SessionStart**: 注入项目上下文
- **PreToolUse[Bash]**: 安全拦截
- **PostToolUse[Write/Edit]**: 质量门禁
- **Stop**: 会话收集 + 触成语义提取

### 7.2 Stop Hook 数据模型

```json
{
  "session_id": "sess_001",
  "timestamp": "2026-04-30T14:30:00+08:00",
  "mode": "team",                    // team|autopilot|ultrawork|ralph|pipeline|ccg|solo
  "duration_minutes": 45,
  "phases_completed": ["plan", "execute", "review"],
  
  "agents_used": [
    {"agent": "product-manager", "model": "sonnet", "task": "需求澄清"},
    {"agent": "backend-dev", "model": "sonnet", "task": "实现过滤逻辑"},
    {"agent": "code-reviewer", "model": "sonnet", "task": "代码审查"}
  ],
  
  "skills_used": [
    {"skill": "requirement-analysis", "invoked": true},
    {"skill": "tdd", "invoked": true}
  ],
  
  "artifacts": {
    "files_changed": 12,
    "lines_added": 340,
    "lines_deleted": 45,
    "tests_added": 8
  },
  
  "corrections": [
    {
      "target": "skill:testing",
      "context": "Service 层涉及事务回滚测试",
      "ai_wrong": "建议使用 Mockito mock DataSource",
      "user_corrected": "涉及 @Transactional 的用集成测试而非 mock",
      "resolution": "改为 @SpringBootTest，测试通过",
      "root_cause": "testing skill 缺少事务场景的测试策略分支"
    }
  ],
  
  "instinct_candidates": []
}
```

---

## 8. 项目目录结构（最终版）

```
claude-harness-kit/                         # 插件根目录
│
├── .claude-plugin/
│   └── plugin.json                      # 插件元数据
│
├── package.json                         # npm 包
├── README.md                            # 安装 + 使用 + Agent/Skill 目录
│
├── agents/                              # 22 个 Agent
│   ├── architect.md                     # 架构设计 (Opus)
│   ├── tech-lead.md                     # 技术评审 (Opus)
│   ├── product-manager.md               # 需求分析 (Sonnet)
│   ├── executor.md                      # 通用执行 (Sonnet)
│   ├── backend-dev.md                   # 后端开发 (Sonnet)
│   ├── frontend-dev.md                  # 前端开发 (Sonnet)
│   ├── database-dev.md                  # 数据库 (Sonnet)
│   ├── devops.md                        # DevOps (Sonnet)
│   ├── migration-dev.md                 # 迁移专项 (Sonnet)
│   ├── code-reviewer.md                 # 代码审查 (Sonnet)
│   ├── security-auditor.md              # 安全审计 (Opus)
│   ├── qa-tester.md                     # QA 测试 (Sonnet)
│   ├── test.md                          # 测试工程 (Sonnet)
│   ├── explore.md                       # 代码探索 (Haiku)
│   ├── codebase-analyzer.md             # 项目分析 (Haiku)
│   ├── impact-analyzer.md               # 影响评估 (Haiku)
│   ├── orchestrator.md                  # 多 Agent 编排 (Sonnet)
│   ├── ralph.md                         # 持久执行 (Sonnet)
│   ├── learner.md                       # 知识提取 (Sonnet)
│   ├── gc.md                            # 知识垃圾回收 (Sonnet)
│   ├── verifier.md                      # 专项验证 (Sonnet)
│   └── oracle.md                        # 疑难咨询 (Opus)
│
├── skills/                              # 20 个 Skill
│   ├── requirement-analysis/
│   ├── architecture-design/
│   ├── task-distribution/
│   ├── karpathy-guidelines/
│   ├── tdd/
│   ├── database-designer/
│   ├── api-designer/
│   ├── code-quality/
│   ├── testing/
│   ├── security-audit/
│   ├── performance/
│   ├── git-master/
│   ├── ship/
│   ├── debugging/
│   ├── migration/
│   ├── docker-compose/
│   ├── multi-model-review/
│   ├── context-compaction/
│   └── parallel-dispatch/
│
├── rules/                               # 6 条规则
│   ├── general.md
│   ├── collaboration.md
│   ├── system-design.md
│   ├── expert-mode.md
│   ├── quality-gates.md
│   └── security.md
│
├── hooks/
│   ├── bin/
│   │   ├── context-injector.py          # SessionStart: 上下文注入
│   │   ├── safety-check.sh              # PreToolUse: 安全拦截
│   │   ├── quality-gate.sh              # PostToolUse: 质量门禁
│   │   └── collect-session.py           # Stop: 会话收集
│   └── lib/
│       └── extract_semantics.py          # 语义提取（公用库）
│
├── evolve-daemon/                       # [可选] 自进化守护进程
│   ├── daemon.py
│   ├── analyzer.py
│   ├── proposer.py
│   ├── config.yaml
│   └── templates/
│
├── instinct/                            # 本能知识库
│   └── instinct-record.json
│
├── templates/                           # 项目模板
│   ├── CLAUDE.md.template              # 项目 CLAUDE.md 模板
│   └── repo-index.json                 # 多仓库索引
│
├── cli/                                 # kit CLI 工具
│   ├── kit.sh                           # 主入口
│   ├── init.py                          # kit init
│   ├── sync.py                          # kit sync
│   ├── migrate.py                       # kit migrate
│   └── scan.py                          # kit scan
│
└── docs/
    ├── evolve-daemon-design.md
    ├── cleanup-checklist.md
    └── architecture-v2.md               # 本文件
```

---

## 9. 安全边界

| 规则 | 说明 |
|------|------|
| **提案永不自动应用** | 高置信度 (>0.8) 本能自动应用仅限 skills/rules，不改安全配置 |
| **Agent 工具白名单** | 审查类 Agent 禁止 Write/Edit/Bash |
| **安全模块不可进化** | security.md rule、safety-check.sh hook 锁定，AI 不可修改 |
| **独立 API Key** | evolve-daemon 使用独立 Key，不消耗团队配额 |
| **审核不可跳过** | 所有代码变更必须过至少一个审查 Agent |

---

## 10. 实施路线

### Phase 1: 清理 + 骨架（2-3h）
- 执行 cleanup-checklist.md 全部删除
- 通用化 Agent/Skill/Rule
- 创建新目录结构

### Phase 2: Agent + Skill 扩展（3-4h）
- 新增 12 个 Agent（executor, ralph, learner, verifier 等）
- 新增 9 个 Skill（tdd, api-designer, multi-model-review 等）
- 写好每个 Agent 的 system prompt

### Phase 3: Hook + 上下文层（2-3h）
- 实现 context-injector.py
- 实现 collect-session.py（含 rich context 数据模型）
- 实现 extract_semantics.py（Haiku 语义提取）
- 配置 settings.json

### Phase 4: CLI 工具（2-3h）
- 实现 kit.sh 主入口
- 实现 kit init（项目分析 + CLAUDE.md 生成）
- 实现 kit sync（中央配置同步）

### Phase 5: evolve-daemon（2-3h）
- 实现 daemon.py + analyzer.py + proposer.py
- 实现 instinct 系统
- 配置 cron/launchd

### Phase 6: 试点验证（1-2 周）
- 团队内 3-5 人试用
- 在 3-5 个真实项目上验证
- 收集反馈迭代

---

## 11. 借鉴与致谢

| 来源 | 借鉴点 |
|------|--------|
| **everything-claude-code** | 5 阶段编排、Instinct v2 持续学习、Agent 模型分层 |
| **oh-my-claudecode** | 7 种执行模式、Ralph Loop、跨模型编排 |
| **Superpowers** | 7 阶段工程流水线、TDD 铁律、微任务拆分 |
| **Claude Code 源码 (KAIROS)** | 后台 daemon、autoDream 记忆合并、"hint vs truth" 语义 |
| **ZoomInfo 案例** | Agent-legibility、shared_memory.json 状态机 |
| **Start.io Ralph Loop** | 持续执行直到完成、显式完成条件 |
