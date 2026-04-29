---
name: batch-edit
description: 批量多文件编辑：批量重命名、跨文件搜索替换、长任务续跑。用于代码重构、批量修改配置文件。触发词：批量编辑、重命名、多文件修改
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit, Grep, Glob, ast_grep_search, ast_grep_replace, lsp_rename
context: fork
---

# 批量多文件编辑

用于大规模代码重构、批量修改配置文件、跨文件搜索替换等场景。通过系统化的方法处理多文件编辑任务，避免遗漏和错误。

## 何时使用

以下场景应优先使用此技能：

| 场景 | 示例 | 推荐方法 |
|------|------|----------|
| 变量/函数重命名 | 将 `getUserById` 改为 `fetchUserById` | LSP 重命名或 AST-grep |
| 跨文件字符串替换 | 将所有 `localhost:8080` 改为环境变量 | Grep + Edit 组合 |
| 批量修改配置文件 | 修改多个微服务的端口配置 | Glob + Edit 批量替换 |
| 代码模式替换 | 将旧 API 调用模式替换为新模式 | AST-grep 精确替换 |
| 删除死代码 | 移除项目中未使用的 import | AST-grep 搜索 + 确认后删除 |

**不宜使用**：
- 单文件内的简单修改（直接用 Edit）
- 语义复杂的重构（如提取方法、改变类层次结构）
- 需要理解业务逻辑的修改

## 1. 批量重命名变量/函数

### 方法一：LSP 重命名（推荐）

使用 Language Server Protocol 的重命名功能，可靠性最高：

```bash
# 1. 定位要重命名的符号
lsp_find_references

# 2. 验证重命名是否有效
lsp_prepare_rename

# 3. 执行重命名（自动更新所有引用）
lsp_rename
```

**适用场景**：
- 变量、函数、类名重命名
- 需要保持语义正确性
- 项目有完整的 LSP 支持

**优势**：
- 自动处理所有引用
- 保持语法正确性
- 支持预览变更

### 方法二：AST-grep 精确替换

基于抽象语法树的模式匹配，适合结构化替换：

```bash
# 搜索模式
ast_grep_search --pattern 'const $NAME = require("$PATH")'

# 替换模式
ast_grep_replace --pattern 'const $NAME = require("$PATH")' --rewrite 'import $NAME from "$PATH"'
```

**适用场景**：
- 模式化的代码结构替换
- 需要保留匹配内容的替换
- 跨语言代码转换

### 手动批量重命名流程

对于复杂场景，按以下步骤执行：

```markdown
1. 搜索确认：Grep 找到所有使用位置
2. 分类处理：按文件类型/重要性分组
3. 逐批修改：每批 5-10 个文件，确认后再继续
4. 验证完整：再次 Grep 确认无遗漏
5. 测试通过：运行测试确保功能正常
```

## 2. 跨文件搜索替换

### 基础替换流程

```bash
# 第一步：精确搜索，确认范围
grep --path "src/" --pattern "oldPattern" --output-mode "content"

# 第二步：分析匹配结果，确认替换安全
# - 检查是否有误匹配
# - 确认替换不会破坏其他逻辑
# - 识别需要排除的文件

# 第三步：分批替换
# 建议按目录或文件类型分批，每批验证

# 第四步：验证替换结果
grep --path "src/" --pattern "newPattern"  # 确认新模式存在
grep --path "src/" --pattern "oldPattern"  # 确认旧模式已清除
```

### 正则表达式替换

支持正则表达式的跨文件替换：

```bash
# 示例：批量替换日志级别
# 原始: logger.info("User logged in")
# 目标: logger.debug("User logged in")

# 使用正则捕获组
ast_grep_replace --pattern 'logger\.(info|warn)\($MSG\)' --rewrite 'logger.debug($MSG)'
```

**常用正则替换模式**：

| 场景 | 正则模式 | 替换为 |
|------|----------|--------|
| console.log 替换 | `console\.(log\|debug\|info)` | `logger.$1` |
| 路径替换 | `\/api\/v1\/` | `/api/v2/` |
| 变量命名 | `_(\w+)` | `$1` |
| 注释模板 | `/\*\*\s*\n\s*\*\s*@(\w+)` | `/** @returns */` |

### 批量替换安全检查清单

执行替换前必须确认：

- [ ] 已备份或可从版本控制恢复
- [ ] 理解每个匹配项的上下文
- [ ] 识别并排除测试文件（如果需要）
- [ ] 确认没有动态拼接的字符串被误改
- [ ] 准备好回滚方案

## 3. 长任务续跑机制

### 任务状态保存

对于耗时的批量任务，记录关键状态信息：

