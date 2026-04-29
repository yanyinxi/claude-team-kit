# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- SKILL REFERENCE: 自动加载项目级 skill，确保不同模型都能使用 -->
<!-- See: .claude/skills/karpathy-guidelines/SKILL.md -->

<skill-ref>
@.claude/skills/karpathy-guidelines/SKILL.md
</skill-ref>

## 项目概述

视频素材查询服务 — 一个前后端分离的 Java + Vue 3 全栈项目，提供视频素材的数据存储、查询统计和 Excel 导入功能。

## 开发命令

### 一键启动
```bash
./start-local.sh    # 自动检测并安装依赖，启动 PostgreSQL + 后端 + 前端
```

### 后端 (Spring Boot)
```bash
cd main/backend
mvn spring-boot:run              # 启动后端服务
mvn test                         # 运行单元测试
mvn test -Dtest=AssetServiceTest # 运行单个测试类
mvn package                      # 构建 jar 包
```

### 前端 (Vue 3)
```bash
cd main/frontend
npm install                      # 安装依赖
npm run dev                      # 启动开发服务器
npm run build                    # 构建生产版本
npm run lint                     # ESLint 检查并修复
npm run test:e2e                 # 运行 E2E 测试
```

## 技术架构

### 后端技术栈
- Spring Boot 3.3.4 + Java 17
- MyBatis-Plus 3.5.7（数据访问）
- PostgreSQL 15（数据库）
- Spring Security + Bucket4j（安全 + 限流）
- SpringDoc OpenAPI（API 文档）

### 前端技术栈
- Vue 3 + TypeScript
- Vite 5（构建工具）
- Pinia（状态管理）
- Element Plus（UI 组件库）
- ECharts（数据可视化）
- Vue Router 4（路由）

### 分层架构（后端）

```
api/         → Controller 层，接收 HTTP 请求
service/     → 业务逻辑层
mapper/      → 数据访问层，MyBatis-Plus
domain/      → 实体类
config/      → Spring 配置类
ingest/      → ETL 导入服务（Excel 解析、数据归一化）
```

### 安全防护

请求处理链：`RateLimitFilter → ApiKeyAuthFilter → Controller → Prometheus 指标`

- 限流：Bucket4j，10 请求/秒
- 认证：X-API-Key 请求头，白名单匹配
- 权限：RBAC（USER/ADMIN 角色）
- SQL 注入：字段名/操作符/返回值三重白名单

### 可观测性

- Actuator：`/actuator/health`, `/actuator/info`
- Prometheus：`/actuator/prometheus`
- Swagger UI：`/swagger-ui.html`

## 数据库设计要点

- PostgreSQL text[] 数组存储标签/分类
- JSONB 存储稀疏字段（extra）
- 8 个业务索引支持高效查询
- 归一化处理在 ETL 阶段完成，应用层无数据转换负担

## .claude 目录结构

```
.claude/
├── settings.json            # [官方] 权限、hooks、环境变量配置
├── settings.local.json      # [官方] 本地覆盖配置（不入 git）
├── agents/                  # [官方] Agent 定义文件
├── skills/                  # [官方] 技能定义（/命令）
├── rules/                   # [官方] 策略规则文件
├── hooks/                   # Claude Code 钩子脚本
│   ├── path_validator.py    # PreToolUse: 路径验证
│   └── scripts/             # 运行时钩子
│       ├── auto_evolver.py      # PostToolUse/Agent
│       ├── session_evolver.py   # Stop
│       └── strategy_updater.py  # Stop
├── lib/                     # Python 共享库
│   ├── constants.py             # 常量定义
│   ├── parallel_executor.py     # 并行执行器
│   └── examples/                # 示例代码
├── data/                    # 数据文件
│   ├── capabilities.json        # 能力清单
│   ├── knowledge_graph.json     # 知识图谱
│   ├── strategy_weights.json    # 策略权重
│   └── strategy_variants.json   # 策略变体
├── docs/                    # 文档
├── memory/                  # 记忆反馈
├── tests/                   # 测试脚本
├── logs/                    # 运行时日志（不入 git）
└── claude-harness.sh        # 项目初始化 CLI
```

**官方标准文件位置**（不可移动）：
- `settings.json` - 必须在 `.claude/` 根目录
- `settings.local.json` - 必须在 `.claude/` 根目录
- `skills/<name>/SKILL.md` - 技能定义
- `agents/*.md` - 子代理定义
- `rules/*.md` - 策略规则文件（自动加载）

---

## 专家模式

> **重要**: 处理复杂问题时，必须激活专家模式。详见 `.claude/rules/expert-mode.md`

### 【架构师专家模式】

你现在是资深系统架构师，输出必须遵循以下规则：
1. 所有方案必须符合生产级最佳实践，包含边界校验、风险评估、可扩展性分析；
2. 禁止模糊表述，所有结论必须给出可落地的步骤或代码；
3. 主动识别方案中的潜在漏洞、性能瓶颈和运维风险，并给出规避方案。

### 【强制深度思考模式】

请以多步骤链式推理的方式，对问题进行完整拆解，不跳步、不省略关键逻辑，先输出详细的思考过程，再给出最终方案。

**激活条件**: 架构设计、技术决策、复杂重构、多模块变更时自动生效。