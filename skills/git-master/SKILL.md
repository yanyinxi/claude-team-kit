---
name: git-master
description: Git 高级工程化：规范化 commit message、分支管理策略、自动化检查。用于代码提交、分支管理、版本发布。触发词：commit、rebase、squash、git
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Bash
context: fork
---

# Git Master Skill

Git 高级工程化技能，提供规范的提交信息格式、分支管理策略、自动化检查流程和版本发布能力。

## 何时使用

在以下场景中应调用此技能：

- **代码提交**：需要创建规范化的 commit message
- **分支管理**：进行分支创建、合并、删除、重命名等操作
- **版本发布**：准备发布版本、创建标签、生成 CHANGELOG
- **历史整理**：需要压缩（squash）、变基（rebase）提交历史
- **协作规范**：团队需要统一的 Git 工作流
- **触发词**：当用户提及 `commit`、`rebase`、`squash`、`git`、`分支`、`版本发布` 等关键词时

## Conventional Commits 格式规范

### 基本格式

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Type 类型定义

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(auth): add OAuth2 login support` |
| `fix` | Bug 修复 | `fix(api): resolve null pointer exception` |
| `docs` | 文档更新 | `docs(readme): update installation guide` |
| `style` | 代码格式（不影响功能） | `style(formatter): adjust indentation` |
| `refactor` | 重构（既不是新功能也不是修复） | `refactor(service): extract common logic` |
| `perf` | 性能优化 | `perf(cache): add Redis caching layer` |
| `test` | 测试相关 | `test(unit): add controller unit tests` |
| `build` | 构建系统或外部依赖 | `build(docker): update base image version` |
| `ci` | CI 配置文件和脚本 | `ci(github): add workflow for e2e tests` |
| `chore` | 其他不修改源代码或测试文件的更改 | `chore(deps): update npm dependencies` |
| `revert` | 回滚之前的提交 | `revert: feat(auth): add OAuth2 login` |

### Scope 作用域

可选，用于指定提交影响的范围：

- 模块名：`feat(api): add user endpoint`
- 文件名：`fix(controller): resolve validation bug`
- 功能名：`feat(payment): integrate Stripe API`

### Subject 规则

- 使用现在时态祈使句
- 首字母小写
- 结尾不加句号
- 长度控制在 50 个字符以内
- 空格后直接跟描述

### Body 规则

- 详细说明 what 和 why
- 每行不超过 72 个字符
- 使用过去时态描述

### Footer 规则

用于 BREAKING CHANGE 和关联 Issue：

```
BREAKING CHANGE: <description>

Closes #123
Refs #456
```

### 完整示例

```
feat(auth): implement JWT token refresh mechanism

- Add refresh token endpoint
- Store refresh token in httpOnly cookie
- Implement token rotation strategy

Closes #45
Refs #32
```

## 分支管理策略

### Git Flow

适用于有计划发布周期的项目（如定期版本发布）：

```
main (或 master)  ────●────●────●────●──── (tag: v1.0.0)
                        \                  \
                         \                  ●──●──● (release/v1.0)
                          \                /
                           ●──●──●──●──●── (develop)
                                  \
                                   ●──●──● (feature/login)
