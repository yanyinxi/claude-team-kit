# Claude Code 内部架构深度研究

> 来源：6 次聚焦 Web 搜索 + 源码泄露分析 + 社区分析 + 本地代码库分析
> 日期：2026-04-30

---

## 1. 多 Agent 架构模式

### 1.1 Coordinator + Fork Subagent（核心模式）

```
Coordinator (tools stripped to Agent / SendMessage / TaskStop)
  → Spawns Worker subagents in parallel fork contexts
  → Each worker gets byte-identical prompt cache prefix (nearly free to spawn)
  → Workers return only <task-notification> XML summaries, not full conversation
```

**关键洞察**：Fork Agent 继承父级 prompt 缓存前缀，5 个并行 subagent 成本接近 1 个串行 agent（81-92% 缓存命中率，缓存读取 90% 折扣）。

### 1.2 `/simplify` 3-Agent 并行模式（69 行代码）

```
git diff → 3 parallel agents:
  Agent 1: Code reuse audit (搜索已有工具)
  Agent 2: Code quality audit (冗余状态、参数蔓延、抽象泄漏)
  Agent 3: Efficiency audit (多余工作、并发缺失、热路径膨胀)
  → Aggregate results → Serial fixes (fixes have dependencies)
```

**规则**：始终**并行分析，串行修复**。分析任务无依赖；修复有。

### 1.3 Agent 类型（最小权限，6 内置）

| Agent | 工具 | 用途 |
|-------|------|------|
| `general` | All | 完整实现 |
| `explore` | Read, Grep, Glob | 代码发现 |
| `plan` | Read, Grep, Glob | 架构设计（不写） |
| `verification` | Read, Bash(test) | 回归验证 |
| `claudeCodeGuide` | Read | 自帮助/文档 |
| `statuslineSetup` | Limited | UI 配置 |

权限级联：`general > explore/plan > verification`。

---

## 2. 插件架构模式

### 2.1 目录结构规范

```
my-plugin/
├── .claude-plugin/plugin.json    # 仅元数据
├── skills/                       # SKILL.md 在根级别
├── agents/                       # Agent .md 在根级别
├── hooks/hooks.json              # Hook 配置在根级别
# ~~commands/~~                   # Slash 命令 (已移除)
├── rules/                        # Rule .md 文件
└── README.md
```

**关键**：组件目录必须在插件根目录——不在 `.claude-plugin/` 内。

### 2.2 Skills 渐进披露

```markdown
---
name: my-skill
description: What and WHEN to use. 30-50 tokens. Written in third person.
context: fork | inline
allowed-tools: [Read, Grep]
model: claude-sonnet-4-20250514
---

# Skill Body (keep under 500 lines / 2,000 words)
```

- 描述始终加载（~30-50 tokens）
- 正文按需加载
- 用 `references/` 子目录放详细文档——仅按需加载
- 永不链式引用（file1 → file2 → file3）

---

## 3. 上下文管理与 Prompt 缓存

### 3.1 缓存数据（核心经济指标）

| 阶段 | 总 Tokens | 前缀复用率 |
|------|----------|-----------|
| Explore subagent | 546K | **92.06%** |
| Plan subagent | 528K | **93.23%** |
| Main execution | 827K | **97.83%** |

**如何实现**：
- 系统提示、工具列表、subagent 定义形成稳定前缀
- 工具按字母序排列（确定性排序 → 缓存命中）
- Agent 列表从工具移到消息附件（~10.2% 缓存 token 减少）
- 缓存写入：1.25x 基础价格；缓存读取：**90% 折扣**

### 3.2 上下文预算管理

| 使用率 | 动作 |
|--------|------|
| 0-50% | 正常操作 |
| 50-70% | 监控，准备压缩 |
| 70-85% | 在逻辑断点 `/compact` |
| 85-95% | 紧急 `/compact` |
| 95%+ | `/clear` 并重启 |

### 3.3 大规模代码库四大策略

1. **分层阅读**：`tree -L 2 -d` → 入口文件 → 定向 Grep → 具体文件
2. **依赖映射**：修改前搜索所有调用点
3. **模块隔离**：一个会话 = 一个模块。不相关任务间 `/clear`
4. **显式边界**："只修改 `packages/billing/`，需要改外部时停下问"

---

## 4. 记忆系统

### 4.1 四层架构

| 层 | 触发 | 持久化 | 上限 |
|----|------|--------|------|
| **CLAUDE.md** | 手动 | 磁盘，始终加载 | N/A |
| **Auto Memory** | Claude 决定 | `~/.claude/projects/<project>/memory/` | 200 行 / 25KB |
| **AutoDream** | >24h + >=5 会话 | 后台 fork 进程 | 200 行索引 |
| **KAIROS** | 心跳 `<tick>` | 始终在线守护 | 7 天过期 |

### 4.2 CLAUDE.md 层级（优先级顺序）

| 优先级 | 位置 | 范围 |
|--------|------|------|
| 1 | 托管策略 (`/etc/claude-code/CLAUDE.md`) | 组织级 |
| 2 | `./CLAUDE.md` 或 `.claude/CLAUDE.md` | 团队（提交） |
| 2 | `.claude/rules/*.md` | 团队（提交） |
| 3 | `~/.claude/CLAUDE.md` | 用户全局 |
| 4 | `./CLAUDE.local.md` | 本地（gitignore） |

