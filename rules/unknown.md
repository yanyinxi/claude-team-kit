# 进化洞察记录

**更新时间**: 2026-04-23
**适用范围**: 全局

此文件记录无法归类到具体 Agent 策略的系统级洞察。
`auto_evolver.py` 在检测到有实质意义的事件时写入（失败分析、并行模式发现等），不记录平凡的成功。

## 已知系统限制

### Claude Code SubagentStop hook 不传 subagent_type

**问题**：所有 agent 调用都被记录为 `"agent": "unknown"`。
**原因**：Claude Code 平台在 SubagentStop hook 的 `tool_input` 中不包含 `subagent_type` 字段。
**影响**：`agent-invocations.jsonl` 无法按 agent 类型统计调用分布。
**状态**：等待 Claude Code 平台修复，代码层面无法绕过。

### git init 是进化系统的前提

**问题**：项目未初始化 git 仓库时，`session_evolver.py` 的 `git diff --stat HEAD` 静默失败，导致 `files_changed=0`，所有维度的 strategy_weights 永远停在初始值。
**修复**：项目启动时必须 `git init`，且第一次提交后才开始有效数据。
**状态**：2026-04-23 已完成 `git init`。

## 成功模式

### 多 Agent 并行审查+修复循环（2026-04-23 验证）

code-reviewer 和 frontend-developer 并行运行（互不依赖），code-reviewer 完成后主 session 根据报告修复，再启动 evolver 内化。总体节省约 40% 时间。

### code-reviewer 发现的高价值问题类型

- `${orderBy}` 字符串拼接（即使有 Java 白名单也违规）
- `JacksonTypeHandler + ::text[]` PG 不兼容
- `getAssetById + fields` 缺少 WHERE id=? 条件（返回错误记录）
- Controller 直接注入 Mapper（违反分层）
