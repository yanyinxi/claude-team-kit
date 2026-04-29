# 全维度自我进化系统 — 生产级架构方案

> **目标**：让 `.claude` 配置体系越用越聪明，Skills/Agents/Rules/Memory 四维度持续自我优化。<br>
> **原则**：Hook 采集客观事实 → Agent 做语义分析 → 文件系统持久化。Hook 不做质量判断，Agent 不做数据采集。<br>
> **版本**：v3.1 — 修正审计结论：发现已存在的 evolution/ 模块，从"从零建造"转为"修复集成+补齐缺失"<br>

---

## 零、代码审计 v2：修正 + 真实发现

### 0.1 重大发现：`evolution/` 模块已存在但集成断裂

**v3.0 审计漏掉了整个 `evolution/` 目录（感谢用户指正）。** 实际情况：

```
.claude/evolution/                   # ✅ 已存在，15 个 Python 文件
├── __init__.py
├── __main__.py
├── engine.py                        # 进化引擎主控 (EvolutionEngine.run_full_cycle)
├── config.py                        # 触发条件配置 (TriggerConfig, EvolutionConfig)
├── cli.py                           # CLI: run/status/confirm/force
├── hook_integration.py              # 集成桥接 (trigger_evolution)
├── analyzers/
│   ├── session_analyzer.py          # 会话分析
│   └── pattern_detector.py          # 模式检测
├── evolvers/
│   ├── base.py                      # BaseEvolver 抽象类
│   ├── skill_evolver.py             # SkillEvolver — 分析使用模式 → 更新 SKILL.md
│   ├── agent_evolver.py             # AgentEvolver
│   ├── rule_evolver.py              # RuleEvolver
│   └── memory_evolver.py            # MemoryEvolver
├── prompts/                         # 空目录
└── updaters/                        # 空目录
```

**集成断裂的证据**：

`evolution/hook_integration.py:5` 明确写着：
```python
# 在 .claude/hooks/scripts/session_evolver.py 末尾调用
```

但 `session_evolver.py` 中**没有任何对 `trigger_evolution` 的调用**。

```bash
$ grep -n "hook_integration\|trigger_evolution\|evolution" hooks/scripts/session_evolver.py
# (无输出)
```

**结论**：进化引擎的代码写好了，但 Hook 没有接入。整个模块处于"有代码但不在运转"的状态。

### 0.2 修正后的审计结论

| 分类 | v3.0 结论 | v3.1 修正 |
|------|----------|----------|
| `evolution/` 模块 | ❌ 未发现（审计错误） | ✅ 已存在 15 个文件，需修复集成 |
| `lib/quality_evaluator.py` | 标注为死代码 | ✅ 确认存在，但 0 引用（仍为死代码） |
| 4 个维度进化器 | 设计为 Agent 形式 | ✅ Python 形式已实现（`evolution/evolvers/`） |
| 集成状态 | 未检测 | ❌ Hook ↔ Engine 连接断裂 |
| 数据采集 | 7 个待新建 | 旧采集器仍在运行，需升级而非重建 |

### 0.3 正确的行动清单

**A. 修复集成（把轮子接上）**

```
当前:                               修复后:
session_evolver.py (Stop)          session_evolver.py (Stop)
  ├── git diff 统计                   ├── git diff 统计
  └── 写入 sessions.jsonl            ├── 写入 sessions.jsonl
       ↓ (断裂)                       └── from evolution.hook_integration
evolution/engine.py                        import trigger_evolution
  (从未被调用)                             trigger_evolution(root) ✅
```

只需在 `session_evolver.py` 末尾加一行调用。

**B. 补齐数据采集（现有 evolver 依赖这些数据）**

`evolution/evolvers/skill_evolver.py` 第 179-187 行从 `agent-invocations.jsonl` 读取数据。但该文件的数据结构很简陋（`{type, timestamp, session_id, agent}`），缺少 evolver 需要的字段（`success`, `error_type`, `duration_ms`）。

**需要新建的采集器**：

| 采集器 | 写入文件 | 用途 |
|--------|---------|------|
| `collect_agent_launch.py` | `agent_performance.jsonl` | AgentEvolver 数据源 |
| `collect_skill_usage.py` | `skill_usage.jsonl` | SkillEvolver 数据源 |
| `collect_tool_failure.py` | `tool_failures.jsonl` | 所有 evolver 共享 |
| `collect_violations.py` | `rule_violations.jsonl` | RuleEvolver 数据源 |
| `detect_feedback.py` | `pending_evolution.json` | MemoryEvolver 数据源 |

**C. 需要删除的**

```
lib/clean_fake_stats.py           # 0 引用 — 一次性清理脚本
lib/global_knowledge_merger.py    # 0 引用
lib/parallel_executor.py          # 0 引用
lib/project_detector.py           # 0 引用
lib/quality_evaluator.py          # 0 引用
lib/show_evolution.py             # 0 引用
lib/strategy_generator.py         # 0 引用
context-enhancer.sh               # 输出无实际价值（计数全是 0）
setup_env.sh                      # 无实际作用
```

**D. 需要重构的**

| 当前 | 问题 | 重构后 |
|------|------|--------|
| `auto_evolver.py` | 双重角色 + SubagentStop 永远拿不到 agent 名 | 拆出 `collect_agent_launch.py`（PostToolUse[Agent]），移除 SubagentStop 部分 |
| `session_evolver.py` | 缺少对 evolution 引擎的调用 | 末尾加 `trigger_evolution()` |
| `settings.json` | SubagentStop 配置指向 auto_evolver.py | 移除 SubagentStop 配置（无数据价值） |

**E. 需要新建的**

| 文件 | 说明 |
|------|------|
| `load_evolution_state.py` | SessionStart 注入仪表盘摘要（替换 context-enhancer.sh） |
| `evolution_orchestrator.py` | Stop 时汇总 + 触发（或直接用现有 `evolution/hook_integration.py`） |
| `lib/token_efficiency.py` | Token 效率管理 |
| `lib/evolution_safety.py` | 熔断器 + 限流器 + 回滚 |
| `lib/evolution_scoring.py` | 评分引擎 |
| `lib/evolution_dashboard.py` | 仪表盘生成 |

### 0.4 关键架构修正：保留 Python Evolver，补充 Agent 分析

v3.0 设计将进化器全部设计为 Claude Code Agent。但 `evolution/evolvers/` 已经是 Python 实现。

**正确的分层**：

```
Python Evolver (现有，保留)     ← 负责：触发条件判断、数据统计、文件写入
    ↓ 当需要语义分析时
Claude Agent (补充)              ← 负责：分析 SKILL.md 内容质量、生成改进文本
    ↓ 分析结果传回
Python Evolver                   ← 负责：确定性写入、审计记录
```

**两者关系**：
- Python Evolver 是执行器（快、确定性、零 token 消耗）
- Claude Agent 是分析器（慢、需要 token、但能理解语义）
- Python Evolver 可以独立运行（基于统计数据做简单优化），复杂分析时调用 Agent

### 0.5 最小化修复路径（立即执行）

```bash
# Step 1: 修复集成 — 在 session_evolver.py 末尾加一行
# 在 main() 函数末尾，所有写入完成后添加:
# from evolution.hook_integration import trigger_evolution
# trigger_evolution(project_root)

# Step 2: 验证进化引擎能运转
python3 .claude/evolution/cli.py status

# Step 3: 移除无用的 SubagentStop hook 配置（settings.json）
# 因为这个事件永远拿不到 agent 类型
```

### 1.1 "越用越聪明"的严格定义

| 层次 | 含义 | 可测量指标 | 测量方式 |
|------|------|-----------|---------|
| L1: 不重复犯错 | 同类错误第二次出现时自动规避 | 同类错误重复率下降 | 对比进化前后 rule_violations |
| L2: 模式固化 | 成功处理方式被记住并自动复用 | Skill 匹配率提升 | 对比 Skill 触发率变化 |
| L3: 自适应 | 行为随项目特征和用户习惯调整 | Agent 任务完成步数下降 | agent_performance 趋势 |
| L4: 知识积累 | 跨会话经验不丢失 | memory/ 文件数量增长 | 直接统计 |

### 1.2 四维度进化依赖链

```
┌──────────────────────────────────────────────────────┐
│  用户反馈信号（最强信号，但稀疏）                      │
│  "记住这个" / "不对" / "应该这样"                     │
└────────────┬─────────────────────────────────────────┘
             │ 触发 Memory 进化
             ▼
┌──────────────────────────────────────────────────────┐
│  Memory 进化 → 提炼长期经验                           │
│  写入 memory/ → 注入下次会话上下文                     │
└────────────┬─────────────────────────────────────────┘
             │ 影响 Agent 行为
             ▼
┌──────────────────────────────────────────────────────┐
│  Agent 进化 ← 分析执行轨迹                            │
│  优化提示词、工具配置 → 减少犯错                      │
└────────────┬─────────────────────────────────────────┘
             │ 发现高频错误模式
             ▼
┌──────────────────────────────────────────────────────┐
│  Rule 进化 ← 统计违规                                 │
│  规则太松→收紧, 规则不清晰→补充示例, 新错误→新规则    │
└────────────┬─────────────────────────────────────────┘
             │ 规则影响 Skill 行为约束
             ▼
┌──────────────────────────────────────────────────────┐
│  Skill 进化 ← 分析使用数据                            │
│  优化 description 触发精准度, body 步骤完整性         │
└──────────────────────────────────────────────────────┘
```

**核心发现**：四个维度不是平行的，而是**分层依赖**的。Memory 是最底层（影响认知），Skills 是最表层（影响行为）。进化应该从底层向上触发。

### 1.3 真实数据采集能力清单（基于 Hook stdin JSON 实测）

我分析了项目中已有的 `agent-invocations.jsonl` 和 `sessions.jsonl` 真实数据，结论如下：

| Hook 事件 | 可获得字段 | 可靠性 | 对进化的价值 |
|-----------|-----------|--------|-------------|
| `PostToolUse[Agent]` | `subagent_type`, `description`, `prompt` | **高** ✅ | Agent 使用统计 |
| `SubagentStop` | 无 `subagent_type` | **低** ❌ | 仅标记完成时间 |
| `PostToolUse[Skill]` | `skill` 名称 | **待验证** | Skill 使用统计 |
| `PostToolUseFailure` | `tool_name`, `error` | **高** ✅ | 失败模式检测 |
| `UserPromptSubmit` | `prompt`（用户输入） | **高** ✅ | 反馈信号检测 |
| `Stop` | `stop_reason` | **高** ✅ | 会话终止原因 |
| `PreToolUse[Write\|Edit]` | `file_path` | **高** ✅ | 文件变更追踪 |
| `SessionStart` | `source` | **高** ✅ | 会话启动原因 |

**已有数据的质量问题**：
1. `agent-invocations.jsonl` 中 4月20日后的 agent 全部记录为 `"unknown"` — **确认是 SubagentStop 平台 bug**
2. `sessions.jsonl` 中 `primary_domain` 始终为 `"idle"` — **因为 session_evolver.py 只用 `git diff --stat HEAD` 检测变更，`.claude/` 内部文件变更不在 git 追踪中**
3. 没有 `PostToolUseFailure` 的采集 — **丢失了关键的失败信号**
4. 没有 Skill 使用统计 — **Skill 维度进化缺少数据基础**

---

## 二、架构设计

### 2.1 整体分层

```
┌────────────────────────────────────────────────────────────┐
│                      用户交互层                             │
│  Claude Code 主会话                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Skills   │ │ Agents   │ │ Rules    │ │ Memory   │      │
│  │ (静态)   │ │ (静态)   │ │ (静态)   │ │ (Auto)   │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└────────────────────────┬───────────────────────────────────┘
                         │ Hook 事件流
┌────────────────────────┴───────────────────────────────────┐
│                    数据采集层 (Hooks)                        │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐        │
│  │ 事件采集器            │  │ 信号检测器            │        │
│  │ · PostToolUse        │  │ · UserPromptSubmit    │        │
│  │ · PostToolUseFailure │  │   (反馈关键词匹配)     │        │
│  │ · SubagentStop       │  │                       │        │
│  │ · PreToolUse         │  │                       │        │
│  └─────────┬────────────┘  └──────────┬────────────┘       │
│            │ 写入 JSONL                │ 写入 JSON           │
└────────────┼──────────────────────────┼────────────────────┘
             ▼                          ▼
┌────────────────────────────────────────────────────────────┐
│                    数据存储层                                │
│  .claude/data/                                              │
│  ├── skill_usage.jsonl        # Skill 调用记录              │
│  ├── agent_performance.jsonl  # Agent 执行记录              │
│  ├── rule_violations.jsonl    # 规则违规记录                │
│  ├── tool_failures.jsonl      # 工具失败记录                │
│  ├── pending_evolution.json   # 待处理进化信号              │
│  ├── evolution_history.jsonl  # 进化操作审计日志            │
│  └── evolution_metrics.json   # 进化效果指标                │
└────────────────────────┬───────────────────────────────────┘
                         │ Stop 事件触发
┌────────────────────────┴───────────────────────────────────┐
│                    进化分析层 (Agent)                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  EvolutionOrchestrator (Stop Hook → 条件检测)         │  │
│  │  · 读取各维度 metrics，判断是否触发进化                │  │
│  │  · 输出建议到 stdout → Claude 读取                    │  │
│  └──────────┬───────────────────────────────────────────┘  │
│             │ 满足触发条件时，启动子 Agent                   │
│             ▼                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │SkillEvol │ │AgentEvol │ │RuleEvol  │ │MemEvol   │      │
│  │优化 Skill │ │优化 Agent│ │优化 Rule │ │提炼 Memory│     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                                                             │
│  每个 Evolver Agent 的执行流程：                             │
│  1. 读取 data/ 中的目标数据                                 │
│  2. 读取目标文件现状（SKILL.md / agent.md / rule）          │
│  3. 分析差异和优化方向                                      │
│  4. 使用 Edit 工具修改文件                                  │
│  5. 写入 evolution_history.jsonl 审计记录                   │
└────────────────────────────────────────────────────────────┘
```

