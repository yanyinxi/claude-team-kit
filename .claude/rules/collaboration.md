# 协作规范

## 多 Agent 工作原则

1. **上下文优先** — 执行前先读取 CLAUDE.md 和相关知识库
2. **唯一信源** — 文件修改以 CLAUDE.md 指定路径为准，避免路径漂移
3. **验证后交付** — 测试通过后再提交，不留半成品
4. **进化反馈** — 错误/异常写入 instinct 数据供后续学习

## 提交规范

- 提交前运行 `npm test`
- commit message 格式: `type(scope): message`
- type: feat/fix/docs/chore/refactor

## 路径规范

- 运行时数据: `harness/instinct/`
- Hook 脚本: `harness/hooks/` (通过符号链接 `hooks/` 访问)
- 知识库: `.claude/knowledge/`