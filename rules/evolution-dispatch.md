# 进化派发规则

**更新时间**: 2026-04-28（v2 — SessionStart hook 强制注入 Agent 派发指令）
**适用范围**: 全局（SessionStart 后首次响应）

## 机制概览

进化派发现在是**全自动**的，带硬回退保障：

1. Stop hook (`session_evolver.py`) → 聚合数据 → 写入 `pending_evolution.json`
2. SessionStart hook (`auto_evolver.py`) → 读取 triggers → 更新 `consecutive_missed` 计数
3. 安全门禁（熔断器 + 限流器 + 文件存在性）
4. 主路径：构建 `evolutionDispatch` + `evolutionMandate` → 注入系统上下文 → LLM 派发 Agent evolver
5. **硬回退**：同一 trigger `consecutive_missed >= 2` → Python `EvolutionEngine.force_evolve()` 接管
6. **放弃机制**：`consecutive_missed >= 5` → 移除 trigger，记录警告
7. Agent evolvers → 分析执行数据 → 重写目标文件 → 清除自己的 trigger → 追加 `evolution_history.jsonl`

## 强制派发协议

当系统上下文包含 `evolutionMandate` 时，你**必须**在处理完用户请求的第一个响应中派发进化 Agent。

`evolutionDispatch` 数组中每个元素包含 `agent_call` 字段，直接作为 `Agent()` 工具调用的参数：

```
Agent(
    subagent_type=dispatch.agent_call.subagent_type,
    description=dispatch.agent_call.description,
    prompt=dispatch.agent_call.prompt,
    run_in_background=True
)
```

### 派发映射

| dispatch.dimension | evolver agent | 目标文件类型 |
|---|---|---|
| `skill` | skill-evolver | `.claude/skills/<target>/SKILL.md` |
| `agent` | agent-evolver | `.claude/agents/<target>.md` |
| `rule` | rule-evolver | `.claude/rules/<target>.md` |
| `memory` | memory-evolver | `.claude/memory/<target>.md` |

### 并发限制

- 每次会话最多派发 3 个进化 Agent（与 `EvolutionRateLimiter.MAX_PER_SESSION` 一致）
- `auto_evolver.py` 已在注入前完成安全门禁（熔断器 + 限流器 + 文件存在性）
- 所有 evolver 互不依赖，可以并行派发

### 进化完成后

用 Python 清除 `pending_triggers`：

```python
import json, os
from pathlib import Path

root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
pending_path = root / ".claude" / "data" / "pending_evolution.json"
if pending_path.exists():
    data = json.loads(pending_path.read_text())
    data["pending_triggers"] = []
    pending_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
```

保留 `feedback_signals` 不清除。

## 反模式

### ⚠️ 忽视 evolutionMandate

系统上下文包含 `evolutionMandate` 但主 session 没有派发进化 Agent → 进化永不执行，`pending_evolution.json` 堆积。这是自动化指令，不可跳过。

### ⚠️ 不清除 pending_triggers

进化完成后不清除 → 下次会话重复派发相同进化。

### ⚠️ 手动修改 evolutionDispatch

不要自己构建 `Agent()` 参数 — 直接使用 `evolutionDispatch[].agent_call` 中的精确参数。
