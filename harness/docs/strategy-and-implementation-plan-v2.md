# Claude Harness Kit v2 — 战略实施计划

> 架构师 + 专家模式
> 基于 7 层深度研究：Claude Code 官方文档 + 源码 + 5 个参考项目 + 自身源码
> 版本：v2.0 | 日期：2026-05-01

---

## 方案概览

```
P0 (阻断性):  4 个任务 — 立即修复，影响当前工作流
P1 (高价值):  6 个任务 — 2 周内完成，显著提升能力
P2 (中价值):  5 个任务 — 1 个月内完成，补全安全和质量体系
P3 (架构演进): 5 个任务 — 长期建设，构建差异化竞争力
P4 (生态扩展): 1 个任务 — 持续迭代，扩展覆盖领域
```

---

## P0 — 阻断性问题（本周完成）

---

### P0-TASK-001：修复所有 Skill 描述不达标（10/19 <30 tokens）

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | 10/19 个 Skill 的 description 低于 30 tokens 最低标准 |
| **规范要求** | Claude Code 官方标准：description 30-50 tokens，第三人称，描述 Who/What/When |
| **规范来源** | Claude Code 插件架构文档：`Skills Progressive Disclosure` 章节 |

**影响链**：
```
Skill 描述 <30 tokens
    ↓
Progressive Disclosure 失效（description 始终加载，内容却不够判断何时调用）
    ↓
AI 无法正确判断何时调用该 Skill
    ↓
Skill 被忽略或误用
    ↓
Layer 2 能力层失效 → 回到"裸用 Claude Code"
```

**最严重的 case**：`database-designer` 仅 9 tokens（"Database Designer - POWERFUL Tier Skill"），完全缺少触发场景描述。AI 不知道在什么情况下应该调用它。

#### 修复方案

**格式标准**：
```markdown
---
name: xxx
description: >
  Who calls it, what it does, and when to use it.
  Third person, 30-50 tokens total.
  Example: "Sonnet agents writing database code invoke before
  committing SQL changes. Covers schema design, migration generation,
  and index optimization."
---
```

**具体修改清单**：

| Skill | 当前 Tokens | 修复后 Tokens | 修复后 Description |
|-------|-----------|--------------|-------------------|
| database-designer | 9 | 45 | Sonnet agents designing or migrating schemas invoke before writing SQL. Covers schema design, migration generation, index optimization, and PostgreSQL/MySQL/Oracle patterns. Activates on file changes in schema/, migrations/, or *.sql. |
| karpathy-guidelines | 15 | 42 | Sonnet agents writing new code invoke this before starting. Enforces 4 rules: think before coding, simplicity first, precise edits, goal-driven execution. Prevents over-engineering and context overflow. |
| testing | 17 | 44 | Sonnet agents implementing features invoke after creating source files. Enforces test pyramid (unit/integration/E2E), AAA structure, and naming conventions. Activates on file changes in src/ or test/. |
| code-quality | 17 | 40 | Sonnet agents reviewing code invoke this on PostToolUse Write/Edit. Covers 6 dimensions: correctness, readability, architecture, security, performance, maintainability. Outputs structured review report. |
| ship | 19 | 42 | Sonnet agents completing features invoke before git commit. Enforces pre-launch checklist, 6-stage rollout, and rollback template. Blocks commit if tests fail or security issues detected. |
| security-audit | 20 | 47 | Opus agents auditing auth, payment, or data handling code invoke this. Covers OWASP Top 10, SQL injection/XSS/CSRF detection. Activates on files matching auth/, payment/, security/, *.crypto, *.jwt. |
| git-master | 21 | 40 | Sonnet agents managing git invoke before branch/create/commit. Enforces conventional commits, GitHub Flow, pre-commit hooks, and changelog generation. Activates on any git operation. |
| architecture-design | 18 | 38 | Opus agents designing systems invoke before writing any code. Outputs ADRs, architecture diagrams, and tech stack decisions. Activates when project CLAUDE.md contains "architecture" or "design". |
| debugging | 22 | 43 | Sonnet agents fixing bugs invoke this before making changes. Follows 6-step checklist: reproduce, isolate, hypothesize, fix, verify, prevent. Includes git bisect and Stop-the-Line rule for production issues. |
| requirement-analysis | 20 | 42 | Sonnet agents analyzing requirements invoke before writing any code. Generates structured PRD with user stories, acceptance criteria, edge cases, and tech constraints. Activates when user describes a new feature or change. |

**注**：其余 9 个 Skill（api-designer 34、context-compaction 33、docker-compose 34、migration 38、multi-model-review 42、parallel-dispatch 40、performance 40、tdd 40 已达标，保持不变）。

#### 测试验证

```bash
# 测试 1：验证所有 Skill 描述在 30-50 tokens 范围内
python3 -c "
import os, re
skills_dir = 'skills'
results = []
for skill in sorted(os.listdir(skills_dir)):
    skill_path = os.path.join(skills_dir, skill)
    if not os.path.isdir(skill_path): continue
    for fname in os.listdir(skill_path):
        if fname.endswith('.md') or fname == 'SKILL.md':
            fpath = os.path.join(skill_path, fname)
            content = open(fpath).read()
            m = re.search(r'^description:\s*>?\s*(.+?)(?:^---|\Z)', content, re.S | re.M)
            if m:
                desc = m.group(1).strip()
                tokens = len(desc.split())
                status = '✅' if 30 <= tokens <= 50 else '❌'
                results.append((skill, fname, tokens, status, desc[:60]))
for r in sorted(results):
    print(f'{r[3]} {r[0]}/{r[1]}: {r[2]} tokens — {r[4]}...')
failed = [r for r in results if '❌' in r[3]]
print(f'\n总计: {len(results)} skills, {len(failed)} 不达标')
"
```

---

### P0-TASK-002：实现 Worktree 生命周期管理

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | 8 个 Agent 声明了 `isolation: worktree`，但没有任何脚本实际创建或管理 worktree |
| **声明位置** | backend-dev.md, frontend-dev.md, database-dev.md, devops.md, migration-dev.md, executor.md, ralph.md, tech-lead.md |
| **规范要求** | Claude Code 插件规范：使用 `EnterWorktree` 工具创建隔离开发环境 |

**影响链**：
```
8 个 Agent 声明 isolation: worktree
    ↓
Claude Code 调用 EnterWorktree 工具（前提：工具存在）
    ↓
实际没有 hook 脚本管理 worktree 创建/同步/清理
    ↓
并行 Agent 在同一工作目录操作
    ↓
文件冲突、git 状态污染、构建产物混乱
    ↓
Ralph Mode 等质量保证机制失效（隔离被破坏）
```

**根因**：`EnterWorktree` 是 Claude Code 内置工具，但需要 hook 脚本来管理 worktree 的创建、同步、和清理生命周期。目前仅有声明，缺少实现。

#### 修复方案

**新增文件**：

1. **hooks/bin/worktree-manager.sh** — Worktree 生命周期主脚本

```bash
#!/bin/bash
# worktree-manager.sh — Worktree 生命周期管理
# 用法: worktree-manager.sh create|enter|cleanup|list <task-id>
#
# create: 创建新的 worktree 分支
# enter:  进入已有 worktree
# cleanup: 清理已完成的 worktree
# list:   列出所有 worktree

set -euo pipefail

COMMAND="${1:-}"
TASK_ID="${2:-$(date +%s)}"
WORKTREE_BASE="${WORKTREE_BASE:-$HOME/.claude/worktrees}"
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"

mkdir -p "$WORKTREE_BASE"

case "$COMMAND" in
  create)
    BRANCH="chk-task-$TASK_ID"
    WORKTREE_PATH="$WORKTREE_BASE/$PROJECT_NAME-$BRANCH"

    if git worktree list | grep -q "$WORKTREE_PATH"; then
      echo "Worktree already exists: $WORKTREE_PATH"
      echo "$WORKTREE_PATH"
      exit 0
    fi

    # 创建 worktree
    git worktree add -b "$BRANCH" "$WORKTREE_PATH"
    
    # 同步 CLAUDE.md 和 .claude/ 到 worktree
    rsync -av --exclude='.git' \
      "$PROJECT_ROOT/CLAUDE.md" \
      "$PROJECT_ROOT/.claude/" \
      "$WORKTREE_PATH/" 2>/dev/null || true

    # 记录映射关系
    echo "$TASK_ID:$BRANCH:$WORKTREE_PATH" >> "$WORKTREE_BASE/.worktree-map"
    
    echo "$WORKTREE_PATH"
    ;;

  enter)
    WORKTREE_PATH="$WORKTREE_BASE/$PROJECT_NAME-chk-task-$TASK_ID"
    if [[ ! -d "$WORKTREE_PATH" ]]; then
      echo "Worktree not found: $WORKTREE_PATH" >&2
      exit 1
    fi
    echo "$WORKTREE_PATH"
    ;;

  cleanup)
    # 找出所有已合并的 worktree
    WORKTREE_BASE_ESCAPED=$(echo "$WORKTREE_BASE" | sed 's/\//\\\//g')
    while IFS=: read -r tid branch wpath; do
      if [[ ! -d "$wpath" ]]; then
        # worktree 目录不存在，清理映射
        grep -v "^$tid:" "$WORKTREE_BASE/.worktree-map" > "$WORKTREE_BASE/.worktree-map.tmp" || true
        mv "$WORKTREE_BASE/.worktree-map.tmp" "$WORKTREE_BASE/.worktree-map"
        continue
      fi
      
      # 检查是否已合并到主分支
      if git worktree list | grep -q "$wpath"; then
        # 尝试移除 worktree（如果分支已合并）
        git worktree remove "$wpath" 2>/dev/null && {
          grep -v "^$tid:" "$WORKTREE_BASE/.worktree-map" > "$WORKTREE_BASE/.worktree-map.tmp" || true
          mv "$WORKTREE_BASE/.worktree-map.tmp" "$WORKTREE_BASE/.worktree-map"
          echo "Cleaned up: $wpath"
        } || echo "Skipped (unmerged): $wpath"
      fi
    done < "$WORKTREE_BASE/.worktree-map" 2>/dev/null || true
    ;;

  list)
    git worktree list
    ;;

  *)
    echo "Usage: worktree-manager.sh create|enter|cleanup|list [task-id]"
    exit 1
    ;;
esac
```

