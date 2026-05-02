# 自动进化系统（Auto-Evolve）技术文档

> 全自动闭环进化系统 — 无需人工观察，持续自我优化

## 目录

1. [核心特性](#核心特性)
2. [架构概览](#架构概览)
3. [工作原理](#工作原理)
4. [核心模块](#核心模块)
5. [工作流程](#工作流程)
6. [配置说明](#配置说明)
7. [操作手册](#操作手册)
8. [数据流](#数据流)
9. [决策引擎](#决策引擎)
10. [验证闭环](#验证闭环)
11. [风险控制](#风险控制)

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **自动启动** | 插件安装后自动启动调度器，无需手动配置 |
| **心跳检测** | 每 3 小时检查是否需要进化，防止长期不进化 |
| **双模式触发** | 支持外部（cron）和内置定时任务两种模式 |
| **观察期验证** | 改动进入 7 天观察期，自动监控效果 |
| **自动回滚** | 效果不好时自动回滚，保证系统稳定 |
| **时间衰减** | 旧数据置信度逐渐下降，保持系统敏锐度 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         自动进化闭环系统                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌──────────────┐     ┌─────────────────────────────┐  │
│  │ Claude Code │────▶│   Hook 采集   │────▶│    sessions.jsonl          │  │
│  │   会话       │     │  (自动触发)   │     │    (数据存储)               │  │
│  └─────────────┘     └──────────────┘     └─────────────┬───────────────┘  │
│                                                         │                   │
│                                                         ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      调度器层 (Scheduler)                            │   │
│  │  ┌─────────────────────┐        ┌─────────────────────┐            │   │
│  │  │  定时进化任务        │        │  心跳检测任务         │            │   │
│  │  │  (scheduler_interval│        │  (heartbeat_check    │            │   │
│  │  │   = 30 minutes)     │        │   = 180 minutes)     │            │   │
│  │  └─────────────────────┘        └─────────────────────┘            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                         │                   │
│                                                         ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      分析层 (Analyzer)                               │   │
│  │  • 纠正热点分析     • 失败模式分析     • 技能覆盖分析               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                         │                   │
│                                                         ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      决策层 (LLM Decision)                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                     │   │
│  │  │ auto_apply │  │  propose   │  │   skip     │                     │   │
│  │  │ (低风险)   │  │ (高风险)   │  │ (数据不足) │                     │   │
│  │  └────────────┘  └────────────┘  └────────────┘                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                         │                   │
│                                          ┌──────────────┴───────────────┐ │
│                                          ▼                               │ │
│  ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────┐ │ │
│  │  备份 (backups/)   │◀───│  应用改动            │    │  提案生成   │ │ │
│  │  原文件            │    │  (agents/*.md)      │    │  (propose)  │ │ │
│  └─────────────────────┘    └─────────────────────┘    └─────────────┘ │ │
│                                                         │               │ │
│                                                         ▼               │ │
│  ┌─────────────────────────────────────────────────────────────────┐     │ │
│  │                      观察期验证 (7天)                             │     │ │
│  │  ┌─────────────────┐              ┌─────────────────┐           │     │ │
│  │  │ 指标恶化 → 回滚  │              │ 指标稳定 → 固化  │           │     │ │
│  │  └─────────────────┘              └─────────────────┘           │     │ │
│  └─────────────────────────────────────────────────────────────────┘     │ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 工作原理

### 1. 数据采集层

Claude Code 每次会话结束时，Hook 自动采集数据：

```
会话结束 → Stop Hook → collect-session.py → sessions.jsonl
```

**采集内容**：
- 会话元数据（时长、模式、使用的 agents）
- Agent 调用统计
- 工具失败记录
- 用户纠正信息
- Git 变更统计

### 2. 调度器层

调度器是整个系统的核心，负责触发进化分析：

```
┌─────────────────────────────────────────────────────────────────┐
│                        调度器工作原理                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  启动方式：                                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 方式1: SessionStart Hook 自动启动                        │    │
│  │   hooks.json → auto-start-evolve.py → Scheduler.start() │    │
│  │                                                         │    │
│  │ 方式2: 手动启动                                          │    │
│  │   python3 daemon.py start                               │    │
│  │                                                         │    │
│  │ 方式3: 外部 cron 触发                                    │    │
│  │   */30 * * * * python3 daemon.py run                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  任务类型：                                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 任务1: 定时进化任务                                       │    │
│  │   • 每 30 分钟（可配置）执行一次                          │    │
│  │   • 检查是否满足触发条件                                   │    │
│  │   • 满足条件则执行完整分析                                 │    │
│  │                                                         │    │
│  │ 任务2: 心跳检测任务                                       │    │
│  │   • 每 3 分钟（与进化任务同频率）检查                      │    │
│  │   • 读取 analysis_state.json 获取上次进化时间             │    │
│  │   • 如果超过 3 小时未进化，触发紧急进化                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  触发条件：                                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ ✓ 新会话数 >= min_new_sessions (默认 2)                   │    │
│  │ ✓ 同一 target 被同一模式纠正 >= min_same_pattern (默认 3)  │    │
│  │ ✓ 距上次分析 >= max_hours_since_last_analyze (默认 6h)   │    │
│  │ ✓ 心跳检测：超过 heartbeat_check_minutes (默认 180min)   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3. 分析层

Analyzer 分析采集的数据，输出热点和模式：

```python
{
    "total_sessions": 10,
    "correction_hotspots": {"agent:backend-dev": 5},
    "correction_patterns": {"print_debug": 5},
    "tool_failures": {"Read": 3, "Bash": 2},
    "should_propose": True,  # 是否需要优化
}
```

### 4. 决策层

LLM 根据分析结果做决策：

| 决策 | 条件 | 行为 |
|------|------|------|
| `auto_apply` | confidence >= 0.8 && risk_level == "low" | 直接修改文件 |
| `propose` | 新目标/高风险/多文件 | 生成提案等待人工确认 |
| `skip` | 数据不足 | 不干预 |

### 5. 验证闭环

改动应用后进入 7 天观察期：

```
Day 0: 应用改动，备份原文件
Day 1-7: 持续收集指标
Day 7: 评估
  ├── 指标恶化 → 自动回滚 → 降低 confidence
  └── 指标稳定 → 固化 → 增加 confidence
```

---

## 工作原理举例讲解

为了帮助你理解这个系统是如何工作的，我们用一个具体例子来说明：

**场景：backend-dev Agent 反复被用户纠正"不要使用 print 调试"**

### 第一步：数据采集

用户连续多次与 Claude Code 会话，每次都因为 `backend-dev` Agent 使用了 `print()` 调试而纠正它：

```json
// sessions.jsonl 中的记录
{"session_id": "s1", "corrections": [{"type": "print_debug", "target": "backend-dev"}]}
{"session_id": "s2", "corrections": [{"type": "print_debug", "target": "backend-dev"}]}
{"session_id": "s3", "corrections": [{"type": "print_debug", "target": "backend-dev"}]}
{"session_id": "s4", "corrections": [{"type": "print_debug", "target": "backend-dev"}]}
{"session_id": "s5", "corrections": [{"type": "print_debug", "target": "backend-dev"}]}
```

### 第二步：触发分析

调度器（每 30 分钟运行一次）检查发现：
- 新会话数 5 >= min_new_sessions 2 ✓
- 同一 target (backend-dev) 被同一模式纠正 5 次 >= min_same_pattern 3 ✓

满足触发条件，进入分析阶段。

### 第三步：Analyzer 分析

```python
# analyzer.py 输出
{
    "total_sessions": 10,
    "correction_hotspots": {"agent:backend-dev": 5},
    "correction_patterns": {"print_debug": 5},
    "primary_target": "agent:backend-dev",
    "should_propose": True,  # 热点明显，需要改进
}
```

### 第四步：LLM 决策

LLM 分析后做出决策：

```python
{
    "action": "auto_apply",   # 低风险，可以自动改
    "confidence": 0.88,       # 置信度 > 0.8
    "risk_level": "low",       # 只是一个调试习惯提示
    "target_file": "agents/backend-dev.md",
    "suggested_change": "在 ## 注意事项 后追加: 避免使用 print() 调试，推荐使用 logging 模块"
}
```

### 第五步：自动应用

```python
# apply_change.py 执行
1. 备份原文件 → .claude/data/backups/auto-xxx_backend-dev.md
2. 读取 agents/backend-dev.md
3. 在指定位置插入新内容
4. 记录到 proposal_history.json
5. 进入观察期
```

### 第六步：观察期（7天）

接下来的 7 天，系统继续收集数据，观察：

| 指标 | 基准值 | 7天后 | 判定 |
|------|--------|-------|------|
| success_rate | 0.85 | 0.87 | 提升 ✓ |
| failure_rate | 0.10 | 0.08 | 下降 ✓ |
| correction_rate | 0.15 | 0.05 | 大幅下降 ✓ |

### 第七步：固化

观察期结束，指标稳定：

```python
# instinct_updater.py 更新
{
    "id": "auto-xxx",
    "reinforcement_count": 1,  # 验证通过次数
    "confidence": 0.90,        # 从 0.88 提升到 0.90
    "consolidated_at": "2026-05-09T10:30:00"
}
```

### 第八步：时间衰减（长期）

90 天后，这条改进的置信度会衰减：

```
weight = 0.5 ^ (90 / 90) = 0.5
新 confidence = 0.90 * 0.5 = 0.45
```

这意味着：如果之后持续纠正 Agent"不要使用 print"，系统会认为这个改动已经"过时"，需要重新验证。

---

## 核心模块

| 文件 | 作用 | 触发时机 |
|------|------|----------|
| `daemon.py` | 主入口，支持 check/run/start/stop | 外部调用 |
| `scheduler.py` | 内置定时任务调度器 | 自动触发 |
| `analyzer.py` | 数据分析 | daemon 调用 |
| `llm_decision.py` | LLM 决策引擎 | daemon 调用 |
| `apply_change.py` | 自动应用改动 | 决策后调用 |
| `rollback.py` | 自动回滚 | 观察期触发 |
| `instinct_updater.py` | 本能更新/衰减 | 定期调用 |

### Hook 采集模块

| 文件 | 作用 | 触发时机 |
|------|------|----------|
| `collect-session.py` | 收集会话元数据 | Stop Hook |
| `collect-agent.py` | 记录 Agent 调用 | PostToolUse[Agent] |
| `collect-failure.py` | 记录工具失败 | PostToolUseFailure |
| `collect-skill.py` | 记录 Skill 使用 | PostToolUse[Skill] |
| `auto-start-evolve.py` | 自动启动调度器 | SessionStart Hook |

---

## 工作流程

### 完整闭环流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         自动进化闭环系统                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [用户会话]                                                                 │
│       ↓                                                                    │
│   [Hook 数据采集] ──→ sessions.jsonl                                         │
│       ↓                         ↓                                          │
│   [阈值预筛选] ───────────→ [触发分析]                                       │
│       ↓                                                                    │
│   [LLM 分析] ───────────→ [LLM 决策]                                         │
│       ↓                                                                    │
│   ├── auto_apply ──→ [直接修改文件] ──→ [备份] ──→ [记录历史] ──→ [观察期]   │
│   ├── propose ────→ [生成提案]                                              │
│   └── skip ───────→ [无需干预]                                              │
│       ↓                                                                    │
│   [观察期验证]                                                               │
│       ↓                                                                    │
│   ├── 指标恶化 ──→ [自动回滚] ──→ [降低 confidence]                          │
│   └── 指标稳定 ──→ [固化] ──→ [增强 confidence]                             │
│       ↓                                                                    │
│   [时间衰减] ──→ [旧数据置信度自动下降]                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

详细步骤：
1. 用户与 Claude Code 会话
2. 会话结束时，Hook 自动采集数据写入 sessions.jsonl
3. 首次会话时，SessionStart Hook 自动启动调度器
4. 调度器按配置间隔（默认 30 分钟）检查触发条件
5. 心跳检测（默认 3 小时）确保长期未进化时自动触发
6. 满足条件 → analyzer 分析数据
7. analyzer 输出热点和模式 → llm_decision 做决策
8. 决策结果：
   - auto_apply: 低风险高置信 → 直接改文件
   - propose: 高风险/新目标 → 生成提案等待人工确认
   - skip: 数据不足 → 不干预
9. 改动进入 7 天观察期
10. 观察期内持续收集指标，评估改动效果
11. 效果不好 → 自动回滚；效果稳定 → 固化并增强置信度
12. 时间衰减：旧数据置信度逐渐下降，确保系统不会固步自封
```

### 数据采集流程

```
Stop Hook 触发
    ↓
读取 .session_start 文件（获取开始时间、模式）
    ↓
聚合 agent_calls.jsonl（统计 agents 使用情况）
    ↓
聚合 failures.jsonl（统计失败类型、工具）
    ↓
执行 git diff（统计文件变更）
    ↓
构建 session 对象
    ↓
写入 sessions.jsonl
    ↓
返回收集结果
```

---

## 配置说明

**配置文件**: `evolve-daemon/config.yaml`

详细配置说明请参考配置文件内的注释。

### 关键配置项

```yaml
daemon:
  mode: both                      # both = 外部+内置都支持
  scheduler_interval: 30 minutes  # 定时任务间隔
  run_on_startup: false           # 启动时立即运行
  heartbeat_check_minutes: 180     # 心跳检测间隔（3小时）
  auto_start_on_install: true      # 安装时自动启动

thresholds:
  min_new_sessions: 2              # 最少新会话数
  min_same_pattern_corrections: 3   # 同一模式被纠正次数

observation:
  days: 7                          # 观察期天数

decay:
  half_life_days: 90               # 置信度半衰期
```

---

## 操作手册

### 快速开始

**方式一：自动启动（推荐）**

插件安装后，首次使用 Claude Code 时，SessionStart Hook 会自动启动调度器。

**方式二：手动启动**

```bash
cd evolve-daemon
pip install APScheduler
python3 daemon.py start
```

### 查看状态

```bash
# 查看调度器状态
cd evolve-daemon && python3 scheduler.py status

# 查看系统状态
cd evolve-daemon && python3 daemon.py status

# 检查触发条件
cd evolve-daemon && python3 daemon.py check
```

### 停止调度器

```bash
cd evolve-daemon && python3 daemon.py stop
```

### 手动触发分析

```bash
cd evolve-daemon && python3 daemon.py run
```

### macOS 配置 launchd（外部触发）

```bash
cd evolve-daemon
python3 daemon.py install-launchd
launchctl load ~/Library/LaunchAgents/com.claude-harness-kit.evolve.plist
```

### Linux 配置 systemd

```bash
# 创建 service 文件
sudo tee /etc/systemd/system/claude-evolve.service > /dev/null << 'EOF'
[Unit]
Description=Claude Harness Kit Auto-Evolve

[Service]
Type=oneshot
WorkingDirectory=/path/to/project
ExecStart=/usr/bin/python3 /path/to/project/evolve-daemon/daemon.py run
Environment="CLAUDE_PROJECT_DIR=/path/to/project"
EOF

# 创建 timer 文件
sudo tee /etc/systemd/system/claude-evolve.timer > /dev/null << 'EOF'
[Unit]
Description=Claude Harness Kit Auto-Evolve Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec=4h
Unit=claude-evolve.service

[Install]
WantedBy=timers.target
EOF

# 启用
sudo systemctl daemon-reload
sudo systemctl enable claude-evolve.timer
sudo systemctl start claude-evolve.timer
```

---

## 数据流

### 输入数据

| 文件 | 来源 | 内容 |
|------|------|------|
| `sessions.jsonl` | collect-session.py | 会话元数据 |
| `agent_calls.jsonl` | collect-agent.py | Agent 调用记录 |
| `failures.jsonl` | collect-failure.py | 工具失败记录 |
| `instinct-record.json` | instinct_updater.py | 本能记录 |

### 输出数据

| 文件 | 用途 |
|------|------|
| `proposals/*.md` | 改进提案 |
| `proposal_history.json` | 提案历史 |
| `analysis_state.json` | 分析状态 |
| `instinct-record.json` | 更新后的本能记录 |
| `.claude/data/backups/*` | 文件备份 |

---

## 决策引擎

### 决策流程

```
输入: sessions, analysis, config
    ↓
规则检查:
    ↓
├── 安全相关? ──→ 强制 propose
├── 新目标? ────→ 强制 propose
├── 高风险模式? ──→ 强制 propose
└── 通过 ↓
    ↓
LLM 评估:
    ↓
├── confidence >= 0.8 && risk_level == "low" → auto_apply
├── 新目标/高风险 → propose
└── 数据不足 → skip
    ↓
输出决策
```

### LLM Prompt 示例

```
你是 AI 工程规范进化助手。分析使用数据，判断是否需要改进 Agent/Skill/Rule 定义。

决策选项：
1. auto_apply: 置信度极高，风险极低，可以自动应用
2. propose: 需要人工 Review，生成提案
3. skip: 数据不足以支撑建议

决策规则：
- 低风险（comment/format/typo/docs） + 高置信（>= 0.8）→ auto_apply
- 新目标、未验证的改动 → propose
- 高风险（安全/权限/新目标/多文件）→ propose
- 数据不足以支撑明确建议 → skip

输出格式（JSON）：
{
  "action": "auto_apply" | "propose" | "skip",
  "reason": "决策理由",
  "confidence": 0.0-1.0,
  "target_file": "agents/xxx.md 或 skills/xxx/SKILL.md",
  "suggested_change": "具体改动内容",
  "risk_level": "low" | "medium" | "high"
}
```

---

## 验证闭环

### 观察期验证流程

```
Day 0: 应用改动
    ↓
Day 1-7: 收集指标
    ↓
Day 7: 评估
    ↓
├── 指标恶化 → 回滚 → 降低 confidence
└── 指标稳定 → 固化 → 增强 confidence
```

### 回滚触发条件

```python
def should_rollback(metrics, baseline, config):
    # 成功率下降 > 10%
    if success_rate_delta < -0.10:
        return True

    # 纠正率上升 > 20%
    if correction_rate > baseline * 1.20:
        return True

    # 失败率上升 > 10%
    if failure_rate > baseline * 1.10:
        return True

    return False
```

### 熔断器逻辑

```python
# 最近一周回滚 >= 5 次 → 暂停系统
if rollbacks_last_week >= 5:
    pause_system(days=30)

# 同一 target 连续被拒 >= 3 次 → 暂停该 target
if consecutive_rejects >= 3:
    pause_target(days=30)
```

---

## 风险控制

### 三层防护

| 层级 | 机制 | 作用 |
|------|------|------|
| **规则层** | 高风险模式检测 | 阻止危险改动 |
| **LLM 层** | 置信度评估 | 确保改动质量 |
| **指标层** | 观察期验证 | 快速发现回滚 |

### 文件备份

- 备份目录: `.claude/data/backups/`
- 备份命名: `{decision_id}_{filename}`
- 恢复机制: `apply_change.py` → `rollback_proposal()`

---

## 文件结构

```
.
├── evolve-daemon/
│   ├── config.yaml           # 统一配置（含详细注释）
│   ├── daemon.py             # 主入口
│   ├── scheduler.py           # 内置调度器
│   ├── analyzer.py            # 数据分析
│   ├── llm_decision.py        # LLM 决策引擎
│   ├── apply_change.py        # 自动应用
│   ├── rollback.py            # 自动回滚
│   ├── instinct_updater.py    # 时间衰减
│   └── proposer.py            # 提案生成
│
├── hooks/bin/
│   ├── collect-session.py     # 会话采集
│   ├── collect-agent.py       # Agent 调用记录
│   ├── collect-failure.py     # 失败记录
│   ├── collect-skill.py       # Skill 使用记录
│   └── auto-start-evolve.py   # 自动启动调度器
│
├── instinct/
│   └── instinct-record.json   # 本能记录
│
└── .claude/data/
    ├── sessions.jsonl         # 会话日志
    ├── agent_calls.jsonl       # Agent 调用
    ├── failures.jsonl          # 失败记录
    ├── proposal_history.json    # 提案历史
    ├── analysis_state.json      # 分析状态
    └── backups/                # 文件备份
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-05-02 | 初始版本，全自动闭环实现 |
| 1.1 | 2026-05-02 | 增加心跳检测、内置调度器、自动启动 |