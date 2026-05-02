---
name: multi-model-review
description: >
  使用多个AI模型进行独立验证的交叉审查。适用于关键代码路径、安全敏感变更或需要第二意见时。
  同时发3个独立Agent（Sonnet代码审查+Opus安全审计+Sonnet测试覆盖），
  汇总结果并对比差异。激活条件：用户要求多方面审查或涉及安全/支付代码。
---

# Multi-Model Review — 多模型交叉审查

## 适用场景

- 安全敏感代码（认证、支付、权限）
- 核心业务逻辑
- 关键架构决策
- 用户明确要求"多方面审查"

## 审查流程

1. 同时发 3 个独立 Agent：
   - code-reviewer (Sonnet) — 代码质量
   - security-auditor (Opus) — 安全审计
   - qa-tester (Sonnet) — 测试覆盖
2. 汇总 3 个独立审查结果
3. 对比差异，高亮不一致点
4. 差异项人工决策

## 输出

```markdown
# 交叉审查报告

## 一致发现
- all agree: xxx

## 差异发现
| 问题 | Reviewer | Auditor | Tester |
|------|----------|---------|--------|
| xxx  | PASS     | WARN    | PASS   |
```