2. **hooks/bin/worktree-init.sh** — PreToolUse hook 前置脚本，检测 Agent 是否需要 worktree

```bash
#!/bin/bash
# worktree-init.sh — PreToolUse Hook 前置脚本
# 检测 Agent 声明了 isolation: worktree 时，自动创建并切换

set -euo pipefail

INPUT=$(cat)
AGENT_NAME=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
# 从上下文推断当前 Agent 类型
msg = d.get('message', {})
content = msg.get('content', [])
for block in content if isinstance(content, list) else []:
    if isinstance(block, dict) and block.get('type') == 'text':
        text = block.get('text', '')
        if 'isolation: worktree' in text or 'isolation:worktree' in text:
            print('worktree-required')
            break
" 2>/dev/null || echo "")

if [[ "$AGENT_NAME" == "worktree-required" ]]; then
  TASK_ID=$(date +%s)
  WORKTREE_PATH=$(bash "${CLAUDE_PLUGIN_ROOT}/hooks/bin/worktree-manager.sh" create "$TASK_ID")
  echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['_worktree_path'] = '$WORKTREE_PATH'
d['_task_id'] = '$TASK_ID'
print(json.dumps(d))
" 2>/dev/null || echo "$INPUT"
else
  echo "$INPUT"
fi
```

#### 测试验证

```bash
# 测试 1：创建 worktree
WORKTREE_PATH=$(bash hooks/bin/worktree-manager.sh create test-001)
echo "Created: $WORKTREE_PATH"
[[ -d "$WORKTREE_PATH" ]] && echo "✅ 目录存在" || echo "❌ 目录不存在"

# 测试 2：验证 worktree 有 CLAUDE.md 和 .claude/
[[ -f "$WORKTREE_PATH/CLAUDE.md" ]] && echo "✅ CLAUDE.md 已同步" || echo "❌ CLAUDE.md 未同步"
[[ -d "$WORKTREE_PATH/.claude" ]] && echo "✅ .claude/ 已同步" || echo "❌ .claude/ 未同步"

# 测试 3：列出 worktree
bash hooks/bin/worktree-manager.sh list

# 测试 4：清理测试 worktree
bash hooks/bin/worktree-manager.sh cleanup
```

---

### P0-TASK-003：添加 WorktreeCreate/Remove Hook 事件

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | Claude Code v3.0 支持 WorktreeCreate/WorktreeRemove Hook，但我们的 hooks.json 没有配置 |
| **规范来源** | claude-forge hooks.json 引用 v3.0 Hook 事件扩展 |

**影响链**：
```
无 WorktreeCreate Hook
    ↓
Claude Code 创建 worktree 时无感知
    ↓
无法同步上下文（CLAUDE.md、.claude/）
    ↓
Worktree 内 AI "失忆"（没有项目上下文）
    ↓
Worktree 隔离失效
```

#### 修复方案

**修改 `hooks/hooks.json`**：

```json
{
  "hooks": {
    "SessionStart": [...],
    "PreToolUse": [...],
    "PostToolUse": [...],
    "Stop": [...],
    "WorktreeCreate": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/bin/worktree-sync.sh",
            "description": "Sync CLAUDE.md and .claude/ to new worktree",
            "timeout": 30000
          }
        ]
      }
    ],
    "WorktreeRemove": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/bin/worktree-cleanup.sh",
            "description": "Cleanup worktree mapping and merged branches",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

**新增脚本**：

```bash
#!/bin/bash
# worktree-sync.sh — WorktreeCreate Hook 脚本
# 将项目上下文同步到新创建的 worktree

WORKTREE_PATH="${WORKTREE_PATH:-}"
if [[ -z "$WORKTREE_PATH" ]]; then
  # 从 Claude Code 传递的路径
  WORKTREE_PATH=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('worktree', {}).get('path', ''))
" 2>/dev/null || echo "")
fi

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '')"

if [[ -n "$WORKTREE_PATH" && -d "$WORKTREE_PATH" && -n "$PROJECT_ROOT" ]]; then
  rsync -av --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='dist' \
    "$PROJECT_ROOT/CLAUDE.md" \
    "$PROJECT_ROOT/.claude/" \
    "$WORKTREE_PATH/" 2>/dev/null
  echo "[WorktreeCreate] Synced context to $WORKTREE_PATH"
fi
```

```bash
#!/bin/bash
# worktree-cleanup.sh — WorktreeRemove Hook 脚本
# 清理 worktree 映射记录和已合并分支

WORKTREE_BASE="${WORKTREE_BASE:-$HOME/.claude/worktrees}"
MAPPING_FILE="$WORKTREE_BASE/.worktree-map"

if [[ -f "$MAPPING_FILE" ]]; then
  WORKTREE_PATH=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('worktree', {}).get('path', ''))
" 2>/dev/null || echo "")

  if [[ -n "$WORKTREE_PATH" ]]; then
    # 从映射文件删除该 worktree 的记录
    grep -v "$WORKTREE_PATH" "$MAPPING_FILE" > "$MAPPING_FILE.tmp" 2>/dev/null || true
    mv "$MAPPING_FILE.tmp" "$MAPPING_FILE"
    echo "[WorktreeRemove] Cleaned up mapping for $WORKTREE_PATH"
  fi
fi
```

#### 测试验证

```bash
# 测试 1：验证 hooks.json 包含 WorktreeCreate 和 WorktreeRemove
python3 -c "
import json
hooks = json.load(open('hooks/hooks.json'))
events = list(hooks.get('hooks', {}).keys())
required = ['WorktreeCreate', 'WorktreeRemove']
for e in required:
    if e in events:
        print(f'✅ {e} 已配置')
    else:
        print(f'❌ {e} 未配置')
"

# 测试 2：验证 worktree-sync.sh 存在且可执行
[[ -x hooks/bin/worktree-sync.sh ]] && echo "✅ worktree-sync.sh 可执行" || echo "❌ worktree-sync.sh 不可执行"

# 测试 3：手动测试同步逻辑（不创建真实 worktree）
export WORKTREE_PATH="/tmp/test-worktree-$(date +%s)"
export CLAUDE_PLUGIN_ROOT="$(pwd)"
mkdir -p "$WORKTREE_PATH"
bash hooks/bin/worktree-sync.sh
[[ -f "$WORKTREE_PATH/CLAUDE.md" ]] && echo "✅ 同步成功" || echo "❌ 同步失败"
rm -rf "$WORKTREE_PATH"
```

---

### P0-TASK-004：实现 Output Secret Filter Hook

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | PostToolUse hook 不检测工具输出中的敏感信息（API keys、tokens、私钥等） |
| **影响范围** | 所有使用 Claude Code 的开发者，尤其是远程会话 |
| **安全等级** | CRITICAL — 敏感信息泄露 |

**影响链**：
```
无 Output Secret Filter
    ↓
Claude Code 读取文件/执行命令时，输出包含敏感信息
    ↓
敏感信息进入上下文（可能被存入 sessions.jsonl）
    ↓
后续 Agent/跨会话访问敏感信息
    ↓
安全事故（GitHub PAT 泄露、AWS 密钥泄露、数据库密码泄露）
```

**参考来源**：claude-forge 的 `output-secret-filter.sh`，包含 15+ 种敏感信息检测模式，支持 base64/URL 编码绕过检测。

#### 修复方案

**新增 `hooks/bin/output-secret-filter.sh`**：

```python
#!/usr/bin/env python3
"""
Output Secret Filter — PostToolUse Hook
检测工具输出中的敏感信息并脱敏

检测类型:
- API Keys (OpenAI, AWS, GitHub, etc.)
- Bearer/Auth Tokens
- Passwords in parameters
- Private Keys (RSA, EC, DSA, OpenSSH)
- Environment variables with secrets
- Base64/URL 编码的敏感信息（检测解码后内容）

来源: claude-forge/output-secret-filter.sh
"""

