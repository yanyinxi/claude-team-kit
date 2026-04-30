---
name: api-designer
description: RESTful API design standards. Use when designing new API endpoints, reviewing API contracts, or establishing API conventions for a project.
---

# API Designer — RESTful API 设计规范

## URL 设计

```
GET    /api/users          # 列表
GET    /api/users/:id      # 详情
POST   /api/users          # 创建
PUT    /api/users/:id      # 全量更新
PATCH  /api/users/:id      # 部分更新
DELETE /api/users/:id      # 删除
```

## 响应格式

```json
{
  "data": { ... },
  "meta": { "page": 1, "pageSize": 20, "total": 100 }
}
```

错误响应：
```json
{
  "error": { "code": "VALIDATION_ERROR", "message": "...", "details": [...] }
}
```

## 状态码

| 码 | 含义 | 使用场景 |
|----|------|---------|
| 200 | OK | 请求成功 |
| 201 | Created | 资源创建成功 |
| 204 | No Content | 删除成功 |
| 400 | Bad Request | 参数校验失败 |
| 401 | Unauthorized | 未认证 |
| 403 | Forbidden | 无权限 |
| 404 | Not Found | 资源不存在 |
| 422 | Unprocessable | 业务逻辑错误 |
| 500 | Server Error | 内部错误 |

## 原则

- 资源用名词复数（/users 非 /getUser）
- 分页查询有默认值（page=1, pageSize=20）
- 过滤/排序/字段选择用查询参数
- 版本策略提前约定（/api/v1/ 或 Header）
