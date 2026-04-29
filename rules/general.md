# General Development Rules（Java 项目）

**更新时间**: 2026-04-23
**适用范围**: 全局（所有文件）

## 最佳实践

### ✅ 使用 Agent 工具调用专业代理

不要主 session 自己写所有代码。正确方式：

```
# 并行分配独立任务
Agent(subagent_type="backend-developer", prompt="实现 AssetController...")
Agent(subagent_type="frontend-developer", prompt="实现 AssetList.vue...")
```

### ✅ Git 提交规范

```
feat(scope):     新功能
fix(scope):      修复 Bug
docs(scope):     文档
refactor(scope): 重构
test(scope):     测试
chore(scope):    构建/配置
```

### ✅ 代码注释规范

- 只在 WHY 非显而易见时写注释（隐藏约束、绕过已知 bug、算法选择原因）
- 不写注释说 WHAT（方法名已经表达了）

### ✅ 目录结构（Java Maven 标准）

| ❌ 禁止 | ✅ 正确 |
|--------|--------|
| `tests/`（根目录） | `main/backend/src/test/java/` |
| `main/tests/`（Python 时代旧规范） | `main/backend/src/test/java/` |
| `main/backend/docs/` | `main/docs/` |

## 反模式

### ⚠️ 不写 .gitignore

`.claude/` 目录必须在 .gitignore 中，不提交 git。

### ⚠️ 用 H2 替代 PostgreSQL 做集成测试

H2 不支持 `text[] @>`、`JSONB`、`ON CONFLICT DO UPDATE`、`gen_random_uuid()`。必须用 Testcontainers 起真实 PG 容器。

### ⚠️ 不规范的 Git 提交

提交信息必须用 `feat/fix/docs/refactor/test/chore` 前缀，便于 session_evolver.py 计算进化指标。

## 📈 合规统计（自动更新）

- **检查次数**: 508
- **违规次数**: 0
- **合规率**: 100.0%
- **最后更新**: 2026-04-28

_此章节由进化系统自动维护_
