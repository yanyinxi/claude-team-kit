---
name: Claude Code 官方能力第一优先级
description: 所有设计决策必须以 Claude Code 官方原生能力为基础，不重复造轮子，只做官方没有的增强
type: feedback
---

# Claude Code 官方能力第一优先级

**Why:** 用户明确要求：Claude Code 官方能力为第一优先级，不能重复造轮子。官方已有的能力直接用，没有的能力才自己规划开发。

**How to apply:**
- Skills 分发/加载/触发 → 用官方的 SKILL.md + progressive disclosure（3 级加载：metadata → instructions → resources）
- Hooks 生命周期 → 用官方的 14 个事件（PreToolUse, PostToolUse, SessionStart, Stop, PreCompact 等）
- Agents 隔离 → 用官方的 context: fork + isolation: worktree
- Plugins 分发 → 用官方的 plugin.json + /plugin install
- Context 压缩 → 用官方的 PreCompact hook
- 自己开发的部分：进化引擎、规则追踪、记忆分类、安全门禁 — 这些是官方没有的能力
