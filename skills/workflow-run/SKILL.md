---
name: workflow-run
description: |
  This skill should be used when the user asks to "run workflow", "execute workflow",
  "build feature", "implement feature", or wants to "build something from scratch".
user-invocable: true
allowed-tools: [Read, Bash, Grep, Glob]
---

# Workflow Orchestration

工作流编排引擎，执行完整的开发周期。

## 工作流阶段

1. **Explore**: 理解需求，探索代码库
2. **Plan**: 设计方案，制定计划
3. **Develop**: 实现功能（可并行后端/前端）
4. **Review**: 代码审查
5. **Fix**: 修复问题（循环直到通过）
6. **Verify**: 验证完成

## 执行

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow run "<任务>"
```

## 书签功能

使用 `/pause` 保存进度，`/resume` 恢复执行。