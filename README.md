# Claude Team Kit

Claude Code 多 Agent 工作流编排 + 四维度自进化插件

## 功能特性

### 1. 自进化系统

- **四维度进化**: Agent / Skill / Rule / Memory
- **评分体系**: A/B/C/D/F 五级评分
- **熔断机制**: 连续退化自动阻止
- **数据轮转**: 7天保留/30天压缩/90天删除

### 2. 工作流编排

- `/evolve` - 进化系统操控台
- `/workflow` - 完整开发周期管理
- `/knowledge-graph` - 知识图谱查询

### 3. Hook 系统

- SessionStart: 状态注入
- PreToolUse: 安全检查
- PostToolUse: 数据采集
- Stop: 进化编排

## 快速开始

```bash
# 加载插件
claude --plugin-dir /path/to/claude-team-kit

# 使用进化系统
/evolve status
/evolve dashboard

# 使用工作流
/workflow run "实现用户登录功能"
/workflow pause
/workflow resume

# 查询知识图谱
/knowledge-graph search "认证"
```

## 目录结构

```
claude-team-kit/
├── .claude-plugin/       # 插件元数据
├── agents/               # Agent 定义 (18个)
├── skills/               # Skill 定义 (23个)
├── hooks/
│   ├── hooks.json        # Hook 配置
│   └── bin/              # Hook 脚本 (11个)
├── rules/                # 规则文件 (8个)
├── lib/                  # Python 引擎 (14个模块)
├── evolution/            # 备用进化引擎
├── config/               # 配置文件
├── memory/               # 记忆文件
└── evolution-cli.py       # 统一 CLI
```

## 进化命令

| 命令 | 功能 |
|------|------|
| `/evolve analyze` | 运行进化编排器 |
| `/evolve status` | 进化安全状态 |
| `/evolve dashboard` | 仪表盘 |
| `/evolve approve <id>` | 批准进化 |
| `/evolve rollback <ver>` | 回滚版本 |
| `/evolve history` | 进化历史 |

## 工作流命令

| 命令 | 功能 |
|------|------|
| `/workflow run <task>` | 开始工作流 |
| `/workflow pause` | 保存书签 |
| `/workflow resume` | 恢复书签 |
| `/workflow status` | 查看状态 |

## 评分等级

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