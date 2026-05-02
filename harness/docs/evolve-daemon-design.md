# 异步自进化守护进程 — 架构设计

## 0. 插件定位

本方案是 **claude-harness-kit 插件的可选模块**。核心价值分层：

```
claude-harness-kit 插件
│
├─ 必装层（团队通用）
│   ├── 8 个 Agent 定义（技术栈无关）
│   ├── 11 个 Skill 模板
│   ├── 4 条通用 Rule
│   └── 2 个安全 Hook
│
└─ 可选层（按需启用）
    └── evolve-daemon/  ← 本方案
         ├── 安装: pip install anthropic pyyaml
         ├── 启用: python3 daemon.py install-launchd
         └── 禁用: launchctl unload ...（零残留）
```

**设计目标**：
- 不装 evolve-daemon 的团队，获得纯粹的 Agent + Skill + Rule 插件
- 装了 evolve-daemon 的团队，获得渐进式的自进化能力
- 插件本身不绑定任何技术栈，通用模式在插件，具体技术栈在项目 CLAUDE.md

---

## 1. 设计背景：为什么当前方案不可能工作

### 问题根源

当前的"自进化"系统存在三个致命缺陷：

| 缺陷 | 说明 |
|------|------|
| **伪异步** | 进化逻辑在 Claude Code 的 Stop Hook 中执行，阻塞会话结束。所谓"静默"只是错觉 |
| **自噬循环** | AI 给自己打分 → 自己改自己的 prompt → 无外部验证 → 必然劣化。LLM 不能做自己的裁判 |
| **无独立计算** | 进化依赖 Claude Code 内的 Agent 调用，本质是 LLM 改 LLM。硬编码的打分公式（30% performance + 25% effect + ...）毫无统计意义 |

### Claude Code 源码的启示

2026 年 3 月 Claude Code v2.1.88 源码泄露揭示了 Anthropic 内部已有的架构规划：

- **KAIROS**：未发布的常驻守护进程，在源码中被引用超过 150 次。脱离终端后转为后台 daemon，通过 inotify/FSEvents 监听文件变化，定时接收 `<tick>` 信号自主决策
- **autoDream**：KAIROS 的记忆子系统，仅在用户空闲时触发。执行三操作 — Merge（合并跨会话观察）、Conflict Resolution（消除矛盾）、Tentative→Absolute（多证据固化假设）
- **核心设计哲学**：autoDream 的记忆被标注为 "hint"（线索）而非 "truth"（事实），使用前需重新验证——这避免了错误累积

两个社区项目已经验证了这个方向：
- **heartbeat**（uameer）：`observe → decide → act → sleep` 循环，模型无关
- **AutoDream**（JaWaMi73）：11 个 hooks 覆盖 6 个事件，3 种运行模式（Active/AFK/Maintenance）

---

## 2. 核心设计约束：LLM 不能被数据集饿死

### 2.1 两个方案的本质区别

不是架构的区别（都调用 LLM），是**数据颗粒度的区别**：

```
旧方案: "testing skill 被使用 5 次，失败 3 次" → LLM 只能瞎猜
新方案: "用户在事务回滚场景说'不要 mock 验证，用集成测试'，改为集成测试后通过"
         → LLM 能精准定位 testing/SKILL.md 缺少的事务测试规则
```

**LLM 的强项是语义理解**——从具体的纠正模式中归纳出规则缺失。给它统计数字就是在浪费它的能力。给它上下文故事，它才能产出有价值的改进。

### 2.2 数据量对比

| | 旧方案 | 新方案 |
|---|---|---|
| 一个会话的数据量 | ~200 bytes（统计数字） | ~2-5 KB（结构化上下文） |
| LLM 能分析出什么 | 泛泛的套话建议 | 精确到文件+行号的改进 |
| 示例产出 | "建议优化测试覆盖" | "testing/SKILL.md 第 3 步增加: 涉及事务的操作优先使用 @SpringBootTest" |

---

## 3. 整体架构

### 3.1 四层架构

> **核心变化**: 数据采集层拆为两阶段 — 元数据收集（10ms）+ 语义提取（Haiku，异步 2-3s）

