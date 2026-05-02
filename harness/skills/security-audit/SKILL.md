---
name: security-audit
description: >
  Opus agents审计认证、支付或数据处理代码时调用，进行OWASP Top 10审查。
  涵盖SQL注入、XSS、CSRF、硬编码密钥和依赖漏洞扫描。
  激活条件：匹配auth/、payment/、security/、*.crypto或*.jwt的文件。
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
context: fork
agent: security-auditor
---

# 安全审计技能

## 何时使用

当需要以下操作时使用此技能：

- 代码安全审查和漏洞扫描
- SQL 注入风险检测
- XSS 跨站脚本漏洞检测
- 硬编码密钥/凭证检测
- 依赖库漏洞扫描（OWASP Top 10）
- 合规审计和安全评估
- PR 合并前的安全检查

## 工作流程

### 第一步：确定审计范围

- 明确审计的代码范围（整个项目 / 单个模块 / 单个文件）
- 了解技术栈（Java/Spring、Vue、PostgreSQL 等）
- 确定审计深度（快速扫描 / 深度检查）

### 第二步：执行安全扫描

| 扫描类型 | 工具/方法 | 覆盖范围 |
|----------|-----------|----------|
| SQL 注入 | Grep 模式匹配 + 代码审查 | Controller、Mapper、Service |
| XSS 漏洞 | Grep 模式匹配 + HTML 转义检查 | 前端 Vue、后端响应 |
| 硬编码密钥 | Grep 敏感字符串模式 | 配置文件、代码文件 |
| 依赖漏洞 | 依赖扫描工具 | pom.xml、package.json |
| 代码规范 | 静态分析工具 | 整体代码库 |

### 第三步：生成审计报告

按严重程度分类问题，提供修复建议和优先级。

---

## SQL 注入扫描方法

### 扫描目标

- 直接字符串拼接的 SQL 查询
- 未使用参数化查询的数据库操作
- 动态构建的 SQL 语句
- ORM 查询中的潜在注入点

### 扫描模式

```bash
# 高风险模式（需重点关注）
grep -rn "Statement\|executeQuery\|executeUpdate\|createStatement" --include="*.java"
grep -rn "concat\|+\s*\"\|String.format" --include="*.xml"
grep -rn "\${" --include="*.xml"  # MyBatis 动态 SQL

# 中风险模式（需审查）
grep -rn "\.query\|\.execute\|\.update" --include="*.java"
grep -rn "where.*=" --include="*.java"
```

### 安全实践检查清单

- [ ] 所有数据库查询使用参数化查询（PreparedStatement）
- [ ] MyBatis 使用 `#{}` 而非 `${}` 进行参数绑定
- [ ] 禁止使用字符串拼接构建 SQL 语句
- [ ] 用户输入经过验证和清理
- [ ] 使用 ORM 框架的参数化 API
- [ ] 查询字段和操作符使用白名单枚举

### 修复建议模板

```markdown
### 🔴 SQL 注入风险

| 文件 | 行号 | 问题代码 | 风险等级 | 修复建议 |
|------|------|----------|----------|----------|
| xxx.java | 45 | `stmt.executeQuery("SELECT * FROM users WHERE id=" + userId)` | Critical | 使用 PreparedStatement 参数化查询 |

**修复代码示例**：
```java
// 修复前（危险）
stmt.executeQuery("SELECT * FROM users WHERE id=" + userId);

// 修复后（安全）
PreparedStatement ps = conn.prepareStatement("SELECT * FROM users WHERE id = ?");
ps.setString(1, userId);
ps.executeQuery();
```
```

---

## XSS 漏洞检测方法

### 扫描目标

- 未经过滤的用户输入直接输出到 HTML
- 未转义的动态内容渲染
- 不安全的 DOM 操作
- 响应头设置不当

### 扫描模式

```bash
# 前端 Vue/React 风险
grep -rn "v-html\|innerHTML\|dangerouslySetInnerHTML" --include="*.vue" --include="*.tsx"
grep -rn "\{\{.*\}\}" --include="*.vue"  # 未转义插值

# 后端响应风险
grep -rn "response.getWriter\|Writer.write\|@ResponseBody" --include="*.java"
grep -rn "setHeader\|addHeader" --include="*.java"

# JavaScript 风险
grep -rn "eval\|Function\|setTimeout.*eval\|setInterval.*eval" --include="*.js" --include="*.ts"
```

### 安全实践检查清单

- [ ] 用户输入在输出前进行 HTML 转义
- [ ] 使用框架默认的转义机制（如 Vue `{{}}` 插值）
- [ ] 避免使用 `v-html`、`innerHTML`、`dangerouslySetInnerHTML`
- [ ] 设置正确的 Content-Type 响应头
- [ ] 配置 CSP（内容安全策略）响应头
- [ ] 对用户输入实施输入验证

### 修复建议模板

```markdown
### 🟠 XSS 跨站脚本漏洞

| 文件 | 行号 | 问题代码 | 风险等级 | 修复建议 |
|------|------|----------|----------|----------|
| xxx.vue | 23 | `<div v-html="userContent"></div>` | High | 使用 `{{ userContent }}` 或自定义转义函数 |
```

