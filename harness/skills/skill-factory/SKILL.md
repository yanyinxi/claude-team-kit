---
name: skill-factory
description: >
  Skill 创建工厂。用于从工作流记录生成 SKILL.md。
  当要求创建新 Skill、或从历史会话提取 Skill 时调用。
user-invocable: true
---

# Skill Factory

## 何时使用

- 用户要求创建新的 Skill
- 从工作流记录中提取 Skill 模式
- 标准化 Skill 定义格式

## 创建流程

1. 分析需求和触发场景
2. 确定 skill name (kebab-case)
3. 创建 `harness/skills/<name>/` 目录
4. 编写 SKILL.md (标准格式)
5. 可选: 添加 scripts/ 目录

## SKILL.md 标准格式

```yaml
---
name: <skill-name>
description: >
  一行描述。说明何时调用此 Skill。
  触发条件: <具体触发条件>
user-invocable: true/false
---

# Skill 标题

## 何时使用

## 工作流程

## 示例
```

## 目录结构

```
harness/skills/<name>/
├── SKILL.md          # 必需: Skill 定义
├── README.md         # 可选: 详细文档
└── scripts/          # 可选: 辅助脚本
    ├── collect.sh
    └── validate.py
```