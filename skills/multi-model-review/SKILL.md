---
name: multi-model-review
description: Cross-model code review using multiple AI models for independent verification. Use for critical code paths, security-sensitive changes, or when second opinion is needed.
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
