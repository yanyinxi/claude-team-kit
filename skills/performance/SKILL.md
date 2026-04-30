---
name: performance
description: Performance analysis and optimization guidelines. Use when investigating slow responses, high resource usage, or before deploying performance-sensitive features.
---

# Performance — 性能分析与优化

## 分析流程

### 1. 测量先行
- 确认具体瓶颈在哪（用 profiler / metrics，不靠直觉）
- 测量：响应时间、吞吐量、资源使用

### 2. 定位热点
- 数据库：慢查询、N+1 问题、缺失索引
- 应用：不必要循环、重复计算、阻塞调用
- 网络：过多请求、大 payload、未压缩

### 3. 优化
- 数据库：加索引、批量操作、连接池调优
- 应用：缓存、懒加载、异步非阻塞
- 网络：分页、压缩、CDN

## 原则

- 不在没测量的情况下优化
- 优化最痛的 20%，能解决 80% 的问题
- 优化后再次测量确认改善
- 不牺牲可读性换微小性能提升