```
┌──────────────────────────────────────────────────────────────────────┐
│                    第 1 层：元数据采集层                                │
│                  （Hook，同步，< 10ms，零 AI 调用）                     │
│                                                                      │
│  Claude Code 会话                                                    │
│  ┌──────────────┐    PostToolUse Hook  ┌────────────────────┐       │
│  │  工作对话     │ ───────────────────→ │ collect_agent.py   │       │
│  │              │                      │ collect_skill.py   │       │
│  │  Agent 调用   │                      │ collect_failure.py │       │
│  │  Skill 调用   │                      └─────────┬──────────┘       │
│  │  Tool 失败    │                                │                  │
│  │  用户纠正     │                      写入临时 jsonl（1ms/条）       │
│  └──────┬───────┘                                │                  │
│         │                                        ▼                  │
│         │  Stop Hook           ┌─────────────────────────────────┐   │
│         └──────────────────────│ collect_session.py              │   │
│                                │ 聚合本轮所有临时 jsonl 为一行摘要 │   │
│                                │ 追加到 data/sessions.jsonl      │   │
│                                │ 耗时 < 10ms                      │   │
│                                └─────────────────────────────────┘   │
│                                                                      │
│  设计原则：Hook 只采集元数据，不做 AI 调用                              │
├──────────────────────────────────────────────────────────────────────┤
│                    第 2 层：语义提取层                                  │
│           （Stop Hook 末尾，异步 2-3s，调用 Haiku，成本极低）           │
│                                                                      │
│  sessions.jsonl 刚写入的一行                                         │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────┐            │
│  │  extract_semantics.py                                │            │
│  │                                                      │            │
│  │  从本轮对话中提取用户纠正/Agent 失败的具体上下文          │            │
│  │  → 调用 Claude Haiku（~$0.0001/次，可忽略）            │            │
│  │  → 输入: 用户纠正 Ai 的原始对话片段 + 用户反馈文字       │            │
│  │  → 输出: 结构化摘要                                    │            │
│  │                                                      │            │
│  │  {                                                   │            │
│  │    "correction_context": "testing skill 建议 mock",   │            │
│  │    "correction_detail": "用户说: 涉及事务用集成测试",   │            │
│  │    "resolution": "改为 @SpringBootTest 后通过"         │            │
│  │  }                                                   │            │
│  │                                                      │            │
│  │  回填到 sessions.jsonl 当前行                          │            │
│  └──────────────────────────────────────────────────────┘            │
│                                                                      │
│  设计原则：                                                           │
│  - 用最便宜的模型（Haiku）做最简单的语义提取                             │
│  - 不决策、不改文件、只做"对话→结构化摘要"                              │
│  - 异步执行，不阻塞会话结束（用户已经可以关终端）                         │
│  - 如果提取失败（超时/无纠正），sessions.jsonl 已有元数据兜底            │
├──────────────────────────────────────────────────────────────────────┤
│                    第 3 层：分析决策层                                  │
│           （独立进程，cron/launchd 调度，调用 Sonnet/Opus）              │
│                                                                      │
│                      ┌──────────────────────┐                        │
│                      │   evolve-daemon.py    │                        │
│                      │                      │                        │
│  data/sessions.jsonl │  1. 读取 5-10 个会话   │                        │
│  ──────────────────→ │     每个含 rich context│                        │
│                      │  2. 聚合分析          │                        │
│                      │  3. 调用 Claude API   │                        │
│                      │     (独立 API Key)    │                        │
│                      │  ★ 输入: 用户的纠正故事 │                        │
│                      │     + 原始 skill/agent│                        │
│                      │  ★ 输出: 精确改进建议   │                        │
│                      │  4. 生成提案文件       │                        │
│                      │                      │                        │
│                      └──────────┬───────────┘                        │
│                                 │                                     │
│  触发条件（满足任一）：                                                  │
│  - 累计 ≥ 5 个新会话未分析                                              │
│  - 同一 target 被纠正 ≥ 3 次                                           │
│  - 距上次分析 ≥ 6 小时                                                  │
│                                                                      │
│  调度方式：                                                             │
│  - macOS: launchd (LaunchAgent, 每 4 小时 + 空闲时触发)                 │
│  - Linux: systemd timer + cron 双保险                                  │
│  - 通用: cron (*/30 * * * * 检查触发条件)                               │
├──────────────────────────────────────────────────────────────────────┤
│                    第 4 层：人工审核层                                  │
│                        （Git，同步，按需）                              │
│                                                                      │
│  proposals/2026-04-30_testing-transaction-mock-issue.md               │
│  ┌──────────────────────────────────────────────────────┐            │
│  │ # 进化提案：testing skill 增加事务测试规则              │            │
│  │                                                      │            │
│  │ ## 数据依据                                          │            │
│  │ 近 5 个会话中，用户 3 次在涉及数据库事务的测试场景       │            │
│  │ 手动纠正 AI 的测试建议：                                │            │
│  │                                                      │            │
│  │ - Session #12: 用户纠正 → "mock 验证事务回滚有 bug，    │            │
│  │   改为 @SpringBootTest + @Transactional 集成测试"      │            │
│  │ - Session #14: 同样模式再次纠正                        │            │
│  │ - Session #15: 用户直接跳过 skill 建议，手动写测试      │            │
│  │                                                      │            │
│  │ ## 建议改动                                          │            │
│  │ testing/SKILL.md 第 3 步 "选择测试类型" 增加:          │            │
│  │ + 涉及 @Transactional 或数据库写操作的场景，            │            │
│  │   优先使用集成测试而非 mock 验证                         │            │
│  │                                                      │            │
│  │ ## 风险评估                                          │            │
│  │ Low — 仅影响测试策略建议，不改代码逻辑                   │            │
│  │                                                      │            │
│  │ → PR: #42 (待审核)                                   │            │
│  └──────────────────────────────────────────────────────┘            │
│                                                                      │
│  设计原则：                                                           │
│  - 进化结果永不自动应用                                                │
│  - 生成 Markdown 提案文件，提交为 PR                                   │
│  - 人工 Review → Merge → 下次会话生效                                 │
│  - 如果 7 天未处理，自动 close                                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 与当前方案的对比

| 维度 | 当前方案 | 新方案 |
|------|----------|--------|
| **进化触发** | 每轮 Stop Hook 都跑 | 积累 ≥5 会话 / 每 4-6 小时 |
| **执行方式** | Hook 中同步阻塞（~30s） | 独立进程，cron 调度 |
| **数据颗粒度** | 统计数字（"用了5次，失败3次"） | 语义上下文（"用户说xxx，改为xxx"） |
| **分析输入** | session counts + 硬编码打分 | 用户纠正故事 + 原始 skill/agent 定义 |
| **分析引擎** | Python 加权公式 | Claude Haiku 提取 + Sonnet/Opus 深度分析 |
| **应用方式** | 直接改文件 | 生成 PR，人工审核 |
| **代码量** | 3500+ 行 Python | ~600 行 Python |
| **对主会话影响** | 阻塞 Stop 事件 | 零影响（元数据 10ms + 语义提取异步 2-3s） |
| **安全性** | 自动修改 prompt，无回滚 | PR diff 可见，可 revert |
| **记忆语义** | "事实"（直接修改） | "线索"（hint，需验证形成提案） |
| **提案质量** | 泛化套话建议 | 精确到文件+行号+场景的可执行改进 |

---

## 3. 完整请求链路

### 3.1 主链路：一次进化提案的完整生命周期

```
 ═══════════════════════════════════════════════════════════════════════════
                         时间线: 一次进化提案的完整生命周期
 ═══════════════════════════════════════════════════════════════════════════

  T+0h    [会话 1] 用户让 AI 写 UserService 集成测试，AI 用 testing skill 建议 mock
              │    用户纠正: "这个涉及事务回滚，mock 验证不到真实行为，用集成测试"
              │    用户手动改为 @SpringBootTest + @Transactional
              │    Stop Hook:
              │    ├─ collect_session.py → 元数据 {skills_used:[testing], corrections:1}
              │    └─ extract_semantics.py (Haiku, 异步 2s) →
              │        回填 rich context: {
              │          "skill": "testing",
              │          "context": "UserService 事务回滚测试",
              │          "correction": "用户说: mock 验证不到事务真实行为，用集成测试",
              │          "resolution": "改为 @SpringBootTest + @Transactional，测试通过"
              │        }
              ▼
  T+2h    [会话 2] AI 用 testing skill 处理 ProductService 测试，同样建议 mock 事务
              │    用户再次纠正: "和上次一样，涉及数据库写操作不要 mock"
              │    Stop Hook → extract_semantics.py 提取 →
              │        回填: {context:"ProductService 写操作测试", correction:"同上模式"}
              ▼
  T+5h    [会话 3] 用户直接跳过 testing skill，手动写集成测试模板
              │    Stop Hook → 元数据 {skills_used:[testing, skipped]}
              ▼
  T+8h    [会话 4] AI 用 testing skill，用户再次手动改写为集成测试
              │    用户说: "以后涉及数据库的测试场景直接走集成测试，别建议 mock 了"
              │    Stop Hook → extract_semantics.py 提取 →
              │        回填: {context:"数据库测试场景通用规则", correction:"用户明确偏好集成测试"}
              ▼
  T+10h   [会话 5] 正常会话，无测试相关纠正
              │    Stop Hook → 元数据正常
              ▼
 ═══════════════════════════════════════════════════════════════════════════
                         ▼ 触发阈值: 5 个新会话 ▼
 ═══════════════════════════════════════════════════════════════════════════

  T+10.5h [Cron 触发] evolve-daemon.py 唤醒
              │
              ├─ 1. 扫描 data/sessions.jsonl 中 5 个新会话
              │     发现 testing skill 被纠正 3 次，模式完全一致
              │
              ├─ 2. 触发条件检查
              │     ✅ 新会话 ≥ 5
              │     ✅ testing skill 被纠正 ≥ 3 次（同一模式）
              │     ✅ 距上次分析 > 6h
              │
              ├─ 3. 构建分析 Prompt → 调用 Claude Sonnet
              │     输入: 
              │       - 3 条带 context/correction/resolution 的结构化纠正记录
              │       - testing/SKILL.md 原文
              │       - 用户最后说的 "涉及数据库直接走集成测试"
              │
              │     Claude 分析:
              │       "testing/SKILL.md 的 '选择测试类型' 决策树缺少分支:
              │        涉及 @Transactional / 数据库写操作 → 集成测试
              │        这是用户的明确偏好且验证有效（3/3 次纠正后通过）"
              │
              ├─ 4. 生成提案文件
              │     proposals/2026-04-30_testing-skill-transaction-rule.md
              │       建议: SKILL.md 第 3 步增加事务场景 → 集成测试的规则
              │
              ├─ 5. 写入分析状态
              │     data/analysis_state.json ← {last_analyzed_session_id, time}
              │
              └─ 6. gh pr create
                     --title "testing skill: 增加数据库事务场景的集成测试规则"
                     
  T+10.6h [Daemon 退出] 等待下次触发

 ═══════════════════════════════════════════════════════════════════════════
                         ▼ 人工介入 ▼
 ═══════════════════════════════════════════════════════════════════════════

  T+12h   [用户 Review] 打开 proposals/2026-04-30_testing-skill-transaction-rule.md
              │
              ├─ 阅读数据依据: 3 个独立会话中同一模式被纠正 ✅ 证据充分
              ├─ 审查建议改动: SKILL.md 增加事务→集成测试规则 ✅ 精准可执行
              ├─ 审查风险评估: Low ✅ 
              │
              └─ 决定: Approve → Merge PR
              
  T+12.1h [Merge 后] testing/SKILL.md 更新
              │
              └─ 下次 Claude Code 会话自动加载新规则
              
 ═══════════════════════════════════════════════════════════════════════════
                         ▼ 验证循环 ▼
 ═══════════════════════════════════════════════════════════════════════════

  T+14h   [会话 6] testing skill 被调用，涉及事务场景
              │    自动走集成测试建议，用户未纠正 ✅
              │    Stop Hook → extract_semantics.py: {corrections: 0}
              │
  T+20h   [会话 7] testing skill 被调用，事务场景，集成测试，用户未纠正 ✅
              │
              └─ 3 天后，daemon 分析确认: testing skill 在事务场景纠正率 3/5 → 0/2
                 验证通过，标记提案为 "verified" ✅