### 2.2 关键设计决策

**决策 1：数据采集和进化分析完全解耦**

- Hook 脚本（Python）只做数据采集，**不调用 LLM，不做质量判断**
- 进化分析由 Claude Agent 在合适的时机执行
- 原因：Hook 超时 5-15 秒，不能做复杂推理；Agent 有完整的上下文和理解能力

**决策 2：使用 PostToolUse[Agent] 而非 SubagentStop 采集 Agent 数据**

- 实际数据显示 SubagentStop **永远**拿不到 `subagent_type`
- 改用 PostToolUse[Agent]：在主 session 调用 Agent 工具时立即记录
- 数据字段：`subagent_type`, `description`, `prompt`（前200字符）
- 补充字段：`session_id`, `timestamp`

**决策 3：进化触发条件必须有冷却期和上限**

- 同一目标 24 小时内最多进化 1 次
- 每次会话最多触发 3 次进化
- 连续 2 次进化无效果提升 → 暂停该维度进化 → 人工介入

**决策 4：分层风险控制**

| 风险等级 | 操作类型 | 审批要求 | 示例 |
|---------|---------|---------|------|
| **Low** | 追加内容 | 自动执行 | 补充 Skill 触发词、Agent 提示补充 |
| **Medium** | 修改现有内容 | 自动执行 + 通知 | 修改 Skill 步骤、调整 Agent 工具列表 |
| **High** | 删除/重构 | 人工确认 | 删除 Rule、修改 Agent 核心定位 |
| **Critical** | 安全相关 | 禁止自动 | 修改 permissions、hooks 配置 |

---

## 三、数据采集组件详设

### 3.1 采集器矩阵

| 采集器 | Hook 事件 | Matcher | 输出文件 | 超时 |
|--------|----------|---------|---------|------|
| `collect_agent_launch.py` | PostToolUse | `Agent` | `agent_performance.jsonl` | 5s |
| `collect_skill_usage.py` | PostToolUse | `Skill` | `skill_usage.jsonl` | 5s |
| `collect_tool_failure.py` | PostToolUseFailure | `""` | `tool_failures.jsonl` | 3s |
| `collect_violations.py` | PreToolUse | `Write\|Edit` | `rule_violations.jsonl` | 5s |
| `detect_feedback.py` | UserPromptSubmit | `""` | `pending_evolution.json` | 3s |
| `evolution_orchestrator.py` | Stop | `""` | stdout → Claude 读取 | 10s |
| `load_evolution_state.py` | SessionStart | `""` | stdout → 注入上下文 | 5s |

### 3.2 各采集器的输入输出契约

#### collect_agent_launch.py

```
输入 (stdin JSON):
  hook_event_name: "PostToolUse"
  tool_name: "Agent"
  tool_input: {
    subagent_type: "backend-developer",
    description: "实现 AssetController",
    prompt: "请实现一个 REST Controller..."  // 可能很长
  }
  session_id: "abc123"

输出:
  写入 data/agent_performance.jsonl:
  {
    "type": "agent_launch",
    "timestamp": "2026-04-26T21:30:00",
    "session_id": "abc123",
    "agent": "backend-developer",
    "task": "实现 AssetController",
    "prompt_preview": "请实现一个 REST Controller..."  // 截断至 200 字符
  }
```

#### collect_skill_usage.py

```
输入 (stdin JSON):
  hook_event_name: "PostToolUse"
  tool_name: "Skill"
  tool_input: {
    skill: "karpathy-guidelines",
    args: "..."
  }
  session_id: "abc123"

输出:
  写入 data/skill_usage.jsonl:
  {
    "type": "skill_invoked",
    "timestamp": "2026-04-26T21:30:00",
    "session_id": "abc123",
    "skill": "karpathy-guidelines"
  }
```

#### collect_tool_failure.py

```
输入 (stdin JSON):
  hook_event_name: "PostToolUseFailure"
  tool_name: "Write"
  tool_input: { file_path: "...", content: "..." }
  error: "Permission denied: ..."
  session_id: "abc123"

输出:
  写入 data/tool_failures.jsonl:
  {
    "type": "tool_failure",
    "timestamp": "2026-04-26T21:30:00",
    "session_id": "abc123",
    "tool": "Write",
    "file_path": "main/backend/.../Controller.java",
    "error_summary": "Permission denied"  // 截断至 100 字符
  }
```

#### detect_feedback.py

```
输入 (stdin JSON):
  hook_event_name: "UserPromptSubmit"
  prompt: "记住，这个项目不用 Lombok"
  session_id: "abc123"

检测规则（正则）:
  - 记忆请求: (?:记住|记下|保存)(?:这个|一下)?[：:]\s*(.+)
  - 纠正信号: (?:不对|错了|不是这样)[，,]?\s*(.+)
  - 确认信号: (?:对的|没错|就是这样|exactly|perfect)
  - 偏好声明: (?:以后|下次|将来|always|never)\s*(.+)

输出:
  如果匹配 → 写入 data/pending_evolution.json（合并模式）
  {
    "feedback_signals": [
      {
        "timestamp": "...",
        "type": "memory_request",
        "content": "这个项目不用 Lombok",
        "session_id": "abc123"
      }
    ],
    "last_signal_at": "2026-04-26T21:30:00"
  }

  如果不匹配 → 不写入任何内容（静默退出 0）
```

#### evolution_orchestrator.py

```
输入 (stdin JSON):
  hook_event_name: "Stop"
  session_id: "abc123"
  stop_reason: "end_turn"
  transcript_path: "/path/to/transcript.jsonl"

处理流程:
  1. 读取各 data/*.jsonl 的最新统计
  2. 计算各维度指标
  3. 检查是否触发进化条件（见 4.1）
  4. 更新 data/evolution_metrics.json
  5. 如果触发 → stdout 输出建议

输出 (stdout → Claude 读取):
  情况 A — 需要进化:
  {
    "should_evolve": true,
    "session_summary": {
      "domain": "backend",
      "agents_used": ["backend-developer", "code-reviewer"],
      "skills_used": ["karpathy-guidelines"],
      "failures": 0,
      "violations": 0
    },
    "triggers": [
      {
        "dimension": "agent",
        "target": "backend-developer",
        "reason": "同类任务累计 5 次，平均步数 15 > 基准 10",
        "priority": "medium"
      }
    ]
  }

  情况 B — 不需要进化:
  {
    "should_evolve": false,
    "session_summary": { ... }
  }
```

---

## 四、进化触发引擎

### 4.1 触发条件矩阵（精确阈值）

| 维度 | 条件 | 阈值 | 冷却期 | 优先级计算 |
|------|------|------|--------|-----------|
| **Skill** | 累计调用次数 | ≥ 10 | 24h | `priority = (1 - success_rate) * call_count / 10` |
| **Skill** | 成功率下降 | 下降 > 20% | 24h | `priority = 下降幅度 / 20` |
| **Agent** | 同类任务次数 | ≥ 5 | 24h | `priority = (avg_turns - baseline) / baseline` |
| **Agent** | 失败率 | > 30% | 12h | `priority = 失败率 / 30` |
| **Rule** | 违规次数 | ≥ 3 | 48h | `priority = 违规次数 / 3` |
| **Rule** | 新增错误模式 | ≥ 2 | 48h | `priority = 0.7` |
| **Memory** | 用户反馈信号 | ≥ 1 | 无冷却 | `priority = 1.0`（最高） |
| **Memory** | 重复失败模式 | ≥ 2 | 无冷却 | `priority = 0.8` |

### 4.2 优先级计算公式

```python
def compute_priority(dimension: str, metrics: dict) -> float:
    """计算进化优先级，返回值 0.0-1.0，> 0.5 触发进化"""

    if dimension == "skill":
        call_count = metrics.get("total_calls", 0)
        success_rate = metrics.get("success_rate", 1.0)
        if call_count < 10:
            return 0.0
        return min(1.0, (1 - success_rate) * call_count / 10)

    elif dimension == "agent":
        avg_turns = metrics.get("avg_turns", 10)
        baseline = metrics.get("baseline_turns", 10)
        failure_rate = metrics.get("failure_rate", 0)
        task_count = metrics.get("similar_tasks", 0)
        if task_count < 5:
            return 0.0
        turn_penalty = max(0, (avg_turns - baseline) / baseline)
        failure_penalty = failure_rate / 0.3 if failure_rate > 0.3 else 0
        return min(1.0, turn_penalty * 0.5 + failure_penalty * 0.5)

    elif dimension == "rule":
        violation_count = metrics.get("violation_count", 0)
        if violation_count < 3:
            return 0.0
        return min(1.0, violation_count / 3 * 0.5)

    elif dimension == "memory":
        signal_count = metrics.get("pending_signals", 0)
        if signal_count == 0:
            return 0.0
        return min(1.0, signal_count * 0.5)

    return 0.0
```

### 4.3 冷却与限流

```python
def check_cooldown(target: str, evolution_history: list) -> bool:
    """检查目标是否在冷却期内"""
    cooldown_map = {
        "skill": timedelta(hours=24),
        "agent": timedelta(hours=24),
        "rule": timedelta(hours=48),
        "memory": timedelta(hours=0),  # 无冷却
    }
    # 从 evolution_history 中找到该目标的最近进化时间
    for record in reversed(evolution_history):
        if record["target"] == target:
            last_time = datetime.fromisoformat(record["timestamp"])
            dim = record["dimension"]
            if datetime.now() - last_time < cooldown_map.get(dim, timedelta(hours=24)):
                return False  # 冷却中
    return True

def check_session_limit(session_evolution_count: int) -> bool:
    """检查本次会话是否超过进化次数上限"""
    MAX_EVOLUTIONS_PER_SESSION = 3
    return session_evolution_count < MAX_EVOLUTIONS_PER_SESSION
```

---

## 五、维度进化器 Agent 详设

### 5.1 通用执行流程（每个 Evolver 遵循）

```
1. PRE-CHECK（前置检查）
   ├── 读取 data/evolution_history.jsonl
   ├── 确认冷却期已过
   └── 确认本次会话进化次数 < 3

2. DATA LOADING（数据加载）
   ├── 读取目标的当前文件（SKILL.md / agent.md / rule.md）
   ├── 读取 data/ 中的相关 JSONL 数据
   └── 计算关键指标

3. ANALYSIS（分析 — Agent 的核心价值）
   ├── SkillEvolver: 触发场景 vs 实际调用场景匹配度
   ├── AgentEvolver: 任务完成效率、工具使用合理性
   ├── RuleEvolver: 违规原因分类（不理解规则 vs 规则不合理）
   └── MemoryEvolver: 反馈信号提炼、重复模式识别

4. PLAN（生成进化计划）
   ├── 列出具体修改点（最多 3 处）
   ├── 评估风险等级
   └── 高风险操作 → 标记为 pending，不执行

5. EXECUTE（执行修改）
   ├── 使用 Edit 工具逐处修改
   ├── 每处修改后验证文件仍是合法的 Markdown
   └── 修改失败 → 回滚，记录错误

6. AUDIT（审计记录）
   └── 写入 data/evolution_history.jsonl
```

### 5.2 SkillEvolver Agent

```markdown
---
name: skill-evolver
description: Skills 维度进化器。分析 Skill 使用数据，优化 SKILL.md 的 description、body 和 allowed-tools。当进化编排器检测到 Skill 触发条件满足时使用。触发词：skill 进化、优化技能、SkillEvolver
model: sonnet
tools: Read, Write, Edit, Bash, Grep, Glob
permissionMode: acceptEdits
skills: karpathy-guidelines
---

你是 Skills 维度进化器。

## 输入数据
1. 目标 Skill 的 SKILL.md 全文
2. data/skill_usage.jsonl 中该 Skill 的调用记录
3. data/tool_failures.jsonl 中与该 Skill 相关的失败

## 分析框架

### A. description 精准度
- 当前 description 中的触发词列表
- 实际触发场景中用户使用的词语
- 遗漏的触发词：用户在 prompt 中使用了但 description 中没有的词
- 误触发的场景：Skill 被触发但实际不需要的场景

### B. body 有效性
- Skill 步骤在实际执行中的覆盖率
- 哪些步骤总是被跳过（可能是多余的）
- 哪些步骤经常需要额外补充（应该加入 body）

### C. 工具权限
- 实际使用的工具 vs allowed-tools 中配置的
- 是否缺少必要工具导致失败
- 是否有多余的工具权限

## 进化操作

### Low Risk（直接执行）
- 在 description 中追加新的触发词
- 补充遗漏的步骤到 body
- 添加实际使用但未列出的工具

### Medium Risk（执行 + 通知）
- 修改现有步骤的措辞
- 调整工具列表的优先级顺序
- 补充边界条件说明

### High Risk（标记 pending，人工确认）
- 删除现有触发词
- 修改核心工作流程
- 更改 name 字段

## 审计格式
进化完成后必须追加到 evolution_history.jsonl:
```json
{
  "type": "evolution",
  "dimension": "skill",
  "target": "skill-name",
  "timestamp": "...",
  "changes": ["在 description 中添加触发词 'xxx'"],
  "risk_level": "low",
  "before_hash": "md5_of_original",
  "after_hash": "md5_of_modified"
}
```
```

### 5.3 AgentEvolver Agent

