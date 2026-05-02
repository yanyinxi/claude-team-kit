---
name: continuous-learning-v2
description: >
  本能观测系统 v2。自动捕获用户反馈、代码模式、执行轨迹，提取为本能记录并持续进化。
  支持 PreToolUse + PostToolUse + UserPromptSubmit 三路 Hook 事件监听，自动将观测数据
  写入 observations.jsonl。后台 Haiku Agent 分析生成候选本能，置信度动态演化。
  激活条件：用户纠正 / 确认 / 拒绝提示词时触发本能记录。
---

# continuous-learning-v2 — 本能观测与进化系统 v2

## 架构概览

```
用户交互
    ↓
┌──────────────────────────────────────────┐
│  Claude Code Hooks（PreToolUse +          │
│  PostToolUse + UserPromptSubmit）          │
│  自动捕获事件                              │
└────────┬─────────────────────────────────┘
         ↓
┌────────────────────┐
│  observe.sh        │ → observations.jsonl
│  (轻量事件捕获)      │
└────────┬───────────┘
         ↓
┌────────────────────┐
│  后台 Haiku Agent   │ → 本能候选生成
│  (异步分析)          │
└────────┬───────────┘
         ↓
┌────────────────────┐
│  instinct-record   │ → 本能记录持久化
│  (agents/instinct/) │
└────────────────────┘
         ↓
┌────────────────────┐
│  /evolve 进化系统    │ → Skill 建议
└────────────────────┘
```

## 事件捕获机制

### Hook 类型

| Hook | 触发场景 | 捕获内容 |
|------|---------|---------|
| `PreToolUse` | 工具调用前 | 意图推断、上下文 |
| `PostToolUse` | 工具调用后 | 结果质量、成功/失败 |
| `UserPromptSubmit` | 用户提交提示词 | 反馈模式、意图澄清 |

### observe.sh 事件提取

**UserPromptSubmit 反馈检测**：

```
用户输入 → 正则匹配 → 分类

纠正类关键词：不对 / not right / wrong / 错了 / incorrect / should be / 应该 / 改成 / change to / fix / 修正
    ↓
反馈类型 = "correction"
    ↓
提取：原内容 + 用户期望 → 本能候选

确认类关键词：好 / good / correct / 可以 / ok / perfect / 很好
    ↓
反馈类型 = "approval"
    ↓
提取：模式强化信号

拒绝类关键词：不对 / no / don't / stop / 别
    ↓
反馈类型 = "rejection"
    ↓
提取：边界条件识别
```

**PostToolUse 模式检测**：

```
Read 工具 → 提取文件类型（.tsx/.py/.go）
Write/Edit 工具 → 检测内容关键词（test/spec/config/setup）
    ↓
模式类型：code_write / test_write / config_write
```

## 本能候选生成流程

1. **事件累积**：observe.sh 持续写入 `observations.jsonl`
2. **Haiku 异步分析**：后台 Agent 读取观测日志
3. **候选提取**：Haiku 识别重复模式，生成本能提案
4. **置信度初始化**：
   - 首次观测：confidence = 0.3（OBSERVE）
   - eval_count ≥ 1：confidence += 0.1
   - eval_count ≥ 3：confidence += 0.1（PROPOSAL）
   - 用户 confirm：confidence = 0.9（AUTO）

## 观测数据结构

```json
{
  "timestamp": "2026-05-01T12:00:00Z",
  "session_id": "uuid",
  "hook_type": "UserPromptSubmit",
  "tool": "",
  "feedback": "correction",
  "patterns": ""
}
```

## 与旧版本 continuous-learning 的区别

| 维度 | v1 | v2（本技能） |
|------|----|------------|
| 事件捕获 | PostToolUse Only | PreToolUse + PostToolUse + UserPromptSubmit |
| 反馈检测 | 无 | 中文/英文双模式正则 |
| 数据存储 | 内存 | JSONL 持久化 |
| 异步分析 | 同步 | 后台 Haiku |
| 置信度 | 固定 | 动态演化 |

## 使用方式

本能观测系统在后台自动运行，无需用户主动调用。下列场景自动触发本能记录：

```
用户纠正 AI 错误时
    ↓
"不对，应该是这样..."
    ↓
observe.sh 捕获 correction 事件
    ↓
Haiku 分析，生成本能候选
    ↓
下次遇到类似场景，AI 自动检索本能库
```

## 验证方法

```bash
# 1. Hook 脚本可执行
[[ -x hooks/bin/observe.sh ]] && echo "✅"

# 2. UserPromptSubmit 反馈检测
echo '{"sessionId":"test","message":{"type":"user","content":"不对，这个逻辑有问题"}}' | bash hooks/bin/observe.sh
# 期望：写入 observations.jsonl，feedback=correction

# 3. 确认正常内容不误触发
echo '{"sessionId":"test","message":{"type":"user","content":"请帮我写一个函数"}}' | bash hooks/bin/observe.sh
# 期望：无输出（不匹配反馈关键词）

# 4. 观测文件生成
ls .claude/homunculus/observations.jsonl && echo "✅ 观测日志存在"
```

## Red Flags

- `observations.jsonl` 持续为空（Hook 未触发）
- 本能记录全是 OBSERVE，无 PROPOSAL（用户从不确认）
- 本能置信度从不高（缺少反馈机制）