文件是**拼接**的，不覆盖。路径作用域规则（通过 `paths` frontmatter）按需加载。

---

## 5. KAIROS / AutoDream 守护进程架构

### 5.1 KAIROS 核心循环

```
while True:
    observe()       # 读取项目上下文 + 记忆
    decide()        # 行动或等待
    if acting:
        do_one_thing()
        log_it()
        update_memory()
    sleep(interval)
```

**关键约束**：
- **15 秒延迟规则**：阻塞用户超过 15 秒的操作自动推迟
- **仅追加日志**：不能删除历史
- **7 天自动过期**：防止静默永久运行
- **3 个独占工具**：SendUserFile、PushNotification、SubscribePR
- **PROACTIVE 标志**：用于主动发现用户未提出的问题

### 5.2 AutoDream — AI "REM 睡眠"

```
触发：距上次 >= 24h 且 >= 5 个新会话
运行方式：Fork 子进程，只读代码访问
```

四阶段流水线：
1. **Orient** — 扫描记忆目录，读索引
2. **Gather** — 搜索会话记录中新知识
3. **Consolidate** — 写入/更新记忆，解决矛盾
4. **Prune** — 保持 `MEMORY.md` 在 200 行内

结果：跨会话上下文膨胀减少约 40%。

---

## 6. 安全架构（7 层独立）

```
预过滤（剥离被拒绝的工具）
  → PreToolUse Hooks（用户定义的确定性门禁）
  → Deny-First 规则评估（Deny 永远优先于 Allow）
  → 权限处理器（4 分支：coordinator / swarm-worker / classifier / interactive）
  → 分类器（侧载小模型，看到工具调用而非模型输出）
  → Shell 沙箱
  → Hook 拦截
```

**Subagent 安全泄漏点**：
1. 权限继承 — 父级 `bypassPermissions`，子级无法自限
2. 上下文继承 — Fork 子级看到完整父级对话历史（无脱敏）
3. 记录持久化 — `recordSidechainTranscript()` 序列化敏感上下文
4. MCP 服务器共享 — 仅可累加，无 per-agent 过滤
5. 后台 Agent 漂移 — 工具集在 spawn 时冻结，权限中途撤销后仍存活

---

## 7. 100+ 仓库管理生产模式

### 7.1 每个仓库必需基础设施

```
repo/
├── CLAUDE.md                    # 必须存在（根级约定）
├── .claude/
│   ├── settings.json            # Hooks, 权限
│   ├── rules/*.md               # 路径作用域规则
│   ├── LOCAL_SUMMARY.md         # 10-20 行：目的、入口、陷阱
│   └── agents/*.md              # 仓库特定 Agent
```

### 7.2 路径作用域规则（多仓库关键）

```yaml
---
paths: ["packages/auth/**/*.ts"]
---
# 仅在 Claude 接触 auth 代码时加载
```

### 7.3 大规模迁移：执行驱动范式

```
Read → Grep → Modify → Execute → Error → Fix → Re-execute
```

不尝试构建完整心智模型，依赖执行反馈循环。

---

## 8. 未发布功能（源码泄露）

| 功能 | 状态 | 标志 |
|------|------|------|
| KAIROS daemon | 未发布 | 编译时 |
| AutoDream | 部分活跃 | `dream` 命令 |
| BUDDY (Tamagotchi) | 计划 2026年5月 | 18 物种，5 属性 |
| Undercover Mode | 活跃（内部） | 从提交中剥离 AI 痕迹 |
| ULTRAPLAN | 内部 | 10-30 分钟 Opus 规划 |
| Voice Mode | 标志后 | 直接语音交互 |
| Bridge Mode | 标志后 | 从浏览器/手机远程控制 |
| Coordinator Mode | 实验性 | `CLAUDE_CODE_COORDINATOR_MODE=1` |
| Anti-Distillation | 活跃 | 注入假工具定义防止竞争对手训练 |

---

## 9. 对我们 V2 的影响

| 发现 | 影响 |
|------|------|
| 92% 缓存复用 | Agent/Rule 文件必须字母序排列 |
| 15 秒延迟规则 | evolve-daemon 加入阻塞时间限制 |
| AutoDream ≥24h+≥5 会话 | 记忆合并触发条件明确 |
| 路径作用域规则 | 管理 100+ 仓库上下文的核心技术 |
| Deny-First 原则 | 安全模型必须 Deny 优先 |
| 仅追加日志 | 采集数据用 JSONL，不可删除 |
| Progressive Disclosure | Skill/Agent 描述精准 30-50 tokens |
| Fork 继承缓存 | 并行 Agent 设计利用前缀复用 |

---

## 致谢

- Claude Code 源码泄露分析（Tencent Cloud, Beam, SourceTrail, TowardsAI, Ars Technica）
- NEXUS Hyper Agent Team（31 Agent 生产级编排）
- Harness Factory Pattern（6 种架构模式，+60% 质量提升）
- KAIROS heartbeat 模式（@uameer）
- OpenCastor AutoDream 实现（4 阶段流水线）
