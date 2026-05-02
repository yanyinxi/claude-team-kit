---
name: context-compaction
description: >
  长会话的上下文窗口压缩策略。上下文使用率超过70%或阶段切换时调用。
  涵盖文件中介制、Checkpoint模式和Fresh Start三种策略。
  激活条件：上下文超限、多阶段工作流阶段切换。
---

# Context Compaction — 上下文压缩策略

## 触发时机

- 上下文使用率 >70%
- 多阶段工作流切换阶段时
- 对话超过 30 轮

## 压缩策略

### 1. 文件中介制
```
当前阶段输出 → 写入文件 → /clear → 下一阶段读文件
```

每个阶段的关键产出写成文件：
- plan.md → PRD 和方案
- implementation.md → 实现要点
- review-comments.md → 审查意见

### 2. Checkpoint 模式
```
/compact → 保留最近 10 轮 + 文件引用
```

### 3. Fresh Start
```
/clear → 从文件中恢复上下文 → 继续工作
```

## 原则

- 关键状态一定落盘（不依赖上下文记忆）
- 文件用 checkbox 格式追踪进度：`- [ ]` `- [~]` `- [x]`
- 每个阶段开始重新读关键文件
