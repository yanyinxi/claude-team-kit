---
name: gate-guard
description: >
  架构守卫 Skill。在首次代码变更前拦截，要求提供事实证据（文件路径、函数签名或 Schema 定义），
  防止无根据修改。内置 DENY → FORCE → ALLOW 三阶段协议，适用于关键业务逻辑、核心模块重构等高风险变更场景。
  强制 Read 目标文件后引用相关代码再执行 Edit，拦截 rm/mv/git reset 等危险 Bash 操作。
---

# gate-guard — 架构守卫 Skill

## 核心原则

**第一个 Edit/Write/Bash 之前必须提供证据**，否则阻断。

```
用户首次变更请求
    ↓
GateGuard 拦截
    ↓
要求提供以下之一：
  • 引用文件路径 + 行号
  • 函数签名
  • Schema/API 定义
    ↓
DENY（无证据）→ 用户补充 → FORCE（有证据）→ ALLOW
```

## 3阶段协议

### Stage 1：DENY（阻断）

**触发条件**：首次 Edit/Write/Bash 请求，无引用任何现有代码

**响应**：
```
🔴 GateGuard: DENY

  变更类型：<描述>
  当前文件：<目标文件>

  ❌ 无事实证据，不允许变更

  请提供以下证据之一：
  [1] 引用现有代码：`Read` 目标文件 → 引用相关代码段
  [2] 引用函数签名：函数名 + 参数类型
  [3] 引用 Schema：API/数据模型定义

  继续前请先 `Read` 相关文件。
```

**为什么 DENY**：
- AI 会"幻觉"出解决方案
- 无上下文时修改容易破坏现有逻辑
- 强制搜索现有代码 → 减少错误

---

### Stage 2：FORCE（要求证据）

**触发条件**：用户提供证据

**FORCE 清单**（按类型）：

| 变更类型 | 最低证据要求 |
|---------|------------|
| 修改函数 | 函数签名 + 调用点 |
| 修改 API | Schema 定义 + 调用方 |
| 修改数据模型 | 引用现有字段 + 使用方 |
| 新增文件 | 引用类似文件作为模板 |
| 删除文件 | 引用所有引用点 |

**证据格式示例**：
```
✅ 证据：
  - 引用文件：src/services/auth.ts:42
    const token = jwt.verify(token, secret);
  - 引用函数签名：
    function verifyToken(token: string, secret: string): Promise<User>
```

---

### Stage 3：ALLOW（放行）

**触发条件**：证据充分且有效

**响应**：
```
🟢 GateGuard: ALLOW

  证据已确认：
  - 引用文件：src/services/auth.ts:42
  - 函数签名：verifyToken(token, secret): Promise<User>

  已解锁变更。
  继续执行修改。
```

## 使用场景

### 场景 1：重构关键函数

```
> 修改 verifyToken 函数，添加缓存

🔴 GateGuard: DENY
  请先 Read src/services/auth.ts 并引用相关代码
```

```
✅
  引用：src/services/auth.ts:38-50
  export async function verifyToken(token: string, secret: string) {
    const user = await db.users.findByToken(token);
    return user;
  }

🟢 GateGuard: ALLOW — 已解锁
```

### 场景 2：修改 API Schema

```
> 修改 POST /api/users 的请求体，添加 role 字段

🔴 GateGuard: DENY
  请先 Read 相关 Schema 并引用现有字段定义
```

```
✅
  引用：types/user.ts:12
  interface UserSchema {
    id: string;
    email: string;
  }

🟢 GateGuard: ALLOW — 确认添加 role: string 字段
```

### 场景 3：删除文件

```
> 删除 src/utils/legacy-helper.ts

🔴 GateGuard: DENY
  删除前请先 grep 搜索所有引用点
```

```
✅
  引用搜索结果：
  - src/services/payment.ts:23 import { legacyHelper } from '../utils/legacy-helper'
  - src/workers/billing.ts:15 import { legacyHelper } from '../utils/legacy-helper'
  需要先处理 2 个引用点

🟢 GateGuard: ALLOW — 确认引用已处理
```

## 适用边界

**GateGuard 介入**：
- Edit/Write 涉及核心模块（auth/payment/billing）
- Bash 执行 `rm`/`mv`/`git reset` 等危险命令
- 修改 API 路由或中间件
- 删除非测试文件

**GateGuard 跳过**：
- 新增独立文件（已有模板）
- Read 操作（只读不修改）
- 明显安全的操作（添加 console.log、日志）
- 已有明确证据的变更

## 验证方法

```bash
# 1. Skill 文件存在
[[ -f skills/gate-guard/SILL.md ]] && echo "✅"

# 2. 包含 3 个 Stage
for stage in "DENY" "FORCE" "ALLOW"; do
  grep -qi "$stage" skills/gate-guard/SILL.md && echo "✅ $stage" || echo "❌ $stage"
done

# 3. 包含证据格式
grep -q "引用文件\|函数签名\|Schema" skills/gate-guard/SILL.md && echo "✅ 证据类型"
```

## Red Flags

- 无证据直接执行 Edit/Write
- 用户说"就这样改"就跳过审查
- 引用文件但内容不相关（虚假证据）