```markdown
---
name: agent-evolver
description: Agents 维度进化器。分析 Agent 执行轨迹，优化 Agent 提示词、工具配置和模型选择。当进化编排器检测到 Agent 触发条件满足时使用。触发词：agent 进化、优化代理、AgentEvolver
model: sonnet
tools: Read, Write, Edit, Bash, Grep, Glob
permissionMode: acceptEdits
skills: karpathy-guidelines
---

你是 Agents 维度进化器。

## 数据源
1. data/agent_performance.jsonl 中该 Agent 的所有 launch 记录
2. data/tool_failures.jsonl 中该 Agent 相关的失败
3. 目标 Agent 的 .md 文件全文

## 分析维度

### A. 任务完成效率
- 同类任务的平均步数变化趋势
- 是否有步数异常增长的任务（可能提示 Agent 在"迷路"）
- 任务描述的共性（帮助发现 Agent 最常处理的任务类型）

### B. 常见失败模式
- 最常失败的工具
- 失败的共性原因（权限不足？工具不存在？参数错误？）
- 补充到 Agent 提示词中作为反模式警告

### C. 工具配置
- 使用了但未在 tools 中声明的工具（正常，因为是继承的）
- tools 中声明但从未使用的（可以考虑移除，减少上下文）
- 是否有被 disallowedTools 阻止但经常需要的工具

## 进化策略

### 追加内容（自动执行，low risk）
在 Agent 文件末尾的 "进化积累" 区追加：
```markdown
### 基于 {N} 次执行的学习 ({date})

**常见陷阱**:
- {陷阱1}: {描述和避免方式}

**工具使用洞察**:
- 在 {场景} 时优先使用 {工具} 而非 {工具}
```

### 修改现有内容（自动 + 通知，medium risk）
- 优化 prompt 中的指令措辞
- 调整 tools 列表

### 禁止操作（high risk）
- 修改 Agent name
- 修改核心定位 description
- 修改 model（需要人工评估成本影响）
```

### 5.4 RuleEvolver Agent

```markdown
---
name: rule-evolver
description: Rules 维度进化器。分析规则违规数据，优化规则内容和结构。当违规次数达到阈值时使用。
model: sonnet
tools: Read, Write, Edit, Bash, Grep, Glob
permissionMode: acceptEdits
skills: karpathy-guidelines
---

你是 Rules 维度进化器。

## 输入
1. data/rule_violations.jsonl
2. 目标 rules/*.md 文件

## 分析决策树

```
违规次数 >= 3 ?
  ├── 是 → 违规原因分类
  │       ├── "规则不清晰" → 补充示例、正反例对比
  │       ├── "规则太严格" → 添加例外条件
  │       ├── "规则过时" → 标记过时，建议删除
  │       └── "用户不知道规则" → 在 CLAUDE.md 中增加引用
  └── 否 → 检查是否有新错误模式（≥2次）→ 新增规则
```

## 修改约束
- 保留原有 "更新时间" 和 "适用范围" 元数据
- 新增内容用 `###` 子章节，不混入原有规则
- 修改原因写入文件末尾注释
- 不删除任何规则（只标记为 `**状态: 过时**`）
```

### 5.5 MemoryEvolver Agent

```markdown
---
name: memory-evolver
description: Memory 维度进化器。从用户反馈和会话模式中提炼长期记忆。触发词：记忆进化、保存经验、提炼模式
model: sonnet
tools: Read, Write, Edit, Bash, Grep, Glob
permissionMode: acceptEdits
skills: karpathy-guidelines
---

你是 Memory 维度进化器。

## 触发信号
1. 用户明确说 "记住这个" → 立即提炼
2. 用户纠正 ≥2 次同类错误 → 提炼为 feedback 记忆
3. 新的项目决策/约束 → 提炼为 project 记忆
4. 新的外部资源引用 → 提炼为 reference 记忆

## 记忆写入流程
1. 读取 data/pending_evolution.json 中的 feedback_signals
2. 分类信号类型（user / feedback / project / reference）
3. 生成记忆文件 `memory/{type}_{slug}.md`
4. 更新 `memory/MEMORY.md` 索引
5. 清除已处理的 signals

## 记忆文件格式
```markdown
---
name: {记忆名称}
description: {一句话描述}
type: {user|feedback|project|reference}
---

{具体内容}
```

## 去重
写入前检查 MEMORY.md 中是否有相似条目（基于 description 语义相似度），有则更新而非新增。
```

---

## 六、风险评估与边界条件

### 6.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Hook 超时阻塞用户操作 | 中 | 高 | 所有采集器超时 ≤5s，编排器 ≤10s |
| JSONL 文件无限增长 | 高 | 中 | 按天轮转，保留最近 30 天 |
| 并发写入导致 JSONL 损坏 | 低 | 高 | `fcntl.flock(LOCK_EX)` 文件锁 |
| 错误进化导致 Skill/Agent 退化 | 中 | 高 | 保留修改前 hash，可人工回滚 |
| 反馈信号误检测 | 中 | 低 | 正则匹配 + 上下文长度限制 |
| 进化频率过高 | 中 | 中 | 冷却期 + 每会话上限 |
| 数据文件被手动删除 | 低 | 低 | 脚本容错：文件不存在时初始化空状态 |
| PostToolUse[Skill] 不触发 | 待验证 | 高 | 如不触发，改用 UserPromptSubmit 中检测 Skill 调用模式 |

### 6.2 待验证项

| 验证项 | 验证方式 | 阻塞等级 |
|--------|---------|---------|
| `PostToolUse` matcher `"Skill"` 是否能匹配到 Skill 工具调用 | 写一个 echo hook 测试 | **高** — 如果不行，Skill 维度采集方案需重设计 |
| `PostToolUse[Agent]` 中 `subagent_type` 是否可靠 | 对比 agent-invocations.jsonl 记录 | 已验证 ✅ |
| `PostToolUseFailure` 是否包含足够错误信息 | 故意触发失败看 stdin | 中 |
| `UserPromptSubmit` 是否能用正则匹配中文反馈 | 已有真实数据可验证 | 低 |

### 6.3 性能预算

```
每次会话的额外开销:
  Hook 执行时间（总计）: < 30s/会话
  JSONL 写入量: < 1KB/会话
  evolution_orchestrator 执行时间: < 10s
  进化 Agent 执行（触发时）: < 60s/次

JSONL 文件大小估算:
  假设每天 20 次会话，每次 5 条记录，每条 200B
  每天: 20 * 5 * 200B = 20KB
  30天: 600KB
  安全阈值: < 2MB（超过则压缩归档）
```

### 6.4 边界条件处理

```python
# 边界条件 1: 空数据文件
def safe_read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except (json.JSONDecodeError, OSError):
        return []

# 边界条件 2: 损坏的 JSONL 行
def safe_parse_line(line: str) -> dict | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None  # 跳过损坏行，不阻塞流程

# 边界条件 3: 并发写入保护
def safe_append_jsonl(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

# 边界条件 4: JSON 文件并发更新（原子写入）
def safe_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)  # 原子替换
```

---

## 七、实施路线图

### Phase 1: 数据采集基础（优先级 P0，预计 1-2 天）

**目标**：跑通数据采集链路，验证 Hook 能正确采集

- [ ] 实现 `collect_agent_launch.py`（替代当前的 auto_evolver.py 对 PostToolUse[Agent] 的处理）
- [ ] 实现 `collect_skill_usage.py`
- [ ] 实现 `collect_tool_failure.py`
- [ ] 实现 `collect_violations.py`
- [ ] 实现 `detect_feedback.py`
- [ ] 创建 `data/` 目录 + `.gitignore` 规则
- [ ] 更新 `settings.json` hooks 配置
- [ ] **验证关键项**：PostToolUse `matcher: "Skill"` 是否有效
- [ ] 运行 5 次真实会话，检查数据文件是否正确写入

### Phase 2: 进化编排器（优先级 P0，预计 1 天）

**目标**：进化触发条件能正确检测

- [ ] 实现 `evolution_orchestrator.py`
- [ ] 实现 `load_evolution_state.py`
- [ ] 实现 `evolution_metrics.json` 初始化
- [ ] 测试：模拟触发条件，验证编排器输出正确的 `should_evolve` 信号

### Phase 3: 维度进化器（优先级 P1，预计 3-4 天）

**目标**：四个维度进化器能独立完成分析→修改→审计流程

- [ ] 创建 `agents/skill-evolver.md`
- [ ] 创建 `agents/agent-evolver.md`
- [ ] 创建 `agents/rule-evolver.md`
- [ ] 创建 `agents/memory-evolver.md`
- [ ] 每个进化器单独测试（人工触发，验证产出质量）
- [ ] 端到端测试：Hook 采集 → 编排器检测 → 进化器执行 → 文件修改生效

### Phase 4: 效果验证与运维（优先级 P2，预计 2 天）

**目标**：能量化进化效果，有回滚能力

- [ ] 实现进化效果指标采集（进化前后对比）
- [ ] 实现进化回滚脚本
- [ ] 实现数据轮转清理脚本
- [ ] 编写运维文档

---

## 八、settings.json 变更

### 8.1 需要修改的 hooks 配置

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/collect_agent_launch.py",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/collect_skill_usage.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/collect_tool_failure.py",
            "timeout": 3
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/collect_violations.py",
            "timeout": 5
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/detect_feedback.py",
            "timeout": 3
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/evolution_orchestrator.py",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/load_evolution_state.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### 8.2 需要移除/合并的旧配置

- `PostToolUse[Write|Edit] → quality-gate.sh`：保留，与采集器同时运行（并行）
- `PostToolUse[Agent] → auto_evolver.py`：替换为 `collect_agent_launch.py`
- `SubagentStop → auto_evolver.py`：**移除**（无法获取 agent 类型，纯噪声）
- `PreToolUse[Write|Edit] → path_validator.py`：保留
- `PreToolUse[Bash] → safety-check.sh`：保留
- `UserPromptSubmit → context-enhancer.sh`：保留，与 detect_feedback.py 并行
- `Stop → session_evolver.py + strategy_updater.py`：简化为 `evolution_orchestrator.py`

---

## 九、潜在问题与规避方案

### 9.1 已识别问题

**问题 1: PostToolUse `matcher: "Skill"` 可能不生效**
- 风险：Claude Code 的 Skill 工具调用可能不以 "Skill" 为 tool_name
- 规避：Phase 1 第一件事就是验证。如果不行，改用 UserPromptSubmit 检测 Skill 调用
- 替代方案：在 `evolution_orchestrator.py` 中解析 transcript.jsonl，统计 Skill 调用

**问题 2: Agent 执行质量无法自动评估**
- 风险：我们只能知道 Agent 被调用了，但不知道产出好不好
- 缓解：通过间接信号判断 — 用户是否立即纠正、后续是否有 PostToolUseFailure、Agent 输出是否被主 Agent 接受
- 长期方案：引入 code-reviewer 对 Agent 产出的评估

**问题 3: 反馈信号误检测**
- 风险：用户说"记住这个网址"被误识别为 Memory 进化信号
- 缓解：增加上下文长度限制（> 10 字符）、过滤 URL/代码片段
- 持续优化：误检测率纳入 evolution_metrics，过高时调整正则

**问题 4: 进化导致退化**
- 风险：自动修改后 Skill/Agent 表现更差
- 缓解：
  - 进化历史保留修改前 hash
  - 提供回滚命令：`python3 .claude/lib/rollback_evolution.py --target skill-name`
  - 连续 2 次进化后指标下降 → 暂停该维度进化

### 9.2 运维风险

**风险: settings.local.json SessionStart 篡改全局配置**
- 这是之前分析发现的 Bug，必须在 Phase 1 修复
- 移除 `settings.local.json` 中修改 `~/.claude/settings.json` 的 hook

**风险: JSONL 文件被 .gitignore 但 data/ 目录不存在**
- 所有采集器必须在写入前 `mkdir(parents=True, exist_ok=True)`

---

## 十、总结

### 核心设计原则

1. **Hook 只采集事实，Agent 才做判断** — 单一职责
2. **分层触发，底层优先** — Memory → Rules → Agents → Skills
3. **冷却 + 限流** — 防抖动，避免过度进化
4. **分层风险控制** — Low 自动、Medium 通知、High 人工
5. **完整审计追踪** — 每次进化写入 evolution_history.jsonl

### 与 v1 方案的关键差异

| 方面 | v1 方案 | v2 方案（本方案） |
|------|---------|------------------|
| Agent 数据采集 | SubagentStop（不工作） | PostToolUse[Agent]（已验证） |
| 失败信号 | 未采集 | PostToolUseFailure 独立采集 |
| 进化触发 | 固定阈值 | 优先级计算 + 冷却 + 限流 |
| 风险控制 | 无分层 | Low/Medium/High/Critical 四级 |
| 审计追踪 | 部分 | 完整 evolution_history.jsonl |
| 边界处理 | 缺失 | 空文件/损坏行/并发写入全覆蓋 |
| 性能预算 | 未定义 | 每会话 < 30s Hook + < 60s 进化 |

---

## 十一、各维度自我进化数据流程图

### 11.1 Skills 维度数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    SKILLS 进化数据流                          │
└─────────────────────────────────────────────────────────────┘

[用户发起任务]
      │
      ▼
┌──────────────────┐
│  Claude 匹配 Skill │  基于 SKILL.md description 自动匹配
│  (官方机制)        │
└────────┬─────────┘
         │ 匹配成功，Skill 被调用
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: PostToolUse[Skill]                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ collect_skill_usage.py                                  │ │
│  │                                                        │ │
│  │ 输入 (stdin JSON):                                     │ │
│  │   tool_name: "Skill"                                   │ │
│  │   tool_input.skill: "karpathy-guidelines"              │ │
│  │   tool_input.args: "..."                               │ │
│  │   session_id: "abc123"                                 │ │
│  │                                                        │ │
│  │ 处理:                                                  │ │
│  │   1. 提取 skill 名称                                   │ │
│  │   2. 提取调用时间戳                                    │ │
│  │   3. 关联 session_id                                   │ │
│  │                                                        │ │
│  │ 输出 → data/skill_usage.jsonl:                         │ │
│  │   {"type":"skill_invoked","skill":"...","ts":"..."}    │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ 数据积累
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: Stop → evolution_orchestrator.py                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Skill 维度检测逻辑:                                     │ │
│  │                                                        │ │
│  │   stats = group_by_skill(read_jsonl("skill_usage"))    │ │
│  │                                                        │ │
│  │   for skill_name, s in stats:                          │ │
│  │     call_count = s.total_calls                         │ │
│  │     success_rate = estimate_success_rate(skill_name)   │ │
│  │                                                        │ │
│  │     if call_count >= 10 and success_rate < 0.8:        │ │
│  │       priority = (1-success_rate) * call_count/10      │ │
│  │       if not in_cooldown(skill_name, 24h):             │ │
│  │         emit_trigger("skill", skill_name, priority)    │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ trigger 信号 (stdout JSON)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  SkillEvolver Agent 启动                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                         │ │
│  │  Step 1: 读取目标 SKILL.md 全文                        │ │
│  │  Step 2: 读取 skill_usage.jsonl 中该 Skill 的记录      │ │
│  │  Step 3: 分析                                           │ │
│  │    ├── description 匹配度                               │ │
│  │    │   · 当前触发词 vs 用户实际用词                     │ │
│  │    │   · 遗漏的触发词                                   │ │
│  │    │   · 误触发场景                                     │ │
│  │    ├── body 步骤有效性                                  │ │
│  │    │   · 总是被跳过的步骤 → 可能冗余                    │ │
│  │    │   · 总是需要额外补充的 → 应加入 body               │ │
│  │    └── 工具权限足够性                                   │ │
│  │        · PostToolUseFailure 中该 Skill 的错误           │ │
│  │                                                         │ │
│  │  Step 4: 执行修改 (Edit 工具)                           │ │
│  │    Low risk: 追加触发词 → 自动执行                      │ │
│  │    Medium risk: 修改步骤 → 自动执行 + 通知              │ │
│  │    High risk: 改核心流程 → 标记 pending                 │ │
│  │                                                         │ │
│  │  Step 5: 审计                                           │ │
│  │    写入 evolution_history.jsonl                         │ │
│  │    evolution_metrics.json 更新 success_rate 基线        │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                       │ Live Reload 立即生效
                       ▼
              ┌──────────────────┐
              │  下次会话自动使用  │
              │  进化后的 Skill    │
              └──────────────────┘
```

