---
name: 所有需求必须先走 Agent，Agent 无法处理才用 Claude Code 直接能力
description: 任何需求（功能开发、检查、审查、调试、分析）都必须优先通过 Agent 工具派发专业子 Agent，仅当 Agent 无法胜任时才由主 session 直接处理
type: feedback
---

所有需求必须先走 Agent。主 session 不应直接实现任何非平凡任务，而是识别合适的专业 Agent 并派发。

**Why:** 用户明确要求：项目拥有完整的多 Agent 体系（.claude/ 目录），所有需求走 Agent 优先是核心工作模式；直接动手是对该体系能力的浪费，也违反 general.md 规范。

**How to apply:**
- **默认行为**：收到任何需求，第一步判断应该派发给哪个（些）Agent，然后调用 `Agent(subagent_type=..., prompt=...)`
- **可并行的任务**：前端/后端/测试独立时，在同一 response 里同时发出多个 Agent 调用
- **串行依赖**：code-reviewer 等必须等上游完成，串行调用
- **允许直接处理的情形**（Agent 无法处理）：
  - 单行 / 极简 fix（typo、obvious 1-liner）
  - 纯信息性问答（无需读写文件）
  - Agent 工具本身不可用或明确失败后的兜底
- **错误做法**：用 Read/Bash/Grep/Edit 自己逐步实现任何复杂任务，把专业 Agent 的工作揽到主 session
- **决策口诀**："这件事哪个 Agent 能做？→ 派给它。没有合适 Agent？→ 自己做。"