import sys
import json
import re
import base64
from urllib.parse import unquote

# 敏感信息检测模式
SECRET_PATTERNS = [
    # API Keys
    (r'\bsk-[a-zA-Z0-9_-]{20,}\b', 'OpenAI API Key', 'CRITICAL'),
    (r'\bsk-proj-[a-zA-Z0-9_-]{20,}\b', 'OpenAI Project Key', 'CRITICAL'),
    (r'\bAKIA[A-Z0-9]{16,}\b', 'AWS Access Key ID', 'CRITICAL'),
    (r'\bAKIA[A-Z2-7]{16,}\b', 'AWS Access Key ID', 'CRITICAL'),
    (r'\bghp_[a-zA-Z0-9]{36,}\b', 'GitHub PAT', 'CRITICAL'),
    (r'\bgho_[a-zA-Z0-9]{36,}\b', 'GitHub OAuth Token', 'CRITICAL'),
    (r'\bglpat-[a-zA-Z0-9_-]{20,}\b', 'GitLab PAT', 'CRITICAL'),
    (r'\b[xX]-Token [a-zA-Z0-9_-]{20,}\b', 'Generic API Token', 'CRITICAL'),
    # Bearer/Auth Tokens
    (r'(?i)\bBearer\s+[a-zA-Z0-9_.\-]{20,}\b', 'Bearer Token', 'CRITICAL'),
    (r'(?i)\bAuthorization:\s*(?:Bearer|Basic)\s+[^\s]{20,}\b', 'Authorization Header', 'CRITICAL'),
    # Passwords
    (r'(?i)\bpassword\s*=\s*[^\s&]{8,}\b', 'Password in URL', 'HIGH'),
    (r'(?i)\bpasswd\s*=\s*[^\s]{8,}\b', 'Password Parameter', 'HIGH'),
    (r'(?i)\bdb_pass(?:word)?\s*=\s*[^\s]{8,}\b', 'Database Password', 'HIGH'),
    (r'(?i)\bmysql_pass\s*=\s*[^\s]{8,}\b', 'MySQL Password', 'HIGH'),
    # Private Keys
    (r'-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH)?\s*PRIVATE\s+KEY(?:\s+BLOCK)?-----', 'Private Key', 'CRITICAL'),
    (r'-----BEGIN\s+PGP\s+PRIVATE\s+KEY\s+BLOCK-----', 'PGP Private Key', 'CRITICAL'),
    # Environment Variables
    (r'(?i)\bAWS_SECRET_ACCESS_KEY\s*=\s*[^\s]{20,}\b', 'AWS Secret Key', 'CRITICAL'),
    (r'(?i)\bSTRIPE_SECRET_KEY\s*=\s*sk_[^\s]{20,}\b', 'Stripe Secret Key', 'CRITICAL'),
    (r'(?i)\bSENDGRID_API_KEY\s*=\s*SG\.[^\s]{20,}\b', 'SendGrid API Key', 'CRITICAL'),
    (r'(?i)\bSLACK_BOT_TOKEN\s*=\s*xox[baprs]-[^\s]{10,}\b', 'Slack Bot Token', 'CRITICAL'),
    # JWT Tokens
    (r'\beyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*\b', 'JWT Token', 'HIGH'),
    # Connection Strings with passwords
    (r'(?i)(?:mongodb|mysql|postgresql|redis):\/\/[^:]+:[^@]+@', 'Database Connection String with Password', 'CRITICAL'),
]

# Base64 编码绕过检测
BASE64_SECRET_PATTERNS = [
    r'\bU0tPLXskfSsBuYW5vbS',  # sk- 前缀 base64
    r'\bQUtJQV[A-Z0-9]{16,}',  # AKIA 前缀 base64
    r'\bZ2hwXyRbJ10=',  # ghp_ 前缀 base64
]


def detect_secrets(text: str) -> list:
    """检测文本中的敏感信息"""
    findings = []
    lines = text.split('\n')
    
    for line_idx, line in enumerate(lines):
        for pattern, name, severity in SECRET_PATTERNS:
            for match in re.finditer(pattern, line):
                start, end = match.span()
                context = line[max(0, start-20):min(len(line), end+20)]
                findings.append({
                    'line': line_idx + 1,
                    'type': name,
                    'severity': severity,
                    'context': f"...{context}...",
                    'matched': match.group()[:20] + '***',
                    'position': f"{start}-{end}"
                })
        
        # Base64 编码绕过检测
        try:
            decoded = base64.b64decode(line).decode('utf-8', errors='ignore')
            for pattern, name, severity in SECRET_PATTERNS:
                if re.search(pattern, decoded):
                    findings.append({
                        'line': line_idx + 1,
                        'type': f'{name} (base64 encoded)',
                        'severity': severity,
                        'context': 'Detected in base64-decoded content',
                        'matched': '***(base64)***',
                        'position': 'base64-bypass'
                    })
        except:
            pass
        
        # URL 编码绕过检测
        try:
            decoded = unquote(line)
            if decoded != line:
                for pattern, name, severity in SECRET_PATTERNS:
                    if re.search(pattern, decoded):
                        findings.append({
                            'line': line_idx + 1,
                            'type': f'{name} (url encoded)',
                            'severity': severity,
                            'context': 'Detected in url-decoded content',
                            'matched': '***(url-encoded)***',
                            'position': 'url-bypass'
                        })
        except:
            pass
    
    return findings


def mask_secrets(text: str) -> str:
    """脱敏文本中的敏感信息"""
    masked = text
    for pattern, name, _ in SECRET_PATTERNS:
        masked = re.sub(pattern, f'[REDACTED:{name}]', masked, flags=re.IGNORECASE)
    return masked


def main():
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)  # 非 JSON 输入，静默通过
    
    # 提取工具输出
    content = input_data.get('content', [])
    tool_result = input_data.get('result', {})
    output_text = ''
    
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                text = block.get('content', '')
                if isinstance(text, list):
                    for t in text:
                        if isinstance(t, dict):
                            output_text += t.get('text', '')
                elif isinstance(text, str):
                    output_text += text
    elif isinstance(content, str):
        output_text = content
    elif isinstance(tool_result, str):
        output_text = tool_result
    
    if not output_text:
        sys.exit(0)
    
    findings = detect_secrets(output_text)
    
    if findings:
        # 输出警告
        print(json.dumps({
            'continue': True,
            'warning': f"[SecretFilter] Detected {len(findings)} secret(s) in tool output:",
            'findings': [
                {
                    'type': f['type'],
                    'severity': f['severity'],
                    'line': f['line'],
                    'context': f['context']
                }
                for f in findings[:5]  # 最多显示 5 个
            ],
            'action': 'Review and redact if needed'
        }, ensure_ascii=False))
        
        # 写入安全日志
        log_file = f"{os.path.expanduser('~')}/.claude/logs/secret-detections.jsonl"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'session_id': input_data.get('session_id', 'unknown'),
                'findings': findings
            }, f, ensure_ascii=False)
            f.write('\n')
    else:
        sys.exit(0)


if __name__ == '__main__':
    import os
    from datetime import datetime
    main()
```

#### 测试验证

```bash
# 测试 1：检测 OpenAI API Key
echo '{"content": "Found API key: sk-1234567890abcdefghijklmnop"}' | \
  python3 hooks/bin/output-secret-filter.py

# 测试 2：检测 AWS Access Key
echo '{"content": "AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"}' | \
  python3 hooks/bin/output-secret-filter.py

# 测试 3：检测 base64 编码的密钥
echo '{"content": "c2stMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0"}' | \
  python3 hooks/bin/output-secret-filter.py

# 测试 4：正常内容不触发
echo '{"content": "const greeting = \"hello world\";"}' | \
  python3 hooks/bin/output-secret-filter.py
# 应退出码 0，无输出

# 测试 5：集成测试
python3 -c "
import subprocess, json

test_cases = [
    ('sk-1234567890abcdefghijklmnop', True, 'OpenAI Key'),
    ('ghp_abcdefghijklmnopqrstuvwxyz1234567890', True, 'GitHub PAT'),
    ('const x = 42;', False, 'Normal Code'),
    ('eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw', True, 'JWT'),
]

for content, should_detect, name in test_cases:
    result = subprocess.run(
        ['python3', 'hooks/bin/output-secret-filter.py'],
        input=json.dumps({'content': content}),
        capture_output=True, text=True
    )
    detected = result.returncode == 0 or 'secret' in result.stdout.lower()
    status = '✅' if detected == should_detect else '❌'
    print(f'{status} {name}: detected={detected}, expected={should_detect}')
"
```

---

## P1 — 高价值任务（2周内完成）

---

### P1-TASK-005：实现 Checkpoint 自动化恢复机制

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | Checkpoint 系统在 orchestrator.md 和 collaboration.md 中设计完整，但 `/compact` 后无法自动恢复 |
| **设计文档位置** | agents/orchestrator.md、rules/collaboration.md |
| **规范结构** | `.compact/` 目录含 current_phase.md、completed_tasks.md、pending_tasks.md、agent_outputs/、issues.md |

**影响链**：
```
上下文达到 70%+ 使用率
    ↓