### 11.2 Agents 维度数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTS 进化数据流                          │
└─────────────────────────────────────────────────────────────┘

[主 Agent 决定委托子 Agent]
      │
      ▼
┌──────────────────┐
│ Agent 工具调用     │  主 session 调用 Agent 工具
│ (官方机制)        │  subagent_type + description + prompt
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: PostToolUse[Agent]                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ collect_agent_launch.py                                 │ │
│  │                                                        │ │
│  │ 输入 (stdin JSON):                                     │ │
│  │   tool_input.subagent_type: "backend-developer"        │ │
│  │   tool_input.description: "实现 AssetController"       │ │
│  │   tool_input.prompt: "请实现一个 REST Controller..."   │ │
│  │   session_id: "abc123"                                 │ │
│  │                                                        │ │
│  │ 处理:                                                  │ │
│  │   1. 提取 subagent_type（这是唯一可靠来源！）          │ │
│  │   2. 提取 description（任务摘要）                      │ │
│  │   3. 截断 prompt 至 200 字符（避免存储膨胀）           │ │
│  │   4. 写入 agent_performance.jsonl                      │ │
│  │                                                        │ │
│  │ 输出 → data/agent_performance.jsonl:                   │ │
│  │   {"type":"agent_launch","agent":"backend-developer",  │ │
│  │    "task":"实现 AssetController","ts":"..."}           │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: PostToolUseFailure (如果 Agent 内工具调用失败)         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ collect_tool_failure.py                                │ │
│  │                                                        │ │
│  │ 输入: tool_name, error, file_path                     │ │
│  │ 输出 → data/tool_failures.jsonl:                       │ │
│  │   {"type":"tool_failure","tool":"Write",               │ │
│  │    "error":"Permission denied","ts":"..."}             │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  [用户纠正 / 反馈]                                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Hook: UserPromptSubmit → detect_feedback.py            │ │
│  │                                                        │ │
│  │ 检测: 用户是否纠正了 Agent 的输出？                     │ │
│  │   "不对，这个 Controller 应该用 @RestController"       │ │
│  │   → 记录为 Agent 输出质量的间接信号                     │ │
│  │                                                        │ │
│  │ 输出 → data/pending_evolution.json                     │ │
│  │   feedback_signals: [{"type":"correction",             │ │
│  │     "content":"@RestController","agent":"..."}]        │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ 数据积累
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: Stop → evolution_orchestrator.py                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Agent 维度检测逻辑:                                     │ │
│  │                                                        │ │
│  │   stats = group_by_agent(read_jsonl("agent_performance"))│
│  │                                                        │ │
│  │   for agent_name, s in stats:                          │ │
│  │     similar_tasks = cluster_tasks(s.tasks)             │ │
│  │     avg_turns = estimate_turns(s)                      │ │
│  │     failure_rate = s.failures / s.total                │ │
│  │                                                        │ │
│  │     if similar_tasks >= 5 and not in_cooldown:         │ │
│  │       priority = compute(avg_turns, failure_rate)      │ │
│  │       if priority > 0.5:                               │ │
│  │         emit_trigger("agent", agent_name, priority)    │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ trigger 信号
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  AgentEvolver 启动                                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                        │ │
│  │  Step 1: 读取目标 agent.md 全文                        │ │
│  │  Step 2: 读取 agent_performance.jsonl + failures       │ │
│  │  Step 3: 分析                                          │ │
│  │    ├── 任务完成效率（步数趋势）                         │ │
│  │    ├── 常见失败模式（提取到反模式）                     │ │
│  │    ├── 工具使用合理性（多/少/错）                       │ │
│  │    └── 用户纠正频次（间接质量信号）                     │ │
│  │                                                        │ │
│  │  Step 4: 执行修改                                      │ │
│  │    在 agent.md 末尾 "进化积累" 区追加:                  │ │
│  │    · 常见陷阱 + 避免方式                               │ │
│  │    · 工具使用洞察                                      │ │
│  │    · 边界条件提醒                                      │ │
│  │                                                        │ │
│  │  Step 5: 更新 evolution_metrics.json agent 基线        │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 11.3 Rules 维度数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    RULES 进化数据流                           │
└─────────────────────────────────────────────────────────────┘

