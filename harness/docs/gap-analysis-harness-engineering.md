# Claude Harness Kit vs Harness Engineering 深度差距分析

> 生成时间: 2026-05-01  
> 分析范围: v0.4 完整代码库 vs OpenAI Harness Engineering + Harness CI/CD Platform

---

## 一、当前实现状态总览

| 模块 | 规划 | 实际 | 完成度 | 状态 |
|------|:--:|:--:|:--:|:--:|
| **Agents** | 22 | 22 | 100% | ✅ |
| **Skills** | 20 | 19 | 95% | ⚠️ |
| **Rules** | 6 | 6 | 100% | ✅ |
| **7种执行模式** | 7 | 7 | 100% | ✅ |
| **CLI工具** | 8 | 8 | 100% | ✅ |
| **evolve-daemon** | 5组件 | 5组件 | 100% | ✅ |
| **知识生命周期** | lifecycle.py+yaml | 已实现 | 100% | ✅ |
| **GC Agent** | agents/gc.md | 已实现 | 100% | ✅ |
| **意图检测** | intent_detector.py | 已实现 | 100% | ✅ |
| **自动回滚** | rollback.py | 已实现 | 100% | ✅ |
| **Skill INDEX.md** | 20个 | **0个** | 0% | 🔴 |
| **instinct记录** | 50+条 | 10条 | 20% | ⚠️ |
| **Sessions数据** | 大量 | 22条 | 初期 | ⚠️ |

**整体评估**: 架构完整度 95%，运行就绪度 30%

---

## 二、核心差距详解

### 🔴 差距 1：渐进式知识索引（Progressive Disclosure）完全缺失

**Harness Engineering 要求**:
```
Stage 1: INDEX.md (~50 tokens/skill) 始终加载
Stage 2: 匹配时加载完整 INDEX.md (~300 tokens)
Stage 3: 执行时加载 SKILL.md 正文
节省 ~90% skill 上下文占用
```

**当前状态**:
```bash
$ find skills -name "INDEX.md" | wc -l
0  # 一个都没有！
```

**影响**: 每次对话都加载全部 SKILL.md (~23K tokens)，无缓存优化，上下文浪费严重。

**修复方案**:
```bash
# 为每个 Skill 创建 INDEX.md
python3 cli/generate_skill_index.py --all
```

---

### 🟠 差距 2：Instinct 数据积累不足

**Harness Engineering 要求**:
- 置信度升级路径: 0.3 → 0.5 → 0.7 → 0.9
- 需要 ≥50 条真实纠正记录才能启动学习闭环

**当前状态**:
```json
// instinct/instinct-record.json
{
  "records": [
    {"id": "seed-001", "source": "seed", "confidence": 0.7},
    {"id": "seed-002", "source": "seed", "confidence": 0.7},
    // ... 总共只有 10 条，其中 5 条是种子，5 条是测试数据
  ]
}
```

**问题**: 没有真实的用户纠正数据，evolve-daemon 分析的是"空转"。

---

### 🟠 差距 3：知识生命周期系统未激活

**已实现的组件**:
- ✅ `knowledge/lifecycle.py` - 成熟度检查、衰减逻辑、跨项目提升
- ✅ `knowledge/lifecycle.yaml` - 配置定义
- ✅ `knowledge/project/` 和 `knowledge/team/` 目录结构

**未激活的原因**:
```bash
$ ls knowledge/project/
# 空目录

$ ls knowledge/team/
# 空目录
```

没有实际的知识条目，生命周期引擎无数据可处理。

**修复方案**:
```bash
# 创建首批知识条目
mkdir -p knowledge/project/{model,decision,guideline,pitfall,process}
mkdir -p knowledge/team/tech-wiki
# 手动创建 5-10 条初始知识
```

---

### 🟡 差距 4：Hook 系统集成状态未知

**已配置的 Hooks** (hooks/hooks.json):
- ✅ SessionStart: context-injector.py
- ✅ PreToolUse[Bash]: safety-check.sh
- ✅ PreToolUse[Write|Edit]: tdd-check.sh
- ✅ PostToolUse[Write|Edit]: quality-gate.sh
- ✅ PostToolUse[Agent]: collect-agent.py
- ✅ PostToolUse[Skill]: collect-skill.py
- ✅ PostToolUseFailure: collect-failure.py
- ✅ Stop: collect-session.py

