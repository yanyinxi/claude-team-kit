# Harness Engineering 借鉴方案：Claude Harness Kit 自进化能力升级

## 一、调研概要

通过对 OpenAI Harness Engineering 方法论和 Harness CI/CD 平台的深度分析，提炼出两大来源的可借鉴模式：

| 来源 | 核心思想 | 关键机制 |
|------|---------|---------|
| **OpenAI Harness Engineering** | Human steers, Agents execute | Symphony 编排器、知识生命周期、GC Agent、意图失败检测 |
| **Harness CI/CD Platform** | Self-healing pipelines | AutoFix Agent、AI 验证+自动回滚、持续验证、优化建议 |

---

## 二、当前项目差距分析

### 2.1 我们已有的

| 模块 | 能力 | 成熟度 |
|------|------|:--:|
| `evolve-daemon/` | 数据采集 → 语义提取 → 分析 → 提案 | 基础 |
| `agents/learner.md` | Instinct 系统，置信度 0.3→0.5→0.7→0.9 | 基础 |
| `rules/quality-gates.md` | 每阶段出口条件 | 基础 |
| `instinct/instinct-record.json` | 用户纠正记录 | 空库 |
| `hooks/bin/collect-*.py` | 会话/Agent/Skill 数据采集 | 可用 |
| `agents/orchestrator.md` | 多 Agent 并行编排 | 可用 |

### 2.2 我们缺失的（对标 Harness Engineering）

| 能力 | Harness Engineering 做法 | 我们的差距 |
|------|-------------------------|-----------|
| **知识生命周期** | 5 层架构 + 3 级成熟度 + 自动衰减 | 无 |
| **垃圾回收 Agent** | 定期扫描模式漂移，自动提交修复 PR | 无 |
| **意图失败检测** | "遵循了规则但错过了产品意图"的捕获 | 无 |
| **进化自动回滚** | 提案导致质量下降 → 自动回滚 | 无 |
| **渐进式知识加载** | 3 级索引（50行目录→300行分类→完整条目） | 无 |
| **优化建议引擎** | 参数调优、模型切换、流水线并行化建议 | 无 |

---

## 三、技术方案

### 3.1 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                   Claude Harness Kit v2.1                   │
├─────────────────────────────────────────────────────────┤
│  Layer 4: 持续治理 (Continuous Governance)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ 知识生命 │ │ GC Agent │ │ 意图检测 │ │ 进化回滚   │ │
│  │ 周期管理 │ │ 定期扫描 │ │ 失败捕获 │ │ 自动熔断   │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Layer 3: 知识架构 (Context Engineering)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐ │
│  │ 5层存储  │ │ 3级索引  │ │ 跨项目知识提升           │ │
│  └──────────┘ └──────────┘ └──────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Layer 2: 执行层 (已有)                                  │
│  orchestrator | 20 agents | 19 skills | 6 rules         │
├─────────────────────────────────────────────────────────┤
│  Layer 1: 数据层 (已有)                                  │
│  hooks → collect → evolve-daemon → analyze → propose    │
└─────────────────────────────────────────────────────────┘
```

### 3.2 核心新增模块

#### 模块一：知识生命周期系统 (Knowledge Lifecycle)

**借鉴来源**: OpenAI Harness Engineering + 社区 5 层知识架构实践

**文件**: `knowledge/lifecycle.yaml` + `knowledge/lifecycle.py`

```
知识成熟度:
  draft → verified (≥1 工作流使用) → proven (≥2 不同项目验证)

自动衰减:
  proven: 12 个月未使用 → verified
  verified: 6 个月未使用 → draft
  draft: 持续未使用 + lint 标记 → archived

知识提升:
  Layer 3 (项目) → Layer 1/2 (跨项目) 当被 ≥2 个项目引用且验证通过
```

**5 层存储**:
| 层 | 范围 | 存储位置 |
|----|------|---------|
| L0-P | 个人偏好 | `~/.claude/` (不入 git) |
| L0-T | 团队约定 | `team-knowledge.git` |
| L1 | 技术知识 | `team-knowledge.git/tech-wiki/` |
| L2 | 业务领域 | `team-knowledge.git/biz-wiki/{domain}/` |
| L3 | 项目特定 | 项目 `.claude/knowledge/` |

**5 种知识类型**:
| 类型 | 定义 | 示例 |
|------|------|------|
| `model` | 实体定义、数据结构 | 用户模型、订单状态机 |
| `decision` | 架构决策 + 理由 | 为什么选 Redis 而非 Memcached |
| `guideline` | 推荐/禁止实践 | `recommend`: 使用连接池 / `avoid`: 裸 SQL |
| `pitfall` | 已知风险、失败模式 | N+1 查询、缓存雪崩 |
| `process` | 业务流程、操作步骤 | 发布流程、回滚步骤 |

#### 模块二：垃圾回收 Agent (GC Agent)

**借鉴来源**: OpenAI Symphony GC — 定期扫描模式漂移，自动提交修复 PR

**文件**: `agents/gc.md`

```yaml
name: gc
description: 知识垃圾回收 Agent，定期扫描项目模式漂移、过期知识、技术债务
model: sonnet
schedule: weekly  # 通过 cron/launchd 触发
```

**工作流程**:
```
1. Scan: 对比 knowledge/ 条目 vs 代码实际模式
2. Detect: 
   - 知识条目过期 (代码已不符合)
   - 模式漂移 (同一模式出现 3+ 变体)
   - 死知识 (从未被引用)
3. Report: 生成 drift-report.md
4. Action: 
   - Low risk → 自动提交修复 PR
   - Medium risk → 创建 issue 通知
   - High risk → 仅报告，等待人工