```

### 3.2 数据流架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         开发机器                                 │
│                                                                   │
│  ┌──────────────────┐         ┌──────────────────────────┐      │
│  │  Claude Code      │         │  launchd / cron            │      │
│  │                   │         │                            │      │
│  │  Session 1..N     │         │  每 4h 或 空闲时触发:       │      │
│  │  ┌─────────────┐  │         │  ┌──────────────────────┐  │      │
│  │  │ Agent 调用   │  │         │  │ evolve-daemon.py     │  │      │
│  │  │ Skill 调用   │  │         │  │                      │  │      │
│  │  │ Tool 失败    │  │         │  │ python3              │  │      │
│  │  │ 用户纠正     │  │         │  │ .claude/evolve-      │  │      │
│  │  └──────┬───────┘  │         │  │ daemon/daemon.py     │  │      │
│  │         │          │         │  │ check --threshold=5  │  │      │
│  │         │ Stop Hook│         │  └──────────┬───────────┘  │      │
│  │         ▼          │         │             │              │      │
│  │  collect_session   │         │             │ 满足阈值      │      │
│  │  .py (10ms)        │         │             ▼              │      │
│  │         │          │         │  ┌──────────────────────┐  │      │
│  │         │ 追加一行  │         │  │ analyzer.py          │  │      │
│  │         ▼          │         │  │ 聚合 + 统计           │  │      │
│  │  data/sessions     │         │  └──────────┬───────────┘  │      │
│  │  .jsonl            │         │             │              │      │
│  └─────────┬──────────┘         │             ▼              │      │
│            │                    │  ┌──────────────────────┐  │      │
│            │   读取              │  │ proposer.py          │  │      │
│            └────────────────────┼──│                      │  │      │
│                                 │  │ 调用 Claude API      │  │      │
│                                 │  │ 生成改进提案         │  │      │
│                                 │  └──────────┬───────────┘  │      │
│                                 │             │              │      │
│                                 │             ▼              │      │
│                                 │  ┌──────────────────────┐  │      │
│                                 │  │ proposals/            │  │      │
│                                 │  │ YYYY-MM-DD_xxx.md     │  │      │
│                                 │  └──────────┬───────────┘  │      │
│                                 │             │              │      │
│                                 │             │ gh pr create │      │
│                                 │             ▼              │      │
│                                 │  ┌──────────────────────┐  │      │
│                                 │  │ GitHub PR             │  │      │
│                                 │  │ → 人工 Review         │  │      │
│                                 │  │ → Merge / Close       │  │      │
│                                 │  └──────────────────────┘  │      │
│                                 └──────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Hook 触发时序

```
Claude Code 会话生命周期
═══════════════════════════════════════════════════════════════