**差距**: Hook 脚本是否真正被 Claude Code 调用？无法验证，因为:
1. 这是插件系统，需要安装到 Claude Code 才能生效
2. 当前只是文件存在，没有运行时验证

**修复方案**:
```bash
# 安装插件
claude plugins marketplace add --scope local $(pwd)
claude plugins install claude-harness-kit

# 验证 Hook 触发
tail -f .claude/data/sessions.jsonl
```

---

### 🟡 差距 5：evolve-daemon 未进入生产循环

**已实现**:
- ✅ daemon.py - 触发条件检查、定时任务
- ✅ analyzer.py - 聚合分析
- ✅ proposer.py - 生成提案
- ✅ rollback.py - 自动回滚逻辑
- ✅ intent_detector.py - 意图失败检测

**未启动**:
```bash
$ ps aux | grep evolve
# 没有运行中的守护进程

$ launchctl list | grep claude-harness
# 没有注册的服务
```

**修复方案**:
```bash
# 注册并启动守护进程
python3 evolve-daemon/daemon.py install-launchd
launchctl load ~/Library/LaunchAgents/com.claude-harness-kit.evolve.plist

# 验证运行
python3 evolve-daemon/daemon.py status
```

---

### 🟢 差距 6：7种执行模式缺少运行时验证

**已实现的模式配置** (cli/modes/):
- ✅ solo.json / auto.json / team.json / ultra.json
- ✅ pipeline.json / ralph.json / ccg.json

**但缺少**:
- 实际项目验证数据
- 各模式的成功率统计
- 模式推荐准确率（根据任务类型自动选择）

---

## 三、与 OpenAI Harness Engineering 的核心差距

| 能力 | Harness Engineering | Claude Harness Kit | 差距 | 优先级 |
|------|--------------------|-------------------|:--:|:--:|
| **Symphony 编排器** | 全自动 Agent 调度 | orchestrator.md 定义 | 🟡 | P1 |
| **知识生命周期** | 5层+3级成熟度+自动衰减 | 实现完整但未激活 | 🟠 | P1 |
| **GC Agent** | 定期扫描+自动PR | agents/gc.md 定义 | 🟡 | P1 |
| **意图失败检测** | 实时捕获+学习 | intent_detector.py 实现 | 🟡 | P2 |
| **进化自动回滚** | 7天观察+熔断 | rollback.py 实现 | 🟡 | P2 |
| **渐进式索引** | 3级加载 | **完全缺失** | 🔴 | **P0** |
| **跨项目知识提升** | L3→L1自动提升 | lifecycle.py 实现 | 🟠 | P2 |
| **优化建议引擎** | 参数/模型/并行化建议 | **未实现** | 🔴 | P2 |

---

## 四、与 Harness CI/CD Platform 的差距

| 能力 | Harness Platform | Claude Harness Kit | 差距 | 优先级 |
|------|-----------------|-------------------|:--:|:--:|
| **AutoFix Agent** | 自动修复 pipeline 失败 | **未实现** | 🔴 | P1 |
| **AI 验证** | 部署前自动验证 | verifier Agent 定义 | 🟡 | P2 |
| **自动回滚** | 指标恶化自动回滚 | rollback.py 实现 | 🟡 | P2 |
| **持续验证** | 生产环境持续监控 | **未实现** | 🔴 | P2 |
| **优化建议** | 参数调优建议 | **未实现** | 🔴 | P3 |

---

## 五、关键阻塞点（Blockers）

### Blocker 1: Skill INDEX.md 完全缺失
**影响**: 无法启用渐进式加载，上下文消耗大  
**解决**: 为每个 Skill 创建 INDEX.md（30-50行摘要）  
**工作量**: 19 skills × 10分钟 = 3小时

### Blocker 2: Plugin 未安装到 Claude Code
**影响**: Hook 不触发，无法收集 session 数据  
**解决**: 执行安装流程
```bash
claude plugins marketplace add --scope local $(pwd)
claude plugins install claude-harness-kit
```

### Blocker 3: evolve-daemon 未运行
**影响**: 无自动分析、无提案生成  
**解决**: 注册 launchd/systemd 服务

### Blocker 4: 缺乏真实项目数据
**影响**: instinct 无法升级，知识无法积累  
**解决**: 需要在真实项目中使用 3-5 周积累数据

---

## 六、实施路线图（优先级排序）

