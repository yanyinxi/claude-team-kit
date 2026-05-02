---
name: security-pipeline
description: >
  安全扫描流水线 Skill。提供 CWE Top 25 漏洞检测规则（CWE-89 SQL 注入、CWE-79 XSS、CWE-78 命令注入、CWE-798 硬编码凭证），
  自动修复 Before/After 示例代码和 STRIDE 威胁建模模板，内置 vuln_prioritizer.py 按 CVSS 优先级排序。
  适用于代码审计和安全合规检查场景，CRITICAL 漏洞阻断即使使用 --no-verify。
---

# security-pipeline — 安全扫描流水线 Skill

## 核心能力

1. **CWE Top 25 漏洞检测**：SQL 注入、XSS、命令注入、硬编码凭证等
2. **自动修复建议**：Before/After 代码示例
3. **STRIDE 威胁建模**：6 类威胁分类与缓解措施
4. **漏洞优先级排序**：CVSS × exploitability × asset_value × exposure
5. **vuln_prioritizer.py**：自动化漏洞评分工具

## CWE Top 25 检测规则

### 🔴 CRITICAL（阻断级）

#### CWE-78：OS Command Injection

**检测模式**：
```
grep -rn "os.system\|subprocess\.(call|run|shell=True|Popen)" --include="*.py" .
grep -rn "`.*\$({\|\\$(" --include="*.sh" .
grep -rn "exec\s*\(" --include="*.js" .
```

**高风险函数**：
- Python: `os.system()`, `subprocess.run(shell=True)`, `exec()`, `eval()`
- JavaScript: `eval()`, `Function()`, `new Function()`
- Shell: `$( )`, `` ` ` ``, `| sh`

**自动修复示例**：

```python
# ❌ Before（命令注入）
import os
cmd = f"grep {user_input} /var/log/app.log"
os.system(cmd)

# ✅ After（参数化，无 shell 执行）
import subprocess
result = subprocess.run(["grep", user_input, "/var/log/app.log"],
                       capture_output=True, text=True)
```

```javascript
// ❌ Before
const cmd = `grep ${userInput} /var/log/app.log`;
exec(cmd);

// ✅ After
const { grep } = require('child_process');
spawn('grep', [userInput, '/var/log/app.log']);
```

---

#### CWE-89：SQL Injection

**检测模式**：
```
grep -rn "\.execute\s*\(\s*['\"]SELECT\|\.query\s*\(\s*['\"]SELECT" .
grep -rn "f\"SELECT\|f'SELECT\|SELECT.*\+ " .
```

**高风险模式**：
- 字符串拼接 SQL：`"SELECT * FROM users WHERE id=" + userId`
- f-string 插值：`f"SELECT * FROM {table}"`
- 格式化字符串：`"SELECT * FROM {} WHERE id={}".format(uid)`

**自动修复示例**：

```python
# ❌ Before
cursor.execute(f"SELECT * FROM users WHERE id={user_id}")

# ✅ After
cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
```

```javascript
// ❌ Before
const query = `SELECT * FROM users WHERE id = ${req.params.id}`;

// ✅ After
const query = 'SELECT * FROM users WHERE id = ?';
db.query(query, [req.params.id]);
```

---

#### CWE-798：Hardcoded Credentials

**检测模式**：
```
grep -rn "password\s*=\s*['\"][^'\"]{8,}" .
grep -rn "api[_-]?key\s*=\s*['\"]sk-" .
grep -rn "secret\s*=\s*['\"][a-zA-Z0-9]{20,}" .
grep -rn "aws[_-]?access[_-]?key" .
```

**暴露场景**：
- 源代码中的 API Key：`api_key = "sk-antapi03-xxx..."`
- 数据库密码：`PASSWORD=admin123`
- AWS 凭证：`AWS_ACCESS_KEY_ID=AKIA...`

**自动修复示例**：

```python
# ❌ Before
OPENAI_API_KEY = "sk-antapi03-xxxxx"

# ✅ After
import os
openai.api_key = os.environ.get("OPENAI_API_KEY")
# 配合 .env 文件：OPENAI_API_KEY=<your-key>
```

---

#### CWE-306：Missing Authentication

**检测模式**：
- API 路由无 `@auth_required` 装饰器
- API Gateway 无 authentication 配置
- GraphQL 端点无 `isAuthenticated` 规则

---

### 🟠 HIGH（警告级）

#### CWE-79：XSS（Cross-Site Scripting）

**检测模式**：
```javascript
// 危险：直接插入用户输入到 DOM
innerHTML = userInput;
document.write(userInput);
$(el).html(userInput);

// 危险：URL 参数未转义
<a href="?search=<%= request.params.search %>">
```

**自动修复示例**：

```javascript
// ❌ Before
element.innerHTML = userInput;

// ✅ After
element.textContent = userInput;
// 或使用 DOMPurify
import DOMPurify from 'dompurify';
element.innerHTML = DOMPurify.sanitize(userInput);
```

---

#### CWE-502：Deserialization

**检测模式**：
```python
# Python pickle 反序列化
import pickle
data = pickle.loads(request.body)

# Java YAML 反序列化
YAML.load(body)  # 不安全
YAML.safe_load(body)  # 安全
```

---

#### CWE-77：Command Injection（变体）

同 CWE-78，但影响路径：
- Dockerfile 中的 `RUN` 命令
- CI/CD pipeline 脚本
- 容器 entrypoint

---

### 🟡 MEDIUM（建议级）

#### CWE-22：Path Traversal

**检测模式**：
```
grep -rn "open\s*\(" --include="*.py" . | grep -v "safe_path"
grep -rn "sendFile\|sendfile\|StaticInline" --include="*.js" .
```

**自动修复示例**：

```python
# ❌ Before
@app.route('/files/<filename>')
def download(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ✅ After
@app.route('/files/<filename>')
def download(filename):
    safe_path = os.path.realpath(UPLOAD_DIR)
    requested_path = os.path.realpath(os.path.join(UPLOAD_DIR, filename))
    if not requested_path.startswith(safe_path):
        abort(403)
    return send_from_directory(safe_path, os.path.basename(requested_path))
```

---

## STRIDE 威胁建模模板

| 威胁类别 | 描述 | 缓解措施 |
|---------|------|---------|
| **S**poofing（伪装） | 冒充他人身份 | 强身份验证（MFA、JWT） |
| **T**ampering（篡改） | 修改数据或代码 | 完整性校验（HMAC、数字签名） |
| **R**epudiation（抵赖） | 否认已执行操作 | 审计日志、数字签名 |
| **I**nformation Disclosure（信息泄露） | 泄露敏感信息 | 加密（TLS、AES）、访问控制 |
| **D**enial of Service（拒绝服务） | 服务不可用 | 限流、冗余、CDN |
| **E**levation of Privilege（权限提升） | 获得超出权限 | 最小权限原则、RBAC |

### STRIDE 分析示例

```
API 端点：POST /api/transfer

S（伪装）：攻击者伪造他人身份发起转账
  → 缓解：JWT + 2FA 验证

T（篡改）：请求参数在传输中被修改（金额）
  → 缓解：请求体 HMAC 签名

R（抵赖）：用户否认发起过转账
  → 缓解：审计日志 + 操作视频录屏

I（信息泄露）：转账金额暴露给日志系统
  → 缓解：敏感字段加密存储

D（拒绝服务）：API 被频繁调用导致瘫痪
  → 缓解：API 限流（rate limiter hook）

E（权限提升）：普通用户获得管理员权限
  → 缓解：RBAC + 定期权限审计
```

## vuln_prioritizer.py 使用方法

```bash
# 漏洞列表输入（JSON 格式）
python3 vuln_prioritizer.py --input vulns.json

# 输出：按优先级排序的漏洞列表
```

**输入格式**：
```json
[
  {
    "id": "CWE-89",
    "cvss": 9.8,
    "exploitability": 3.2,
    "asset_value": 9.0,
    "exposure": 8.0
  }
]
```

**算法**：`priority_score = cvss × exploitability × asset_value × exposure`

**输出格式**：
```
Priority  Vuln ID   Score  CVSS  Exploitability
--------  --------  -----  ----  ---------------
1        CWE-78    250.0  9.8   3.2
2        CWE-89    220.0  9.8   2.8
```

## CI/CD 集成

在项目中集成安全扫描：

```yaml
# .github/workflows/security-scan.yml
name: Security Scan

on: [push, pull_request]

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Security Pipeline
        run: |
          grep -rn "password\s*=\s*['\"][^'\"]{8,}" src/ || true
          grep -rn "\.execute\s*\(\s*['\"]SELECT.*\+" src/ || true
          npm audit --audit-level=high
```

## Red Flags

- 源代码中有 `api_key = "sk-...` 格式的硬编码
- SQL 查询使用字符串拼接而非参数化
- `innerHTML` 直接插入用户输入
- `subprocess.run(shell=True)` 处理外部输入
- API 端点无 authentication/authorization