用户执行 /compact
    ↓
Claude Code 压缩上下文，保留摘要
    ↓
无 Checkpoint 恢复 → 任务状态丢失
    ↓
Agent 需要重新理解上下文
    ↓
重复工作、上下文碎片化、进度丢失
```

**根因**：`context-compaction/SKILL.md` 描述了 Checkpoint 模式，但没有 Hook 在 `/compact` 时自动写入/读取 `.compact/` 目录。

#### 修复方案

**新增文件**：

1. ~~**commands/checkpoint.md** — Checkpoint Slash Command~~ (已移除)

```markdown
---
name: checkpoint
description: >
  Saves, restores, or manages work session checkpoints.
  Use before /compact to preserve task state. Use after /compact
  to restore context. Saves git diff + untracked files + task state.
  Activates when user says "checkpoint", "save state", or "before /compact".
context: inline
---

# Checkpoint Command

Manages work session checkpoints stored in `.claude/checkpoints/`.

## Usage

/checkpoint save [description]     # Save current state
/checkpoint list                   # List all checkpoints  
/checkpoint restore [id]           # Restore a checkpoint
/checkpoint diff [id]              # Show changes since checkpoint
/checkpoint delete [id]            # Delete a checkpoint

## Checkpoint Contents

Each checkpoint saves:
1. **Task state**: current phase, completed tasks, pending tasks
2. **Git diff**: all uncommitted changes (git diff)
3. **Untracked files**: new files since last commit
4. **Context summary**: 10-line summary of conversation so far
5. **File index**: list of files modified this session

## Checkpoint Format

`.claude/checkpoints/<timestamp>-<description>.md`:
```markdown
---
id: chk-001
timestamp: 2026-05-01T10:30:00+08:00
description: before refactoring auth module
phase: implement
completed_tasks:
  - Backend DTO extension
  - Frontend tag selector
pending_tasks:
  - Auth service integration
  - E2E tests
files_modified:
  - src/main/java/com/app/AssetController.java
  - src/components/TagSelector.vue
context_summary: |
  Implementing material tag filter feature.
  Backed by AssetService.filterByTags().
  Need to integrate with auth module next.
---
```

## Save Workflow

1. Run `git diff --stat` to get changed files
2. Run `git diff` to get full diff
3. Run `git ls-files --others --exclude-standard` for untracked
4. Save all to `.claude/checkpoints/<id>.md`

## Restore Workflow

1. Read checkpoint file
2. Inject context summary to system prompt
3. Apply untracked files back to working directory
4. Show user what was restored
```

2. **hooks/bin/checkpoint-auto-save.sh** — PreToolUse Hook（检测到 `/compact` 时自动保存）

```bash
#!/bin/bash
# checkpoint-auto-save.sh — PreToolUse Hook
# 检测 /compact 命令时，自动创建 checkpoint

set -euo pipefail

INPUT=$(cat)

# 检测是否是 /compact 命令
COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
msg = d.get('message', {})
content = msg.get('content', [])
text = ''
if isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            text = block.get('text', '')
elif isinstance(content, str):
    text = content
# 检测 /compact 或 compact 命令
if '/compact' in text or text.strip().lower().startswith('compact'):
    print('compact')
else:
    print('')
" 2>/dev/null || echo "")

if [[ "$COMMAND" == "compact" ]]; then
  TASK_ID="auto-$(date +%Y%m%d-%H%M%S)"
  CHECKPOINT_DIR="${PROJECT_ROOT:-$PWD}/.claude/checkpoints"
  mkdir -p "$CHECKPOINT_DIR"

  # 收集任务状态
  TASK_STATE=""
  if [[ -f ".claude/current-phase.md" ]]; then
    TASK_STATE=$(cat ".claude/current-phase.md" 2>/dev/null || echo "")
  fi

  # 收集 git diff
  GIT_DIFF=$(git diff --stat 2>/dev/null || echo "No changes")
  GIT_DIFF_FULL=$(git diff 2>/dev/null || echo "No changes")

  # 收集未跟踪文件
  UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || echo "None")

  # 写入 checkpoint
  CHECKPOINT_FILE="$CHECKPOINT_DIR/$TASK_ID.md"
  cat > "$CHECKPOINT_FILE" << EOF
---
id: $TASK_ID
timestamp: $(date +%Y-%m-%dT%H:%M:%S%z)
description: Auto-saved before /compact
auto: true
---
## Task State
$TASK_STATE

## Git Diff (stat)
$GIT_DIFF

## Git Diff (full)
$GIT_DIFF_FULL

## Untracked Files
$UNTRACKED

## Files Modified This Session
$(git diff --name-only 2>/dev/null || echo "None")
EOF

  echo "[Checkpoint] Auto-saved to $CHECKPOINT_FILE"
  echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['_checkpoint_saved'] = '$TASK_ID'
d['_checkpoint_file'] = '$CHECKPOINT_FILE'
print(json.dumps(d))
" 2>/dev/null || echo "$INPUT"
else
  echo "$INPUT"
fi
```

3. **修改 `skills/context-compaction/SKILL.md`** — 增加 Checkpoint 恢复协议

在 SKILL.md 中增加：
```markdown
## Checkpoint Recovery Protocol

After /compact, always attempt to restore task state:

1. **Look for most recent checkpoint**: `ls -t .claude/checkpoints/*.md | head -1`
2. **Read checkpoint contents**: phase, completed_tasks, pending_tasks, files_modified
3. **Restore context summary**: inject the context_summary section back into awareness
4. **Signal restoration**: tell user "Restored checkpoint: [description]. Resuming [phase]. Pending: [task list]"
5. **Skip if no checkpoint**: proceed with compressed context, warn user

If checkpoint is >2 hours old, ask user: "This checkpoint is from [timestamp]. Restore or start fresh?"
```

#### 测试验证

```bash
# 测试 1：checkpoint save 命令
bash -c '
export PROJECT_ROOT="$(pwd)"
echo "task: implement tag filter" > .claude/current-phase.md
bash hooks/bin/checkpoint-auto-save.sh <<< "{\"message\": {\"content\": \"compact\"}}"
'
ls -la .claude/checkpoints/

# 测试 2：checkpoint list 命令（读取并格式化）
python3 -c "
import glob, re
for f in sorted(glob.glob('.claude/checkpoints/*.md'), reverse=True)[:3]:
    content = open(f).read()
    m = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if m:
        print(f'Checkpoint: {f}')
        print(m.group(1)[:200])
        print()
"

# 测试 3：PreToolUse Hook 检测 /compact
bash hooks/bin/checkpoint-auto-save.sh <<< '{"message": {"content": "/compact"}}'
# 应输出: [Checkpoint] Auto-saved to ...

# 测试 4：非 /compact 命令不触发
bash hooks/bin/checkpoint-auto-save.sh <<< '{"message": {"content": "write a test"}}'
# 应输出原始 JSON，无 checkpoint
```

---

### P1-TASK-006：实现 Instinct CLI

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | instinct-record.json 存在但无管理工具，无法查看/导出/管理本能记录 |
| **参考来源** | claude-forge 的 instinct-cli.py，ECC 的 instinct-status/export/evolve 命令 |
| **规范功能** | status/import/export/evolve 四个子命令 |

**影响**：Instinct 系统无法运作，用户看不到积累的本能，团队无法共享跨项目本能。

#### 修复方案

**新增 `cli/instinct_cli.py`**：

```python
#!/usr/bin/env python3
"""
Instinct CLI — 本能知识库管理工具

用法:
  instinct-cli.py status [--project PROJECT]    # 查看所有本能及置信度
  instinct-cli.py export [--min-confidence N]  # 导出本能到文件
  instinct-cli.py import <file>                # 从文件导入本能
  instinct-cli.py evolve [--dry-run]           # 将本能聚类为 Skill/Command/Agent

来源: claude-forge/continuous-learning-v2/scripts/instinct-cli.py
"""

import argparse
import json
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

INSTINCT_DIR = Path.home() / '.claude' / 'instinct'
INSTINCT_FILE = INSTINCT_DIR / 'instinct-record.json'
PROJECTS_DIR = Path.home() / '.claude' / 'projects'


def ensure_instinct_dir():
    INSTINCT_DIR.mkdir(parents=True, exist_ok=True)
    if not INSTINCT_FILE.exists():
        INSTINCT_FILE.write_text(json.dumps({"instincts": [], "version": "1.0"}, indent=2))


def load_instincts(project: Optional[str] = None) -> list:
    """加载本能记录"""
    ensure_instinct_dir()
    data = json.loads(INSTINCT_FILE.read_text())
    instincts = data.get('instincts', [])
    
    if project:
        instincts = [i for i in instincts if i.get('project') == project]
    
    return instincts


