---
name: tdd
description: Test-Driven Development workflow. Use when writing new features, fixing bugs, or any code change that should be verified. Enforces RED → GREEN → REFACTOR cycle.
---

# TDD — 测试驱动开发

## RED → GREEN → REFACTOR

```
RED:   先写失败的测试（描述期望行为）
GREEN: 写最少代码让测试通过
REFACTOR: 消除重复，改善结构，保持测试绿
```

## 规则

1. **永远测试先行**：代码在测试之后
2. **最小步长**：每步只让一个测试从红变绿
3. **重构时测试保持绿**：重构不改行为，只改结构
4. **一个测试一个行为**：不写多合一的测试

## 测试命名

```
should[ExpectedBehavior]_when[Condition]
例: shouldReturn404_whenUserNotFound
    shouldThrowValidationError_whenEmailIsEmpty
```

## 测试结构

```
Arrange:  准备测试数据和依赖
Act:      执行被测行为
Assert:   验证结果
```

## Red Flags

- 实现代码写在测试之前
- 测试依赖执行顺序
- 测试不可重复运行
