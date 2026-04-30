---
name: migration
description: Framework and dependency migration guide. Use when upgrading framework versions, replacing deprecated APIs, or performing large-scale codebase migrations.
---

# Migration — 框架与依赖迁移

## 迁移流程

### 1. 评估
- 扫描所有需要变更的文件和 API
- 评估变更量和风险等级
- 如果变动 >50 文件，分批次执行

### 2. 试点
- 选最小模块先跑通
- 记录所有坑和解决方式
- 产出 migration playbook

### 3. 批量
- 逐模块：迁移 → 测试 → 提交
- 失败即停，不继续下一模块
- 每模块独立 commit

### 4. 验证
- 全量测试通过
- 静态分析无新告警
- 更新项目文档

## 原则

- 小步提交：每个模块独立 commit，可独立 revert
- 迁移前确保现有测试全通过
- 灰度：先在分支验证，再合入主干
- 产出 playbook 供后续参考