SessionStart
  │
  ├─ [不触发任何进化 hook] ← 设计原则: 会话启动不做额外开销
  │
  ├─ UserPromptSubmit
  │     └─ [可选] collect_feedback.py → 检测用户是否给了纠正/偏好信号
  │          写入 data/feedback.jsonl（一行，~2ms）
  │
  ├─ PostToolUse[Agent]
  │     └─ [可选] collect_agent.py → 记录 agent 调用结果
  │          写入 data/agent_calls.jsonl（一行，~1ms）
  │
  ├─ PostToolUse[Skill]
  │     └─ [可选] collect_skill.py → 记录 skill 使用情况
  │          写入 data/skill_calls.jsonl（一行，~1ms）
  │
  ├─ PostToolUseFailure
  │     └─ [可选] collect_failure.py → 记录工具失败
  │          写入 data/failures.jsonl（一行，~1ms）
  │
  └─ Stop  ← 唯一汇总点
        └─ collect_session.py
              ├─ 1. 收集元数据（< 10ms）
              │     读取本轮所有临时 jsonl 文件
              │     构建会话摘要行:
              │       - agents_used: [orchestrator, code-reviewer]
              │       - skills_used: [testing, karpathy-guidelines]
              │       - tool_failures: 1 (Bash timeout)
              │       - user_corrections_count: 1
              │       - git_diff_stats: 5 files, +120 -30
              │       - duration_minutes: 45
              │
              ├─ 2. 写入 data/sessions.jsonl（一行 JSON，~2KB）
              │
              └─ 3. 触发语义提取（异步，不阻塞会话结束）
                    extract_semantics.py
                      ├─ 输入: 本轮对话中 "用户纠正 AI" 的相关片段
                      ├─ 调用 Haiku（成本 ~$0.0001，耗时 2-3s）
                      └─ 回填 sessions.jsonl 添加 rich_context:
                           {
                             "corrections": [
                               {
                                 "skill": "testing",
                                 "context": "UserService 事务回滚测试",
                                 "correction": "用户说: mock 验证不到真实事务行为",
                                 "resolution": "改为集成测试后通过"
                               }
                             ]
                           }

