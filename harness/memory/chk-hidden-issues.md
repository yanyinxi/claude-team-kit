---
name: chk-hidden-issues
description: CHK 插件隐蔽问题记录：plugin/slashCommands、Agent 前缀等
type: project
---

## CHK 插件已知隐蔽问题

### 1. plugin/slashCommands 配置问题
- 插件入口 `index.js` 中 `slashCommands` 字段可能不会被 Claude Code 识别
- 解决方案：使用 `/chk` 风格命令时，确保在 `skills/` 目录有对应实现

### 2. Agent 前缀问题
- Agent 定义文件命名与引用必须一致
- 使用 `Agent: agent-name` 时，agent-name 必须是已注册的 Agent ID

### 3. 路径规范
- Hook 脚本统一在 `harness/hooks/`
- instinct 数据路径已统一到 `harness/memory/`
- agents/ 旧路径已迁移到 `harness/agents/`

### 4. 安装注意事项
- Claude Code 插件安装需要正确配置 package.json 的 `main` 字段
- 版本号必须与 version.json 保持同步

**Why:** 项目演进过程中产生的路径漂移和配置问题，需要记录避免重复踩坑