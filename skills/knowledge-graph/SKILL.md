---
name: knowledge-graph
description: |
  This skill should be used when the user asks to "query knowledge graph",
  "search knowledge", "add to knowledge graph", or mentions "knowledge".
user-invocable: true
allowed-tools: [Read, Bash, Grep]
---

# Knowledge Graph

知识图谱系统，管理 skill/agent/pattern/concept 节点和关系。

## 命令

### 查询
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py kg search "<query>"
```

### 添加节点
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py kg add-node <type> <name> "<data>"
```

### 查看关系
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py kg relations <node-id>
```

## 节点类型

- skill: 技能节点
- agent: Agent 节点
- pattern: 模式节点
- concept: 概念节点

## 关系类型

- uses: 使用关系
- composes: 组成关系
- depends: 依赖关系