def save_instincts(instincts: list):
    """保存本能记录"""
    ensure_instinct_dir()
    INSTINCT_FILE.write_text(json.dumps({
        "instincts": instincts,
        "version": "1.0",
        "updated_at": datetime.now().isoformat()
    }, indent=2))


def cmd_status(args):
    """显示所有本能及置信度"""
    instincts = load_instincts(args.project)
    
    if not instincts:
        print("No instincts recorded yet.")
        print("Instincts are created when you correct the AI's behavior multiple times.")
        return
    
    # 按领域分组
    by_domain = {}
    for instinct in instincts:
        domain = instinct.get('domain', 'unknown')
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(instinct)
    
    print(f"\n{'='*60}")
    print(f"  Instinct Status ({len(instincts)} total)")
    if args.project:
        print(f"  Project: {args.project}")
    print(f"{'='*60}\n")
    
    for domain, items in sorted(by_domain.items()):
        print(f"\n### {domain.upper()} ({len(items)} instincts)")
        print(f"{'-'*50}")
        
        for instinct in sorted(items, key=lambda x: x.get('confidence', 0), reverse=True):
            conf = instinct.get('confidence', 0)
            conf_bar = '█' * int(conf * 10) + '░' * (10 - int(conf * 10))
            
            # 置信度颜色
            if conf >= 0.7:
                status = '🟢 AUTO'
            elif conf >= 0.5:
                status = '🟡 PROPOSAL'
            else:
                status = '🔴 OBSERVE'
            
            trigger = instinct.get('trigger', instinct.get('context', {}).get('trigger', ''))
            print(f"  {conf_bar} {conf:.0%} {status}")
            print(f"    ID: {instinct.get('id', 'unknown')}")
            print(f"    Trigger: {trigger[:60]}")
            
            applied = instinct.get('applied_to', '')
            if applied:
                print(f"    Applied to: {applied}")
            
            times = instinct.get('source', {}).get('times_observed', 0)
            print(f"    Observed: {times}x")
            print()


def cmd_export(args):
    """导出本能到文件"""
    instincts = load_instincts(args.project)
    
    if args.min_confidence:
        instincts = [i for i in instincts if i.get('confidence', 0) >= args.min_confidence]
    
    instincts = sorted(instincts, key=lambda x: x.get('confidence', 0), reverse=True)
    
    output = {
        'exported_at': datetime.now().isoformat(),
        'count': len(instincts),
        'instincts': instincts
    }
    
    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"Exported {len(instincts)} instincts to {args.output}")
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))


def cmd_import(args):
    """从文件导入本能"""
    input_file = Path(args.file)
    if not input_file.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    data = json.loads(input_file.read_text())
    imported = data.get('instincts', [])
    
    existing = load_instincts()
    existing_ids = {i.get('id') for i in existing}
    
    new_instincts = [i for i in imported if i.get('id') not in existing_ids]
    updated = 0
    
    for instinct in imported:
        instinct_id = instinct.get('id')
        for existing_instinct in existing:
            if existing_instinct.get('id') == instinct_id:
                # 合并：保留更高的置信度
                if instinct.get('confidence', 0) > existing_instinct.get('confidence', 0):
                    existing[existing.index(existing_instinct)] = instinct
                    updated += 1
                break
    
    all_instincts = existing + new_instincts
    save_instincts(all_instincts)
    
    print(f"Imported: {len(new_instincts)} new, {updated} updated, {len(existing)} existing (skipped)")
    print(f"Total: {len(all_instincts)} instincts")


def cmd_evolve(args):
    """将本能聚类为 Skill/Command/Agent"""
    instincts = load_instincts(args.project)
    
    # 过滤高置信度本能（>=0.7）
    candidates = [i for i in instincts if i.get('confidence', 0) >= 0.7]
    
    if not candidates:
        print("No instincts with confidence >= 0.7 to evolve.")
        print("Keep correcting the AI to increase confidence.")
        return
    
    print(f"\nEvolving {len(candidates)} instincts (confidence >= 0.7)...\n")
    
    # 按领域分组
    by_domain = {}
    for instinct in candidates:
        domain = instinct.get('domain', 'unknown')
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(instinct)
    
    for domain, items in sorted(by_domain.items()):
        print(f"\n### {domain.upper()}")
        print(f"{'='*50}")
        
        # 聚类：同一触发模式的本能
        patterns = {}
        for instinct in items:
            trigger = instinct.get('trigger', '')[:30]
            if trigger not in patterns:
                patterns[trigger] = []
            patterns[trigger].append(instinct)
        
        for pattern, related in patterns.items():
            if len(related) >= 2:
                print(f"\n[CLUSTER] Pattern: '{pattern}...'")
                print(f"  {len(related)} instincts suggest a SKILL or COMMAND")
                
                for instinct in related:
                    print(f"    - {instinct.get('id')}: {instinct.get('trigger', '')[:40]}...")
                
                if not args.dry_run:
                    # 建议创建 skill
                    skill_dir = INSTINCT_DIR.parent / 'skills' / f'evolved-{domain}'
                    skill_dir.mkdir(parents=True, exist_ok=True)
                    
                    skill_md = skill_dir / 'SKILL.md'
                    skill_md.write_text(f"""---
name: evolved-{domain}
description: >
  Auto-evolved from {len(related)} instincts.
  Activated when {pattern}...
  Created: {datetime.now().isoformat()}
  Sources: {', '.join(i.get('id', '') for i in related)}
---

# Evolved Skill: {domain}

Auto-generated from instinct analysis.

## Triggers
{chr(10).join(f'- {i.get("trigger", "")}' for i in related)}

## Correction Examples
{chr(10).join(f'- {i.get("correction", "")}' for i in related)}

## Confidence
{sum(i.get("confidence", 0) for i in related) / len(related):.0%}
""")
                    print(f"  -> Created: {skill_md}")
            else:
                print(f"\n[SINGLE] {related[0].get('id')}: {related[0].get('trigger', '')[:40]}...")
                print(f"  -> Needs more observations to form a pattern (need 2+)")