═══════════════════════════════════════════════════════════════
Hook 设计原则:
  1. 会话中: 只做数据采集（写一行 JSONL），不做任何分析
  2. Stop: 聚合本轮数据为一个摘要行，非阻塞
  3. 永远不在 Hot Path 上做 AI 调用或文件修改
```

---

## 4. 核心组件设计

### 4.1 目录结构

```
.claude/
├── evolve-daemon/                  # 进化守护进程（独立于 Claude Code）
│   ├── daemon.py                   # 主入口，调度循环（~80行）
│   ├── analyzer.py                 # 数据聚合与统计分析（~150行）
│   ├── proposer.py                 # Claude API 调用 + 提案生成（~150行）
│   ├── extract_semantics.py        # 语义提取：Haiku 分析对话纠正上下文（~80行）
│   ├── config.yaml                 # 配置文件
│   └── templates/
│       ├── proposal.md             # 提案模板
│       ├── analysis_prompt.md      # 深度分析 API 的 system prompt
│       └── extract_prompt.md       # 语义提取 API 的 system prompt
│
├── hooks/
│   └── bin/
│       ├── collect_session.py      # Stop Hook: 会话摘要 + 触成语义提取（~60行）
│       ├── collect_agent.py        # PostToolUse[Agent]: agent 调用记录（~30行）
│       ├── collect_skill.py        # PostToolUse[Skill]: skill 使用记录（~30行）
│       └── collect_failure.py      # PostToolUseFailure: 工具失败记录（~30行）
│
├── data/                           # 运行时数据（.gitignore）
│   ├── sessions.jsonl              # 会话摘要日志（含 rich_context）
│   ├── analysis_state.json         # 分析进度状态
│   └── .gitkeep
│
├── proposals/                      # 进化提案（git track）
│   └── .gitkeep
│
└── settings.json                   # Hook 配置
```

### 4.2 config.yaml

```yaml
# evolve-daemon 配置文件
daemon:
  schedule: "*/30 * * * *"           # cron: 每 30 分钟检查一次
  idle_trigger_minutes: 120          # 空闲触发: 120分钟无会话后触发
  extract_timeout_seconds: 5         # 语义提取超时
  
thresholds:
  min_new_sessions: 5               # 最少新会话数才触发分析
  min_same_pattern_corrections: 3   # 同一 target 被同一模式纠正的最少次数
  max_hours_since_last_analyze: 6   # 最长分析间隔（强制触发）
  
claude_api:
  extract_model: "claude-haiku-4-5"      # 语义提取用（成本最低）
  extract_max_tokens: 512
  extract_temperature: 0.1
  analyze_model: "claude-sonnet-4-6"     # 深度分析用
  analyze_max_tokens: 4096
  analyze_temperature: 0.3

safety:
  max_proposals_per_day: 3          # 每天最多生成提案数
  auto_close_days: 7                # 未处理提案自动关闭天数
  breaker:                          # 同一 target 连续被拒 → 暂停
    max_consecutive_rejects: 3
    pause_days: 30

paths:
  data_dir: ".claude/data"
  proposals_dir: ".claude/proposals"
  skills_dir: ".claude/skills"
  agents_dir: ".claude/agents"
  rules_dir: ".claude/rules"