---

## 硬编码密钥检测

### 扫描目标

- 硬编码的 API 密钥、密码、Token
- 硬编码的加密密钥（对称加密）
- 数据库连接凭证
- 云服务访问凭证
- 私钥和证书

### 扫描模式

```bash
# 敏感关键词
grep -rn "password\|secret\|token\|api_key\|apikey\|private_key\|credential" --include="*.java" --include="*.js" --include="*.ts" -i

# 常见密钥格式
grep -rn "sk-\|AKIA\|ghp_\|eyJhbGciOi" --include="*.java" --include="*.js" --include="*.ts"
grep -rn "-----BEGIN.*PRIVATE KEY-----" --include="*.pem" --include="*.key"

# 配置文件中明文密码
grep -rn "password\s*=\s*["\']" --include="*.properties" --include="*.yml"
```

### 安全实践检查清单

- [ ] 所有敏感配置使用环境变量
- [ ] 使用密钥管理服务（AWS Secrets Manager、HashiCorp Vault）
- [ ] 配置文件不提交到版本控制
- [ ] 数据库密码使用强哈希存储
- [ ] 定期轮换 API 密钥和密码
- [ ] 添加敏感文件到 `.gitignore`

### 修复建议模板

```markdown
### 🔴 硬编码密钥/凭证

| 文件 | 行号 | 问题代码 | 风险等级 | 修复建议 |
|------|------|----------|----------|----------|
| xxx.java | 12 | `private static final String API_KEY = "sk-xxx"` | Critical | 使用环境变量 `System.getenv("API_KEY")` |
| xxx.properties | 5 | `db.password=mySecretPass` | Critical | 使用环境变量引用 |

**修复代码示例**：
```java
// 修复前（危险）
private static final String API_KEY = "sk-xxx";

// 修复后（安全）
private static final String API_KEY = System.getenv("API_KEY");
```
```

---

## 依赖漏洞扫描（OWASP Top 10）

### OWASP Top 10 (2021)

| 排名 | 类别 | 描述 |
|------|------|------|
| A01 | 失效的访问控制 | 未对身份验证的用户实施恰当的访问控制 |
| A02 | 加密失败 | 加密失败或缺乏有效加密导致数据泄露 |
| A03 | 注入 | SQL 注入、NoSQL 注入、OS 注入等 |
| A04 | 不安全的设计 | 安全设计缺陷，缺少或无效的安全控制 |
| A05 | 安全配置错误 | 不安全或不必要的功能配置 |
| A06 | 易受攻击和过时的组件 | 使用已知漏洞的组件 |
| A07 | 识别和身份验证失败 | 身份验证和会话管理功能中的缺陷 |
| A08 | 软件和数据完整性失败 | 不假设第三方资源是可信的 |
| A09 | 安全日志和监控失败 | 日志记录不足，无法检测到攻击 |
| A10 | 服务器端请求伪造（SSRF） | 通过 URL 获取资源时未验证用户输入 |

### 依赖扫描工具

```bash
# Maven 项目（Java）
# 使用 OWASP Dependency-Check
mvn org.owasp:dependency-check-maven:check

# 使用 Snyk
mvn snyk:monitor
mvn snyk:test

# npm 项目（前端）
npm audit
npm audit fix

# 使用 Snyk
npx snyk test
```

### 安全实践检查清单

- [ ] 定期更新依赖库到安全版本
- [ ] 使用依赖扫描工具检测已知漏洞
- [ ] 关注依赖库的安全公告
- [ ] 避免使用已停止维护的库
- [ ] 最小化依赖原则（仅引入必要依赖）
- [ ] 锁定依赖版本（pom.xml / package-lock.json）

---

## 代码规范检查

### 安全编码规范

| 规范项 | 检查内容 | 优先级 |
|--------|----------|--------|
| 输入验证 | 所有用户输入都有验证 | Critical |
| 输出编码 | 所有输出都有适当编码 | Critical |
| 认证授权 | 敏感操作有权限控制 | Critical |
| 错误处理 | 异常不泄露敏感信息 | High |
| 日志记录 | 敏感信息不记录日志 | High |
| 会话管理 | 会话 ID 安全生成和存储 | High |
| 加密传输 | 使用 HTTPS/TLS 加密 | High |
| 资源释放 | 正确关闭文件、连接等资源 | Medium |

### 常见安全问题

```markdown
## 高危问题（必须修复）

1. SQL 注入
2. 硬编码密钥
3. 未授权访问
4. 敏感信息泄露
5. 远程代码执行

## 中危问题（应尽快修复）

1. XSS 跨站脚本
2. CSRF 跨站请求伪造
3. 不安全反序列化
4. 使用不安全的加密算法
5. 日志信息泄露

## 低危问题（建议修复）

1. 缺少安全响应头
2. 错误信息过于详细
3. 不安全的重定向
4. 缺少安全注释
```

---

## 安全检查清单

### 认证与授权

