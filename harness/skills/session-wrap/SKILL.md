---
name: session-wrap
description: >
  会话收尾流水线 Skill。提供 5 阶段收尾框架（Phase 0 上下文收集 → Phase 1 并行 4 个 subagent 收集文档更新、自动化发现、
  经验提取、后续建议 → Phase 2 去重 → Phase 3 用户确认 → Phase 4 执行 → Phase 5 报告写入 .claude/session-wrap/）。
  适用于长时间会话结束后的知识沉淀和后续工作跟踪。
---

# session-wrap — 会话收尾5阶段流水线

## 概述

每个会话结束前自动执行结构化收尾，将隐性经验转化为显性知识。

## Phase 0：上下文收集

```
收集内容：
- git diff（本次会话变更）
- session summary（最后 10 轮摘要）
- 新增/修改文件列表
- TodoWrite 完成状态
- 未完成项记录
```

## Phase 1：4个并行 Subagent

```
┌─────────────────────────────────────────────┐
│  Phase 1（并行执行）                          │
│  ┌──────────────┐  ┌──────────────┐         │
│  │ doc-updater  │  │automation-scout│       │
│  │ 更新相关文档   │  │发现可自动化项  │        │
│  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐           │
│  │learning-extractor││followup-suggester│    │
│  │ 提取本次经验   │  │ 建议后续行动   │        │
│  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────┘
```

### Subagent：doc-updater

**职责**：更新相关文档
- CLAUDE.md — 如果有新陷阱或技术决策
- .claude/knowledge/ — 如果有新模式或经验
- 代码注释 — 如果实现中有值得记录的设计决策

**输出**：
```json
{
  "updated_files": ["CLAUDE.md", "docs/api.md"],
  "new_knowledge": ["避免在 auth middleware 中使用 synchronous calls"],
  "doc_changes": ["更新了架构决策记录"]
}
```

### Subagent：automation-scout

**职责**：发现可自动化项
- 识别重复性手动操作
- 发现 CI/CD 改进机会
- 识别测试覆盖率缺口

**输出**：
```json
{
  "automations": [
    {"task": "run integration tests", "frequency": "daily", "confidence": 0.8},
    {"task": "generate changelog", "frequency": "per-release", "confidence": 0.9}
  ],
  "ci_improvements": ["add e2e smoke test on deploy"]
}
```

### Subagent：learning-extractor

**职责**：从本次会话提取经验
- 成功的模式（下次可复用）
- 失败的模式（下次避免）
- 技术债务发现
- 架构改进建议

**输出**：
```json
{
  "lessons": [
    {"type": "pattern", "desc": "先写测试再实现，节省 30% 调试时间"},
    {"type": "anti-pattern", "desc": "不要在周五下午合并复杂 PR"}
  ],
  "tech_debt": ["refactor auth module to use strategy pattern"],
  "architecture": ["consider event sourcing for audit trail"]
}
```

### Subagent：followup-suggester

**职责**：生成后续行动建议
- 未完成项的接手计划
- 下一会话的切入点
- 长期改进项

**输出**：
```json
{
  "immediate": ["complete integration test for /api/users"],
  "next_session": ["review PR for security concerns in auth module"],
  "backlog": ["implement event sourcing for audit trail"]
}
```

## Phase 2：去重（Deduplicate）

```
合并4个 subagent 的输出：
- 去除重复的发现和建议
- 合并同类项
- 按重要性排序
```

**去重规则**：
- 完全相同的建议 → 合并
- 相似建议（Jaccard similarity > 0.7）→ 合并，选更具体的
- 矛盾建议 → 标记，供人工决策

## Phase 3：用户确认

```
显示汇总，人工确认执行哪些：

## Session Wrap Summary

### 📚 文档更新（2项）
1. [✅] 更新 CLAUDE.md — 添加新陷阱
2. [ ] 更新 API 文档

### 🤖 自动化建议（3项）
1. [ ] 添加每日集成测试 CI
2. [ ] 自动生成 CHANGELOG

### 📖 本次经验（4项）
1. [✅] 记录：先写测试再实现
2. [✅] 记录：避免在 middleware 中同步调用

### 📌 后续行动（5项）
1. [✅] 完成 /api/users 集成测试
2. [✅] 审查 auth 模块 PR

按回车继续（跳过全部建议），
或输入编号选择执行项。
```

## Phase 4：执行选中项

```
按以下顺序执行用户确认的操作：
1. 文档更新（立即执行）
2. 自动化建议（创建 TODO 文件供后续处理）
3. 经验记录（写入 instinct-record.json）
```

## Phase 5：报告写入

```
输出目录：.claude/session-wrap/<session-id>-<timestamp>.md

报告内容：
- Session ID 和时间
- 变更文件统计
- 文档更新记录
- 自动化建议
- 提取的经验
- 后续行动清单
- Instinct 提案（如有）
```

## 与 Stop Hook 的关系

Session Wrap 在 `Stop` hook 触发后执行，
收集 session 数据（来自 `collect-session.py`）作为 Phase 0 输入。

## Red Flags

- Phase 3 跳过所有建议
- 4个 subagent 并行超时
- 报告无人读