```markdown
## 任务进度记录

**任务**: 批量重命名 `getUser` → `fetchUser`
**开始时间**: 2024-01-15 10:30:00
**总文件数**: 47
**已完成**: 23
**进行中**: src/services/UserService.java

### 已完成文件
- src/api/UserController.java
- src/service/UserService.java
- ... (23个文件)

### 待处理文件
- src/repository/UserRepository.java
- src/model/User.java
- ... (24个文件)

### 下一步操作
从 UserRepository.java 继续处理
```

### 续跑步骤

1. **读取任务记录**：查看上次的进度状态
2. **定位断点**：从"进行中"的文件继续
3. **验证一致性**：检查已修改文件与记录是否一致
4. **继续执行**：完成剩余文件
5. **更新记录**：记录新的完成状态

### 断点恢复检查

```bash
# 验证文件状态一致性
git diff --stat  # 检查已修改文件数量
grep "getUser" src/  # 确认还有无遗漏
```

## 4. 任务进度跟踪

### 多阶段任务管理

使用 todowrite 工具跟踪进度：

```typescript
// 批量替换任务示例
todowrite([
  { content: "搜索并确认所有匹配项", status: "completed", priority: "high" },
  { content: "替换 src/api/ 目录下文件", status: "in_progress", priority: "high" },
  { content: "替换 src/service/ 目录下文件", status: "pending", priority: "high" },
  { content: "替换 src/controller/ 目录下文件", status: "pending", priority: "high" },
  { content: "运行测试验证替换正确性", status: "pending", priority: "high" },
  { content: "手动验证关键功能点", status: "pending", priority: "medium" }
])
```

### 进度检查点

每完成一批文件，执行以下检查：

| 检查项 | 命令 | 通过标准 |
|--------|------|----------|
| 语法正确 | `lsp_diagnostics` | 无 error |
| 编译通过 | `mvn compile` / `npm run build` | 成功 |
| 测试通过 | `mvn test` / `npm test` | 全部通过 |
| 无遗漏 | `grep "oldPattern"` | 0 结果 |

## 5. 最佳实践

### 核心原则

1. **先搜后改**
   - 永远先用 Grep/AST-grep 搜索确认范围
   - 不确定时缩小范围，多次验证

2. **小步快跑**
   - 单次替换不超过 20 个文件
   - 每批验证后再继续

3. **可逆操作**
   - 优先使用版本控制而非备份
   - 复杂修改前创建分支

4. **验证闭环**
   - 替换后必须验证
   - 运行测试确保功能无损

### 常见陷阱及规避

| 陷阱 | 规避方法 |
|------|----------|
| 遗漏匹配项 | 使用 `head_limit` 分批检查，确保全覆盖 |
| 误匹配无关内容 | 增加上下文匹配条件，减少误报 |
| 破坏动态拼接 | 检查是否有字符串拼接的调用，必要时排除 |
| 编码问题 | 明确文件编码，使用 UTF-8 |
| 换行符差异 | 统一使用项目默认的换行符风格 |

### 推荐工作流

```markdown
1. 明确范围
   └── 定义要修改的文件集合（目录/扩展名/路径模式）

2. 搜索定位
   └── Grep/AST-grep 确认所有匹配项
   └── 分析匹配结果，排除不需要修改的位置

3. 分类规划
   └── 按文件重要性分组（核心/配置/测试）
   └── 规划修改顺序（从重要到次要）

4. 分批执行
   └── 每批 5-10 个文件
   └── 每批完成后执行验证检查点

5. 整体验证
   └── 运行完整测试套件
   └── 手动验证关键功能
   └── 代码审查确认修改合理
```

## 6. 参考资料

### 工具文档

| 工具 | 文档 | 适用场景 |
|------|------|----------|
| **AST-grep** | https://ast-grep.github.io/ | 结构化代码模式替换 |
| **LSP 重命名** | 编辑器内置 | 符号重命名 |
| **Grep** | 本工具文档 | 文本搜索 |
| **Glob** | 本工具文档 | 文件发现 |

### IDE 参考

- **VS Code**: 多文件编辑 - `Cmd+Shift+F` 全局替换，`Cmd+Shift+H` 局部替换
- **IntelliJ IDEA**: 重构工具 - `Shift+F6` 重命名，`Ctrl+Shift+R` 批量替换
- **WebStorm**: 支持正则表达式的批量替换和文件范围限定

### 社区最佳实践

- AST-grep 官方指南：提供结构化搜索和替换的最佳实践
- VS Code 批量编辑技巧：使用正则和捕获组实现复杂替换
- 重构手册：Martin Fowler - 描述了安全的大规模代码修改方法论

---

## 进化记录

_此章节由维护者按需更新，记录从实际任务执行中学到的经验和最佳实践。_

### 2024-01-15 初始版本

- 创建基础工作流程
- 定义常用的批量操作模式