- [ ] 敏感 API 有认证要求
- [ ] 密码使用强哈希算法存储（bcrypt、Argon2）
- [ ] 密码有复杂度要求
- [ ] 登录失败有锁定机制
- [ ] 会话超时配置合理
- [ ] 使用 JWT 时有签名验证和过期检查
- [ ] 基于角色的访问控制（RBAC）正确实现

### 数据保护

- [ ] 敏感数据加密存储
- [ ] 传输层使用 TLS 1.2+
- [ ] 敏感配置不硬编码
- [ ] 数据库使用最小权限原则
- [ ] 敏感日志脱敏处理
- [ ] 文件上传有类型和大小限制

### API 安全

- [ ] API 有速率限制
- [ ] 输入参数有验证
- [ ] 响应有适当的信息隐藏
- [ ] CORS 配置正确
- [ ] 无敏感信息在 URL 中
- [ ] 使用标准 HTTP 方法

### 日志与监控

- [ ] 登录尝试有日志记录
- [ ] 敏感操作有审计日志
- [ ] 异常信息不泄露堆栈
- [ ] 有安全事件监控告警
- [ ] 日志保留时间合理

---

## 最佳实践

### 安全开发周期（SDL）

```
需求设计 → 安全评审 → 安全编码 → 安全测试 → 安全部署 → 持续监控
    ↑                                              ↓
    ←——————————————— 反馈改进 ←———————————————————————
```

### 纵深防御原则

1. **边界防护**：网络层防火墙、WAF
2. **应用防护**：输入验证、输出编码
3. **数据防护**：加密、访问控制
4. **运营防护**：监控、审计、响应

### 安全编码原则

| 原则 | 说明 |
|------|------|
| 最小权限 | 只授予必要权限 |
| 默认安全 | 默认配置是安全的 |
| 纵深防御 | 多层安全防护 |
| 失败安全 | 失败时默认拒绝 |
| 职责分离 | 关键操作需要多方授权 |
| 开放设计 | 依赖算法保密是错误的 |
| 完整校验 | 客户端和服务端都要校验 |

---

## 输出格式

```markdown
# 安全审计报告：[审计范围]

## 审计概览
- 审计时间：YYYY-MM-DD
- 审计范围：XXX
- 发现问题数：XX
- 严重问题：XX
- 重要问题：XX
- 建议：XX

## 问题列表

### 🔴 严重问题（Critical）

| 文件 | 行号 | 问题类型 | 风险等级 | 修复建议 |
|------|------|----------|----------|----------|
| api/user.java | 45 | SQL 注入 | Critical | 使用参数化查询 |
| config/SecurityConfig.java | 12 | 硬编码密钥 | Critical | 使用环境变量 |

### 🟠 高危问题（High）

| 文件 | 行号 | 问题类型 | 风险等级 | 修复建议 |
|------|------|----------|----------|----------|
| utils/XssUtil.java | 8 | XSS 防护缺失 | High | 添加 HTML 转义 |

### 🟡 中危问题（Medium）

| 文件 | 行号 | 问题类型 | 风险等级 | 修复建议 |
|------|------|----------|----------|----------|
| controller/ApiController.java | 23 | 缺少速率限制 | Medium | 添加限流配置 |

### 💡 建议（Suggestions）

| 文件 | 行号 | 建议 | 原因 |
|------|------|------|------|
| pom.xml | - | 更新依赖版本 | 修复已知漏洞 |
```

---

## 参考资料

### 官方标准

- **OWASP Top 10**: https://owasp.org/Top10/
- **OWASP Cheat Sheet Series**: https://cheatsheetseries.owasp.org/
- **CWE (Common Weakness Enumeration)**: https://cwe.mitre.org/
- **NIST Cybersecurity Framework**: https://csrc.nist.gov/publications/sp800-53

### 安全工具

| 工具 | 用途 | 链接 |
|------|------|------|
| SonarQube | 静态代码分析 | https://www.sonarqube.org/ |
| Checkmarx | 应用安全测试 | https://www.checkmarx.com/ |
| Fortify | 静态应用安全测试 | https://www.microfocus.com/en-us/solutions/application-security |
| Snyk | 依赖漏洞扫描 | https://snyk.io/ |
| OWASP ZAP | 动态应用安全测试 | https://www.zaproxy.org/ |
| Dependency-Check | 依赖漏洞扫描 | https://jeremylong.github.io/OWASP-Dependency-Check/ |

### 学习资源

- **GitHub Security Lab**: https://securitylab.github.com/
- **Mozilla Security Guidelines**: https://wiki.mozilla.org/Security
- **Microsoft Security Guidelines**: https://learn.microsoft.com/en-us/azure/security/

---

## 📈 进化记录（手动维护）

_此章节由维护者按需更新，记录从实际安全审计任务执行中学到的经验和最佳实践。_

### 2026-04-26

- 创建安全审计技能
- 包含 SQL 注入、XSS、硬编码密钥检测方法
- 添加 OWASP Top 10 (2021) 依赖扫描指南
- 提供完整的安全检查清单和最佳实践