```

#### 模块三：进化自动回滚 (Evolution Auto-Rollback)

**借鉴来源**: Harness AI-Powered Verification + Auto-Rollback

**文件**: `evolve-daemon/rollback.py` (新增)

```
提案应用后 7 天观察期:
  Day 0: 提案应用
  Day 1-6: 持续收集效果指标
  Day 7: 自动评估
    ├── 指标提升 → 固化提案
    ├── 指标持平 → 保留观察 (+7 天)
    └── 指标下降 → 自动回滚 + 通知

熔断机制:
  连续 2 次提案回滚 → 锁定该模块 30 天
  连续 3 次全局回滚 → 切换为纯人工模式
```

**效果指标**:
| 指标 | 采集方式 | 阈值 |
|------|---------|------|
| 任务成功率 | PostToolUse 采集 | 下降 >10% 触发回滚 |
| 用户纠正率 | instinct 记录 | 上升 >20% 触发回滚 |
| Agent 调用失败率 | PostToolUseFailure 采集 | 上升 >5% 触发回滚 |
| 用户满意度 | 会话结束评分 | <3/5 触发回滚 |

#### 模块四：意图失败检测 (Intent-Failure Detection)

**借鉴来源**: OpenAI — "Agent followed the rules but missed the product's intent"

**文件**: `evolve-daemon/intent_detector.py` (新增)

```
检测模式:
  1. 任务声明完成 + 验收标准通过 BUT 用户手动修改了产出
     → 意图失败 (表面正确，实质不对)
  
  2. 同一任务类型反复出现用户纠正
     → 规则/Skill 未覆盖关键意图
  
  3. Agent 产出在后续阶段被大量重写
     → 上游意图传递断裂

捕获方式:
  PostToolUse[Edit] 检测用户手动编辑
  → 对比 Agent 最后产出 vs 最终状态
  → diff 率 >30% → 记录为意图失败
  → 纳入 evolve-daemon 分析管道
```

#### 模块五：渐进式知识索引 (Progressive Disclosure Index)

**借鉴来源**: OpenAI — 50行目录 → 300行分类 → 完整条目

**文件**: 各 Skill 目录下新增 `INDEX.md` (约 30-50 行)

```
Skill 加载三阶段:
  Stage 1 (始终加载): INDEX.md 的标题+一句话描述（~50 tokens/skill）
    → 23 个 skill × 50 tokens = ~1150 tokens 始终占用
  
  Stage 2 (按需加载): 当 Agent 匹配到相关 skill 时加载完整 INDEX.md（~300 tokens）
  
  Stage 3 (深度加载): 执行具体任务时加载 SKILL.md 正文

相比当前（始终加载所有 SKILL.md），节省 ~90% skill 上下文占用
```

---

## 四、实施计划

### Phase 1: 基础建设（本次实施）

| 任务 | 产出 | 风险 |
|------|------|:--:|
| 创建 `knowledge/` 目录结构 | 5 层存储模板 | Low |
| 创建 `agents/gc.md` | GC Agent 定义 | Low |
| 创建 `evolve-daemon/rollback.py` | 进化回滚逻辑 | Low |
| 创建 `evolve-daemon/intent_detector.py` | 意图失败检测 | Medium |
| 各 Skill 创建 `INDEX.md` | 渐进索引 | Low |

### Phase 2: 试点验证（Phase 6 同步）

| 任务 | 产出 | 风险 |
|------|------|:--:|
| 3-5 人团队试点 | 真实数据积累 | Medium |
| instinct 记录积累 ≥50 条 | 置信度系统可启动 | Medium |
| 首次 GC Agent 运行 | 验证漂移检测 | Low |

### Phase 3: 自动化闭环（数据积累后）

| 任务 | 产出 | 风险 |
|------|------|:--:|
| 首次自动回滚触发 | 验证熔断机制 | High |
| 知识自动提升 (L3→L1) | 跨项目知识共享 | Medium |
| evolve-daemon 全流程自动化 | 无需人工干预 | High |

---

## 五、风险与边界

### 安全边界（不可突破）

| 规则 | 原因 |
|------|------|
| 自动回滚不可删除代码 | 只能添加 git revert commit |
| GC Agent 不可修改安全配置 | `rules/security.md` 为只读 |
| 知识衰减不可删除 proven 条目 | 只能降级，归档需人工确认 |
| 意图检测不可自动修改 Agent 定义 | 只生成提案，人工审批 |

### 降级策略

| 场景 | 处理 |
|------|------|
| evolve-daemon 不可用 | 退化到手动 evolve analyze |
| instinct 数据不足 | 退回模板化建议 |
| 知识库为空 | 从 CLAUDE.md 和 git log 自动播种 |
| 连续回滚 | 锁定进化，切换为纯人工模式 |

---

## 六、验证计划

1. **知识生命周期**: 创建 draft 条目 → 模拟使用 → 验证成熟度提升 → 模拟衰减
2. **GC Agent**: 故意制造模式漂移 → 运行 GC → 验证检测率和误报率
3. **进化回滚**: 部署低质量提案 → 验证 7 天后自动回滚
4. **意图检测**: 模拟 Agent 产出+用户修改 → 验证 diff 检测
5. **渐进索引**: 测量 skill 加载 token 消耗 → 对比优化前后

---

## 七、关键指标

| 指标 | 当前 | 目标 |
|------|:--:|:--:|
| instinct 记录数 | 0 | ≥50 (Phase 2) |
| 知识条目数 | 0 | ≥30 (Phase 2) |
| 自动回滚成功率 | N/A | 100% (无漏回滚) |
| 意图失败检测率 | N/A | ≥70% |
| Skill 上下文占用 | ~23000 tokens | ~2300 tokens (90% ↓) |
| GC Agent 误报率 | N/A | <20% |