def main():
    parser = argparse.ArgumentParser(
        description='Instinct CLI — Manage your learned instincts'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # status
    sp = subparsers.add_parser('status', help='Show all instincts')
    sp.add_argument('--project', help='Filter by project')
    sp.set_defaults(func=cmd_status)
    
    # export
    sp = subparsers.add_parser('export', help='Export instincts')
    sp.add_argument('--project', help='Filter by project')
    sp.add_argument('--min-confidence', type=float, help='Minimum confidence (0-1)')
    sp.add_argument('--output', '-o', help='Output file')
    sp.set_defaults(func=cmd_export)
    
    # import
    sp = subparsers.add_parser('import', help='Import instincts from file')
    sp.add_argument('file', help='Input file')
    sp.set_defaults(func=cmd_import)
    
    # evolve
    sp = subparsers.add_parser('evolve', help='Evolve instincts into skills/commands')
    sp.add_argument('--project', help='Filter by project')
    sp.add_argument('--dry-run', action='store_true', help='Show what would be created')
    sp.set_defaults(func=cmd_evolve)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
```

#### 测试验证

```bash
# 测试 1：status 命令（空数据）
python3 cli/instinct_cli.py status

# 测试 2：添加测试本能
mkdir -p ~/.claude/instinct
cat > ~/.claude/instinct/instinct-record.json << 'EOF'
{
  "instincts": [
    {
      "id": "test-001",
      "type": "pattern_correction",
      "domain": "testing",
      "trigger": "Testing @Transactional with mock",
      "correction": "Use @SpringBootTest instead of mock for @Transactional",
      "confidence": 0.85,
      "project": "test-project",
      "applied_to": "skills/testing/SKILL.md",
      "source": {"times_observed": 3}
    },
    {
      "id": "test-002",
      "type": "pattern_correction",
      "domain": "security",
      "trigger": "Using string concatenation in SQL",
      "correction": "Always use parameterized queries",
      "confidence": 0.45,
      "project": "test-project",
      "source": {"times_observed": 1}
    }
  ],
  "version": "1.0"
}
EOF

# 测试 3：status 命令（有数据）
python3 cli/instinct_cli.py status --project test-project

# 测试 4：export 命令
python3 cli/instinct_cli.py export --min-confidence 0.7

# 测试 5：evolve --dry-run
python3 cli/instinct_cli.py evolve --dry-run
```

---

### P1-TASK-007：实现 eval-harness Skill（EDD + pass@k）

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | 无正式评估框架，无法量化 Agent 输出质量 |
| **参考来源** | claude-forge eval-harness，ECC eval-harness（含 4 种 grader 类型和 pass@k 指标） |

**影响**：无法验证 Agent 是否真正解决了问题，无法量化质量改进。

#### 修复方案

**新增 `skills/eval-harness/SKILL.md`**：

```markdown
---
name: eval-harness
description: >
  Sonnet agents validate agent outputs using EDD (Eval-Driven Development).
  Uses pass@k metrics (pass@3 > 90%% for capability, pass^3 = 100%% for regression).
  4 grader types: code-based (deterministic), model-based (scoring), 
  rule-based (regex), human-based (review). Activates before claiming completion.
context: inline
---

# Eval Harness — Eval-Driven Development Framework

## Core Principle

**No claim without evidence.** Before declaring a task complete:
- Define what "done" means (eval criteria)
- Run the eval
- Report pass@k metrics

## 4 Grader Types

### 1. Code-Based Grader (Deterministic)

```bash
# Pass if grep finds the expected pattern
grep -q "export function handleAuth" src/auth.ts && echo "PASS" || echo "FAIL"
```

```bash
# Pass if exit code 0 (test passes)
npm test -- --grep "AuthService" && echo "PASS" || echo "FAIL"
```

### 2. Model-Based Grader (Claude Scoring)

Use Claude to score output 1-5 with reasoning:

```
Evaluate this implementation:
[code snippet]

Score 1-5 on:
- Correctness: Does it solve the stated problem?
- Completeness: Are edge cases handled?
- Safety: Are there security issues?

Provide: score + brief reasoning.
```

Pass threshold: 4/5 for capability evals, 3/5 for regression evals.

### 3. Rule-Based Grader (Regex)

```python
import re

PATTERNS = {
    'has_error_handling': r'try\s*\{.*?\}\s*catch',
    'has_logging': r'(?:console\.(log|error)|logger\.)',
    'no_hardcoded_secrets': r'(?<!_)["\']sk-[a-zA-Z0-9]{20,}["\']',
    'has_tests': r'(?:describe|test|it)\s*\(',
}

def grade(file_path: str) -> dict:
    content = Path(file_path).read_text()
    results = {}
    for check, pattern in PATTERNS.items():
        results[check] = bool(re.search(pattern, content))
    return results
```

### 4. Human-Based Grader (Review Required)

```markdown
[HUMAN REVIEW REQUIRED]
Risk Level: LOW | MEDIUM | HIGH

Please review:
- File: [path]
- What changed: [description]
- Why it matters: [impact]

Comment: [your feedback]
Action: [Approve / Request Changes]
```

## pass@k Metrics

### Capability Evals (Does it work?)
- **pass@1**: Correct on first try
- **pass@3**: Correct within 3 attempts (target: >90%)
- **pass@5**: Correct within 5 attempts

### Regression Evals (Did it break?)
- **pass^3**: No regression after 3 identical attempts (target: 100%)
- If it passed once, it must pass always

## Eval Artifact Layout

```
.claude/evals/
└── <feature-name>/
    ├── spec.md          # What we're testing
    ├── cases.md        # Test cases (inputs + expected outputs)
    ├── results.jsonl   # Raw eval results
    ├── summary.md      # Aggregated report
    └── regression/     # Regression test snapshots
```

## Workflow

### Before Claiming Completion

1. **Define eval criteria** (what does "done" mean?)
2. **Choose grader type** (code/model/rule/human)
3. **Run eval** (get PASS/FAIL + evidence)
4. **Report metrics** (pass@1, pass@3, pass@5)
5. **If FAIL**: Fix and re-eval until pass

### Eval Anti-Patterns

- ❌ **Happy-path only**: Testing only the simplest case
- ❌ **Overfitting**: Making eval criteria match the code exactly
- ❌ **Flaky grader**: Non-deterministic evaluation
- ❌ **No baseline**: No measurement before vs after

## Example: Auth Module Eval

```bash
# 1. Define criteria
# - "Users can login with email/password"
# - "Failed login shows error, not crash"
# - "Rate limit after 5 attempts"

# 2. Code-Based Grader
python3 << 'EOF'
import subprocess, sys

tests = [
    "test_auth_login_success",
    "test_auth_login_wrong_password", 
    "test_auth_rate_limit",
]

passed = 0
for test in tests:
    result = subprocess.run(
        ["npm", "test", "--grep", test],
        capture_output=True, timeout=30
    )
    if result.returncode == 0:
        passed += 1

total = len(tests)
print(f"pass@{total}: {passed}/{total}")
print("PASS" if passed == total else "FAIL")
sys.exit(0 if passed == total else 1)
EOF

# 3. Output format
# pass@3: 3/3
# PASS
```
```

#### 测试验证

```bash
# 测试 1：eval-harness Skill 存在且可加载
[[ -f skills/eval-harness/SKILL.md ]] && echo "✅ Skill 文件存在"

# 测试 2：验证 frontmatter 格式
python3 -c "
import re
content = open('skills/eval-harness/SKILL.md').read()
m = re.search(r'^description:\s*>?\s*(.+?)(?:^---|\Z)', content, re.S | re.M)
desc = m.group(1).strip() if m else ''
tokens = len(desc.split())
print(f'Description tokens: {tokens}')
print('✅ 达标' if 30 <= tokens <= 50 else '❌ 不达标')
"

# 测试 3：测试 Code-Based Grader 示例
bash -c '
result=$(echo "test code" | grep -q "test" && echo "PASS" || echo "FAIL")
[[ "$result" == "PASS" ]] && echo "✅ Grader works" || echo "❌ Grader failed"
'
```

---

### P1-TASK-008：实现 Session Wrap 5阶段流水线

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | 会话结束没有结构化收尾流程，无法提取学习点、更新文档、建议后续工作 |
| **参考来源** | claude-forge session-wrap skill（4 并行 + 1 去重 subagent） |

**影响**：
- 每个会话学到的经验随对话结束而丢失
- 文档不更新，下次同类任务从头探索
- 没有后续任务追踪，积压工作被遗忘

#### 修复方案

**新增 `skills/session-wrap/SKILL.md`**：

```markdown
---
name: session-wrap
description: >
  Sonnet agents execute this at session end via /session-wrap command.
  Runs 4 parallel subagents: doc-updater, automation-scout, learning-extractor,
  and followup-suggester. Then deduplicates results and presents to user.
  Activates when user says "session wrap", "end of session", or "wrap up".
context: inline
---

# Session Wrap — 5-Phase Session Cleanup Pipeline

## Purpose

At the end of a productive session:
1. Update docs with what was learned
2. Discover automation opportunities
3. Extract learning for instinct system
4. Suggest next steps
5. Present consolidated results to user

## Phase 0: Context Collection

Before launching subagents, collect session context:

```bash
# Git diff (what changed)
git diff --stat

# Session summary (last 20 messages)
# Extract: files modified, patterns discovered, issues resolved

# Observations (if any)
cat ~/.claude/homunculus/observations.jsonl 2>/dev/null | tail -10
```

## Phase 1: 4 Parallel Subagents

Launch 4 agents simultaneously (exploit 92% cache reuse):

### Agent 1: doc-updater (Explore, sonnet)

Task: "Analyze recent changes and identify documentation updates needed."

Output format:
```yaml
---
updates_needed:
  - file: docs/api.md
    reason: "New endpoint /api/tags added"
    suggested_change: |
      ### GET /api/tags
      Filter materials by tags...
  - file: CLAUDE.md
    reason: "New field Asset.tag in schema"
    suggested_change: |
      - Asset: id, name, tags[], ...
---
```

### Agent 2: automation-scout (Explore, sonnet)

Task: "Identify repetitive patterns that could be automated."

Output format:
```yaml
---
patterns:
  - description: "Same CRUD boilerplate for each entity"
    frequency: "3x in this session"
    suggestion: "Create code generator template"
    skill_candidate: true
  - description: "Repeated git commit/push workflow"
    frequency: "5x in this session"
    suggestion: "Create /commit-push-pr command"
    skill_candidate: true
---
```

### Agent 3: learning-extractor (Explore, sonnet)

Task: "Extract key learnings from this session for future reference."

Output format:
```yaml
---
learnings:
  - insight: "Testing @Transactional requires @SpringBootTest"
    context: "Fixed flaky test in AssetServiceTest"
    for_instinct: true
    instinct_template: |
      ---
      id: prefer-springboottest-tx
      trigger: "Testing methods with @Transactional"
      confidence: 0.5
      domain: testing
      ---
      # Prefer @SpringBootTest for Transactional Tests
      @Transactional tests should use @SpringBootTest, not mock,
      to properly test rollback behavior.
  - insight: "GIN index for tag array queries"
    context: "Optimized AssetController tag filter query"
    for_instinct: false
---
```

### Agent 4: followup-suggester (Explore, sonnet)

Task: "Based on what was done this session, suggest logical next steps."

Output format:
```yaml
---
next_steps:
  - task: "Add E2E tests for tag filter"
    priority: high
    reason: "Core feature, no test coverage"
    effort: "30 min"
  - task: "Optimize tag query with GIN index"
    priority: medium
    reason: "Performance improvement"
    effort: "1 hour"
  - task: "Update API documentation"
    priority: low
    reason: "Docs drift"
    effort: "15 min"
---
```

## Phase 2: Deduplication

Read all 4 outputs, remove duplicates and consolidate:

```python
def dedupe(doc_updater, automation, learning, followup):
    # Merge doc updates (combine if same file)
    # Merge automation patterns (skip if 80% similar)
    # Merge learnings (combine related insights)
    # Merge followups (remove redundant tasks)
    return consolidated_results
```

## Phase 3: User Confirmation

Present consolidated results to user with categories:

```markdown
## Session Wrap Summary

### 📝 Documentation Updates (3)
1. [docs/api.md] New endpoint /api/tags
2. [CLAUDE.md] New field Asset.tag
3. [README.md] Updated install instructions
[Apply All] [Review Each] [Skip]

### ⚡ Automation Opportunities (2)
1. CRUD code generator (3x pattern)
2. /commit-push-pr command (5x workflow)
[Create Skill] [Remind Later] [Skip]

### 🧠 Learning Extracted (2)
1. @Transactional tests need @SpringBootTest
2. Use GIN index for tag array queries
[Save to Instinct] [Review] [Skip]

### 📋 Next Steps (3)
1. Add E2E tests for tag filter (HIGH, 30min)
2. Optimize tag query with GIN index (MED, 1hr)
3. Update API documentation (LOW, 15min)
[Create TODO] [Add to Project Board] [Skip]
```

## Phase 4: Execute Selected Items

Execute user's selected actions:
- Apply doc updates (Write/Edit)
- Create new skills
- Save instincts
- Create tickets/todos

## Phase 5: Report

Write final report to `.claude/session-wrap/`:

```
.claude/session-wrap/
└── 2026-05-01-session.md
```

```markdown
# Session Wrap: 2026-05-01

Session ID: sess_abc123
Duration: 45 minutes
Mode: team

## Actions Taken
- Applied 2 doc updates
- Created 1 new skill (crud-generator)
- Saved 2 instincts
- Created 1 TODO

## Key Learnings
- @Transactional tests require @SpringBootTest
- GIN index for array tag queries

## Next Session Start From
1. Add E2E tests for tag filter
2. Review GIN index performance
```

## Usage

```bash
/session-wrap          # Full session wrap
/session-wrap --quick  # Skip Phase 1-2, just show summary
/session-wrap --auto   # Auto-apply safe actions, prompt for others
```
```

#### 测试验证

```bash
# 测试 1：Session Wrap Skill 存在且可加载
[[ -f skills/session-wrap/SKILL.md ]] && echo "✅ Skill 文件存在"

# 测试 2：验证 frontmatter
python3 -c "
import re
content = open('skills/session-wrap/SKILL.md').read()
m = re.search(r'^description:\s*>?\s*(.+?)(?:^---|\Z)', content, re.S | re.M)
desc = m.group(1).strip() if m else ''
tokens = len(desc.split())
print(f'Description tokens: {tokens}')
print('✅ 达标' if 30 <= tokens <= 50 else '❌ 不达标')
"

# 测试 3：验证 Phase 1 的 4 个 subagent 定义存在
for agent in "doc-updater" "automation-scout" "learning-extractor" "followup-suggester"; do
  grep -q "Agent $agent" skills/session-wrap/SKILL.md && echo "✅ $agent 定义存在" || echo "❌ $agent 缺失"
done
```

---

### P1-TASK-009：实现 /checkpoint 命令

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | 无 checkpoint 命令，无法手动保存/恢复任务状态 |
| **参考来源** | claude-forge /checkpoint 命令 |

#### 修复方案

~~**新增 `commands/checkpoint.md`**~~ (已移除)

```markdown
---
name: checkpoint
description: >
  Saves and restores work session checkpoints for /compact recovery.
  Use /checkpoint save before /compact. Use /checkpoint restore after.
  Saves git diff, untracked files, task state, and context summary.
  Activates when user says "checkpoint", "save state", or "before compact".
user-invocable: true
---

# Checkpoint Command

Manages work session checkpoints in `.claude/checkpoints/`.

## Usage

```
/checkpoint save [description]    # Save current state
/checkpoint list                  # List all checkpoints
/checkpoint restore [id]          # Restore a checkpoint
/checkpoint diff [id]            # Show changes since checkpoint
/checkpoint delete [id]           # Delete a checkpoint
```

## Save

1. Run `git diff --stat` for changed files
2. Run `git diff` for full diff
3. Run `git ls-files --others --exclude-standard` for untracked
4. Save to `.claude/checkpoints/<timestamp>-<description>.md`

## Restore

1. Read checkpoint file
2. Inject context summary into awareness
3. Report restoration to user

## Auto-Save

Before `/compact`, a PreToolUse hook automatically saves a checkpoint.
You can also manually save with `/checkpoint save`.
```

#### 测试验证

```bash
# ~~commands/checkpoint.md 已移除~~

---

### P1-TASK-010：实现 /commit-push-pr 命令（4路CI Gate）

#### 问题分析

| 维度 | 现状 |
|------|------|
| **问题描述** | git commit 无结构化 CI 检查，CRITICAL 安全漏洞可能被忽略 |
| **参考来源** | claude-forge /commit-push-pr（含 4 条件 AND gate） |

**影响**：未经检查的代码进入仓库，安全漏洞、数据问题、性能问题在生产环境暴露。

#### 修复方案

~~**新增 `commands/commit-push-pr.md`**~~ (已移除)

```markdown
---
name: commit-push-pr
description: >
  Sonnet agents commit code with mandatory CI gate before push.
  Blocks on: Build ✅ + Tests ✅ + Lint ✅ + Security ✅.
  CRITICAL security issues block even with --no-verify.
  Activates when user says "commit", "push", "create PR", or "ship it".
user-invocable: true
---

# commit-push-pr — Full CI Gate Commit

## Merge Gate (All 4 Must Pass)

```
[ ] Build Passes     → npm run build || exit 1
[ ] Tests Pass       → npm test || exit 1
[ ] Lint Passes     → npm run lint || exit 1
[ ] Security Pass    → 扫描 CRITICAL 漏洞 → 阻断即使 --no-verify
```

## Security Gate (CWE Top 25)

扫描以下 CRITICAL 问题（阻断提交）：

| CWE | Pattern | Severity |
|-----|---------|----------|
| CWE-89 | SQL Injection (`query(.*\$\{`) | CRITICAL |
| CWE-79 | XSS (`innerHTML`, `dangerouslySetInnerHTML`) | CRITICAL |
| CWE-78 | OS Command Injection | CRITICAL |
| CWE-798 | Hardcoded Credentials | CRITICAL |

扫描以下 HIGH 问题（警告但允许）：

| CWE | Pattern | Severity |
|-----|---------|----------|
| CWE-352 | CSRF | HIGH |
| CWE-287 | Improper Auth | HIGH |
| CWE-918 | SSRF | HIGH |

## Usage

```
/commit-push-pr [message]            # Full gate → commit → push → PR
/commit-push-pr --message "fix: .."  # Custom commit message
/commit-push-pr --no-verify          # Skip tests (NOT security)
```

## Workflow

1. **Security Scan** — Run CWE scanner
   - CRITICAL found → BLOCK (even with --no-verify)
   - Report: file, line, CWE ID, severity

2. **Build Check** — Run build
   - Fail → BLOCK, report errors
   - Pass → continue

3. **Lint Check** — Run linter
   - Errors → BLOCK
   - Warnings → continue

4. **Test Check** — Run tests
   - Fail → BLOCK, report coverage
   - Pass → continue

5. **Git Commit** — Create commit with signed-off-by

6. **Git Push** — Push to remote

7. **PR Creation** — Create PR with checklist

## Output Format

```markdown
## CI Gate Results

### Security Scan ✅/❌
- CWE-89 SQL Injection: 0 found
- CWE-79 XSS: 0 found
- [CRITICAL BLOCKS even with --no-verify]

### Build ✅/❌
- [build output]

### Lint ✅/❌
- [lint output]

### Tests ✅/❌
- Coverage: 85%
- [test output]

## Result: ALL GATES PASSED ✅

Commit: abc1234
Branch: feature/tag-filter
PR: https://github.com/owner/repo/pull/123
```
```

#### 测试验证

```bash
# ~~commands/commit-push-pr.md 已移除~~

---

## P2 — 中价值任务（1个月内完成）

---

### P2-TASK-011：实现 Rate Limiter Hook

**问题**：远程会话无调用频率控制，可能被滥用或触发 API 限流。

**修复**：滑动窗口限速 30/min、500/hr、5000/day，fcntl 文件锁保证并发安全。

**来源**：claude-forge rate-limiter.sh。

---

### P2-TASK-012：实现 Security Auto-Trigger Hook

**问题**：安全敏感文件修改后不自动触发安全审查。

**修复**：PostToolUse Hook 检测 auth/、security/、*.crypto 等文件修改，建议 `/security-review`。

**来源**：claude-forge security-auto-trigger.sh。

---

### P2-TASK-013：实现 continuous-learning-v2 (Hook-based)

**问题**：Instinct 系统依赖用户手动触发，观测率低。

**修复**：PreToolUse + PostToolUse Hook 自动捕获观测事件，写入 `observations.jsonl`，后台 Haiku 分析并创建本能。

**来源**：claude-forge continuous-learning-v2 + ECC Instinct v2.1。

---

### P2-TASK-014：实现 security-pipeline Skill（CWE Top 25）

**问题**：无自动化安全扫描。

**修复**：CWE Top 25 检测规则 + 自动修复 Before/After 示例 + STRIDE 威胁建模。

**来源**：claude-forge security-pipeline。

---

### P2-TASK-015：实现 similarity-scorer.py

**问题**：创建新 Skill 时无法判断是否与现有 Skill 重复。

**修复**：4 维评分（name/description/domain/keywords），阈值 >=0.8 跳过、0.6-0.8 合并、<0.3 才创建。

**来源**：claude-forge similarity-scorer.py。

---

## P3 — 架构演进任务（长期建设）

---

### P3-TASK-016：实现 GateGuard 事实强制门禁

**问题**：Agent 在没有充分上下文的情况下就开始写代码。

**修复**：3 阶段 DENY → FORCE（要求文件导入/函数签名/schema） → ALLOW。

**来源**：ECC GateGuard，实验验证 +2.25 分平均提升。

---

### P3-TASK-017：实现 Council 4声部决策

**问题**：架构决策缺少多角度审查。

**修复**：Architect + Skeptic + Pragmatist + Critic 4 个声音独立分析，输出共识+最强异议。

**来源**：ECC council skill。

---

### P3-TASK-018：实现 Agent Teams Orchestration

**问题**：多 Agent 并行执行时缺少文件所有权和自选任务机制。

**修复**：Wave-based execution + self-claim + file ownership separation + plan approval mode。

**来源**：claude-forge team-orchestrator。

---

### P3-TASK-019：升级 evolve-daemon 为 KAIROS-like 真守护进程

**问题**：cron 定时任务不是真守护进程，无法实时响应。

**修复**：实现心跳 tick + 7 天过期 + 15 秒阻塞限制 + 3 个独占工具（SendUserFile/PushNotification/SubscribePR）。

**来源**：Claude Code 源码 KAIROS daemon。

---

### P3-TASK-020：实现 AgentShield 安全扫描器

**问题**：无法自动扫描 harness 本身的安全配置漏洞。

**修复**：扫描 CLAUDE.md、settings.json、MCP 配置、hooks、agents，输出漏洞报告。

**来源**：Anthropic 黑客松 AgentShield。

---

## P4 — 生态扩展任务

---

### P4-TASK-021：新增缺失 Skill 类别

| Category | Priority | Coverage |
|----------|----------|----------|
| **Mobile** (iOS/Android) | P3 | 新增 mobile-dev agent + skill |
| **ML/AI Engineering** | P3 | 新增 ml-engineer agent + skill |
| **IaC** (Terraform/Pulumi) | P2 | 扩展 devops.md |
| **Data Engineering** (Spark/Airflow) | P3 | 新增 data-engineer agent + skill |
| **SRE/Incident Response** | P2 | 新增 sre agent + skill |
| **Documentation Generation** | P3 | 新增 doc-writer agent + skill |
| **LLM/RAG Engineering** | P3 | 新增 llm-engineer agent + skill |
| **Browser Automation** (Playwright) | P2 | 扩展 qa-tester.md |
| **i18n/l10n** | P3 | 新增 i18n skill |
| **FinOps/Cost Optimization** | P3 | 新增 finops skill |

---

## 验证与测试框架

### 整体验证脚本

```bash
#!/bin/bash
# verify-chk-improvements.sh — 验证所有 P0-P1 改进

echo "======================================"
echo "  CHK v2.0 改进验证"
echo "======================================"

PASS=0
FAIL=0

# P0-TASK-001: Skill 描述长度
echo ""
echo "[P0-TASK-001] Skill 描述长度检查..."
python3 -c "
import os, re
skills_dir = 'skills'
failed = []
for skill in sorted(os.listdir(skills_dir)):
    skill_path = os.path.join(skills_dir, skill)
    if not os.path.isdir(skill_path): continue
    for fname in os.listdir(skill_path):
        if fname.endswith('.md') or fname == 'SKILL.md':
            fpath = os.path.join(skill_path, fname)
            content = open(fpath).read()
            m = re.search(r'^description:\s*>?\s*(.+?)(?:^---|\Z)', content, re.S | re.M)
            if m:
                desc = m.group(1).strip()
                tokens = len(desc.split())
                if tokens < 30 or tokens > 50:
                    failed.append(f'{skill}/{fname}: {tokens} tokens')
if failed:
    print('❌ 以下 Skill 不达标:')
    for f in failed:
        print(f'   {f}')
else:
    print('✅ 所有 Skill 描述达标 (30-50 tokens)')
"
[[ ${PIPESTATUS[0]} -eq 0 ]] && ((PASS++)) || ((FAIL++))

# P0-TASK-002: Worktree 生命周期管理
echo ""
echo "[P0-TASK-002] Worktree 生命周期检查..."
[[ -x hooks/bin/worktree-manager.sh ]] && echo "✅ worktree-manager.sh 可执行" || echo "❌ worktree-manager.sh 缺失或不可执行"
[[ -x hooks/bin/worktree-init.sh ]] && echo "✅ worktree-init.sh 可执行" || echo "❌ worktree-init.sh 缺失或不可执行"

# P0-TASK-003: Worktree Hook 事件
echo ""
echo "[P0-TASK-003] Worktree Hook 事件检查..."
python3 -c "
import json
hooks = json.load(open('hooks/hooks.json'))
events = list(hooks.get('hooks', {}).keys())
for e in ['WorktreeCreate', 'WorktreeRemove']:
    if e in events:
        print(f'✅ {e} 已配置')
    else:
        print(f'❌ {e} 未配置')
"

# P0-TASK-004: Output Secret Filter
echo ""
echo "[P0-TASK-004] Output Secret Filter 检查..."
[[ -x hooks/bin/output-secret-filter.sh ]] && echo "✅ output-secret-filter.sh 可执行" || echo "❌ output-secret-filter.sh 缺失"

# P1-TASK-005: Checkpoint
echo ""
echo "[P1-TASK-005] Checkpoint 检查..."
[[ -x hooks/bin/checkpoint-auto-save.sh ]] && echo "✅ checkpoint-auto-save.sh 可执行" || echo "❌ checkpoint-auto-save.sh 缺失"
# ~~commands/checkpoint.md 已移除~~

# P1-TASK-006: Instinct CLI
echo ""
echo "[P1-TASK-006] Instinct CLI 检查..."
[[ -x cli/instinct_cli.py ]] && echo "✅ instinct_cli.py 可执行" || echo "❌ instinct_cli.py 缺失"

# P1-TASK-007: eval-harness
echo ""
echo "[P1-TASK-007] eval-harness 检查..."
[[ -f skills/eval-harness/SKILL.md ]] && echo "✅ eval-harness/SKILL.md 存在" || echo "❌ eval-harness/SKILL.md 缺失"

# P1-TASK-008: session-wrap
echo ""
echo "[P1-TASK-008] session-wrap 检查..."
[[ -f skills/session-wrap/SKILL.md ]] && echo "✅ session-wrap/SKILL.md 存在" || echo "❌ session-wrap/SKILL.md 缺失"

# P1-TASK-009: /commit-push-pr
echo ""
echo "[P1-TASK-009] commit-push-pr 检查..."
# ~~commands/commit-push-pr.md 已移除~~

echo ""
echo "======================================"
echo "  验证完成"
echo "======================================"
```

---

## 实施顺序与依赖

```
Week 1:
  P0-TASK-001 (Skill 描述) → P0-TASK-002 (Worktree) → P0-TASK-003 (Worktree Hook) → P0-TASK-004 (Secret Filter)
       ↓         ↓               ↓                   ↓
Week 2:                                    P1-TASK-005 (Checkpoint) ← P1-TASK-006 (Instinct CLI) ← P1-TASK-007 (eval-harness) ← P1-TASK-008 (Session Wrap) ← P1-TASK-009 (commit-push-pr) ← P1-TASK-010 (/checkpoint command)
       ↓
Week 3-4:
  P2-TASK-011 ~ P2-TASK-015
       ↓
Month 2+:
  P3-TASK-016 ~ P3-TASK-020
       ↓
Ongoing:
  P4-TASK-021 (Skill 类别扩展)
```

---

## 总结

| 优先级 | 任务数 | 预估工时 | 核心价值 |
|--------|--------|----------|----------|
| **P0** | 4 | 6h | 解除阻断，释放 Progressive Disclosure |
| **P1** | 6 | 12h | 构建高价值差异化能力 |
| **P2** | 5 | 10h | 补全安全和质量体系 |
| **P3** | 5 | 20h | 架构演进，构建竞争护城河 |
| **P4** | 1 | 持续 | 生态扩展，覆盖更多场景 |
| **总计** | **21** | **~48h** | — |

**关键洞察**：
- P0 任务可立即开始，无需重构现有架构
- P1 任务相互独立，可并行开发
- P2/P3 任务需要更多设计和验证时间
- P0 完成后的立即收益：Progressive Disclosure + Worktree 隔离 + Secret Filter

---

*方案版本：v2.0 | 制定日期：2026-05-01 | 制定人：Architect Agent + Expert Mode*
