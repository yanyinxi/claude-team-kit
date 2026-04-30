---
scope: global
---

# General Development Rules

**更新时间**: 2026-04-30
**适用范围**: 全局（所有文件）

## 最佳实践

### 使用 Agent 工具调用专业代理

不要主 session 自己写所有代码。正确方式：

```
# 并行分配独立任务
Agent(subagent_type="backend-dev", prompt="实现 AssetController...")
Agent(subagent_type="frontend-dev", prompt="实现 AssetList.vue...")
```

### Git 提交规范

```
feat(scope):     新功能
fix(scope):      修复 Bug
docs(scope):     文档
refactor(scope): 重构
test(scope):     测试
chore(scope):    构建/配置
```

### 代码注释规范

- 只在 WHY 非显而易见时写注释（隐藏约束、绕过已知 bug、算法选择原因）
- 不写注释说 WHAT（方法名已经表达了）

## 反模式

### 不提交 .claude/ 目录

`.claude/` 目录包含会话数据，通过 .gitignore 排除。

### 跳过测试

集成测试应使用真实依赖（如 Testcontainers），不用内存模拟替代。

### 不规范的 Git 提交

提交信息使用 `feat/fix/docs/refactor/test/chore` 前缀，中文描述。
