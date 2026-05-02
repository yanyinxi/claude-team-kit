# auto-execute — 一键全执行 Skill

> 触发词：`全部执行` `一口气` `全部完成` `睡觉了` `忙去了` `一键执行`
>
> 功能：当用户说这些话时，自动执行已授权的任务，无需任何确认。
> 自动分析用户的待办任务，执行 Phase 0 → P → M → V 全部步骤。

## 触发判断逻辑

```python
# 如果用户输入包含以下任意触发词，视为"全执行授权"
TRIGGER_PHRASES = [
    "全部执行", "一口气", "全部完成", "睡觉了", "忙去了",
    "一键执行", "执行所有", "执行全部", "一次性执行",
    "不需要确认", "不需要再问", "直接执行"
]

# 检查条件
def should_auto_execute(user_input: str) -> bool:
    return any(phrase in user_input for phrase in TRIGGER_PHRASES)
```

## 执行流程

### 1. 识别待执行任务

检查当前对话上下文，识别用户授权执行的任务：

| 任务类型 | 判断条件 |
|----------|----------|
| 目录结构重构 | 说过 "restructure" 或看过 `docs/restructure-plan.md` |
| Bug 修复 | 提到 `fix:` 或 `修复` 或 `bug` |
| 新功能 | 提到 `feat:` 或 `实现` 或 `功能` |
| 测试执行 | 提到 `test` 或 `测试` |

### 2. 执行前准备

```bash
# 备份当前状态
git add -A
git stash  # 临时保存当前变更

# 创建执行日志
LOG_FILE=".claude/data/auto-execute-$(date +%Y%m%d-%H%M%S).log"
mkdir -p .claude/data
```

### 3. 执行任务

根据任务类型选择执行路径：

#### 类型 A: 目录结构重构（restructure）

```bash
# Phase 0: 紧急修复
bash scripts/execute-restructure.sh --phase=0

# Phase P: 路径重构
bash scripts/execute-restructure.sh --phase=p

# Phase M: 目录迁移
bash scripts/execute-restructure.sh --phase=m

# Phase V: 验证
bash scripts/execute-restructure.sh --phase=v
```

#### 类型 B: Bug 修复

```bash
# 找到相关测试
pytest tests/ -k "$(basename $BUGGY_FILE)" -v

# 修复并验证
# ... 执行修复 ...
pytest tests/ -k "$(basename $FIXED_FILE)" -v
```

#### 类型 C: 新功能

```bash
# 创建分支
git checkout -b "feat/$(date +%Y%m%d)-auto"

# 执行实现
# ... 实现代码 ...

# 运行测试
npm test

# 提交
git add -A
git commit -m "feat: auto-execute from auto-execute skill"
```

### 4. 执行后处理

```bash
# 恢复用户变更（如果有 stash）
# git stash pop  # 仅在有 stash 时

# 生成执行报告
echo "=== 执行报告 ===" >> $LOG_FILE
echo "任务: $TASK_TYPE" >> $LOG_FILE
echo "开始: $START_TIME" >> $LOG_FILE
echo "结束: $(date)" >> $LOG_FILE
echo "状态: $STATUS" >> $LOG_FILE
```

## 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| 命令执行失败 | 记录日志，继续执行下一步 |
| 测试失败 | 标记失败，生成 Bug 报告 |
| 权限不足 | 提示用户授权 |
| 磁盘空间不足 | 停止并报警 |

## 输出格式

执行完成后，输出简洁报告：

```
✅ 任务执行完成

📊 执行摘要
  - 任务类型: 目录结构重构
  - 执行步骤: Phase 0 → P → M → V
  - 总耗时: 5m 32s
  - 状态: 成功

📁 变更文件
  - 新增: 3 个（paths.py, config_loader.py, execute-restructure.sh）
  - 迁移: 13 个目录/文件
  - 修改: 4 个（package.json, .gitignore, .claudeignore, generate_skill_index.py）

⚠️ 注意事项
  - git commit 尚未执行（手动确认）
  - 建议运行 npm test 验证

💡 后续步骤
  1. git add -A && git commit -m 'feat: 目录结构重构'
  2. npm test
  3. 验证 Claude Code 加载正常
```

## 权限要求

此 Skill 需要以下权限才能正常工作：

```json
{
  "permissions": {
    "allow": [
      "Bash(bash *)",
      "Bash(git *)",
      "Bash(mkdir *)",
      "Bash(mv *)",
      "Bash(npm *)",
      "Bash(python3 *)",
      "Bash(sed *)",
      "Bash(node *)"
    ]
  }
}
```

## 与其他 Skill 的协作

- `ship`: 执行完成后调用 ship skill 进行交付
- `testing`: 如果测试失败，调用 testing skill 分析失败原因
- `git-master`: 如果需要创建分支，调用 git-master skill

## 注意事项

1. **执行前不询问**：用户授权后直接执行
2. **执行中不中断**：遇到错误继续执行下一步
3. **执行后生成报告**：生成可读的完成报告
4. **保留 git 历史**：使用 `git mv` 保留文件历史
5. **可回滚**：每步操作前备份，失败时可回滚