[Claude 准备写入/编辑文件]
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: PreToolUse[Write|Edit]                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ collect_violations.py                                  │ │
│  │                                                        │ │
│  │ 输入 (stdin JSON):                                     │ │
│  │   tool_name: "Write"                                   │ │
│  │   tool_input.file_path: "tests/test.java"              │ │
│  │   session_id: "abc123"                                 │ │
│  │                                                        │ │
│  │ 规则引擎 (内置检测):                                   │ │
│  │                                                        │ │
│  │  ┌─────────────────────────────────────────────┐      │ │
│  │  │ 规则匹配器 (可配置)                          │      │ │
│  │  │                                             │      │ │
│  │  │ 1. .git/ 目录写入 → critical               │      │ │
│  │  │ 2. .env 文件写入  → high                    │      │ │
│  │  │ 3. 测试文件位置错误 → medium                │      │ │
│  │  │ 4. 违反分层架构  → medium                   │      │ │
│  │  │    (Controller 直接注入 Mapper)             │      │ │
│  │  │ 5. 文件路径不规范 → low                     │      │ │
│  │  │    (tests/ 而非 src/test/java/)             │      │ │
│  │  └─────────────────────────────────────────────┘      │ │
│  │                                                        │ │
│  │ 输出 → data/rule_violations.jsonl:                     │ │
│  │   {"type":"violation","rule":"test-location",          │ │
│  │    "file":"tests/test.java","severity":"medium",       │ │
│  │    "session_id":"abc123","ts":"..."}                   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ 数据积累
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: Stop → evolution_orchestrator.py                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Rules 维度检测逻辑:                                     │ │
│  │                                                        │ │
│  │   violations = read_jsonl("rule_violations")           │ │
│  │   by_rule = group_by_rule(violations)                  │ │
│  │                                                        │ │
│  │   for rule_name, items in by_rule:                     │ │
│  │     count = len(items)                                 │ │
│  │     severity_dist = count_by_severity(items)           │ │
│  │                                                        │ │
│  │     if count >= 3 and not in_cooldown(rule, 48h):      │ │
│  │       priority = min(1.0, count/3 * 0.5)               │ │
│  │       if priority > 0.5:                               │ │
│  │         emit_trigger("rule", rule_name, priority)      │ │
│  │                                                        │ │
│  │ 新增模式检测（独立于违规计数）:                         │ │
│  │   patterns = detect_repeating_errors(violations)       │ │
│  │   for pattern in patterns:                             │ │
│  │     if pattern.count >= 2 and pattern.is_new:          │ │
│  │       emit_trigger("rule:new", pattern, 0.7)           │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ trigger 信号
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  RuleEvolver 启动                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                        │ │
│  │  Step 1: 读取目标 rules/*.md 文件                      │ │
│  │  Step 2: 读取 rule_violations.jsonl                    │ │
│  │  Step 3: 违规原因分类                                  │ │
│  │                                                        │ │
│  │   违规率 >= 3 的规则:                                   │ │
│  │   ┌──────────────────────────────────────────────┐    │ │
│  │   │ 原因分类决策树:                               │    │ │
│  │   │                                              │    │ │
│  │   │ 违规文件类型分布分析                          │    │ │
│  │   │  ├── 集中在特定文件类型 → 规则适用范围问题    │    │ │
│  │   │  ├── 分散在各类型 → 可能规则不清晰            │    │ │
│  │   │  └── 全是 high severity → 可能规则太严格      │    │ │
│  │   │                                              │    │ │
│  │   │ 动作:                                        │    │ │
│  │   │  规则不清晰 → 补充示例 + 正反例对比           │    │ │
│  │   │  规则太严格 → 添加例外条件                    │    │ │
│  │   │  规则过时   → 标记 [DEPRECATED]               │    │ │
│  │   │  用户不知   → 在 CLAUDE.md 中增加引用         │    │ │
│  │   └──────────────────────────────────────────────┘    │ │
│  │                                                        │ │
│  │  Step 4: 执行修改                                      │ │
│  │    · 保留原有元数据 (更新时间, 适用范围)               │ │
│  │    · 新增内容用子章节隔离                              │ │
│  │    · 不删除规则（只标记过时）                          │ │
│  │                                                        │ │
│  │  Step 5: 审计 + 更新 evolution_metrics                 │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 11.4 Memory 维度数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY 进化数据流                          │
└─────────────────────────────────────────────────────────────┘

[用户发送消息]
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: UserPromptSubmit → detect_feedback.py                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                        │ │
│  │ 信号检测引擎 (正则匹配):                               │ │
│  │                                                        │ │
│  │  ┌────────────────────────────────────────────┐       │ │
│  │  │ 记忆请求                                     │       │ │
│  │  │ Pattern: (记住|记下|保存)(这个|一下)?[：:]   │       │ │
│  │  │ 示例: "记住，这个项目不用Lombok"             │       │ │
│  │  │ → type: "memory_request"                    │       │ │
│  │  └────────────────────────────────────────────┘       │ │
│  │                                                        │ │
│  │  ┌────────────────────────────────────────────┐       │ │
│  │  │ 纠正信号                                     │       │ │
│  │  │ Pattern: (不对|错了|不是这样)[，,]?          │       │ │
│  │  │ 示例: "不对，Controller应该用@RestController"│       │ │
│  │  │ → type: "correction"                        │       │ │
│  │  └────────────────────────────────────────────┘       │ │
│  │                                                        │ │
│  │  ┌────────────────────────────────────────────┐       │ │
│  │  │ 确认信号 (正面反馈)                          │       │ │
│  │  │ Pattern: (对的|没错|就是这样|exactly|perfect)│       │ │
│  │  │ → type: "confirmation"                      │       │ │
│  │  └────────────────────────────────────────────┘       │ │
│  │                                                        │ │
│  │  ┌────────────────────────────────────────────┐       │ │
│  │  │ 偏好声明                                     │       │ │
│  │  │ Pattern: (以后|下次|将来|always|never)\\s    │       │ │
│  │  │ 示例: "以后所有API都要加版本前缀/v1/"        │       │ │
│  │  │ → type: "preference"                        │       │ │
│  │  └────────────────────────────────────────────┘       │ │
│  │                                                        │ │
│  │ 输出 → data/pending_evolution.json (合并已有信号)      │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Hook: Stop → evolution_orchestrator.py                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Memory 维度检测 (每次 Stop 都检查):                     │ │
│  │                                                        │ │
│  │   pending = read_json("pending_evolution")             │ │
│  │   signals = pending.get("feedback_signals", [])        │ │
│  │                                                        │ │
│  │   if len(signals) > 0:                                 │ │
│  │     # 反馈信号 = 最高优先级，无冷却期                   │ │
│  │     emit_trigger("memory", "feedback", priority=1.0)   │ │
│  │                                                        │ │
│  │ 重复失败模式检测:                                       │ │
│  │   failures = read_jsonl("tool_failures")               │ │
│  │   patterns = find_repeating(failures, min_count=2)     │ │
│  │   for p in patterns:                                   │ │
│  │     if not already_in_memory(p):                       │ │
│  │       emit_trigger("memory", p.pattern, priority=0.8)  │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ trigger 信号
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  MemoryEvolver 启动                                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                        │ │
│  │  Step 1: 读取 pending_evolution.json 中的 signals      │ │
│  │  Step 2: 读取 MEMORY.md 索引（去重检查）               │ │
│  │  Step 3: 分类处理                                      │ │
│  │                                                        │ │
│  │  signal.type == "memory_request":                      │ │
│  │    → 直接创建 memory/{type}_{slug}.md                  │ │
│  │    → 写入 frontmatter + body                           │ │
│  │                                                        │ │
│  │  signal.type == "correction":                          │ │
│  │    → 检查是否同类纠正 >= 2 次                          │ │
│  │    → 是 → 创建 feedback 记忆（反模式）                 │ │
│  │    → 否 → 暂存，等待下次                               │ │
│  │                                                        │ │
│  │  signal.type == "preference":                          │ │
│  │    → 创建 user 记忆                                   │ │
│  │    → 标注适用范围                                      │ │
│  │                                                        │ │
│  │  signal.type == "confirmation":                        │ │
│  │    → 关联到最近的 Agent/Skill 使用                     │ │
│  │    → 作为质量信号的正面样本                            │ │
│  │                                                        │ │
│  │  Step 4: 去重检查                                      │ │
│  │    读取 MEMORY.md 已有条目                             │ │
│  │    语义相似度 > 0.8 → 更新而非新增                      │ │
│  │                                                        │ │
│  │  Step 5: 写入 + 更新索引                               │ │
│  │    memory/{type}_{slug}.md（新记忆文件）               │ │
│  │    MEMORY.md（追加索引行）                             │ │
│  │    pending_evolution.json（清除已处理 signals）        │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                       │ 下次会话
                       ▼
              ┌──────────────────┐
              │  Auto Memory 加载 │
              │  + 进化记忆生效   │
              └──────────────────┘
```

---

## 十二、全链路触发图

### 12.1 一次完整会话的进化全链路

```
时间轴 ──────────────────────────────────────────────────────────────────────▶

┌─ SessionStart ──────────────────────────────────────────────────────────┐
│                                                                         │
│  load_evolution_state.py                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 读取:                                                           │   │
│  │  · data/evolution_metrics.json → 进化状态总览                   │   │
│  │  · data/pending_evolution.json  → 上次会话遗留的待处理信号      │   │
│  │                                                                 │   │
│  │ stdout → 注入上下文:                                            │   │
│  │  "📊 进化状态: Skills 3次进化 | Agents 2次进化 |                │   │
│  │   Rules 0次违规 | Memory 1个待处理信号"                         │   │
│  │                                                                 │   │
│  │  if pending_signals > 0:                                        │   │
│  │    "⚠️ 有 2 个待处理的进化信号，建议处理"                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─ 用户交互循环 ──────────────────────────────────────────────────────────┐
│                                                                         │
│  ┌─────────────────┐                                                   │
│  │ UserPromptSubmit │──▶ detect_feedback.py ──▶ pending_evolution.json │
│  └─────────────────┘                                                   │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                   │
│  │    PreToolUse    │──▶ safety-check.sh (Bash)                        │
│  │                  │──▶ collect_violations.py (Write|Edit)            │
│  └─────────────────┘                                                   │
│           │                                                             │
│           ▼                                                             │
│     [工具执行]                                                          │
│           │                                                             │
│           ├── 成功 ──▶ PostToolUse                                      │
│           │              ├── Agent → collect_agent_launch.py           │
│           │              ├── Skill → collect_skill_usage.py            │
│           │              └── Write|Edit → quality-gate.sh              │
│           │                                                             │
│           └── 失败 ──▶ PostToolUseFailure                              │
│                          └── collect_tool_failure.py                   │
│                                                                         │
│  ┌─────────────────┐                                                   │
│  │  SubagentStop   │──▶ (已移除, 不采集)                              │
│  └─────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─ Stop ──────────────────────────────────────────────────────────────────┐
│                                                                         │
│  evolution_orchestrator.py                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                 │   │
│  │  PHASE 1: 汇总本会话数据                                        │   │
│  │  ┌──────────────────────────────────────────────────────┐      │   │
│  │  │ 读取:                                                │      │   │
│  │  │  · data/skill_usage.jsonl (本次 session_id)          │      │   │
│  │  │  · data/agent_performance.jsonl (本次 session_id)    │      │   │
│  │  │  · data/rule_violations.jsonl (本次 session_id)      │      │   │
│  │  │  · data/tool_failures.jsonl (本次 session_id)        │      │   │
│  │  │  · data/pending_evolution.json                       │      │   │
│  │  │                                                     │      │   │
│  │  │ 汇总 → session_summary:                              │      │   │
│  │  │  {                                                   │      │   │
│  │  │    "domain": "backend",                              │      │   │
│  │  │    "skills_used": ["karpathy-guidelines"],           │      │   │
│  │  │    "agents_used": ["backend-developer"],             │      │   │
│  │  │    "violations": 0,                                  │      │   │
│  │  │    "failures": 0,                                    │      │   │
│  │  │    "feedback_signals": 1                             │      │   │
│  │  │  }                                                   │      │   │
│  │  └──────────────────────────────────────────────────────┘      │   │
│  │                                                                 │   │
│  │  PHASE 2: 检查各维度触发条件                                    │   │
│  │  ┌──────────────────────────────────────────────────────┐      │   │
│  │  │                                                      │      │   │
│  │  │  Memory 维度 (最高优先级)                             │      │   │
│  │  │  ├── 有 feedback_signals? → YES, trigger (p=1.0)     │      │   │
│  │  │  └── 有重复失败模式? → 检查 conditions              │      │   │
│  │  │                                                      │      │   │
│  │  │  Skill 维度                                           │      │   │
│  │  │  ├── 累计调用 >= 10? → 检查 success_rate             │      │   │
│  │  │  ├── 成功率 < 80%? → 计算 priority                   │      │   │
│  │  │  └── 不在冷却期? → trigger                           │      │   │
│  │  │                                                      │      │   │
│  │  │  Agent 维度                                           │      │   │
│  │  │  ├── 同类任务 >= 5? → 检查 avg_turns                 │      │   │
│  │  │  ├── avg_turns > baseline? → 计算 priority            │      │   │
│  │  │  └── 不在冷却期? → trigger                           │      │   │
│  │  │                                                      │      │   │
│  │  │  Rule 维度                                            │      │   │
│  │  │  ├── 违规次数 >= 3? → 计算 priority                  │      │   │
│  │  │  └── 不在冷却期? → trigger                           │      │   │
│  │  └──────────────────────────────────────────────────────┘      │   │
│  │                                                                 │   │
│  │  PHASE 3: 排序 & 限流                                           │   │
│  │  ┌──────────────────────────────────────────────────────┐      │   │
│  │  │  triggers = sorted(triggers, key=priority, reverse)   │      │   │
│  │  │  triggers = triggers[:3]  # 最多 3 个                 │      │   │
│  │  │                                                      │      │   │
│  │  │  for t in triggers:                                  │      │   │
│  │  │    if t.priority > 0.5:                              │      │   │
│  │  │      t.status = "triggered"                          │      │   │
│  │  │    else:                                             │      │   │
│  │  │      t.status = "below_threshold"                    │      │   │
│  │  └──────────────────────────────────────────────────────┘      │   │
│  │                                                                 │   │
│  │  PHASE 4: 输出决策                                              │   │
│  │  ┌──────────────────────────────────────────────────────┐      │   │
│  │  │  stdout → Claude 读取:                               │      │   │
│  │  │  {                                                   │      │   │
│  │  │    "should_evolve": true,                            │      │   │
│  │  │    "session_summary": {...},                         │      │   │
│  │  │    "triggers": [                                     │      │   │
│  │  │      {"dimension":"memory","target":"feedback",      │      │   │
│  │  │       "priority":1.0,"status":"triggered"},          │      │   │
│  │  │      {"dimension":"agent","target":"backend-dev",    │      │   │
│  │  │       "priority":0.6,"status":"triggered"}           │      │   │
│  │  │    ]                                                 │      │   │
│  │  │  }                                                   │      │   │
│  │  └──────────────────────────────────────────────────────┘      │   │
│  │                                                                 │   │
│  │  PHASE 5: 更新全局指标                                          │   │
│  │  ┌──────────────────────────────────────────────────────┐      │   │
│  │  │  evolution_metrics.json ← 更新:                       │      │   │
│  │  │  · 各 Skill/Agent 的累计统计数据                     │      │   │
│  │  │  · 各 Rule 的违规计数                                │      │   │
│  │  │  · 系统级计数器 (total_evolutions, last_evolution)   │      │   │
│  │  └──────────────────────────────────────────────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  输出 → Claude 主 Agent 决定是否启动进化                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
            │ MemoryEvolver│ │ AgentEvolver │ │ SkillEvolver │
            │ (priority 1) │ │ (priority 0.6)│ │ (未触发)     │
            └──────┬───────┘ └──────┬───────┘ └──────────────┘
                   │                │
                   ▼                ▼
        ┌──────────────────┐ ┌──────────────────┐
        │ 提炼用户反馈为    │ │ 分析 Agent 执行   │
        │ Memory 文件       │ │ 追加陷阱+洞察    │
        │ 更新 MEMORY.md    │ │ 更新 agent.md    │
        └──────────────────┘ └──────────────────┘
                   │                │
                   ▼                ▼
        ┌──────────────────────────────────────┐
        │     写入 evolution_history.jsonl     │
        │     (审计日志，不可篡改)              │
        └──────────────────────────────────────┘
```

### 12.2 跨会话进化链路

```
会话 1                      会话 2                      会话 3
───────                     ───────                     ───────

[用户: "实现 API"]          [用户: "实现 API"]          [用户: "实现 API"]
      │                          │                          │
      ▼                          ▼                          ▼
 Skill 匹配失败              Skill 匹配成功              Skill 完美匹配
 (触发词不匹配)             (进化后加了触发词)          (持续优化)
      │                          │                          │
      ▼                          ▼                          ▼
 用户手动调用               Agent 执行正常              Agent 步数减少
      │                          │                          │
      ▼                          ▼                          ▼
 Stop: 采集事件              Stop: 采集事件              Stop: 指标改善
      │                          │                          │
      ▼                          ▼                          ▼
 evolution_orchestrator      evolution_orchestrator      evolution_orchestrator
 trigger: skill (p=0.7)      no trigger                  no trigger
      │                     (成功率 85% > 80%)           (一切正常)
      ▼
 SkillEvolver:
 "添加触发词: build API,
  create endpoint,
  implement controller"

───────────────────────────────────────────────────────────────
 效果链路:

 会话 1: 触发词匹配率 60% → 进化 → 会话 2: 匹配率 85% → 会话 3: 匹配率 95%
          Agent 平均步数 15 → 进化 → Agent 步数 12 → 持续改善 → 步数 9
          违规 3 次 → RuleEvolver 补充示例 → 违规 0 次
          反馈信号 → MemoryEvolver → 下次会话自动注入
```

---

## 十三、安全防护体系

### 13.1 多层防护架构

```
┌─────────────────────────────────────────────────────────────┐
│                    防护层 0: Hook 层                         │
│                                                             │
│  PreToolUse: 阻止危险操作 (safety-check.sh)                 │
│  PreToolUse: 路径验证 (path_validator.py)                   │
│  ─────────────────────────────────────────                  │
│  在进化系统触及文件系统之前，已有两层防护                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    防护层 1: 数据采集层                      │
│                                                             │
│  1. 文件锁 (fcntl.LOCK_EX): 防止并发写入损坏               │
│  2. JSON Schema 校验: 写入前验证 record 结构               │
│  3. 文件大小限制: 单文件 > 2MB → 触发压缩归档              │
│  4. 敏感信息过滤: prompt 截断至 200 字符                   │
│  5. 目录权限检查: data/ 必须是 755                         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    防护层 2: 进化触发层                      │
│                                                             │
│  1. 冷却期检查: 防止频繁进化                               │
│  2. 会话上限: 每会话 ≤ 3 次进化                            │
│  3. 优先级阈值: priority > 0.5 才触发                      │
│  4. 数据充分性: 样本不足不触发                             │
│  5. 错误熔断: 连续 2 次进化无改善 → 暂停该维度             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    防护层 3: 进化执行层                      │
│                                                             │
│  1. 修改前快照: 记录文件 hash (md5)                        │
│  2. 风险分级: Low/Medium/High/Critical                     │
│  3. 高风险拦截: 必须人工确认                               │
│  4. 格式验证: 修改后文件必须是合法 Markdown + YAML         │
│  5. 原子写入: 临时文件 → rename (不直接覆盖)               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    防护层 4: 审计与恢复层                    │
│                                                             │
│  1. 完整审计日志: evolution_history.jsonl                  │
│  2. 回滚能力: 基于 hash 恢复修改前版本                    │
│  3. 效果追踪: 进化前后指标对比                             │
│  4. 告警机制: 异常进化 → stderr + pending_review           │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 安全实现代码

```python
# .claude/lib/evolution_safety.py

import hashlib
import json
import os
import shutil
import fcntl
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List


# ─── 文件快照与回滚 ───────────────────────────────────────────

def snapshot_file(file_path: str) -> str:
    """计算文件 hash 作为快照，用于回滚对比"""
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def backup_file(file_path: str, backup_dir: str = ".claude/data/backups") -> str:
    """创建文件备份，返回备份路径"""
    src = Path(file_path)
    backup = Path(backup_dir) / f"{src.name}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, backup)
    return str(backup)


def rollback_file(file_path: str, backup_path: str) -> bool:
    """从备份恢复文件"""
    try:
        shutil.copy2(backup_path, file_path)
        return True
    except OSError:
        return False


# ─── 进化熔断器 ───────────────────────────────────────────────

class EvolutionCircuitBreaker:
    """
    进化熔断器：防止连续无效进化导致退化。

    规则:
    - 同一目标连续 2 次进化后指标不升反降 → 熔断
    - 熔断后需要人工重置
    - 熔断状态持久化到 evolution_metrics.json
    """

    def __init__(self, metrics_path: str = ".claude/data/evolution_metrics.json"):
        self.metrics_path = Path(metrics_path)
        self.max_consecutive_degradations = 2

    def is_open(self, dimension: str, target: str) -> bool:
        """检查熔断器是否断开（阻止进化）"""
        metrics = self._read_metrics()
        breaker = metrics.get("circuit_breaker", {}).get(dimension, {}).get(target)
        if not breaker:
            return False
        return breaker.get("consecutive_degradations", 0) >= self.max_consecutive_degradations

    def record_result(self, dimension: str, target: str, improved: bool):
        """记录进化结果"""
        metrics = self._read_metrics()
        metrics.setdefault("circuit_breaker", {}).setdefault(dimension, {}).setdefault(target, {})
        breaker = metrics["circuit_breaker"][dimension][target]

        if improved:
            breaker["consecutive_degradations"] = 0
        else:
            breaker["consecutive_degradations"] = breaker.get("consecutive_degradations", 0) + 1
            breaker["last_degradation"] = datetime.now().isoformat()

        if breaker["consecutive_degradations"] >= self.max_consecutive_degradations:
            breaker["status"] = "OPEN"
            breaker["opened_at"] = datetime.now().isoformat()
            breaker["action_required"] = "人工检查并重置熔断器"

        self._write_metrics(metrics)

    def reset(self, dimension: str, target: str):
        """人工重置熔断器"""
        metrics = self._read_metrics()
        path = ["circuit_breaker", dimension, target]
        current = metrics
        for key in path[:-1]:
            current = current.get(key, {})
        if path[-1] in current:
            del current[path[-1]]
        self._write_metrics(metrics)

    def _read_metrics(self) -> dict:
        if self.metrics_path.exists():
            return json.loads(self.metrics_path.read_text())
        return {}

    def _write_metrics(self, data: dict):
        tmp = self.metrics_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(tmp, self.metrics_path)


# ─── 进化限流器 ───────────────────────────────────────────────

class EvolutionRateLimiter:
    """
    进化限流器：防止同一目标被过度进化。

    规则:
    - Skill/Agent: 24h 冷却
    - Rule: 48h 冷却
    - Memory: 无冷却
    - 每会话全局上限: 3 次
    """

    COOLDOWNS = {
        "skill": timedelta(hours=24),
        "agent": timedelta(hours=24),
        "rule": timedelta(hours=48),
        "memory": timedelta(hours=0),
    }
    MAX_PER_SESSION = 3

    def __init__(self, history_path: str = ".claude/data/evolution_history.jsonl"):
        self.history_path = Path(history_path)

    def can_evolve(self, dimension: str, target: str, session_id: str) -> tuple[bool, str]:
        """
        检查是否可以进化。
        返回 (can_evolve: bool, reason: str)
        """
        history = self._read_history()

        # 检查 1: 会话上限
        session_evolutions = [
            h for h in history
            if h.get("session_id") == session_id
            and h.get("timestamp", "").startswith(datetime.now().strftime("%Y-%m-%d"))
        ]
        if len(session_evolutions) >= self.MAX_PER_SESSION:
            return False, f"本次会话已达进化上限 ({self.MAX_PER_SESSION}次)"

        # 检查 2: 冷却期
        cooldown = self.COOLDOWNS.get(dimension, timedelta(hours=24))
        if cooldown.total_seconds() > 0:
            for h in reversed(history):
                if h.get("dimension") == dimension and h.get("target") == target:
                    last_time = datetime.fromisoformat(h["timestamp"])
                    if datetime.now() - last_time < cooldown:
                        remaining = cooldown - (datetime.now() - last_time)
                        hours = remaining.total_seconds() / 3600
                        return False, f"冷却中，还需 {hours:.1f} 小时"

        return True, "OK"

    def _read_history(self) -> list:
        if not self.history_path.exists():
            return []
        records = []
        with open(self.history_path) as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records


# ─── 数据完整性校验 ───────────────────────────────────────────

def validate_record_schema(record: dict, schema: dict) -> tuple[bool, str]:
    """
    轻量级 JSON schema 校验，确保采集器不会写入垃圾数据。

    schema 示例:
    {
      "type": "agent_launch",
      "required": ["type", "timestamp", "session_id", "agent", "task"]
    }
    """
    if record.get("type") != schema.get("type"):
        return False, f"type 不匹配: {record.get('type')} != {schema.get('type')}"
    for field in schema.get("required", []):
        if field not in record:
            return False, f"缺少必需字段: {field}"
    return True, "OK"


# ─── 敏感信息过滤 ────────────────────────────────────────────

def sanitize_prompt(prompt: str, max_length: int = 200) -> str:
    """
    过滤 prompt 中的敏感信息并截断。
    防止 API key、密码等泄露到数据文件中。
    """
    import re

    # 移除常见敏感模式
    patterns = [
        (r'(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[:=]\s*\S+', '[REDACTED]'),
        (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
        (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----.*?-----END', '[REDACTED_KEY]'),
    ]

    sanitized = prompt
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE | re.DOTALL)

    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized


# ─── 文件大小监控 ────────────────────────────────────────────

def check_file_size(path: str, max_size_mb: int = 2) -> bool:
    """
    检查 JSONL 文件是否超过大小限制。
    超过则返回 True（需要轮转）。
    """
    file_path = Path(path)
    if not file_path.exists():
        return False
    return file_path.stat().st_size > max_size_mb * 1024 * 1024


def rotate_jsonl(path: str, keep_days: int = 30):
    """
    轮转 JSONL 文件：重命名为 .YYYY-MM-DD.archive，
    删除超过 keep_days 的旧归档。
    """
    file_path = Path(path)
    if not file_path.exists():
        return

    archive_name = f"{file_path.stem}.{datetime.now().strftime('%Y%m%d')}.archive"
    archive_path = file_path.parent / archive_name
    shutil.move(str(file_path), str(archive_path))

    # 清理旧归档
    for old in file_path.parent.glob(f"{file_path.stem}.*.archive"):
        try:
            date_str = old.suffixes[0].strip(".") if old.suffixes else ""
            # 如果归档超过 keep_days，删除
            old_time = datetime.fromtimestamp(old.stat().st_mtime)
            if datetime.now() - old_time > timedelta(days=keep_days):
                old.unlink()
        except (ValueError, OSError):
            continue
```

### 13.3 自我恢复机制

```
┌─────────────────────────────────────────────────────────────┐
│                    自我恢复流程                               │
└─────────────────────────────────────────────────────────────┘

触发条件:
  ├── 数据文件损坏 (JSONDecodeError 连续 3 行)
  ├── 进化后指标恶化 (熔断器断开)
  ├── 文件被意外删除
  └── Hook 连续失败

恢复等级:

  Level 1: 自动恢复 (无需人工)
  ┌────────────────────────────────────────────────────────┐
  │                                                        │
  │  场景: 空数据文件 / 文件不存在                          │
  │  动作: 初始化空状态，继续运行                           │
  │  示例:                                                 │
  │    if not data_file.exists():                          │
  │        return []  # 空列表，不阻塞流程                  │
  │                                                        │
  │  场景: 损坏的 JSONL 行                                 │
  │  动作: 跳过损坏行，记录 warning 到 stderr               │
  │  示例:                                                 │
  │    for line in f:                                      │
  │        try: record = json.loads(line)                  │
  │        except: corrupted_count += 1; continue          │
  │    if corrupted_count > 0:                             │
  │        print(f"⚠️ 跳过 {corrupted_count} 行损坏数据")   │
  │                                                        │
  │  场景: 单个 JSONL 过大 (> 2MB)                         │
  │  动作: 自动轮转归档，创建新文件                         │
  └────────────────────────────────────────────────────────┘

  Level 2: 半自动恢复 (通知 + 自动)
  ┌────────────────────────────────────────────────────────┐
  │                                                        │
  │  场景: 熔断器断开 (连续退化)                            │
  │  动作:                                                 │
  │    1. 通知用户: "⚠️ skill-name 进化后连续 2 次退化,     │
  │       已暂停自动进化"                                   │
  │    2. 自动回滚到最后已知良好的版本                      │
  │    3. 保留问题数据供分析                                │
  │                                                        │
  │  场景: Hook 连续失败                                    │
  │  动作:                                                 │
  │    1. 累计失败计数                                      │
  │    2. 达到 3 次 → stderr 告警                          │
  │    3. 不影响主流程 (所有 Hook 脚本 exit 0 或 1)         │
  └────────────────────────────────────────────────────────┘

  Level 3: 人工恢复 (需要用户操作)
  ┌────────────────────────────────────────────────────────┐
  │                                                        │
  │  场景: 核心配置文件被错误修改                            │
  │  动作:                                                 │
  │    · 提供了回滚命令:                                    │
  │      python3 .claude/lib/evolution_safety.py rollback   │
  │        --target skill-name --to 20260425_153000         │
  │    · 人工检查差异:                                      │
  │      python3 .claude/lib/evolution_safety.py diff       │
  │        --target skill-name                              │
  │                                                        │
  │  场景: 需要重置整个进化状态                              │
  │  动作:                                                 │
  │    python3 .claude/lib/evolution_safety.py reset-all    │
  │    · 清空 data/*.jsonl                                 │
  │    · 重置 evolution_metrics.json                       │
  │    · 重置所有熔断器                                     │
  │    · 不移除已写入 memory/ 的记忆文件                    │
  └────────────────────────────────────────────────────────┘
```

### 13.4 恢复命令 CLI

```python
# .claude/lib/evolution_safety.py (CLI 扩展)

def cli_rollback(target: str, timestamp: str = None):
    """
    回滚指定目标的进化。
    用法: python3 .claude/lib/evolution_safety.py rollback --target skill:karpathy-guidelines
    """
    # 从 evolution_history.jsonl 找到该目标的进化记录
    # 还原到指定的历史版本
    pass

def cli_diff(target: str):
    """
    对比指定目标的当前版本和最近一次进化前的版本。
    用法: python3 .claude/lib/evolution_safety.py diff --target agent:backend-developer
    """
    pass

def cli_reset_all():
    """
    重置所有进化数据（保留 memory/ 文件）。
    用法: python3 .claude/lib/evolution_safety.py reset-all --confirm
    """
    pass

def cli_status():
    """
    查看进化系统整体状态。
    用法: python3 .claude/lib/evolution_safety.py status
    输出: 各维度进化次数、熔断器状态、数据文件大小、最近进化时间
    """
    pass

def cli_validate():
    """
    验证所有进化相关文件的完整性。
    用法: python3 .claude/lib/evolution_safety.py validate
    检查:
    - JSONL 文件是否可解析
    - evolution_history 与 metrics 是否一致
    - 熔断器状态是否与 history 一致
    - 备份文件是否可读
    """
    pass
```

---

## 十四、各维度安全约束汇总

| 维度 | 最大进化频率 | 冷却期 | 熔断条件 | 回滚方式 |
|------|-------------|--------|---------|---------|
| **Skill** | 1次/24h | 24h | 连续2次成功率下降 | 基于 hash 恢复 |
| **Agent** | 1次/24h | 24h | 连续2次步数增加 | 基于 hash 恢复 |
| **Rule** | 1次/48h | 48h | 连续2次违规增加 | 基于 hash 恢复 |
| **Memory** | 无限制 | 0h | 无熔断（低风险） | 直接删除文件 |
| **全局** | 3次/会话 | — | — | reset-all 命令 |

### 进化安全清单（每次进化前检查）

```python
def pre_evolution_check(dimension: str, target: str, session_id: str) -> dict:
    """
    进化前安全检查，返回所有检查项的结果。
    任何一项失败 → 阻止进化。
    """
    breaker = EvolutionCircuitBreaker()
    limiter = EvolutionRateLimiter()

    checks = {
        "熔断器未断开": not breaker.is_open(dimension, target),
        "冷却期已过": limiter.can_evolve(dimension, target, session_id)[0],
        "数据充分": check_data_sufficiency(dimension, target),
        "目标文件存在": check_target_exists(dimension, target),
        "目标文件可写": check_target_writable(dimension, target),
        "备份已创建": False,  # 在进化执行时创建
    }

    return {
        "can_proceed": all(checks.values()),
        "checks": checks,
        "blocked_by": [k for k, v in checks.items() if not v]
    }
```

---

## 十五、进化仪表盘（Evolution Dashboard）

### 15.1 设计目标

**一站式查看整体进化过程**：
- 每个维度 0-100 分的进化健康度评分
- 每日进化分数趋势
- 进化摘要（最近做了什么进化，效果如何）
- 一眼看出哪个维度在进步、哪个在退化

### 15.2 评分体系

```
维度健康度 = 基础分 + 活跃度分 + 效果分 + 质量分

┌────────────┬────────────────────────────────────────────────┐
│ 评分维度    │ 计算方式                                       │
├────────────┼────────────────────────────────────────────────┤
│ 基础分(40) │ 该维度是否有数据在积累                          │
│            │ · data 文件存在 + 有记录: 30/40                │
│            │ · 记录 >= 10 条: 40/40                         │
├────────────┼────────────────────────────────────────────────┤
│ 活跃度(20) │ 该维度是否在持续使用                            │
│            │ · 近 7 天有数据: 10/20                         │
│            │ · 近 7 天增长率 > 0: 20/20                     │
├────────────┼────────────────────────────────────────────────┤
│ 效果分(25) │ 进化后是否有改善                                │
│            │ · 最近进化后指标改善: 15/25                     │
│            │ · 连续 2 次进化改善: 25/25                     │
│            │ · 熔断器断开: 0/25                             │
├────────────┼────────────────────────────────────────────────┤
│ 质量分(15) │ 数据质量和进化安全性                            │
│            │ · 无损坏数据行: 5/15                            │
│            │ · 进化频率在健康范围: 5/15                      │
│            │ · 无异常波动: 5/15                              │
└────────────┴────────────────────────────────────────────────┘

总分 = 基础分 + 活跃度分 + 效果分 + 质量分  (0-100)
```

### 15.3 各维度评分细则

```python
# .claude/lib/evolution_scoring.py

class EvolutionScorer:
    """进化评分引擎：为每个维度计算 0-100 的进化健康度分数"""

    @staticmethod
    def score_skill(skill_name: str, metrics: dict) -> dict:
        """
        Skill 维度评分细则:
        - 基础分: call_count >= 10 ? 40 : call_count * 4
        - 活跃度: 7天内调用 >= 3 ? 20 : 7天内调用 * 6
        - 效果分: success_rate >= 0.9 ? 25 : success_rate * 25 (熔断时 0)
        - 质量分: 无损坏行(+5) + 频率健康(+5) + 无异常波动(+5)
        """
        base = min(40, metrics.get("total_calls", 0) * 4)
        activity = min(20, metrics.get("calls_last_7d", 0) * 6)
        effect = 0 if metrics.get("circuit_open") else min(25, metrics.get("success_rate", 0) * 25)
        quality = (
            (5 if not metrics.get("corrupted_rows") else 0) +
            (5 if metrics.get("evolution_frequency", 0) <= 1 else 2) +
            (5 if not metrics.get("anomaly_detected") else 0)
        )
        total = base + activity + effect + quality
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": effect, "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": EvolutionScorer._trend(metrics),
        }

    @staticmethod
    def score_agent(agent_name: str, metrics: dict) -> dict:
        """Agent 维度评分"""
        base = min(40, metrics.get("total_tasks", 0) * 8)
        activity = min(20, metrics.get("tasks_last_7d", 0) * 4)
        avg_turns = metrics.get("avg_turns", 15)
        baseline = metrics.get("baseline_turns", 15)
        turn_ratio = baseline / max(avg_turns, 1)  # > 1 表示改善
        effect = 0 if metrics.get("circuit_open") else min(25, turn_ratio * 20)
        quality = 15 if not metrics.get("anomaly_detected") else 5
        total = base + activity + effect + quality
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": EvolutionScorer._trend(metrics),
        }

    @staticmethod
    def score_rule(rule_name: str, metrics: dict) -> dict:
        """Rule 维度评分：违规越少分越高"""
        violations = metrics.get("total_violations", 0)
        base = max(0, 40 - violations * 5)  # 每次违规扣 5 分
        activity = 20 if metrics.get("last_violation_7d") else 10  # 最近有活动
        effect = 0 if metrics.get("circuit_open") else min(25, 25 - violations * 3)
        quality = 15 if not metrics.get("corrupted_rows") else 5
        total = base + activity + effect + quality
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": "📈" if violations <= metrics.get("prev_violations", violations) else "📉",
        }

    @staticmethod
    def score_memory(metrics: dict) -> dict:
        """Memory 维度评分"""
        file_count = metrics.get("total_files", 0)
        base = min(40, file_count * 10)
        activity = 20 if metrics.get("signals_last_7d", 0) > 0 else 10
        effect = min(25, file_count * 5)
        quality = 15
        total = base + activity + effect + quality
        return {
            "total": round(total, 1),
            "breakdown": {"base": base, "activity": activity, "effect": round(effect, 1), "quality": quality},
            "grade": EvolutionScorer._grade(total),
            "trend": "📈" if file_count >= metrics.get("prev_file_count", file_count) else "➡️",
        }

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 80: return "A"
        if score >= 65: return "B"
        if score >= 50: return "C"
        if score >= 35: return "D"
        return "F"

    @staticmethod
    def _trend(metrics: dict) -> str:
        prev = metrics.get("prev_score", metrics.get("total", 0))
        curr = metrics.get("total", 0)
        if curr > prev + 3: return "📈 上升"
        if curr < prev - 3: return "📉 下降"
        return "➡️ 持平"
```

### 15.4 仪表盘数据结构

```json
{
  "dashboard": {
    "generated_at": "2026-04-26T22:00:00",
    "overall_score": 72.5,
    "overall_grade": "B",
    "total_evolutions": 12,
    "days_tracked": 14,
    "summary": "系统整体健康，Memory 维度表现优秀，Agent 维度需关注"
  },
  "dimensions": {
    "skills": {
      "score": 68,
      "grade": "B",
      "trend": "📈 上升",
      "targets": {
        "karpathy-guidelines": { "score": 75, "grade": "B", "total_calls": 42, "success_rate": 0.88, "last_evolution": "2026-04-25" }
      }
    },
    "agents": {
      "score": 55,
      "grade": "C",
      "trend": "📉 下降",
      "targets": {
        "backend-developer": { "score": 52, "grade": "C", "total_tasks": 28, "avg_turns": 15, "last_evolution": "2026-04-20" },
        "code-reviewer": { "score": 70, "grade": "B", "total_tasks": 18, "avg_turns": 8, "last_evolution": null },
        "frontend-developer": { "score": 45, "grade": "D", "total_tasks": 12, "avg_turns": 20, "circuit_open": true }
      }
    },
    "rules": {
      "score": 78,
      "grade": "B",
      "trend": "➡️ 持平",
      "targets": {
        "collaboration.md": { "score": 80, "grade": "A", "violations": 2, "last_violation": "2026-04-23" },
        "test-location": { "score": 75, "grade": "B", "violations": 3, "last_violation": "2026-04-22" }
      }
    },
    "memory": {
      "score": 90,
      "grade": "A",
      "trend": "📈 上升",
      "targets": {
        "total_files": 5,
        "pending_signals": 2,
        "last_updated": "2026-04-26"
      }
    }
  },
  "daily_scores": [
    { "date": "2026-04-13", "overall": 55, "skills": 50, "agents": 50, "rules": 60, "memory": 60 },
    { "date": "2026-04-14", "overall": 57, "skills": 52, "agents": 50, "rules": 62, "memory": 65 },
    { "date": "2026-04-15", "overall": 60, "skills": 55, "agents": 52, "rules": 65, "memory": 68 },
    { "date": "2026-04-20", "overall": 65, "skills": 60, "agents": 55, "rules": 70, "memory": 75 },
    { "date": "2026-04-25", "overall": 72, "skills": 68, "agents": 55, "rules": 78, "memory": 88 },
    { "date": "2026-04-26", "overall": 72.5, "skills": 68, "agents": 55, "rules": 78, "memory": 90 }
  ],
  "recent_evolutions": [
    { "date": "2026-04-25", "dimension": "skill", "target": "karpathy-guidelines", "action": "追加触发词: code review, 审查代码", "effect": "+5 匹配率" },
    { "date": "2026-04-20", "dimension": "agent", "target": "backend-developer", "action": "追加常见陷阱: JacksonTypeHandler + ::text[] 不兼容", "effect": "无显著变化" },
    { "date": "2026-04-18", "dimension": "memory", "target": "feedback_no_lombok", "action": "新增记忆: 项目不使用 Lombok", "effect": "已加载到后续会话" }
  ],
  "alerts": [
    { "level": "warning", "dimension": "agent", "target": "frontend-developer", "message": "熔断器断开，连续 2 次进化无改善，需要人工检查" },
    { "level": "info", "dimension": "memory", "message": "2 个用户反馈信号待处理" }
  ]
}
```

### 15.5 仪表盘 CLI

```bash
# 查看进化仪表盘
python3 .claude/lib/evolution_dashboard.py

# 输出示例:
#
# ╔══════════════════════════════════════════════════════════╗
# ║            🧬 进化仪表盘 (2026-04-26)                    ║
# ╠══════════════════════════════════════════════════════════╣
# ║  整体健康度: 72.5/100 (B)  📈 上升                       ║
# ║  累计进化: 12次  |  追踪天数: 14天                       ║
# ╠══════════════════════════════════════════════════════════╣
# ║                                                          ║
# ║  Skills    ████████████░░░░░░░░  68/100  B  📈          ║
# ║  Agents    ██████████░░░░░░░░░░  55/100  C  📉          ║
# ║  Rules     ███████████████░░░░░  78/100  B  ➡️          ║
# ║  Memory    ██████████████████░░  90/100  A  📈          ║
# ║                                                          ║
# ╠══════════════════════════════════════════════════════════╣
# ║  ⚠️ 告警:                                                ║
# ║  · frontend-developer 熔断器断开 (连续退化)              ║
# ║  · 2 个 Memory 信号待处理                                 ║
# ╠══════════════════════════════════════════════════════════╣
# ║  最近进化:                                                ║
# ║  · 04-25 skill:karpathy-guidelines (+5% 匹配)           ║
# ║  · 04-20 agent:backend-developer (无显著变化)            ║
# ║  · 04-18 memory:feedback_no_lombok (新增)               ║
# ╚══════════════════════════════════════════════════════════╝
```

### 15.6 仪表盘数据生成

```python
# .claude/lib/evolution_dashboard.py

"""
进化仪表盘生成器。
每次 Stop 时由 evolution_orchestrator 调用，更新 dashboard 数据。
"""

def generate_dashboard():
    """生成最新的仪表盘数据"""
    metrics = load_json("data/evolution_metrics.json")
    history = read_jsonl("data/evolution_history.jsonl")
    dashboard = load_json("data/evolution_dashboard.json") or {}

    scorer = EvolutionScorer()

    # 评分各维度
    skill_scores = {}
    for name, m in metrics.get("skills", {}).items():
        skill_scores[name] = scorer.score_skill(name, m)

    agent_scores = {}
    for name, m in metrics.get("agents", {}).items():
        agent_scores[name] = scorer.score_agent(name, m)

    rule_scores = {}
    for name, m in metrics.get("rules", {}).items():
        rule_scores[name] = scorer.score_rule(name, m)

    memory_score = scorer.score_memory(metrics.get("memory", {}))

    # 计算维度总分
    skills_total = avg([s["total"] for s in skill_scores.values()]) if skill_scores else 50
    agents_total = avg([s["total"] for s in agent_scores.values()]) if agent_scores else 50
    rules_total = avg([s["total"] for s in rule_scores.values()]) if rule_scores else 50
    memory_total = memory_score["total"]

    overall = (skills_total + agents_total + rules_total + memory_total) / 4

    # 今日分数追加到 daily_scores
    today = datetime.now().strftime("%Y-%m-%d")
    daily = dashboard.get("daily_scores", [])
    if not daily or daily[-1]["date"] != today:
        daily.append({
            "date": today,
            "overall": round(overall, 1),
            "skills": round(skills_total, 1),
            "agents": round(agents_total, 1),
            "rules": round(rules_total, 1),
            "memory": round(memory_total, 1),
        })
    else:
        daily[-1] = {
            "date": today,
            "overall": round(overall, 1),
            "skills": round(skills_total, 1),
            "agents": round(agents_total, 1),
            "rules": round(rules_total, 1),
            "memory": round(memory_total, 1),
        }
    # 只保留最近 30 天
    daily = daily[-30:]

    dashboard = {
        "generated_at": datetime.now().isoformat(),
        "overall_score": round(overall, 1),
        "overall_grade": scorer._grade(overall),
        "total_evolutions": metrics.get("system", {}).get("total_evolutions", 0),
        "days_tracked": len(daily),
        "summary": generate_summary(overall, skill_scores, agent_scores, rule_scores, memory_score),
        "dimensions": {
            "skills": {"score": round(skills_total, 1), "targets": skill_scores},
            "agents": {"score": round(agents_total, 1), "targets": agent_scores},
            "rules": {"score": round(rules_total, 1), "targets": rule_scores},
            "memory": {"score": round(memory_total, 1), "targets": memory_score},
        },
        "daily_scores": daily,
        "recent_evolutions": history[-5:],  # 最近 5 次进化
        "alerts": generate_alerts(metrics, agent_scores),
    }

    safe_write_json(Path("data/evolution_dashboard.json"), dashboard)

def generate_summary(overall, skills, agents, rules, memory):
    """生成人类可读的进化摘要，控制在 100 字以内"""
    parts = []
    if overall >= 70: parts.append("系统整体健康")
    elif overall >= 50: parts.append("系统运行正常，部分维度需关注")
    else: parts.append("系统需要人工介入")

    # 找出最优和最差维度
    dims = {"Skills": skills, "Agents": agents, "Rules": rules, "Memory": memory}
    best = max(dims, key=lambda k: dims[k]["total"] if isinstance(dims[k], dict) else dims[k])
    worst = min(dims, key=lambda k: dims[k]["total"] if isinstance(dims[k], dict) else dims[k])
    parts.append(f"{best} 表现最好，{worst} 需关注")
    return "。".join(parts)
```

### 15.7 SessionStart 注入进化摘要（极简版，< 200 字）

```python
# load_evolution_state.py 的输出（stdout → 注入上下文）

def generate_context_injection():
    dashboard = load_json("data/evolution_dashboard.json")
    if not dashboard:
        return ""

    alerts = dashboard.get("alerts", [])
    recent = dashboard.get("recent_evolutions", [])[:3]

    lines = [f"🧬 进化: {dashboard['overall_score']}/100 ({dashboard['overall_grade']})"]
    lines.append(f"   S{dashboard['dimensions']['skills']['score']:.0f}"
                 f" A{dashboard['dimensions']['agents']['score']:.0f}"
                 f" R{dashboard['dimensions']['rules']['score']:.0f}"
                 f" M{dashboard['dimensions']['memory']['score']:.0f}")

    if alerts:
        lines.append(f"   ⚠️ {len(alerts)} 个告警")

    return "\n".join(lines)
    # 输出示例:
    # 🧬 进化: 72/100 (B)
    #    S68 A55 R78 M90
    #    ⚠️ 1 个告警
```

---

## 十六、Token 效率设计

### 16.1 核心原则

```
┌─────────────────────────────────────────────────────────────┐
│              TOKEN 效率金字塔                                │
│                                                             │
│                     ┌──────────┐                            │
│                     │ 全量数据  │  ← 仅在进化 Agent 执行时    │
│                     │ (分析用) │     加载，且按需采样         │
│                    ┌┴──────────┴┐                           │
│                    │  摘要数据   │  ← Stop 时计算，            │
│                    │ (决策用)   │     < 500 字               │
│                   ┌┴────────────┴┐                          │
│                   │  仪表盘数据   │  ← SessionStart 注入，     │
│                   │  (感知用)    │     < 200 字              │
│                  ┌┴──────────────┴┐                         │
│                  │  无上下文占用   │  ← 原始 JSONL，           │
│                  │  (存储用)      │     永不到 LLM            │
│                  └───────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### 16.2 各组件 Token 预算

| 组件 | 触发时机 | Token 预算 | 加载策略 |
|------|---------|-----------|---------|
| **SessionStart 注入** | 每次会话启动 | ≤ 200 字 | 总是加载（仪表盘摘要） |
| **Evolution Orchestrator stdout** | 每次 Stop | ≤ 500 字 | 总是加载（触发建议） |
| **SkillEvolver 输入** | 触发进化时 | ≤ 3000 字 | 按需加载（目标 Skill + 摘要数据） |
| **AgentEvolver 输入** | 触发进化时 | ≤ 3000 字 | 按需加载（目标 Agent + 摘要数据） |
| **RuleEvolver 输入** | 触发进化时 | ≤ 2000 字 | 按需加载（目标 Rule + 违规摘要） |
| **MemoryEvolver 输入** | 触发进化时 | ≤ 1500 字 | 按需加载（信号内容 + MEMORY.md） |
| **原始 JSONL 数据** | 永不 | 0 字 | 永不到 LLM，只被 Python 解析 |

### 16.3 数据渐进式加载策略

```python
# .claude/lib/token_efficiency.py

"""
Token 效率管理：三层加载策略。

Layer 1: 元数据层 (≤ 200 tokens) — 总是可用
  进化仪表盘摘要: 总分 + 各维度分 + 告警数
  加载时机: SessionStart 注入

Layer 2: 摘要层 (≤ 1000 tokens) — Stop 时计算
  各维度触发建议 + session_summary
  加载时机: Stop hook stdout

Layer 3: 详情层 (≤ 5000 tokens) — 进化 Agent 按需加载
  目标文件的当前内容 + 相关数据的统计摘要（非原始数据）
  加载时机: 进化 Agent 执行时
"""

class TokenBudget:
    """Token 预算管理器"""

    # 各层的 token 上限（1 token ≈ 0.75 英文词 ≈ 0.5 中文词）
    L1_METADATA = 200      # SessionStart 注入
    L2_SUMMARY = 1000      # Stop orchestrator 输出
    L3_DETAIL = 5000       # 进化 Agent 输入

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算文本的 token 数量"""
        # 粗略估算：英文 0.75 词/token，中文 0.5 字/token
        import re
        en_words = len(re.findall(r'[a-zA-Z]+', text))
        cn_chars = len(re.findall(r'[一-鿿]', text))
        return int(en_words / 0.75 + cn_chars / 0.5)

    @staticmethod
    def truncate_to_budget(text: str, max_tokens: int) -> str:
        """截断文本到指定 token 预算"""
        if TokenBudget.estimate_tokens(text) <= max_tokens:
            return text
        # 二分截断
        lines = text.split("\n")
        result = []
        current = 0
        for line in lines:
            line_tokens = TokenBudget.estimate_tokens(line)
            if current + line_tokens > max_tokens:
                result.append(f"... (截断，剩余 {len(lines) - len(result)} 行)")
                break
            result.append(line)
            current += line_tokens
        return "\n".join(result)

    @staticmethod
    def check_budget(label: str, text: str, budget: int):
        """检查是否超出预算，超出时 stderr 告警"""
        estimated = TokenBudget.estimate_tokens(text)
        if estimated > budget:
            print(f"⚠️ Token 预算超支 [{label}]: {estimated} > {budget}", file=sys.stderr)
            return False
        return True
```

### 16.4 数据压缩策略

```python
def summarize_for_evolver(dimension: str, target: str, raw_data: list) -> dict:
    """
    将原始 JSONL 数据压缩为进化 Agent 所需的结构化摘要。
    进化 Agent 永远不读原始 JSONL，只读摘要。

    压缩比目标: 100:1 (100 条原始记录 → 1 个摘要对象)
    """
    if dimension == "skill":
        return {
            "total_calls": len(raw_data),
            "unique_sessions": len(set(r["session_id"] for r in raw_data)),
            "call_timeline": _compress_timeline([r["timestamp"] for r in raw_data]),
            # 不需要: 每条记录的完整 JSON
        }

    if dimension == "agent":
        return {
            "total_launches": len(raw_data),
            "task_types": _cluster_tasks([r.get("task", "") for r in raw_data]),
            "time_distribution": _hourly_distribution([r["timestamp"] for r in raw_data]),
            "avg_prompt_length": avg([len(r.get("prompt_preview", "")) for r in raw_data]),
            # 不需要: 每个 prompt 的完整文本
        }

    if dimension == "rule":
        # 按规则 + 严重性分组统计
        by_rule = {}
        for r in raw_data:
            rule = r.get("rule", "unknown")
            severity = r.get("severity", "low")
            by_rule.setdefault(rule, {}).setdefault(severity, 0)
            by_rule[rule][severity] += 1
        return {
            "violations_by_rule": by_rule,
            "total": len(raw_data),
            "most_violated_file": _most_common([r.get("file", "") for r in raw_data]),
            # 不需要: 每个违规的完整 file_path + timestamp
        }

    return {"summary": f"{len(raw_data)} records"}


def _compress_timeline(timestamps: list) -> dict:
    """将时间戳列表压缩为按天的计数"""
    by_day = {}
    for ts in timestamps:
        day = ts[:10]  # "2026-04-26"
        by_day[day] = by_day.get(day, 0) + 1
    return {
        "earliest": min(timestamps)[:10] if timestamps else None,
        "latest": max(timestamps)[:10] if timestamps else None,
        "by_day": by_day,
        "trend": "increasing" if len(by_day) >= 3 and _is_increasing(by_day) else "stable"
    }
```

### 16.5 Evolution Orchestrator 的 Token 高效输出

```python
# evolution_orchestrator.py 的 stdout — 严格控制 Token

def output_compact_decision(triggers: list, session_summary: dict):
    """
    输出进化决策到 stdout。
    严格控制输出大小: ≤ 500 字 (~700 tokens)
    """
    if not triggers:
        # 情况 A: 无需进化 — 极简输出
        print(json.dumps({
            "evolve": False,
            "sum": f"domain={session_summary.get('domain','idle')}"
        }, ensure_ascii=False))
        return

    # 情况 B: 需要进化 — 紧凑输出
    compact_triggers = []
    for t in sorted(triggers, key=lambda x: x.get("priority", 0), reverse=True)[:3]:
        compact_triggers.append({
            "dim": t["dimension"][0],       # "s" / "a" / "r" / "m"
            "tgt": t["target"][:30],         # 目标名截断
            "p": round(t["priority"], 2),    # 优先级
            "why": t.get("reason", "")[:60], # 原因截断
        })

    print(json.dumps({
        "evolve": True,
        "sum": f"{session_summary.get('domain','?')}",
        "t": compact_triggers,               # triggers 缩写
    }, ensure_ascii=False))
    # 输出大小: ~200-300 字
```

### 16.6 进化 Agent 的按需加载

```
进化 Agent 执行时的数据加载顺序:

Step 1: 读目标文件 (必须)          ← ~2000 tokens
Step 2: 读数据摘要 (必须)          ← ~500 tokens  (summarize_for_evolver 的输出)
Step 3: 读最近进化历史 (必须)       ← ~300 tokens  (最近 3 条)
Step 4: 读原始数据样本 (按需)       ← 仅在摘要不够时，采样 5-10 条
Step 5: 读完整原始数据 (几乎从不)   ← 仅在调试/人工触发时

总 token 消耗:
  常态: Step 1 + 2 + 3 = ~2800 tokens
  需要采样: + 500 tokens = ~3300 tokens
  永远不超过: 5000 tokens (L3_DETAIL 预算)
```

### 16.7 上下文压缩：历史数据降维

```python
def compact_old_data():
    """
    将旧的原始 JSONL 数据压缩为统计摘要。
    保留最近 7 天的原始数据，7 天前的数据只保留统计摘要。

    压缩比: ~200:1
    """
    data_dir = Path(".claude/data")
    cutoff = datetime.now() - timedelta(days=7)

    for jsonl_file in data_dir.glob("*.jsonl"):
        recent = []
        old_records = []

        for line in safe_read_lines(jsonl_file):
            record = safe_parse_line(line)
            if not record:
                continue
            ts = datetime.fromisoformat(record.get("timestamp", "2000-01-01"))
            if ts > cutoff:
                recent.append(record)
            else:
                old_records.append(record)

        if old_records:
            # 写入统计摘要
            summary_file = data_dir / f"{jsonl_file.stem}_archive_summary.json"
            summary = {
                "compacted_at": datetime.now().isoformat(),
                "original_count": len(old_records),
                "date_range": f"{min(r['timestamp'] for r in old_records)[:10]} ~ {max(r['timestamp'] for r in old_records)[:10]}",
                "stats": compute_basic_stats(old_records),
            }
            safe_write_json(summary_file, summary)

        # 重写为仅保留近期数据
        tmp_file = jsonl_file.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            for r in recent:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp_file, jsonl_file)
```

### 16.8 Token 效率检查清单

```python
TOKEN_CHECKS = {
    "SessionStart 注入": {"budget": 200, "actual": 0, "check": "每次启动"},
    "Stop orchestrator 输出": {"budget": 500, "actual": 0, "check": "每次停止"},
    "进化 Agent 总输入": {"budget": 5000, "actual": 0, "check": "触发进化时"},
    "原始 JSONL 暴露给 LLM": {"budget": 0, "actual": 0, "check": "绝对禁止"},
    "Skill 数据摘要大小": {"budget": 500, "actual": 0, "check": "触发时"},
    "Agent 数据摘要大小": {"budget": 500, "actual": 0, "check": "触发时"},
    "仪表盘注入大小": {"budget": 200, "actual": 0, "check": "每次启动"},
}

def audit_token_usage():
    """Token 效率审计，在所有 Hook 脚本退出前检查"""
    violations = []
    for label, spec in TOKEN_CHECKS.items():
        if spec["actual"] > spec["budget"]:
            violations.append(f"{label}: {spec['actual']} > {spec['budget']}")
    if violations:
        print(f"⚠️ Token 预算违规:\n" + "\n".join(violations), file=sys.stderr)
```

### 16.9 设计决策：什么永远不给 LLM

```
❌ 永不进入 LLM 上下文:
   · 原始 JSONL 文件内容（Python 脚本解析后只传摘要）
   · 完整的 agent-invocations 历史
   · 完整的 session 记录
   · 未压缩的违规列表
   · 其他维度的详细数据（SkillEvolver 只看 Skill 数据）

✅ 可以进入 LLM 上下文:
   · 仪表盘摘要（SessionStart，< 200 字）
   · 触发建议（Stop orchestrator，< 500 字）
   · 目标文件当前内容（进化 Agent，~2000 字）
   · 目标维度的数据摘要（进化 Agent，~500 字）
   · 最近 3 条进化历史（进化 Agent，~300 字）
```

---

## 附录 A：文件清单

| 文件路径 | 类型 | 用途 | Git |
|---------|------|------|-----|
| `.claude/docs/evolution-system-design.md` | 文档 | 本设计文档 | 提交 |
| `.claude/agents/skill-evolver.md` | Agent | Skill 进化器 | 提交 |
| `.claude/agents/agent-evolver.md` | Agent | Agent 进化器 | 提交 |
| `.claude/agents/rule-evolver.md` | Agent | Rule 进化器 | 提交 |
| `.claude/agents/memory-evolver.md` | Agent | Memory 进化器 | 提交 |
| `.claude/hooks/scripts/collect_agent_launch.py` | Hook | Agent 启动采集 | 提交 |
| `.claude/hooks/scripts/collect_skill_usage.py` | Hook | Skill 使用采集 | 提交 |
| `.claude/hooks/scripts/collect_tool_failure.py` | Hook | 失败采集 | 提交 |
| `.claude/hooks/scripts/collect_violations.py` | Hook | 违规采集 | 提交 |
| `.claude/hooks/scripts/detect_feedback.py` | Hook | 反馈信号检测 | 提交 |
| `.claude/hooks/scripts/evolution_orchestrator.py` | Hook | 进化编排器 | 提交 |
| `.claude/hooks/scripts/load_evolution_state.py` | Hook | 状态加载 | 提交 |
| `.claude/lib/evolution_safety.py` | 库 | 安全防护+回滚+熔断 | 提交 |
| `.claude/lib/evolution_scoring.py` | 库 | 评分引擎 | 提交 |
| `.claude/lib/evolution_dashboard.py` | 库 | 仪表盘生成 | 提交 |
| `.claude/lib/token_efficiency.py` | 库 | Token 效率管理 | 提交 |
| `.claude/data/skill_usage.jsonl` | 数据 | Skill 使用记录 | 忽略 |
| `.claude/data/agent_performance.jsonl` | 数据 | Agent 执行记录 | 忽略 |
| `.claude/data/rule_violations.jsonl` | 数据 | 规则违规记录 | 忽略 |
| `.claude/data/tool_failures.jsonl` | 数据 | 工具失败记录 | 忽略 |
| `.claude/data/pending_evolution.json` | 数据 | 待处理进化信号 | 忽略 |
| `.claude/data/evolution_history.jsonl` | 数据 | 进化审计日志 | 忽略 |
| `.claude/data/evolution_metrics.json` | 数据 | 进化效果指标 | 忽略 |
| `.claude/data/evolution_dashboard.json` | 数据 | 进化仪表盘 | 忽略 |
| `.claude/data/backups/` | 备份 | 进化前文件快照 | 忽略 |