```

### 4.3 数据模型：sessions.jsonl 一行

这才是核心——一行 session 的数据模型决定了 LLM 进化分析的天花板：

```json
{
  "session_id": "sess_abc123",
  "timestamp": "2026-04-30T14:30:00+08:00",
  "duration_minutes": 45,
  "git_files_changed": 5,
  "git_lines_added": 120,
  "git_lines_deleted": 30,

  "agents_used": [
    {"agent": "code-reviewer", "task": "审查 AuthService.java"},
    {"agent": "orchestrator", "task": "协调测试+审查并行"}
  ],

  "skills_used": [
    {"skill": "testing", "invoked": true, "user_overrode": true},
    {"skill": "karpathy-guidelines", "invoked": true, "user_overrode": false}
  ],

  "tool_failures": [
    {"tool": "Bash", "command": "mvn test -Dtest=AuthServiceTest", "error": "timeout"}
  ],

  "corrections": [
    {
      "target": "skill:testing",
      "context": "为 UserService 写数据库事务回滚测试",
      "ai_suggestion": "使用 Mockito mock DataSource 验证回滚行为",
      "user_correction": "mock 验证不到真实事务行为，涉及 @Transactional 的场景用集成测试",
      "resolution": "改为 @SpringBootTest + @Transactional，测试通过",
      "root_cause_hint": "testing skill 缺少数据库写操作场景的测试策略指导"
    }
  ],

  "rich_context": {}
}
```

**corrections 数组是 LLM 进化的燃料**。没有它，LLM 只能给套话建议。有了它，LLM 能精准定位到 "testing/SKILL.md 第 3 步缺少事务场景分支"。

### 4.4 collect_session.py（Stop Hook，~60 行）

```python
#!/usr/bin/env python3
"""
Stop Hook: 聚合本轮会话摘要，触成语义提取。
阶段 1: 元数据收集（< 10ms）
阶段 2: 触发 extract_semantics.py（异步，2-3s，不阻塞）
"""
import json, os, sys, subprocess
from datetime import datetime
from pathlib import Path

def main():
    data = json.loads(sys.stdin.read())
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    
    session = {
        "session_id": data.get("session_id", "unknown"),
        "timestamp": datetime.now().isoformat(),
        "duration_minutes": data.get("duration_minutes", 0),
        "agents_used": data.get("agents_used", []),
        "skills_used": data.get("skills_used", []),
        "tool_failures": data.get("tool_failures", 0),
        "corrections": [],     # 由 extract_semantics.py 回填
        "rich_context": {}     # 由 extract_semantics.py 回填
    }
    
    log_file = root / ".claude" / "data" / "sessions.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 写入并记住字节位置（用于后续回填）
    with open(log_file, "a") as f:
        f.write(json.dumps(session, ensure_ascii=False) + "\n")
    
    # 如果有用户纠正，异步触发语义提取（非阻塞）
    if data.get("has_user_corrections"):
        daemon_dir = root / ".claude" / "evolve-daemon"
        subprocess.Popen(
            [sys.executable, str(daemon_dir / "extract_semantics.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    
    print(json.dumps({"collected": True, "extraction_triggered": data.get("has_user_corrections", False)}))

if __name__ == "__main__":
    main()
```

### 4.5 extract_semantics.py（语义提取，~80 行）

```python
#!/usr/bin/env python3
"""
Stop Hook 触发的异步语义提取。
用 Haiku 从本轮对话中提取用户纠正的具体上下文。
原则:
  - 只提取事实（用户说了什么，改了什么），不做判断
  - 超时 5s 放弃，不影响下次会话
  - 成本极低（Haiku ~$0.0001/次）
"""
import json, os, sys, yaml
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic

def load_config():
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    
    # 读取刚写入的最后一个 session
    sessions_file = root / "config"["paths"]["data_dir"] / "sessions.jsonl"
    lines = sessions_file.read_text().strip().splitlines()
    if not lines:
        return
    last_session = json.loads(lines[-1])
    
    # 如果没有纠正数据（元数据标记为 0），跳过
    if not any(s.get("user_overrode") for s in last_session.get("skills_used", [])):
        return
    
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    system_prompt = """你是对话分析器。从用户与 AI 的对话中提取用户纠正 AI 的上下文。

输出 JSON 数组:
[
  {
    "target": "skill:xxx 或 agent:xxx",
    "context": "用户当时在做什么",
    "ai_suggestion": "AI 建议了什么",
    "user_correction": "用户纠正了什么",
    "resolution": "纠正后的结果",
    "root_cause_hint": "可能的skill/agent定义缺失"
  }
]

只输出 JSON，不要解释。如果没有纠正，输出 []。"""
    
    try:
        # 从对话中检测纠正上下文（输入来自 hook 传递的上下文）
        response = client.messages.create(
            model=config["claude_api"]["extract_model"],
            max_tokens=config["claude_api"]["extract_max_tokens"],
            temperature=config["claude_api"]["extract_temperature"],
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(last_session, ensure_ascii=False)}]
        )
        
        corrections = json.loads(response.content[0].text)
        
        # 回填最后一个 session 行
        last_session["corrections"] = corrections
        lines[-1] = json.dumps(last_session, ensure_ascii=False)
        sessions_file.write_text("\n".join(lines) + "\n")
        
    except Exception:
        # 静默失败，元数据已兜底
        pass

if __name__ == "__main__":
    main()
```

### 4.6 daemon.py（守护进程入口）

```python
#!/usr/bin/env python3
"""
进化守护进程入口。
由 cron/launchd 定时触发，执行: 检查 → 聚合 → 分析 → 生成提案。

用法:
  python3 daemon.py check          # 仅检查触发条件，输出状态
  python3 daemon.py run            # 检查并执行分析（默认 cron 模式）
  python3 daemon.py status         # 查看系统状态
"""
import json, os, sys, yaml
from pathlib import Path
from datetime import datetime, timedelta

def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)

