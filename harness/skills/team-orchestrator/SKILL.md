---
name: team-orchestrator
description: >
  多 Agent 编排 Skill。基于 Wave 执行模式，支持 self-claim 任务认领机制和文件所有权分离避免冲突。
  内置 Plan approval 模式（变更前请求批准）和 Lead 1 + Teammates 3 架构，最大 4 Agent 并行执行。
  适用于大规模代码重构、跨模块功能开发和并行任务分解场景。
---

# team-orchestrator — 多 Agent 编排 Skill

## 核心架构

```
Lead Agent
    │
    ├─ Teammate 1（任务 A）
    ├─ Teammate 2（任务 B）
    └─ Teammate 3（任务 C）
         ↓
    Wave 1: A1 + B1 + C1 并行
         ↓
    Wave 2: A2 + B2 + C2 并行（依赖 Wave 1 结果）
         ↓
    Lead Agent 汇总 → 报告
```

## 角色定义

### Lead Agent

**职责**：
- 分解任务为子任务
- 分配给 Teammates
- 收集结果、解决冲突
- 最终质量把关

**能力**：
- `SendMessage` 发送任务
- `SendTask` 并行分配
- `Read` 结果汇总
- `Edit` 最终整合

---

### Teammate Agent

**职责**：
- 认领并执行分配的任务
- 报告进度和结果
- 声明文件所有权

**self-claim 机制**：
```
任务池：
  [A] 文件搜索
  [B] 代码审查
  [C] 测试编写

Teammate 1 认领：[A] → 状态变为 [A-1]
Teammate 2 认领：[B] → 状态变为 [B-2]
Teammate 3 认领：[C] → 状态变为 [C-3]
```

---

## Wave-based 执行

### Wave 结构

```
Wave 1：独立任务（无依赖）
  → Teammate 1：[A1] 搜索文件
  → Teammate 2：[B1] 审查模块
  → Teammate 3：[C1] 编写测试
  ↓ 并行执行

Wave 2：依赖 Wave 1 结果
  → Teammate 1：[A2] 基于搜索结果修改
  → Teammate 2：[B2] 基于审查结果修复
  → Teammate 3：[C2] 基于测试补充覆盖
  ↓ 并行执行

Wave N：直到所有任务完成
```

### Wave 通信格式

```
任务分配：
{
  "type": "task",
  "wave": 1,
  "task_id": "A1",
  "description": "搜索 src/services 下所有 auth 相关文件",
  "output_file": ".claude/team/tasks/A1.json",
  "deadline": "5m"
}

Teammate 报告：
{
  "type": "report",
  "task_id": "A1",
  "status": "completed",
  "result": {
    "files": ["src/services/auth.ts", "src/services/jwt.ts"],
    "count": 2
  }
}
```

---

## 文件所有权分离

**核心原则**：同一文件同一时间只有一个 Agent 修改

### 分配策略

```
src/
  ├── auth/         → Teammate 1
  ├── billing/      → Teammate 2
  └── tests/        → Teammate 3

避免冲突：
  Lead 在分配时检查文件所有权
  冲突 → 等待或重新分配
```

### 冲突解决

```python
# 文件所有权注册表
ownership = {
    "src/services/auth.ts": "teammate-1",
    "src/services/billing.ts": "teammate-2",
}

# 冲突检测
def request_ownership(file, agent):
    if file in ownership and ownership[file] != agent:
        return "DENIED: owned by " + ownership[file]
    ownership[file] = agent
    return "GRANTED"
```

---

## Plan Approval Mode

**目的**：变更前请求用户批准，防止 Agent 盲目执行

### 执行流程

```
Lead Agent 分解任务 → 制定 Plan
    ↓
显示 Plan 摘要：
  📋 Plan #1：
  - 新增 src/services/auth.ts
  - 修改 src/routes/api.ts（+20 行）
  - 删除 src/utils/legacy.ts

用户批准 [y/n]
    ↓
批准后 → Lead 分配执行
    ↓
执行中异常 → 暂停 → 报告 → 等待指令
```

### Plan 格式

```markdown
## Plan #1：实现用户认证 API

### 变更清单
| 文件 | 操作 | Agent | 风险 |
|------|------|-------|------|
| src/services/auth.ts | 新增 | T1 | 低 |
| src/routes/api.ts | 修改 | T2 | 中 |
| src/utils/legacy.ts | 删除 | T3 | 高 |

### 风险评估
- 删除 legacy.ts：需要先确认无引用
- 修改 api.ts：需要回归测试

### 回滚计划
- git revert 可快速回滚
- 建议：分批提交

### 预计时间
- Wave 1（独立）：5 分钟
- Wave 2（依赖）：8 分钟
- 总计：~15 分钟
```

---

## 使用示例

### 示例：重构认证模块

```
> /team 重构 src/services/auth 目录

Lead Agent 分解：
  Wave 1：
    - T1: 列出所有 auth 相关文件
    - T2: 分析现有函数依赖
    - T3: 收集测试覆盖

  Wave 2：
    - T1: 重构 auth service
    - T2: 更新 API 路由
    - T3: 补充边界测试

  Wave 3：
    - T1: 验证重构完整性
    - T2: 更新文档
    - T3: 合并测试报告
```

---

## 与 Worktree 的配合

```
主仓库
    │
    ├─ Worktree 1（Teammate 1）
    │    工作目录：src/services/auth/
    │
    ├─ Worktree 2（Teammate 2）
    │    工作目录：src/routes/
    │
    └─ Worktree 3（Teammate 3）
         工作目录：tests/

各 Worktree 独立，互不干扰
    ↓
Lead Agent 在主仓库汇总
```

---

## 验证方法

```bash
[[ -f skills/team-orchestrator/SKILL.md ]] && echo "✅"

for feature in "wave" "self-claim" "file ownership" "plan approval"; do
  grep -qi "$feature" skills/team-orchestrator/SKILL.md && echo "✅ $feature" || echo "❌ $feature"
done

grep -q "Lead\|Teammate" skills/team-orchestrator/SKILL.md && echo "✅ 角色定义"
```

## Red Flags

- 同一文件被多个 Teammate 修改
- 无 Wave 顺序，任务随意执行
- Teammate 直接执行，不通过 Lead
- Plan 未获批准就执行
- Teammate 跳过 self-claim 抢夺任务
