---
scope: global
---

# Multi-Agent Collaboration Protocol — 多 Agent 协作契约

> **配合 [orchestrator Agent](../agents/orchestrator.md) 使用** — 并行规则、冲突检测、5 阶段流程详见 Agent 定义。本 Rule 补充 Mailbox 协议、Checkpoint 系统和错误处理。

## 1. 信息同步协议

### 1.1 文件交接制 — 不依赖上下文传递状态

每个阶段的产出写入文件，下一阶段读取文件：

```
[分析阶段] → research/summary.md
[设计阶段] → plan/architecture.md
[实现阶段] → output/task_*.md
[审查阶段] → review/report.md
```

**规则**: 跨阶段状态**必须**写入文件。上下文可能被压缩，文件不会丢失。

### 1.2 Mailbox — Agent 间通信

并行 Agent 之间发现需要协同的信息，写入 mailbox/ 目录：

```
mailbox/to_frontend.md  ← backend-dev 通知 API 字段变更
mailbox/to_backend.md   ← frontend-dev 通知需要新接口
```

**协议**:
- Agent 启动时先读 mailbox/ 检查是否有给自己的消息
- Agent 发现需要通知其他 Agent 时写 mailbox/
- 消息格式: 时间 + 来源 + 内容 + 影响范围
- 消息状态: unread → read → resolved

### 1.3 Checkpoint — 压缩安全

```
.compact/
├── current_phase.md     # "Phase 3: Implement, Task 2/4"
├── completed.md         # 已完成任务
├── pending.md           # 待开始任务
└── recovery.md          # 如何从当前状态恢复
```

`/compact` 后，从 checkpoint 文件恢复进度。

## 2. 错误处理

### 2.1 Agent 失败

```
Agent 返回 error →
  工具失败 → 重试 1 次（换参数）
  超时 → 拆分任务
  逻辑错误 → 根因分析 → 修复 → 重新派发
  连续 3 次失败 → 人工介入
```

### 2.2 并行 Agent 部分失败

```
Task A ✅, Task B ❌, Task C ✅
  → 保留 A、C 的产出
  → 修复 B 的根因
  → 仅重派 B
  → 全部通过 → 继续
```

## 3. Anti-Patterns（禁止）

| 禁止 | 原因 | 正确做法 |
|------|------|---------|
| 有依赖的任务并行 | 重复工作 | 串行化依赖 |
| 改同一文件的 Agent 并行 | 冲突 | 合并或串行 |
| 上下文依赖记忆传递状态 | 压缩丢失 | 状态写入文件 |
| 无契约前后端并行 | 字段不一致 | 先定契约再并行 |
| 审查和修复同时进行 | 修复基础不稳 | 先审查完再修复 |
