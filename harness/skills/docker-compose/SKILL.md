---
name: docker-compose
description: >
  Sonnet agents创建Dockerfile、docker-compose.yml或容器化服务时调用。
  涵盖单容器单进程、非root运行、多阶段构建和healthcheck配置。
  激活条件：涉及docker、container、dockerfile、compose相关讨论。
---

# Docker Compose — 容器化部署

## 原则

- 单容器单进程：一个容器跑一个服务
- 非 root 运行：容器内不以 root 身份运行
- Secret 不入镜像：用环境变量或 Secret 管理
- 多阶段构建：分离构建和运行阶段，缩小镜像体积
- 健康检查：每个容器配置 healthcheck

## Dockerfile 模板

```dockerfile
FROM base AS build
# ... build steps

FROM base AS runtime
COPY --from=build /app /app
USER 1000
HEALTHCHECK --interval=30s CMD curl -f http://localhost/health
ENTRYPOINT ["..."]
```

## 常用命令

| 命令 | 用途 |
|------|------|
| `docker compose up -d` | 启动 |
| `docker compose logs -f` | 查看日志 |
| `docker compose exec svc sh` | 进入容器 |
| `docker compose down -v` | 停止并清理 |
