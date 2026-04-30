---
name: context-compaction
description: Context window compaction strategy for long sessions. Use when approaching context limits or between phases of multi-stage workflows.
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