```

#### 分支类型

| 分支 | 命名规则 | 用途 | 合并目标 |
|------|----------|------|----------|
| `main` | `main` | 生产代码 | - |
| `develop` | `develop` | 开发主分支 | main (release) |
| `feature/*` | `feature/<issue-id>-<description>` | 新功能开发 | develop |
| `release/*` | `release/v<version>` | 版本准备 | develop, main |
| `hotfix/*` | `hotfix/<issue-id>-<description>` | 紧急修复 | develop, main |
| `bugfix/*` | `bugfix/<issue-id>-<description>` | 普通 Bug 修复 | develop |

#### Git Flow 命令

```bash
# 开始新功能
git checkout develop
git pull origin develop
git checkout -b feature/123-add-login

# 完成功能
git checkout develop
git pull origin develop
git merge --no-ff feature/123-add-login
git push origin develop
git branch -d feature/123-add-login

# 开始发布
git checkout -b release/v1.0.0
# ... 发布准备和修复
git checkout develop
git merge --no-ff release/v1.0.0
git checkout main
git merge --no-ff release/v1.0.0
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin main --tags

# 紧急修复
git checkout -b hotfix/456-fix-crash main
# ... 修复完成
git checkout develop
git merge --no-ff hotfix/456-fix-crash
git checkout main
git merge --no-ff hotfix/456-fix-crash
git tag -a v1.0.1 -m "Hotfix v1.0.1"
git push origin main --tags
```

### GitHub Flow

适用于持续部署的 Web 应用或小型团队：

```
main ───●────●────●────●────●────●──
          \    \    \    \    \    \
           \    \    \    \    \    ●──●──● (feature/a)
            \    \    \    \    \
             \    \    \    \    ●──●──● (feature/b)
              \    \    \    \
               ●──●──●──●──●──●──●── (PR merged)
```

#### 核心规则

1. 从 `main` 分支创建特性分支
2. 在特性分支上开发并提交
3. 开启 Pull Request
4. 代码审查并合并到 `main`
5. 立即部署到生产环境

#### GitHub Flow 命令

```bash
# 创建特性分支
git checkout main
git pull origin main
git checkout -b feature/add-login

# 开发并推送
git add .
git commit -m "feat: add login form UI"
git push origin feature/add-login

# 创建 PR (通过 GitHub CLI)
gh pr create --title "feat: add login functionality" --body "Closes #123"

# 合并后删除分支
git checkout main
git pull origin main
git branch -d feature/add-login
```

### 分支策略选择

| 场景 | 推荐策略 |
|------|----------|
| 定期版本发布 | Git Flow |
| 持续部署 / Web 应用 | Git Flow |
| 简单项目 / 快速迭代 | GitHub Flow |
| 开源项目 | GitHub Flow + Fork |
| 多版本维护 | Git Flow |

## 自动化检查流程

### pre-commit Hooks

使用 Husky 或 lefthook 配置 Git 钩子：

```bash
# 安装 Husky
npm install husky --save-dev
npx husky install

# 添加 commit-msg 钩子
npx husky add .husky/commit-msg 'npx --no -- commitlint --edit "$1"'

# 添加 pre-commit 钩子
npx husky add .husky/pre-commit 'npx lint-staged'
```

### commitlint 配置

```javascript
// commitlint.config.js
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'feat', 'fix', 'docs', 'style', 'refactor',
        'perf', 'test', 'build', 'ci', 'chore', 'revert'
      ]
    ],
    'type-case': [2, 'always', 'lower-case'],
    'type-empty': [2, 'never'],
    'subject-empty': [2, 'never'],
    'subject-full-stop': [2, 'never', '.'],
    'header-max-length': [2, 'always', 50]
  }
};
```

### lint-staged 配置

```json
// package.json
{
  "lint-staged": {
    "*.{js,ts,jsx,tsx}": ["eslint --fix", "prettier --write"],
    "*.{css,scss,less}": ["stylelint --fix"],
    "*.{json,md,yml}": ["prettier --write"]
  }
}
```

### 完整 pre-commit 配置示例

```yaml
# .husky/pre-commit
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

# 运行 lint-staged
npx lint-staged

# 运行单元测试（可选，根据项目情况）
# npm run test --if-present
```

```yaml
# .husky/commit-msg
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

# 验证 commit message 格式
npx --no -- commitlint --edit "$1"
```

## CHANGELOG 自动生成

### 使用 conventional-changelog

```bash
# 全局安装
npm install -g conventional-changelog-cli

# 生成 CHANGELOG
conventional-changelog -p angular -i CHANGELOG.md -s
```

### 配置 package.json

```json
{
  "scripts": {
    "changelog": "conventional-changelog -p angular -i CHANGELOG.md -s -r 0"
  }
}
```

### 输出格式示例

```
# Changelog

## [1.2.0](https://github.com/user/repo/compare/v1.1.0...v1.2.0) (2024-01-15)


### Features

* **auth:** add OAuth2 login support ([#45](https://github.com/user/repo/issues/45)) ([abc123](https://github.com/user/repo/commit/abc123))


### Bug Fixes

* **api:** resolve null pointer exception ([#32](https://github.com/user/repo/issues/32)) ([def456](https://github.com/user/repo/commit/def456))
```

### 语义化版本自动发布

使用 standard-version 或 release-it：

```bash
# 使用 standard-version
npx standard-version

# 使用 release-it
npx release-it --major
npx release-it --minor
npx release-it --patch
```

release-it 配置文件 `.release-it.json`：

```json
{
  "github": {
    "release": true
  },
  "npm": {
    "publish": true
  },
  "plugins": {
    "@release-it/conventional-changelog": {
      "preset": "angular"
    }
  }
}
```

## 最佳实践

### 提交粒度

- **每次提交完成一个独立功能或修复一个具体问题**
- 避免将多个不相关的更改混入同一提交
- 提交信息应清晰描述「做了什么」和「为什么这样做」

### 提交频率

- 频繁提交优于一次性大规模提交
- 每天至少提交一次工作进度
- 完成任务后立即提交，避免丢失更改

### 代码审查

- 所有合并必须经过 Pull Request 审查
- 审查者负责检查：代码质量、测试覆盖、文档更新
- 使用 squash merge 保持主分支历史整洁

### 分支保护

在 GitHub/GitLab 设置分支保护规则：

```
main 分支保护规则：
☑  Require pull request reviews before merging
☑  Require status checks to pass before merging
☑  Require conversation resolution before merging
☑  Include administrators
☑  Require signed commits (可选)
```

### 常用命令速查

| 操作 | 命令 |
|------|------|
| 查看状态 | `git status` |
| 查看历史 | `git log --oneline --graph` |
| 创建分支 | `git checkout -b <branch>` |
| 切换分支 | `git checkout <branch>` |
| 暂存更改 | `git add -A` |
| 提交更改 | `git commit -m "type(scope): subject"` |
| 拉取更新 | `git pull --rebase origin <branch>` |
| 推送代码 | `git push origin <branch>` |
| 变基合并 | `git rebase main` |
| 压缩合并 | `git merge --squash <branch>` |
| 放弃更改 | `git checkout -- .` |
| 查看差异 | `git diff` |

## 参考资料

- [Conventional Commits 官方规范](https://www.conventionalcommits.org/)
- [A Successful Git Branching Model](https://nvie.com/posts/a-successful-git-branching-model/)
- [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow)
- [Husky Git Hooks](https://typicode.github.io/husky/)
- [commitlint](https://conventional-changelog.github.io/commitlint/)
- [standard-version](https://github.com/conventional-changelog/standard-version)
- [release-it](https://release-it.com/)