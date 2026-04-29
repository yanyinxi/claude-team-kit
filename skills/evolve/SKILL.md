---
name: evolve
description: |
  This skill should be used when the user asks to "analyze evolution",
  "approve evolution", "review evolution proposals", "trigger evolution",
  "check evolution status", "rollback evolution", "evolution history",
  "evolution fitness", or mentions "evolve", "evolution", "self-improve".
version: 1.0.0
user-invocable: true
disable-model-invocation: false
allowed-tools: [Read, Bash, Grep]
---

# Evolution System

进化系统操控台，管理 Agent/Skill/Rule/Memory 四个维度的自进化。

## 命令

### /evolve analyze
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/evolution_orchestrator.py
```

### /evolve status
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution safety status
```

### /evolve dashboard
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/evolution_dashboard.py
```

### /evolve approve <proposal-id>
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution safety approve <id>
```

### /evolve rollback <version>
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution rollback <version>
```

### /evolve history [--limit N]
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution history --limit 10
```

### /evolve effects
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution effects report
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution effects trend
```

### /evolve fitness
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py evolution fitness
```

## 安全级别

| 级别 | 操作 | 审批 |
|------|------|------|
| L1 | memory 追加、skill 缩窄、rule 放松、agent 加约束 | 自动 |
| L2 | agent 修改、skill 扩展、新 rule | `/evolve approve` |
| L3 | 新 agent、skill 重构、rule 集变更 | 多人批准 |

## 评分体系

总分 = 基础分(40) + 活跃度(20) + 效果分(25) + 质量分(15)

| 等级 | 分数 |
|------|------|
| A | ≥80 |
| B | ≥65 |
| C | ≥50 |
| D | ≥35 |
| F | <35 |

## 风险分级

| 等级 | 操作 | 处理 |
|------|------|------|
| Low | 追加内容 | 自动执行 |
| Medium | 修改现有内容 | 自动执行 + 通知 |
| High | 删除/重构 | 人工确认 |
| Critical | 安全相关 | 禁止自动 |