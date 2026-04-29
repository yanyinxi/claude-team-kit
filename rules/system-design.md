# System Design Rules（Java 项目）

**更新时间**: 2026-04-23
**适用范围**: 全局（架构设计场景）

## 核心设计原则

### ✅ 数据库选型：访问模式驱动

不要按技术热度选型，要按访问模式选型：

| 场景 | 推荐 | 原因 |
|------|------|------|
| 结构化过滤 + 聚合 + 强一致 | PostgreSQL | B-tree/GIN/JSONB，ACID |
| 全文检索 + 大规模 facet | ElasticSearch | 倒排索引，relevance |
| 高并发 KV 缓存 | Redis | 内存，O(1) |
| 时序数据 | InfluxDB/TimescaleDB | 时序压缩 |

**当前项目**：PostgreSQL 15（结构化过滤 + 三条聚合 + 强一致导入 = PG 主战场）

### ✅ Schema 设计原则

1. **查询驱动建索引**：为真实查询场景建索引，不为幻想建索引
2. **枚举归一**：DB 只存 canonical code，归一化在应用层（ETL Normalizer）
3. **JSONB 兜底**：稀疏字段用 `extra JSONB + GIN`，不做 EAV 也不做列爆炸
4. **血缘保留**：`source_id + raw_record JSONB`，支持审计和重跑 ETL

### ✅ 防御性设计

- 查询 DSL：字段名/操作符/返回字段**三重白名单**，未知字段 400 而不是静默忽略
- 排序：字段名通过枚举映射到 DB 列名，禁止 `${fieldName}` 字符串拼接
- 分页：`page_size` 上限 200，防止全表扫描

## 反模式

### ⚠️ 技术热度选型

不能因为 ES 流行就选 ES，要先定义访问模式再对照引擎能力。

### ⚠️ 缺少演进路径

每个技术决策都要说明"未来什么情况会推翻这个决定"。选 PG 要说清什么时候会加 ES，否则不是架构师思维。

### ⚠️ schema 里有 magic number 或隐含约定

约束写 DDL（CHECK/UNIQUE/NOT NULL），不要靠代码约定。
