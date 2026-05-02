---
name: eval-harness
description: >
  EDD（Eval-Driven Development）评估框架。提供 4 种 grader 类型（Code-Based/Model-Based/
  Rule-Based/Human-Based）和 pass@k 指标体系（pass@3 > 90% 表示能力、pass^3 = 100% 无回归）。
  内置完整 artifact 布局、Happy-Path 检测和 flaky grader 反模式识别。
  激活条件：eval 任务、pass@k 评估、Agent 能力基准测试。
---

# Eval Harness — 评估驱动开发框架

## 概述

Eval-Driven Development（EDD）通过可量化的指标评估 Agent 能力，避免"感觉良好"的定性判断。

## 核心指标

### pass@k

```
pass@k = P(at least 1 of k samples passes)
```

- **pass@1** — 单次成功率（严格场景）
- **pass@3** — 3次采样中至少1次成功（能力探测，>90% 则认为"具备该能力"）
- **pass^3** — 3次采样全部通过（回归检测，100% = 无回归）

### 能力评估标准

| pass@3 | 能力等级 |
|--------|---------|
| ≥90% | 🟢 已具备该能力 |
| 50-90% | 🟡 部分具备，需增强 |
| <50% | 🔴 不具备该能力 |

### 回归检测标准

| pass^3 | 判定 |
|--------|------|
| 100% | ✅ 无回归 |
| <100% | ⚠️ 存在回归 |

## 4种 Grader 类型

### 1. Code-Based Grader（确定性）

```python
def grader_code(expected: str, actual: str) -> bool:
    """精确匹配或语义等价"""
    return normalize(expected) == normalize(actual)
```

适用：API 响应、数据转换、已知输出

### 2. Model-Based Grader（AI评分）

```python
def grader_model(prompt: str, actual: str) -> float:
    """让评判模型打分 0-1"""
    return call_model(f"""
判断以下代码是否解决了问题：
问题：{prompt}
代码：{actual}
评分 0-1：
""")
```

适用：开放式问题、无标准答案

### 3. Rule-Based Grader（正则/结构）

```python
def grader_rule(actual: str, rules: list[re.Pattern]) -> dict:
    """按规则检查"""
    return {"pass": all(r.search(actual) for r in rules)}
```

适用：安全合规（无硬编码密钥）、代码规范（无 TODO）

### 4. Human-Based Grader（人工审查）

```python
def grader_human(task_id: str) -> bool:
    """人工确认"""
    return ask_user(f"任务 {task_id} 是否满足要求？(y/n)")
```

适用：关键业务逻辑、用户体验评估

## Artifact 布局

```
.claude/evals/<feature-name>/
├── eval.yaml              # 评估配置
├── cases/
│   ├── case-001.json     # 测试用例
│   ├── case-002.json
│   └── ...
├── results/
│   ├── run-20260501.json  # 运行结果
│   └── summary.json        # 汇总
└── graders/
    ├── __init__.py
    ├── code_grader.py
    ├── model_grader.py
    └── rule_grader.py
```

## eval.yaml 格式

```yaml
name: auth-token-validation
grader_type: rule  # code | model | rule | human
pass_threshold: 0.9
cases: cases/*.json
rules:
  - pattern: "password.*="
    severity: critical
  - pattern: "TODO"
    severity: warning
```

## Case 格式

```json
{
  "id": "auth-001",
  "description": "JWT validation must check expiration",
  "input": {
    "token": "eyJhbGc..."
  },
  "expected": "reject expired token",
  "grader_config": {}
}
```

## 反模式检测

### Happy-Path Only（只测正常路径）

→ 必须包含负向测试（invalid input、boundary conditions）

### Overfitting（Grader 过拟合）

→ 相同输入不同 graders 交叉验证

### Flaky Grader（不稳定）

→ 同一代码运行 5 次，≥1 次结果不同 → 修复 grader

### No Baseline（无基线）

→ 每次评估前运行基线版本，建立对比基准

## 执行流程

```
1. 定义 eval.yaml + cases/
2. 选择 grader 类型
3. 运行评估：claude eval <feature-name>
4. 分析 pass@k 报告
5. 若 regression → block PR
6. 若 capability 下降 → alert
```

## 集成 CI

```yaml
# .github/workflows/eval.yml
- name: Run EDD Eval
  run: |
    for feature in $(ls .claude/evals/); do
      claude eval "$feature" --format json > ".claude/evals/$feature/results/ci-$GITHUB_RUN_ID.json"
    done
- name: Check Regression
  run: claude eval --check-regression || exit 1
```

## Red Flags

- 无基线对比就说"pass"
- 只测 happy-path
- Flaky grader 不修复
- pass@3 低于阈值但仍 merge