def load_new_sessions(data_dir, last_analyzed_id=None):
    """加载自上次分析以来的新会话"""
    sessions_file = data_dir / "sessions.jsonl"
    if not sessions_file.exists():
        return []
    
    sessions = []
    with open(sessions_file) as f:
        for line in f:
            if line.strip():
                sessions.append(json.loads(line))
    
    if last_analyzed_id:
        # 只取 last_analyzed_id 之后的会话
        try:
            idx = next(i for i, s in enumerate(sessions) 
                       if s["session_id"] == last_analyzed_id)
            sessions = sessions[idx + 1:]
        except StopIteration:
            pass
    
    return sessions

def check_thresholds(sessions, config, last_analyze_time):
    """检查是否满足触发条件"""
    thresholds = config["thresholds"]
    triggers = []
    
    # 条件1: 新会话数
    if len(sessions) >= thresholds["min_new_sessions"]:
        triggers.append(f"new_sessions: {len(sessions)} >= {thresholds['min_new_sessions']}")
    
    # 条件2: 距上次分析超过最大间隔
    if last_analyze_time:
        hours_since = (datetime.now() - last_analyze_time).total_seconds() / 3600
        if hours_since >= thresholds["max_hours_since_last_analyze"]:
            triggers.append(f"time_elapsed: {hours_since:.1f}h >= {thresholds['max_hours_since_last_analyze']}h")
    
    # 条件3: 同一 target 被同一模式纠正（利用 rich context）
    pattern_groups = {}
    for s in sessions:
        for c in s.get("corrections", []):
            key = f"{c.get('target')}:{c.get('root_cause_hint', 'unknown')}"
            pattern_groups.setdefault(key, []).append(c)
    for key, corrections in pattern_groups.items():
        if len(corrections) >= thresholds["min_same_pattern_corrections"]:
            triggers.append(f"pattern: {key} corrected {len(corrections)} times >= {thresholds['min_same_pattern_corrections']}")
    
    return triggers