### P0: 立即执行（阻塞所有后续）

| 任务 | 命令 | 预计时间 |
|------|------|:--:|
| 创建所有 Skill 的 INDEX.md | `python3 cli/generate_skill_index.py --all` | 3小时 |
| 验证 Plugin 安装 | `claude plugins install` | 10分钟 |
| 启动 evolve-daemon | `daemon.py install-launchd` | 5分钟 |

### P1: 本周内完成

| 任务 | 说明 | 预计时间 |
|------|------|:--:|
| 创建首批知识条目 | 5条 draft + 3条 verified | 2小时 |
| 试点验证 | 1-2个真实项目使用 | 1周 |
| 验证 Hook 数据收集 | 检查 sessions.jsonl 增长 | 持续 |
| 验证 evolve-daemon 分析 | 检查 proposals/ 目录 | 持续 |

### P2: 本月内完成

| 任务 | 说明 | 预计时间 |
|------|------|:--:|
| 实现缺失的 Skill | 19/20，缺1个 | 4小时 |
| 添加 AutoFix Agent | 对标 Harness Platform | 1天 |
| 持续验证系统 | 生产监控机制 | 2天 |
| 积累 50+ instinct 记录 | 启动学习闭环 | 2-3周 |

### P3: 下季度完成

| 任务 | 说明 | 预计时间 |
|------|------|:--:|
| 优化建议引擎 | 参数/模型/并行化建议 | 1周 |
| 跨项目知识提升自动化 | L3→L1 自动触发 | 3天 |
| 首次自动回滚触发 | 验证熔断机制 | 待定 |

---

## 七、关键指标追踪

| 指标 | 当前 | 目标 (P0后) | 目标 (P1后) | 目标 (P2后) |
|------|:--:|:--:|:--:|:--:|
| Skill INDEX.md 覆盖率 | 0% | 100% | 100% | 100% |
| Plugin 安装状态 | ❌ | ✅ | ✅ | ✅ |
| evolve-daemon 运行状态 | ❌ | ✅ | ✅ | ✅ |
| instinct 记录数 | 10 | 10 | 30 | 50+ |
| Sessions 数据量 | 22 | 22 | 100+ | 500+ |
| 知识条目数 | 0 | 5 | 15 | 30+ |
| Skill 上下文占用 | ~23K tokens | ~2.3K tokens | ~2.3K tokens | ~2.3K tokens |

---

## 八、总结

| 维度 | 评分 | 说明 |
|------|:--:|:--|
| **架构设计** | ⭐⭐⭐⭐⭐ | 完全对齐 Harness Engineering |
| **代码实现** | ⭐⭐⭐⭐ | 核心组件都实现了 |
| **数据积累** | ⭐ | 几乎是空的，需要时间 |
| **运行时验证** | ⭐ | Plugin 未安装，未跑起来 |
| **生产就绪** | ⭐ | 还需要 4-6 周验证期 |

### 核心结论

> Claude Harness Kit **设计层面完全对标** Harness Engineering，但**运行层面还在起跑线上**。

最大的差距不是代码，而是:
1. **Skill 渐进索引未实现** (P0)
2. **缺乏真实使用数据** (P1-P2)
3. **Plugin 未激活运行** (P0)

如果现在就投入真实项目使用，预计 **4-6 周后** 可以达到 Harness Engineering Phase 2 水平（有数据积累的试点验证期）。

---

## 附录：快速检查清单

```bash
# 检查 1: INDEX.md 覆盖率
find skills -name "INDEX.md" | wc -l
# 期望: 19, 实际: 0 🔴

# 检查 2: Plugin 安装状态
claude plugins list | grep claude-harness-kit
# 期望: 已安装, 实际: 未知 🟡

# 检查 3: evolve-daemon 运行状态
launchctl list | grep claude-harness
# 期望: 有服务, 实际: 无 🔴

# 检查 4: 数据积累状态
wc -l .claude/data/sessions.jsonl
# 期望: 50+, 实际: 22 🟡

# 检查 5: 知识条目状态
find knowledge -name "*.json" | wc -l
# 期望: 10+, 实际: 0 🔴

# 检查 6: instinct 记录数
cat instinct/instinct-record.json | jq '.records | length'
# 期望: 50+, 实际: 10 🟠
```

---

*本文档由 Claude Code 自动生成，用于指导项目从"架构完整"走向"生产就绪"。*
