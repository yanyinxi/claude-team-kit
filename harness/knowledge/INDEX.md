# claude-harness-kit — 知识库索引

## 架构决策

### 目录结构 (v1.0 重构)
- 全量模块统一到 `harness/` 下
- `hooks/` 为符号链接 → `harness/hooks/`
- instinct 数据路径: `harness/memory/` (v3.0 统一)

### Auto-Evolve 系统
- 4 维度自主进化闭环 (v2)
- 进化数据存储于 `harness/knowledge/evolved/`
- sessions.jsonl 提供执行历史追踪

### 权限模型
- 全局 `*` 权限 + 细粒度 Bash 命令白名单
- MCP 工具全部放行

## 已知陷阱

### Hook 脚本问题 (历史)
- Python import 缺失导致 Traceback
- 修复: `set -euo pipefail` + 显式 import

### Session 统计问题
- sessions.jsonl 时间戳矛盾
- Agent 统计重复计算
- 修复: 统一生成确定性 session_id

### 路径漂移
- agents/instinct → harness/memory (v3.0)
- drift-report 路径需同步更新

## 操作流程

### 安装插件
```bash
./install.sh  # 一键安装
```

### 运行测试
```bash
npm test  # 69 测试，95 分
```

### 启动进化守护进程
```bash
python3 harness/evolve-daemon/evolve-daemon.py
```

## 目录

- `decision/` — 架构决策记录
- `guideline/` — 开发指南
- `pitfall/` — 已知陷阱
- `process/` — 操作流程
- `model/` — 模型提示词