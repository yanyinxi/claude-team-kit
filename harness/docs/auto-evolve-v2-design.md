# Auto-Evolve v2: 4维度自主进化闭环系统

## 文档信息

- 版本: v2.0
- 状态: **已实现** ✅
- 作者: Claude Code (Architect Agent)
- 日期: 2026-05-02
- 实现日期: 2026-05-02

---

## 目录

1. [背景与问题定义](#1-背景与问题定义)
2. [设计原则与约束](#2-设计原则与约束)
3. [整体架构图](#3-整体架构图)
4. [数据流设计](#4-数据流设计)
5. [模块详细设计](#5-模块详细设计)
6. [4维度进化策略](#6-4维度进化策略)
7. [安全机制](#7-安全机制)
8. [实现路线图](#8-实现路线图)
9. [设计决策理由](#9-设计决策理由)
10. [接口定义](#10-接口定义)

---

## 1. 背景与问题定义

### 1.1 现有系统问题

| 问题 | 当前状态 | 影响 |
|------|----------|------|
| 数据采集层 | sessions.jsonl 只含元数据，无语义 | LLM 只能给泛化建议 |
| 决策层 | llm_decision.py 已实现 | 但缺乏风险分级和4维度联动 |
| 执行层 | apply_change.py 已实现 | 但无 extract_semantics.py 支持 |
| 验证层 | rollback.py 已实现 | 但与 instinct 缺乏联动 |
| 4维度 | 无统一进化信号机制 | Agent/Skill/Rules/Memory 各自为政 |

### 1.2 核心问题回答

**Q1: sessions.jsonl 如何转化为可执行的进化信号？**
```
sessions.jsonl (元数据)
    ↓ [extract_semantics.py: Haiku 语义提取]
rich_context.corrections (结构化纠正上下文)
    ↓ [analyzer.py: 聚合分析]
correction_hotspots + correction_patterns
    ↓ [llm_decision.py: 决策]
target_file + suggested_change
```

**Q2: 如何让 LLM 做出"改哪个文件、怎么改"的决策？**
- 分层决策：规则层（硬边界）→ LLM 层（语义理解）→ 风险分级
- 输入：结构化纠正上下文 + 目标文件原文
- 输出：精确到文件+章节+行号的改动建议

**Q3: 如何安全地修改 Agent/Skill/Rules 文件？**
- 备份：每次改动前备份到 `.claude/data/backups/`
- 验证：观察期7天，指标恶化自动回滚
- 熔断：连续失败3次暂停30天

**Q4: 如何确认改动有效？如何回滚？**
- 观察期：收集后续会话指标，与基线对比
- 自动回滚：指标恶化超过阈值时触发
- 手动回滚：支持 `apply_change.py rollback --id xxx`

**Q5: 4维度如何形成统一的进化闭环？**
```
同一数据源 (sessions.jsonl)
    ↓
统一信号 (correction_hotspots)
    ↓
维度分发 (基于 target 前缀)
    ├→ agent:xxx → agents/*.md
    ├→ skill:xxx → skills/*/SKILL.md
    ├→ rule:xxx → rules/*.md
    └→ instinct → instinct-record.json
    ↓
统一验证 (rollback.py 观察指标)
    ↓
统一记忆 (instinct_updater.py 更新置信度)
```

---

## 2. 设计原则与约束

### 2.1 核心原则

1. **渐进式进化**: 不改变现有架构，在现有模块基础上增量开发
2. **可逆性优先**: 所有改动必须可备份、可回滚
3. **数据驱动**: 决策基于实际测量，非直觉
4. **LLM 做擅长的事**: 语义理解、模式识别；不做：数值计算、安全判断
5. **4维度差异化**: 每个维度有不同的进化策略和阈值

### 2.2 约束条件

| 约束 | 说明 |
|------|------|
| Claude Code 无动态 API | 只能通过文件系统扩展 |
| Hook 必须在 50ms 内完成 | 不能在 Hot Path 做 AI 调用 |
| LLM 成本 | 优先使用 Haiku 做提取，Sonnet 做分析 |
| 人工审核 | 安全相关改动必须人工确认 |

---

## 3. 整体架构图

### 3.1 完整数据流

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           4维度自主进化闭环系统                                  ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐   ║
║  │                    第1层: 数据采集层 (Hook，同步 <10ms)                  │   ║
║  │                                                                         │   ║
║  │  PostToolUse[Agent]  → collect-agent.py  → agent_calls.jsonl           │   ║
║  │  PostToolUse[Skill]  → collect-skill.py  → skill_calls.jsonl          │   ║
║  │  PostToolUseFailure  → collect-failure.py → failures.jsonl             │   ║
║  │  Stop               → collect-session.py  → sessions.jsonl             │   ║
║  │                                           ↓                             │   ║
║  │                              [异步触发 extract_semantics.py]            │   ║
║  └─────────────────────────────────────────────────────────────────────────┘   ║
║                                       ↓                                        ║
║  ┌─────────────────────────────────────────────────────────────────────────┐   ║
║  │                    第2层: 语义提取层 (Haiku，异步 2-3s)                   │   ║
║  │                                                                         │   ║
║  │  extract_semantics.py                                                  │   ║
║  │    输入: sessions.jsonl 最后一行 + 会话上下文                              │   ║
║  │    处理: Haiku 提取纠正模式                                              │   ║
║  │    输出: corrections[] (target/context/correction/resolution)          │   ║
║  │           ↓ 回填 sessions.jsonl                                         │   ║
║  │           ↓ 记录 instinct-record.json (confidence=0.3)                  │   ║
║  └─────────────────────────────────────────────────────────────────────────┘   ║
║                                       ↓                                        ║
║  ┌─────────────────────────────────────────────────────────────────────────┐   ║
║  │                    第3层: 分析决策层 (独立进程，cron触发)                  │   ║
║  │                                                                         │   ║
║  │  daemon.py (触发检查)                                                    │   ║
║  │    ├→ check_thresholds(): 满足条件?                                     │   ║
║  │    └→ run_analysis()                                                   │   ║
║  │         ↓                                                               │   ║
║  │  analyzer.py (聚合分析)                                                 │   ║
║  │    输入: sessions.jsonl (N个新会话)                                      │   ║
║  │    处理: 统计纠正热点、失败模式、技能覆盖                                   │   ║
║  │    输出: {correction_hotspots, correction_patterns, primary_target}      │   ║
║  │         ↓                                                               │   ║
║  │  llm_decision.py (LLM决策)                                              │   ║
║  │    输入: analysis结果 + instinct-record.json                            │   ║
║  │    处理: 规则检查 → LLM评估 → 风险分级                                    │   ║
║  │    输出: {action, target_file, suggested_change, confidence, risk_level}│   ║
║  └─────────────────────────────────────────────────────────────────────────┘   ║
║                                       ↓                                        ║
║  ┌─────────────────────────────────────────────────────────────────────────┐   ║
║  │                    第4层: 执行层 (文件操作 + 记录)                        │   ║
║  │                                                                         │   ║
║  │  ┌─────────────────────────────────────────────────────────────────┐    │   ║
║  │  │ action=auto_apply (低风险+高置信)                                  │    │   ║
║  │  │   └→ apply_change.py                                             │    │   ║
║  │  │       1. 备份文件到 backups/                                      │    │   ║
║  │  │       2. 应用改动                                                 │    │   ║
║  │  │       3. 记录 proposal_history.json                               │    │   ║
║  │  │       4. 更新 instinct-record.json (confidence=0.5)               │    │   ║
║  │  └─────────────────────────────────────────────────────────────────┘    │   ║
║  │                                                                         │   ║
║  │  ┌─────────────────────────────────────────────────────────────────┐    │   ║
║  │  │ action=propose (高风险/新目标)                                    │    │   ║
║  │  │   └→ proposer.py                                                 │    │   ║
║  │  │       1. 调用 Sonnet 生成详细提案                                 │    │   ║
║  │  │       2. 保存到 proposals/*.md                                    │    │   ║
║  │  │       3. 记录 instinct-record.json (confidence=0.5, 待审核)         │    │   ║
║  │  └─────────────────────────────────────────────────────────────────┘    │   ║
║  │                                                                         │   ║
║  │  ┌─────────────────────────────────────────────────────────────────┐    │   ║
║  │  │ action=skip (数据不足)                                          │    │   ║
║  │  │   └→ 记录 analysis_state.json，跳过                              │    │   ║
║  │  └─────────────────────────────────────────────────────────────────┘    │   ║
║  └─────────────────────────────────────────────────────────────────────────┘   ║
║                                       ↓                                        ║
║  ┌─────────────────────────────────────────────────────────────────────────┐   ║
║  │                    第5层: 验证层 (独立进程，每日检查)                       │   ║
║  │                                                                         │   ║
║  │  rollback.py (观察期验证)                                                │   ║
║  │    每日检查:                                                            │   ║
║  │      ├→ 收集观察期内会话指标                                             │   ║
║  │      ├→ 与基线对比 (baseline_metrics)                                    │   ║
║  │      └→ 决策: keep / rollback / observe                                 │   ║
║  │                                                                         │   ║
║  │  instinct_updater.py (置信度管理)                                        │   ║
║  │    ├→ 时间衰减 (90天半衰期)                                              │   ║
║  │    ├→ 验证增强 (reinforcement_count++)                                 │   ║
║  │    └→ 回滚降级 (confidence -= 0.1)                                      │   ║
║  └─────────────────────────────────────────────────────────────────────────┘   ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

### 3.2 4维度联动架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    统一数据源: sessions.jsonl                                │
│                                                                             │
│  同一批会话数据 ────────────────────────────────────────────────────────    │
│      │                                                                     │
│      ├─────────────────────────────────────────────────────────────────┐    │
│      │                        analyzer.py 聚合分析                        │    │
│      │                                                                 │    │
│      │  correction_hotspots: {"agent:backend-dev": 5, ...}             │    │
│      │  correction_patterns: {"agent:backend-dev:testing": [...]}       │    │
│      │  skill_usage: {"testing": 10, "git-master": 5}                   │    │
│      │  tool_failures: {"Bash": 8, "Read": 3}                           │    │
│      └─────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│      ┌───────────────────────┼───────────────────────┬──────────────────┐   │
│      │                       │                       │                  │   │
│      ↓                       ↓                       ↓                  ↓   │
│  ┌─────────┐           ┌─────────┐           ┌─────────┐          ┌─────────┐│
│  │  Agent  │           │  Skill  │           │  Rules  │          │ Instinct││
│  │  维度   │           │  维度   │           │  维度   │          │  维度   ││
│  └────┬────┘           └────┬────┘           └────┬────┘          └────┬────┘│
│       │                    │                    │                     │     │
│  agents/*.md          skills/*/SKILL.md    rules/*.md          instinct-   │
│                                                      record.json          │
│       │                    │                    │                     │     │
│       └────────────────────┴────────────────────┴─────────────────────┘     │
│                              │                                              │
│                    ┌──────────┴──────────┐                                 │
│                    │  instinct_updater.py │                                 │
│                    │  统一置信度管理       │                                 │
│                    │  时间衰减 + 验证增强   │                                 │
│                    └─────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据流设计

### 4.1 输入数据

| 文件 | 来源 | 内容 | 格式 |
|------|------|------|------|
| sessions.jsonl | collect-session.py | 会话摘要 | JSONL (每行一个session) |
| agent_calls.jsonl | collect-agent.py | Agent调用记录 | JSONL |
| skill_calls.jsonl | collect-skill.py | Skill使用记录 | JSONL |
| failures.jsonl | collect-failure.py | 工具失败记录 | JSONL |
| instinct-record.json | instinct_updater.py | 本能记录 | JSON |

### 4.2 sessions.jsonl 数据模型

```json
{
  "session_id": "git-abc123-2026-05-02",
  "timestamp": "2026-05-02T08:30:00+08:00",
  "mode": "solo",
  "duration_minutes": 45,

  "agents_used": ["backend-dev", "code-reviewer"],
  "agent_count": 3,
  "agent_distribution": {"backend-dev": 2, "code-reviewer": 1},
  "agent_success_rate": 0.9,

  "tool_failures": 2,
  "failure_types": {"permission_error": 1, "not_found_error": 1},
  "failure_tools": {"Read": 1, "Bash": 1},

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

  "rich_context": {
    "agent_stats": {...},
    "failure_stats": {...},
    "git_stats": {...}
  }
}
```

### 4.3 instinct-record.json 数据模型

```json
{
  "description": "Instinct System — 从用户纠正中学习的可复用行为修正",
  "version": 1,
  "records": [
    {
      "id": "auto-abc12345",
      "pattern": "skill:testing: mock验证不到事务真实行为",
      "context": "涉及 @Transactional 的测试场景",
      "correction": "改为集成测试 @SpringBootTest + @Transactional",
      "root_cause": "testing skill 缺少数据库写操作场景指导",
      "confidence": 0.75,
      "applied_count": 2,
      "reinforcement_count": 3,
      "source": "extract-semantics",
      "created_at": "2026-05-02T08:30:00",
      "last_reinforced_at": "2026-05-05T10:00:00",
      "decay_status": "active",
      "decay_weight": 0.98,
      "updated_at": "2026-05-05T10:00:00"
    }
  ]
}
```

### 4.4 proposal_history.json 数据模型

```json
[
  {
    "id": "auto-20260502103000",
    "action": "auto_apply",
    "reason": "Low risk + high confidence",
    "target_file": "skills/testing/SKILL.md",
    "suggested_change": "append: ## 新增注意事项\n涉及 @Transactional 的测试场景，优先使用集成测试",
    "risk_level": "low",
    "confidence": 0.85,
    "status": "applied",
    "applied_at": "2026-05-02T10:30:00",
    "observation_end": "2026-05-09T10:30:00",
    "backup_path": ".claude/data/backups/auto-20260502103000_testing.md",
    "baseline_metrics": {
      "success_rate": 0.9,
      "failure_rate": 0.1,
      "correction_rate": 0.15,
      "sample_size": 20
    },
    "rollback_triggers": [],
    "rolled_back_at": null,
    "consolidated_at": null
  }
]
```

---

## 5. 模块详细设计

### 5.1 模块总览

| 模块 | 文件 | 状态 | 职责 |
|------|------|------|------|
| 数据采集 | hooks/bin/*.py | 已实现 | 采集会话元数据 |
| 语义提取 | extract_semantics.py | **待实现** | Haiku 提取纠正上下文 |
| 守护进程 | daemon.py | 已实现 | 触发检查、调度 |
| 调度器 | scheduler.py | 已实现 | APScheduler 封装 |
| 分析器 | analyzer.py | 已实现 | 聚合统计 |
| 决策引擎 | llm_decision.py | 已实现 | LLM 决策 |
| 提案生成 | proposer.py | 已实现 | 生成 Markdown 提案 |
| 自动应用 | apply_change.py | 已实现 | 应用改动 |
| 自动回滚 | rollback.py | 已实现 | 观察期验证 |
| 本能更新 | instinct_updater.py | 已实现 | 置信度管理 |
| 数据验证 | validator.py | 已实现 | 格式校验 |

### 5.2 待实现模块详情

#### 5.2.1 extract_semantics.py (待实现)

**职责**: 从会话中提取用户纠正的语义上下文

**输入**:
- sessions.jsonl 最后一行
- 当前会话的 rich_context

**输出**:
- corrections[] 数组，回填 sessions.jsonl
- instinct-record.json 新增记录

**实现要点**:
```python
def extract_with_haiku(session: dict) -> list[dict]:
    """
    调用 Claude Haiku 提取纠正上下文
    成本: ~$0.0001/次
    超时: 5s
    """
    system_prompt = """你是对话分析器。从会话摘要中提取用户纠正 AI 的上下文。

输出 JSON 数组（仅 JSON，无其他文字）:
[
  {
    "target": "skill:xxx 或 agent:xxx",
    "context": "用户当时在做什么",
    "ai_suggestion": "AI 建议了什么",
    "user_correction": "用户纠正了什么",
    "resolution": "纠正后的结果",
    "root_cause_hint": "可能的 skill/agent 定义缺失"
  }
]

如果没有纠正，输出 []。"""

    # 调用 Haiku
    # 解析返回的 JSON
    # 异常时返回空数组
```

**设计理由**: Haiku 成本极低，适合简单的结构化提取任务

### 5.3 模块接口定义

#### 5.3.1 analyzer.py

```python
def aggregate_and_analyze(sessions: list[dict], config: dict, root: Path) -> dict:
    """
    输入: sessions.jsonl 中的新会话列表
    输出: 结构化分析结果

    分析维度:
      1. correction_hotspots: 纠正热点 (target → count)
      2. correction_patterns: 纠正模式 (target:hint → {count, examples[]})
      3. skill_usage: 技能使用统计
      4. tool_failures: 工具失败统计
      5. primary_target: 最需要改进的目标
      6. should_propose: 是否需要提案
    """
```

#### 5.3.2 llm_decision.py

```python
def decide_action(sessions: list[dict], analysis: dict, config: dict) -> dict:
    """
    输入: sessions + analysis结果 + config
    输出: 决策结果

    返回:
    {
        "action": "auto_apply" | "propose" | "skip",
        "reason": str,
        "target_file": str | None,
        "suggested_change": str | None,
        "risk_level": "low" | "medium" | "high",
        "confidence": float (0.0-1.0),
        "id": str,
    }

    决策规则:
      - 规则层: 安全相关 → propose (强制)
      - LLM层: confidence >= 0.8 && risk_level == "low" → auto_apply
      - 默认: propose
    """
```

#### 5.3.3 apply_change.py

```python
def apply_change(decision: dict, root: Path) -> bool:
    """
    根据 decision 应用改动

    返回: True 成功，False 失败

    流程:
      1. 备份原文件到 backups/
      2. 读取当前内容
      3. 应用改动 (精确替换/追加/删除)
      4. 写入新内容
      5. 记录 proposal_history.json
      6. 更新 instinct-record.json
    """

def rollback_proposal(proposal_id: str, root: Path, reason: str) -> bool:
    """
    回滚指定提案

    返回: True 成功，False 失败
    """
```

#### 5.3.4 rollback.py

```python
def run_rollback_check(root: Path, config: dict) -> dict:
    """
    检查所有提案，执行回滚或固化

    返回:
    {
        "status": "completed" | "paused",
        "checked": int,
        "rolled_back": int,
        "consolidated": int,
        "observed": int,
    }
    """

def evaluate_proposal(proposal: dict, metrics: dict, baseline: dict, config: dict) -> str:
    """
    评估是否应该保留或回滚

    返回: "keep" | "rollback" | "observe"
    """
```

#### 5.3.5 instinct_updater.py

```python
def add_pattern(
    pattern: str,
    correction: str,
    root_cause: str = "",
    confidence: float = 0.3,
    source: str = "auto-detected",
    root: Path = None
) -> str:
    """
    添加新本能记录

    返回: record_id
    """

def promote_confidence(record_id: str, delta: float = 0.1, root: Path = None):
    """
    增加置信度 (验证成功后)
    """

def demote_confidence(record_id: str, delta: float = 0.1, root: Path = None):
    """
    降低置信度 (回滚后)
    """

def apply_decay_to_all(instinct: dict, config: dict) -> dict:
    """
    对所有非seed记录应用时间衰减

    公式: weight = 0.5 ^ (age_days / half_life_days)
    """
```

---

## 6. 4维度进化策略

### 6.1 Agent 维度

**定义文件**: `agents/*.md`

**进化信号**:
- Agent 被用户纠正的次数
- Agent 建议被忽略的次数
- Agent 产生的错误数量

**进化策略**:
```
触发条件: 同一 agent 被纠正 >= 3 次 (同一模式)
    ↓
分析: 提取用户纠正的上下文
    ↓
决策:
  ├→ 新 agent → propose (谨慎)
  ├→ 已有 agent + 低风险 → auto_apply
  └→ 已有 agent + 高风险 → propose
    ↓
改动类型:
  ├→ 增加注意事项 (低风险)
  ├→ 优化决策流程 (中风险)
  └→ 重写职责定义 (高风险) → propose
```

**示例**:
```markdown
# agents/backend-dev.md

## 职责
...（原有内容）...

## 新增注意事项 [auto-evolved: 2026-05-02]
- 避免使用 print() 调试，推荐使用 logging 模块
- 涉及数据库事务的场景，优先使用集成测试而非 mock
```

### 6.2 Skill 维度

**定义文件**: `skills/*/SKILL.md`

**进化信号**:
- Skill 建议被用户覆盖的次数
- Skill 相关工具失败次数
- Skill 场景覆盖不足的反馈

**进化策略**:
```
触发条件: 同一 skill 被覆盖 >= 3 次
    ↓
分析: 提取被覆盖的场景和用户偏好
    ↓
决策:
  ├→ 增加示例 → auto_apply
  ├→ 增加步骤 → propose
  └→ 删除/重写 → propose (人工审核)
    ↓
改动类型:
  ├→ 补充示例 (低风险)
  ├→ 增加步骤分支 (中风险)
  └→ 修改核心流程 (高风险) → propose
```

**示例**:
```markdown
# skills/testing/SKILL.md

## 3. 选择测试类型
...（原有内容）...

### 新增场景 [auto-evolved: 2026-05-02]
**涉及 @Transactional 或数据库写操作的场景**
→ 优先使用集成测试 `@SpringBootTest` 而非 mock 验证
→ 示例: 使用 `@DirtiesContext` 确保测试隔离
```

### 6.3 Rules 维度

**定义文件**: `rules/*.md`

**进化信号**:
- 违反规则的错误次数
- 规则不适用的场景反馈
- 新技术栈引入后的规则缺失

**进化策略**:
```
触发条件: 同一规则被违反 >= 5 次 (跨多个会话)
    ↓
分析: 识别规则的适用边界
    ↓
决策:
  ├→ 增加例外情况 → propose
  ├→ 修改规则表述 → propose
  └→ 新增规则 → propose (必须人工审核)
    ↓
改动类型:
  ├→ 增加例外 (中风险)
  └→ 新增规则 (高风险) → propose
```

**示例**:
```markdown
# rules/backend.md

## 异常处理
...（原有内容）...

## 补充说明 [auto-evolved: 2026-05-02]
**外部 API 调用的异常处理**
- 超时异常: 设置合理的 timeout，使用重试机制
- 限流异常: 实现指数退避策略
- 认证异常: 刷新 token 后重试，避免硬编码凭证
```

### 6.4 Instinct (Memory) 维度

**定义文件**: `instinct/instinct-record.json`

**进化信号**:
- 新发现的纠正模式
- 验证通过的改动
- 时间衰减后的旧模式

**进化策略**:
```
新模式发现:
  extract_semantics.py → instinct-record.json (confidence=0.3)
      ↓
验证通过:
  rollback.py → instinct_updater.promote_confidence() (confidence+=0.1)
      ↓
时间衰减:
  instinct_updater.apply_decay_to_all() → confidence *= decay_weight
      ↓
回滚降级:
  rollback.py → instinct_updater.demote_confidence() (confidence-=0.1)
```

**置信度管理**:
```
初始: 0.3 (extract-semantics发现)
验证+: 0.3 → 0.4 → 0.5 → ... → 0.95 (max)
回滚-: 0.3 → 0.2 → 0.1 (floor)
衰减*: 每90天减半
```

### 6.5 4维度联动机制

```python
# 统一的进化信号处理
def process_evolution_signal(signal: dict, config: dict, root: Path):
    """
    统一的进化信号处理器

    signal = {
        "type": "correction",
        "target": "skill:testing",
        "context": "...",
        "correction": "...",
        ...
    }
    """
    target = signal["target"]

    if target.startswith("agent:"):
        _evolve_agent(target, signal, config, root)
    elif target.startswith("skill:"):
        _evolve_skill(target, signal, config, root)
    elif target.startswith("rule:"):
        _evolve_rule(target, signal, config, root)
    else:
        _update_instinct(signal, config, root)
```

---

## 7. 安全机制

### 7.1 备份机制

```
每次应用改动前:
  1. 创建备份目录: .claude/data/backups/
  2. 备份命名: {decision_id}_{filename}
  3. 保留最近100个备份
  4. 超出的自动清理
```

### 7.2 回滚机制

```
触发条件 (满足任一):
  - 成功率下降 > 10%
  - 纠正率上升 > 20%
  - 失败率上升 > 10%
  - 用户反馈负面

执行流程:
  1. 从备份恢复文件
  2. 更新 proposal_history.json (status="rolled_back")
  3. 调用 instinct_updater.demote_confidence()
  4. 发送通知 (如果启用)
```

### 7.3 熔断机制

```
检查条件:
  - 同一 target 连续被拒 >= 3 次 → 暂停该 target 30天
  - 一周内回滚 >= 5 次 → 暂停整个系统 30天

熔断状态:
  - 暂停期间跳过所有进化检查
  - 记录暂停原因和时间
  - 到期后自动恢复
```

### 7.4 观察期机制

```
观察期: 7天 (可配置)

检查间隔: 每日 (由 cron/systemd 触发)

样本要求:
  - < 5 个会话 → 继续观察
  - >= 5 个会话 → 可评估
  - >= 10 个会话 → 可固化

决策条件:
  ├→ 指标稳定 + 样本 >= 10 → keep (固化)
  ├→ 指标恶化 → rollback
  └→ 样本不足 → observe
```

### 7.5 风险分级

| 风险等级 | 条件 | 处理方式 |
|----------|------|----------|
| **low** | 注释/格式/拼写/文档 + 置信度 >= 0.8 | auto_apply |
| **medium** | 已有记录的优化 | propose |
| **high** | 安全/权限/新目标/多文件 | propose (必须人工) |

---

## 8. 实现路线图

### Phase 1: 核心模块实现 (1周)

**目标**: 实现 extract_semantics.py，完善数据采集闭环

| 任务 | 模块 | 优先级 | 估计工时 |
|------|------|--------|----------|
| 实现 extract_semantics.py | 语义提取 | P0 | 2h |
| 集成到 collect-session.py | 数据采集 | P0 | 1h |
| 测试 extract_semantics.py | 验证 | P0 | 2h |
| 完善4维度模板 | proposer | P1 | 4h |

### Phase 2: 决策引擎增强 (1周)

**目标**: 完善 llm_decision.py，支持4维度差异化决策

| 任务 | 模块 | 优先级 | 估计工时 |
|------|------|--------|----------|
| 实现风险分级 | llm_decision | P0 | 4h |
| 实现4维度分发 | llm_decision | P0 | 4h |
| 实现 instinct 联动 | llm_decision | P1 | 4h |
| 测试决策准确性 | 验证 | P1 | 4h |

### Phase 3: 安全机制完善 (1周)

**目标**: 实现完整的备份、回滚、熔断机制

| 任务 | 模块 | 优先级 | 估计工时 |
|------|------|--------|----------|
| 实现备份清理 | apply_change | P0 | 2h |
| 实现熔断检查 | llm_decision | P0 | 4h |
| 实现观察期通知 | rollback | P1 | 2h |
| 集成 instinct 联动 | rollback | P1 | 4h |

### Phase 4: 4维度策略实现 (1周)

**目标**: 实现各维度的差异化进化策略

| 任务 | 维度 | 优先级 | 估计工时 |
|------|------|--------|----------|
| Agent 进化策略 | Agent | P0 | 4h |
| Skill 进化策略 | Skill | P0 | 4h |
| Rules 进化策略 | Rules | P1 | 4h |
| Instinct 策略 | Instinct | P0 | 4h |

### Phase 5: 测试与调优 (持续)

**目标**: 验证系统效果，持续优化

| 任务 | 说明 | 周期 |
|------|------|------|
| 运行观察 | 收集真实数据 | 2周 |
| 调优阈值 | 根据实际效果调整参数 | 持续 |
| 优化 prompt | 提升提案质量 | 持续 |

---

## 9. 设计决策理由

### 9.1 为什么用 Haiku 做语义提取？

| 方案 | 成本 | 速度 | 质量 | 选择 |
|------|------|------|------|------|
| Haiku | ~$0.0001/次 | 2-3s | 足够 | **推荐** |
| Sonnet | ~$0.003/次 | 5-10s | 更高 | 备用 |
| Opus | ~$0.015/次 | 10-20s | 最高 | 不用 |

**理由**: 语义提取是简单的结构化任务，Haiku 足够；成本和速度是关键考量

### 9.2 为什么用独立进程而非内置定时器？

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| 外部 cron/launchd | 简单可靠，进程隔离 | 需要用户配置 | **推荐** |
| 内置 APScheduler | 一键启动 | 进程可能挂 | 备选 |

**理由**: 独立进程更稳定，崩溃不影响 Claude Code；外部调度更符合 Unix 哲学

### 9.3 为什么用文件而非数据库？

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| JSONL + JSON | 简单，Git 友好 | 并发写入需锁 | **推荐** |
| SQLite | 支持并发查询 | 需要安装 | 未来备选 |
| PostgreSQL | 功能强大 | 过度设计 | 不用 |

**理由**: 轻量级文件足够当前需求；Git 版本控制天然支持；无需额外依赖

### 9.4 为什么区分 auto_apply 和 propose？

| 方案 | 安全性 | 效率 | 选择 |
|------|--------|------|------|
| 全自动 | 高风险 | 高 | 不推荐 |
| 全手动 | 无风险 | 低 | 太保守 |
| 分级决策 | 平衡 | 较高 | **推荐** |

**理由**: 低风险高置信的改动可以自动应用加速进化；高风险的保留人工审核确保安全

### 9.5 为什么用 instinct-record.json 而非直接修改文件？

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| instinct 抽象层 | 灵活、可衰减、可验证 | 多一层复杂度 | **推荐** |
| 直接修改 | 简单直接 | 难以回滚、难以验证 | 备选 |

**理由**: instinct 层提供了置信度衰减和验证机制，避免错误累积

---

## 10. 接口定义

### 10.1 CLI 接口

```bash
# daemon.py
python3 daemon.py check          # 检查触发条件
python3 daemon.py run            # 执行分析（外部触发模式）
python3 daemon.py start          # 启动内置调度器
python3 daemon.py stop           # 停止内置调度器
python3 daemon.py status         # 查看系统状态
python3 daemon.py install-launchd # macOS 安装 LaunchAgent

# analyzer.py
python3 analyzer.py analyze --sessions 5  # 分析最近N个会话

# llm_decision.py
python3 llm_decision.py decide --session-id xxx  # 决策指定会话

# apply_change.py
python3 apply_change.py apply --target xxx --change "..."  # 应用改动
python3 apply_change.py rollback --id xxx --reason "..."   # 回滚

# rollback.py
python3 rollback.py check      # 检查所有提案
python3 rollback.py health --id xxx  # 查看健康状态

# instinct_updater.py
python3 instinct_updater.py add --pattern "..." --correction "..."
python3 instinct_updater.py promote --id xxx
python3 instinct_updater.py decay
```

### 10.2 Python API

```python
from evolve_daemon import (
    analyzer,
    llm_decision,
    apply_change,
    rollback,
    instinct_updater,
)

# 分析
analysis = analyzer.aggregate_and_analyze(sessions, config, root)

# 决策
decision = llm_decision.decide_action(sessions, analysis, config)

# 应用
if decision["action"] == "auto_apply":
    apply_change.apply_change(decision, root)

# 回滚检查
rollback.run_rollback_check(root, config)

# 本能更新
instinct_updater.promote_confidence(record_id)
```

---

## 附录 A: 文件结构

```
evolve-daemon/
├── config.yaml              # 配置文件
├── daemon.py                # 主入口
├── scheduler.py             # APScheduler 封装
├── analyzer.py              # 数据分析
├── llm_decision.py          # LLM 决策引擎
├── proposer.py              # 提案生成
├── apply_change.py          # 自动应用
├── rollback.py              # 自动回滚
├── instinct_updater.py      # 本能更新
├── validator.py             # 数据验证
├── extract_semantics.py     # [待实现] 语义提取
└── templates/
    ├── proposal.md          # 提案模板
    ├── analysis_prompt.md   # 分析 Prompt
    └── extract_prompt.md    # 提取 Prompt

.claude/
├── data/
│   ├── sessions.jsonl      # 会话日志
│   ├── agent_calls.jsonl   # Agent调用
│   ├── skill_calls.jsonl   # Skill使用
│   ├── failures.jsonl      # 失败记录
│   ├── error.jsonl         # 错误日志
│   ├── proposal_history.json # 提案历史
│   ├── analysis_state.json  # 分析状态
│   └── backups/            # 文件备份
└── proposals/              # 提案文件

hooks/bin/
├── collect-session.py       # 会话采集
├── collect-agent.py         # Agent采集
├── collect-skill.py         # Skill采集
├── collect-failure.py       # 失败采集
├── collect_error.py         # 错误采集
└── extract_semantics.py     # 语义提取
```

---

## 附录 B: 配置参考

```yaml
# evolve-daemon/config.yaml

thresholds:
  min_new_sessions: 5
  min_same_pattern_corrections: 3
  max_hours_since_last_analyze: 6
  min_failure_count: 5
  min_failure_type_count: 3

decision:
  enabled: true
  auto_apply_threshold: 0.8
  high_risk_threshold: 0.5
  require_human_review:
    - security
    - permission
    - new_target
    - multi_file

observation:
  days: 7
  check_interval_hours: 24
  metrics:
    min_success_rate: 0.8
    max_correction_rate: 0.2
    max_failure_rate_delta: 0.1

safety:
  max_proposals_per_day: 3
  auto_close_days: 7
  breaker:
    max_consecutive_rejects: 3
    max_rollbacks_per_week: 5
    pause_days: 30

decay:
  half_life_days: 90
  decay_floor: 0.1
  max_confidence: 0.95
  reinforcement_bonus: 0.05
```

---

## 附录 C: 参考资料

| 来源 | 借鉴点 |
|------|--------|
| Claude Code KAIROS | 后台 daemon + 定时触发 |
| Claude Code autoDream | 记忆合并/衰减机制 |
| heartbeat (uameer) | observe → decide → act → sleep |
| AutoDream (JaWaMi73) | 双层安全（guardian + breaker） |

---

**文档版本**: v2.0
**最后更新**: 2026-05-02

---

## 附录 D: 实现确认清单 ✅

> 以下条目逐项确认，全部完成于 2026-05-02。

### D.1 核心模块

| 模块 | 文件 | 状态 |
|------|------|------|
| extract_semantics.py | `evolve-daemon/extract_semantics.py` | ✅ 232行 |
| evolve_dispatcher.py | `evolve-daemon/evolve_dispatcher.py` | ✅ 258行 |
| agent_evolution.py | `evolve-daemon/agent_evolution.py` | ✅ 50行 |
| skill_evolution.py | `evolve-daemon/skill_evolution.py` | ✅ 40行 |
| rule_evolution.py | `evolve-daemon/rule_evolution.py` | ✅ 40行 |
| instinct_updater.py (增强) | `evolve-daemon/instinct_updater.py` | ✅ +link_instinct_to_target, find_instinct_by_target |
| daemon.py (重写) | `evolve-daemon/daemon.py` | ✅ 4步闭环 |
| scheduler.py | `evolve-daemon/scheduler.py` | ✅ APScheduler调度 |
| rollback.py (增强) | `evolve-daemon/rollback.py` | ✅ +_promote_instinct_on_observation |
| apply_change.py (增强) | `evolve-daemon/apply_change.py` | ✅ +dimension, linked_instinct_id |

### D.2 维度分发验证

```
输入: correction_hotspots = {
    "agent:backend-dev": 5,
    "skill:testing": 3,
    "tool:Bash": 3,
}
↓ dispatch_evolution()
↓ 输出 3 个 decisions:
  [agent] agent:backend-dev → auto_apply (risk=low)
  [skill] skill:testing → propose (risk=medium)
  [instinct] tool:Bash → auto_apply (risk=low)
```

### D.3 测试覆盖

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| `tests/evolve-daemon/test_evolve_dispatcher.py` | 19 | ✅ 全部通过 |
| `tests/evolve-daemon/test_daemon.py` | 5 | ✅ 全部通过 |
| `tests/evolve-daemon/test_scheduler.py` | 9 | ✅ 全部通过 |
| **合计** | **33** | ✅ |

### D.4 4维度分发规则

| target 前缀 | 维度 | 阈值 | action 策略 |
|-------------|------|------|-------------|
| `agent:` | agent | ≥3次 | 低风险→auto_apply，其他→propose |
| `skill:` | skill | ≥3次 | 始终 propose |
| `rule:` | rule | ≥5次 | 始终 propose |
| `tool:` | instinct | ≥2次 | 始终 auto_apply |
| 其他 | instinct | ≥2次 | 始终 auto_apply |

### D.5 闭环流程

```
daemon.py run_analysis()
    ↓
extract_semantics.py (每个新会话 → Haiku语义提取 → 回填 corrections[])
    ↓
analyzer.py aggregate_and_analyze()
    ↓
evolve_dispatcher.py dispatch_evolution()  ← 4维度分发
    ↓
各维度进化:
  agent → agent_evolution.evolve_agent() → auto_apply/propose
  skill → skill_evolution.evolve_skill() → propose
  rule  → rule_evolution.evolve_rule()  → propose
  instinct → instinct_updater.link_instinct_to_target()
    ↓
proposer.py / apply_change.py
    ↓
rollback.py 观察期通过 → _promote_instinct_on_observation()
```

### D.6 已知限制

- `llm_decision.py` 尚未调用 `dispatch_evolution()`（计划阶段4，原设计过高估计了优先级）
- 实际数据端到端测试未执行（无 sessions.jsonl 真实数据）
- `tool:` 前缀映射到 `instinct` 而非 `tool` 维度（符合设计意图，工具失败走本能管理）
**维护者**: Architect Agent
