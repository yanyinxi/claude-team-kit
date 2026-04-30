---
name: parallel-dispatch
description: Parallel task dispatch and aggregation for multi-agent workflows. Use when tasks can be executed independently, maximizing throughput through concurrent execution.
---

# Parallel Dispatch — 并行任务分派

## 适用条件

- 任务之间无数据依赖
- 每个任务可独立完成
- 任务量 ≥3 个

## 分派规则

```
1. 识别独立任务
2. 按优先级排序
3. 每个 Agent 用 run_in_background=true
4. 汇总结果后用 TodoWrite 追踪完成情况
5. 全部完成后进行最终汇总
```

## 反模式

- 有依赖的任务并行（会导致重复工作）
- 修改同一文件的并行（会产生冲突）
- 不跟踪后台 Agent 状态就继续

## 模式

```
Batch 1 (并行): Task A, Task B, Task C
Batch 2 (依赖 Batch 1): Task D
Batch 3 (并行): Task E, Task F
```