def main():
    config = load_config()
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    data_dir = root / config["paths"]["data_dir"]
    
    # 读取分析状态
    state_file = data_dir / "analysis_state.json"
    state = {}
    if state_file.exists():
        state = json.loads(state_file.read_text())
    
    last_analyzed_id = state.get("last_analyzed_session_id")
    last_analyze_time = None
    if state.get("last_analyze_time"):
        last_analyze_time = datetime.fromisoformat(state["last_analyze_time"])
    
    # 加载新会话
    sessions = load_new_sessions(data_dir, last_analyzed_id)
    
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    
    if cmd == "check":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        print(json.dumps({
            "new_sessions": len(sessions),
            "last_analyze_time": str(last_analyze_time),
            "triggers": triggers,
            "should_run": len(triggers) > 0
        }, indent=2, ensure_ascii=False))
    
    elif cmd == "run":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        if not triggers:
            print("No triggers met, skipping analysis")
            return
        
        # 调用分析器
        from analyzer import aggregate_and_analyze
        from proposer import generate_proposal
        
        analysis = aggregate_and_analyze(sessions, config, root)
        
        if analysis["should_propose"]:
            proposal_path = generate_proposal(analysis, config, root)
            
            # 更新状态
            state["last_analyzed_session_id"] = sessions[-1]["session_id"]
            state["last_analyze_time"] = datetime.now().isoformat()
            state_file.write_text(json.dumps(state, indent=2))
            
            print(f"Proposal generated: {proposal_path}")
        else:
            print("Analysis complete, no proposal needed")
    
    elif cmd == "status":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        proposals_dir = root / config["paths"]["proposals_dir"]
        proposals = list(proposals_dir.glob("*.md")) if proposals_dir.exists() else []
        print(json.dumps({
            "total_sessions": len(list(data_dir.glob("sessions.jsonl"))),
            "new_sessions_since_last_analyze": len(sessions),
            "pending_proposals": len(proposals),
            "will_trigger_on_next_run": len(triggers) > 0,
            "triggers": triggers
        }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

### 4.7 proposer.py（提案生成器）

```python
"""
调用 Claude API 进行深度分析，生成结构化改进提案。
"""
import json, os, yaml
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

def generate_proposal(analysis, config, root):
    """
    输入: analyzer 产出的聚合数据
    输出: proposals/YYYY-MM-DD_description.md
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    # 构建分析 prompt
    system_prompt = f"""你是一个 AI 工程规范优化器。你的任务是分析 Claude Code 的使用数据，
找出 agent 定义、skill 模板、规则文件中的可改进点。

原则:
1. 只提出有数据支撑的建议，不臆测
2. 建议必须具体、可执行（精确到哪个文件的哪个章节/步骤）
3. 必须评估改动风险（low/medium/high）
4. 不提出涉及安全策略或权限配置的改动（这些由人决定）
5. 如果数据不足以支撑任何建议，直接说"无需改进"

你会收到以下数据格式:
- sessions: 最近的会话摘要列表
- targets: 受影响的 agents/skills/rules 及其使用统计
"""
    
    user_message = json.dumps(analysis, ensure_ascii=False, indent=2)
    
    response = client.messages.create(
        model=config["claude_api"]["model"],
        max_tokens=config["claude_api"]["max_tokens"],
        temperature=config["claude_api"]["temperature"],
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    
    # 生成提案文件
    proposal_content = response.content[0].text
    date_str = datetime.now().strftime("%Y-%m-%d")
    target = analysis.get("primary_target", "general")
    
    proposals_dir = root / config["paths"]["proposals_dir"]
    proposals_dir.mkdir(parents=True, exist_ok=True)
    
    proposal_path = proposals_dir / f"{date_str}_{target}-optimize.md"
    proposal_path.write_text(proposal_content, encoding="utf-8")
    
    return proposal_path
```

---

## 5. 调度配置

### 5.1 macOS LaunchAgent

```xml
<!-- ~/Library/LaunchAgents/com.claude-harness-kit.evolve.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-harness-kit.evolve</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/yyx/code/github/claude-harness-kit/.claude/evolve-daemon/daemon.py</string>
        <string>run</string>
    </array>
    <key>StartInterval</key>
    <integer>14400</integer>  <!-- 4 小时 -->
    <key>RunAtLoad</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CLAUDE_PROJECT_DIR</key>
        <string>/Users/yyx/code/github/claude-harness-kit</string>
        <key>ANTHROPIC_API_KEY</key>
        <string><!-- 从 Keychain 或 .env 读取 --></string>
    </dict>
</dict>
</plist>
```

加载: `launchctl load ~/Library/LaunchAgents/com.claude-harness-kit.evolve.plist`

### 5.2 Linux systemd timer + cron 双保险

```ini
# ~/.config/systemd/user/claude-evolve.service
[Unit]
Description=Claude Harness Kit Evolution Daemon

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/code/github/claude-harness-kit/.claude/evolve-daemon/daemon.py run
Environment=CLAUDE_PROJECT_DIR=%h/code/github/claude-harness-kit

# ~/.config/systemd/user/claude-evolve.timer
[Unit]
Description=Claude Harness Kit Evolution Timer

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

---

## 6. 安全边界

| 边界 | 规则 | 原因 |
|------|------|------|
| **提案永不自动应用** | daemon 只生成 .md 文件 | 防止错误改动污染 prompt |
| **API 调用隔离** | 使用独立 API Key，不影响主会话 | 防止 token 消耗影响工作流 |
| **数据最小化** | sessions.jsonl 只存摘要，不含完整对话 | 隐私 + 存储成本 |
| **上限控制** | 每天最多 3 个提案 | 防止异常循环生成大量提案 |
| **自动过期** | 7 天未处理的提案自动 close | 防止积压 |
| **熔断** | 同一 target 连续 3 个提案被拒绝 → 暂停 30 天 | 防止反复提出无效建议 |
| **工作目录只读** | daemon 不写 agents/skills/rules，只写 proposals/ | 数据安全 |

---

## 7. 实施路线

### Phase 1: 清理 + 插件化（1-2h）

- 按 `cleanup-checklist.md` 执行全部删除
- 通用化 Agent：移除 Java/Vue 特定描述
- 通用化 Rule：backend.md/frontend.md 移除，技术栈放项目 CLAUDE.md
- 更新 plugin.json + package.json + README.md
- Hook 配置迁移到 settings.json 标准格式

### Phase 2: 守护进程 MVP（2-3h）

- 创建 evolve-daemon/ 目录 + config.yaml
- 实现 `collect_session.py` Hook（Stop 事件）
- 实现 `extract_semantics.py`（Haiku 语义提取）
- 实现 `daemon.py` + `analyzer.py` + `proposer.py`
- 配置 cron/launchd 调度

### Phase 3: 验证迭代（1 周）

- 运行 1 周，观察提案质量和数量
- 根据 accept/reject 比例调优 system prompt
- 迭代触发阈值（5 会话/3 纠正/6h 间隔）

---

## 8. 借鉴清单

| 来源 | 借鉴点 | 本方案采纳 |
|------|--------|:--:|
| Claude Code KAIROS | 后台 daemon + `<tick>` 信号 | ✅ cron 调度 |
| Claude Code autoDream | 记忆合并/冲突消除/假设固化 | ✅ 多会话聚合分析 |
| Claude Code autoDream | "hint" 语义（非 "truth"） | ✅ 提案制，不自动应用 |
| Claude Code 内存系统 | 文件系统优先，无向量数据库 | ✅ JSONL + Markdown |
| heartbeat | `observe → decide → act → sleep` | ✅ 同构循环 |
| AutoDream (JaWaMi73) | 3 模式: Active/AFK/Maintenance | ✅ check/run/status |
| AutoDream (JaWaMi73) | 双 layer 安全（guardian + breaker） | ✅ 熔断 + 上限控制 |
| Claude Code 源码 | Fork 子进程，缓存继承 | ✅ daemon 用独立 API Key |
