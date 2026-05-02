---
name: sre
description: >
  站点可靠性工程 Skill。提供事故响应流程（SEV1-4 分级）、Runbook 执行规范、SLO/SLI 定义模板、
  告警阈值配置、P50/P95/P99 延迟监控和错误预算计算。内置 5 Why 根因分析法和 postmortem 模板，
  适用于生产环境运维保障、故障快速恢复和可靠性持续改进场景。
  支持 MTTR/MTTF/MTBF 等 SRE 核心指标追踪。
---

# sre — 站点可靠性工程 Skill

## 核心能力

1. **事故响应**：分级 → 定位 → 止损 → 复盘
2. **Runbook 执行**：标准化操作步骤、可审计
3. **SLO/SLI 定义**：量化可靠性目标
4. **告警阈值**：P95/P99 延迟、错误率、饱和度
5. **事后分析**：5 Whys、根因分析、改进措施

## 事故分级

| 级别 | 定义 | 响应时间 | 升级条件 |
|------|------|---------|---------|
| SEV-1 | 全站不可用 | 立即 | 5 分钟无进展 |
| SEV-2 | 核心功能不可用 | 15 分钟 | 30 分钟无进展 |
| SEV-3 | 非核心功能故障 | 1 小时 | 影响用户 >5% |
| SEV-4 | 轻度降级 | 4 小时 | 影响扩大 |

## 事故响应流程

```
SEV-1 触发
    ↓
1️⃣ 响应（0-5 分钟）
  • 值班 SRE 确认告警
  • 创建 Incident Channel
  • 指派 Incident Commander（IC）

2️⃣ 定位（5-30 分钟）
  • IC 协调信息收集
  • Runbook 对照诊断
  • 快速止血（不求根因）

3️⃣ 止损（30 分钟内）
  • 切换流量 / 回滚 / 熔断
  • 验证止血有效
  • 持续监控

4️⃣ 恢复后
  • 完整复盘
  • 写 postmortem
  • 跟进改进措施
```

### 常用止血 Runbook

```bash
# 1. 服务回滚
kubectl rollout undo deployment/<name> -n <namespace>
kubectl rollout undo deployment/<name> -n <namespace> --to-revision=<N>

# 2. 流量切换
# A/B 测试环境切换
kubectl patch service <name> -n <namespace> \
  -p '{"spec":{"selector":{"version":"stable"}}}'

# 3. 熔断
# Hystrix: 请求量阈值触发熔断
# 降级到缓存或静态页面

# 4. Pod 重启
kubectl delete pod <pod-name> -n <namespace>
# Kubernetes 自动重建

# 5. 限流
# API Gateway 层限流
# Redis 计数限流
```

### 常见告警处理

```
❌ P99 延迟 > 2s
  → 检查：CPU 突增 / GC pause / DB slow query
  → 快速止血：水平扩容
  → 根因：分析慢查询

❌ 错误率 > 1%
  → 检查：上游服务 / 依赖超时 / 配置变更
  → 快速止血：切流量到备用集群
  → 根因：日志链路追踪

❌ 内存使用 > 90%
  → 检查：内存泄漏 / 突发流量
  → 快速止血：Pod 重启
  → 根因：heap profile

❌ 连接池耗尽
  → 检查：DB 连接泄漏 / QPS 突增
  → 快速止血：连接池重置
  → 根因：连接未 release
```

## SLO/SLI 定义模板

```yaml
# slo-config.yaml
slos:
  - name: availability
    sli: "API 请求成功比例"
    target: 99.9%           # 允许 downtime: 8.7h/年
    current: 99.95%
    error_budget: 0.05%

  - name: latency-p95
    sli: "P95 响应时间 < 500ms"
    target: 500ms
    current: 320ms
    error_budget: 180ms

  - name: latency-p99
    sli: "P99 响应时间 < 2s"
    target: 2000ms
    current: 1500ms
    error_budget: 500ms

  - name: error-rate
    sli: "5xx 错误率 < 0.1%"
    target: 0.1%
    current: 0.05%
    error_budget: 0.05%

alert_rules:
  - sli: availability
    threshold: 99.5%        # 比 SLO 宽松
    urgency: high
    message: "可用性低于 99.5%，接近 SLO 边界"

  - sli: latency-p95
    threshold: 450ms
    urgency: medium
    message: "P95 延迟接近 SLO 边界"
```

## 事后分析模板（Postmortem）

```markdown
# Postmortem: <事件名称>

**日期**：2026-05-01
**持续时间**：45 分钟
**影响**：约 2000 用户无法完成支付
**级别**：SEV-2

## 时间线
- 14:00 — 监控告警：错误率突增至 15%
- 14:05 — IC 接管，确认影响范围
- 14:15 — 定位到数据库连接池耗尽
- 14:30 — 重启服务，流量恢复
- 14:45 — 完全恢复

## 根因分析（5 Whys）
1. 为什么用户无法支付？
   → 数据库连接等待超时

2. 为什么连接池耗尽？
   → 新上线的批量导入任务占用大量连接

3. 为什么批量导入占用大量连接？
   → SQL 查询未优化，每条记录单独查询

4. 为什么未发现此问题？
   → 压测未覆盖批量导入场景

5. 为什么未覆盖？
   → SRE 未参与该功能 code review

## 改进措施
| 措施 | 负责人 | 完成日期 |
|------|-------|---------|
| 优化批量 SQL（JOIN 替代循环）| @backend | 2026-05-05 |
| 添加批量场景压测 | @qa | 2026-05-08 |
| SRE 参与高流量功能 code review | @sre-lead | 2026-05-10 |

## 复盘结论
根本原因为 SQL N+1 问题，根本措施为代码级优化。
短期止血为重启服务，长期方案为 SQL 优化 + 压测补充。
```

## 验证方法

```bash
[[ -f skills/sre/SKILL.md ]] && echo "✅"

grep -q "SEV-1\|SEV-2\|incident" skills/sre/SKILL.md && echo "✅ 事故分级"
grep -q "rollback\|slo\|alert" skills/sre/SKILL.md && echo "✅ 响应流程"
grep -q "postmortem\|5 Whys\|root cause" skills/sre/SKILL.md && echo "✅ 复盘模板"
```

## Red Flags

- SEV-1 超过 5 分钟无 IC 指派
- 未止血就花时间定位根因
- 事后无 postmortem 记录
- SLO 超出但无人问津
- 改进措施不落地
