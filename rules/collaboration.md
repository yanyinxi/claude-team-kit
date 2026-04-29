# Collaboration Strategy Rules（Java 项目）

**更新时间**: 2026-04-23
**适用范围**: 全局（所有文件）

## 多 Agent 协作规范

### ✅ 正确的 Agent 调用方式（Claude Code）

主 session 充当 Orchestrator，通过 `Agent` 工具调用子 agent：

```
# 并行调用（同一 response 中同时发出）
Agent(subagent_type="frontend-developer", prompt="...", run_in_background=True)
Agent(subagent_type="backend-developer", prompt="...", run_in_background=True)

# 串行调用（需要等待结果）
Agent(subagent_type="code-reviewer", prompt="审查以下代码...")
```

**关键参数**：`subagent_type`（不是 `agent`），`prompt`，可选 `run_in_background=True`。

### ✅ 契约前置：前后端并行前必须定义数据契约

**这是前后端并行开发的前提条件，缺少它会导致两端的命名惯例冲突（如 camelCase vs snake_case），形成运行时补丁。**

**适用场景**：任何涉及前端读取后端 API 响应数据的需求，无论是新功能还是修改现有接口。

**执行步骤**：

1. **Step 1（串行，Orchestrator 自己做）**：在派发任何 agent 前，写出 API 数据契约：
   - 每个接口的响应字段名（统一 camelCase）及类型
   - 示例：
     ```
     GET /api/v1/assets 响应字段：
       id: string, title: string, uploadedAt: string,
       fileSizeBytes: number, sourceDataset: number, ...
     GET /api/v1/stats/uploader-avg-size 响应字段：
       uploader: string, avgSizeBytes: number, avgSizeHuman: string
     ```
   - 契约不需要 OpenAPI 格式，Markdown 表格即可，重要的是**字段名拼写和 case 必须精确**

2. **Step 2（并行）**：把契约原文粘贴进 backend-developer 和 frontend-developer 的 prompt 里，两端都以契约为准实现

3. **Step 3（验证）**：code-reviewer 检查时，确认后端 SQL alias 或 DTO 字段名与契约一致，确认前端没有 `?? row.snake_case` 形式的 fallback（这类 fallback 是契约缺失的症状，不是防御性编程）

**技术规范（与框架无关，适用所有项目）**：
- 响应字段命名：统一 camelCase（前端 JS/TS 惯例优先，因为字段名最终在 TS interface 中声明）
- 后端 Map 返回时：SQL 列必须通过 `AS "camelCaseName"` 别名匹配（PostgreSQL 须加双引号保留大写）
- 后端 DTO 返回时：Java 字段名使用 camelCase，Jackson 默认序列化即匹配
- 禁止的补丁写法：`row.fieldName ?? row.field_name`、`d.someVal ?? d['some_val']` — 出现即表示契约断裂，应修后端，不改前端

### ✅ 并行任务分配原则

- **前后端并行**：frontend-developer 和 backend-developer 互不依赖，同时启动（但须先完成契约定义）
- **审查串行**：code-reviewer 必须在代码完成后启动
- **进化串行**：evolver 在 code-reviewer 给出报告、主 session 完成修复后启动

### ✅ Evolver 使用规范

- `permissionMode: acceptEdits` — 否则后台运行时无法自动编辑文件
- 项目必须 `git init` — 否则 session_evolver.py 的 files_changed 永远为 0

## 反模式

### ⚠️ `Task(agent="...", prompt="...")` 语法错误

正确参数名是 `subagent_type`，工具名是 `Agent`，不存在 `Task` 工具和 `agent=` 参数。

### ⚠️ `background_task(...)` 不存在

这是旧框架的伪代码。并行是通过在同一 response 里同时发出多个 `Agent` 调用实现的。

### ⚠️ 主 session 手写所有代码

浪费多 Agent 并行能力。应将后端/前端/测试任务分别委托给对应专业 Agent。
