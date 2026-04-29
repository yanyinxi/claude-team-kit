---
paths:
  - main/backend/src/main/java/**/*.java
  - main/backend/src/main/resources/**/*.xml
  - main/backend/src/main/resources/**/*.yml
---

# Backend Development Rules（Java / Spring Boot）

**更新时间**: 2026-04-28（v3 — 加入安全过滤器链、统一响应格式规范）
**技术栈**: Java 17 + Spring Boot 3.3 + MyBatis-Plus 3.5 + PostgreSQL 15 + Flyway + Testcontainers

## 最佳实践

### ✅ 异常处理：统一用 ApiException + GlobalExceptionHandler

```java
// ✅ 正确
throw new ApiException(404, "Asset not found: " + id);
throw new ApiException(400, "Invalid filter field: " + rawField);

// ❌ 错误：绕过统一响应格式
throw new ResponseStatusException(HttpStatus.NOT_FOUND, "not found");
```

`GlobalExceptionHandler` 捕获后统一返回 `{ "code": 4xx, "message": "..." }`。

---

### ✅ 数据访问：BaseMapper 做简单查询，XML 做动态 DSL 查询

```java
// ✅ 简单查询
Asset asset = assetMapper.selectById(id);

// ✅ 动态 DSL 查询（复杂过滤/排序）
List<Map<String, Object>> result = assetMapper.selectByDsl(params, fields, orderClauses, limit, offset);

// ❌ 错误：QueryWrapper 不支持 @> / jsonb_path_ops
```

---

### ✅ PostgreSQL text[] 的正确 TypeHandler

`JacksonTypeHandler` 产出 JSON `["a","b"]`，PostgreSQL **不能** 直接 `::text[]` cast（PG 数组字面量是 `{a,b}` 格式）。
必须用自定义 TypeHandler：

```java
// ✅ 正确注解：@MappedTypes（不是 @MappedJavaTypes，后者在 MyBatis 中不存在）
@MappedTypes(List.class)
public class PgStringArrayTypeHandler extends BaseTypeHandler<List<String>> {
    @Override
    public void setNonNullParameter(PreparedStatement ps, int i,
            List<String> parameter, JdbcType jdbcType) throws SQLException {
        // 用 JDBC createArrayOf 正确传递 PG text[]
        Array array = ps.getConnection().createArrayOf("text", parameter.toArray(new String[0]));
        ps.setArray(i, array);
    }
    // getNullableResult: toList((Object[]) rs.getArray(columnName).getArray())
}
```

实体字段：
```java
@TableField(typeHandler = PgStringArrayTypeHandler.class)
private List<String> tags;
```

XML 写入（无需 `::text[]` cast，TypeHandler 已创建正确 JDBC Array）：
```xml
#{tags, typeHandler=com.homework.asset.config.PgStringArrayTypeHandler}
```

---

### ✅ 排序安全：用 `<foreach>/<choose>` 内置列名，禁止 `${orderBy}`

```xml
<!-- ✅ 正确：orderClauses 是 List<SortClause>，字段名 hardcode 在 XML -->
<if test="orderClauses != null and !orderClauses.isEmpty()">
    ORDER BY
    <foreach collection="orderClauses" item="clause" separator=",">
        <choose>
            <when test="clause.columnName == 'uploaded_at'">uploaded_at</when>
            <when test="clause.columnName == 'file_size_bytes'">file_size_bytes</when>
            <otherwise>uploaded_at</otherwise>
        </choose>
        <choose>
            <when test="clause.direction == 'DESC'"> DESC</when>
            <otherwise> ASC</otherwise>
        </choose>
    </foreach>
</if>

<!-- ❌ 错误：即使 Java 层做了白名单，${orderBy} 也违反项目规范 -->
ORDER BY ${orderBy}
```

Java 侧 `QueryDslParser.parseSort()` 返回 `List<SortClause>`，每个 `SortClause` 的 `columnName` 来自枚举，不含用户输入。

---

### ✅ ETL Normalizer 设计原则

```java
// ✅ 纯函数，无副作用，可单元测试
public final class StatusNormalizer {
    private static final Map<String, String> MAP = Map.of(
        "待审核", "pending", "已通过", "approved", "通过", "approved", "已拒绝", "rejected",
        "pending", "pending", "approved", "approved", "rejected", "rejected"
    );
    public static String normalize(String raw) {
        if (raw == null || raw.isBlank()) return null;
        String canonical = MAP.get(raw.strip());
        if (canonical == null) throw new EtlNormalizeException("Unknown status: " + raw);
        return canonical;
    }
}
```

---

### ✅ 幂等 ETL 导入（ON CONFLICT DO UPDATE）

```xml
<insert id="upsert">
    INSERT INTO assets (source_dataset, source_id, title, uploader, uploaded_at,
        file_size_bytes, status,
        tags, city, platform, ...)
    VALUES (#{sourceDataset}, #{sourceId}, #{title}, #{uploader}, #{uploadedAt},
        #{fileSizeBytes}, #{status},
        #{tags, typeHandler=com.homework.asset.config.PgStringArrayTypeHandler},
        #{city}, #{platform}, ...)
    ON CONFLICT (source_dataset, source_id)
    DO UPDATE SET title = EXCLUDED.title, ..., ingested_at = now()
</insert>
```

---

### ✅ 集成测试：Testcontainers（真实 PG，禁止 H2）

```java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AssetControllerIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:15-alpine")
            .withDatabaseName("asset_test").withUsername("test").withPassword("test");

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

---

### ✅ 连接池配置（HikariCP）

```yaml
spring.datasource.hikari:
  maximum-pool-size: 20
  minimum-idle: 5
  connection-timeout: 30000
  pool-name: AssetHikariPool
```

---

### ✅ 安全过滤器链（Spring Security 6.x）

请求处理顺序：`RateLimitFilter → ApiKeyAuthFilter → Controller`

```java
// ✅ 正确：addFilterBefore 的第二个参数必须是 Spring Security 内置 Filter Class
// （如 UsernamePasswordAuthenticationFilter.class），不能用自定义 Filter
.addFilterBefore(rateLimitFilter, UsernamePasswordAuthenticationFilter.class)
.addFilterBefore(apiKeyAuthFilter, UsernamePasswordAuthenticationFilter.class)
```

```java
// ⚠️ OncePerRequestFilter 防重复注册：必须禁止 Spring Boot 自动注册为通用 Servlet Filter
// 否则 OncePerRequestFilter 在 Security 链中会被跳过，返回 403
@Bean
public FilterRegistrationBean<ApiKeyAuthFilter> apiKeyAuthFilterRegistration(ApiKeyAuthFilter filter) {
    FilterRegistrationBean<ApiKeyAuthFilter> registration = new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);  // 仅通过 Security 链执行，不注册为通用 Filter
    return registration;
}
// RateLimitFilter 同理，需要对应的 FilterRegistrationBean
```

**执行顺序控制**：自定义 Filter 通过实现 `Ordered` 接口的 `getOrder()` 方法排定顺序，不要依赖 `addFilterBefore` 的位置顺序。

---

## 反模式

### ⚠️ 禁止 H2 替代 PostgreSQL 做集成测试

- **原因**：H2 不支持 `text[] @>`, `JSONB`, `ON CONFLICT DO UPDATE`, `gen_random_uuid()`
- **正确做法**：Testcontainers 起真实 PG 容器

### ⚠️ 禁止 MyBatis `${}` 占位符

- **原因**：直接拼字符串，SQL 注入漏洞
- **正确做法**：所有值 `#{}`；字段名通过白名单枚举后内置到 XML `<choose>` 分支

### ⚠️ 禁止 `${orderBy}` 排序（即使有 Java 白名单）

- **原因**：违反项目规范；调用链被绕过时即注入
- **正确做法**：`List<SortClause>` + XML `<foreach>/<choose>` 硬编码列名

### ⚠️ JacksonTypeHandler + `::text[]` 不兼容

- **原因**：JSON `["a","b"]` ≠ PG 数组 `{a,b}`，cast 失败
- **正确做法**：`PgStringArrayTypeHandler`（`createArrayOf("text", ...)`）

### ⚠️ `@MappedJavaTypes` 注解不存在

- **原因**：MyBatis 中没有这个注解
- **正确做法**：`@MappedTypes(List.class)`

### ⚠️ Controller 直接注入 Mapper

- **原因**：破坏分层，绕过 Service
- **正确做法**：Controller → Service → Mapper，统计聚合放 `AssetStatsService`

### ⚠️ 禁止在 ETL Normalizer 里 eval 外部数据

- **原因**：Python list 字符串不能 eval，代码注入风险
- **正确做法**：正则提取或 Jackson JSON 解析

## 相关文档

- **项目标准**: `.claude/project_standards.md`
- **TypeHandler**: `main/backend/src/main/java/com/homework/asset/config/PgStringArrayTypeHandler.java`
- **技术设计**: `main/docs/design.md`

## 📈 合规统计（自动更新）

- **检查次数**: 513
- **违规次数**: 0
- **合规率**: 100.0%
- **最后更新**: 2026-04-28

_此章节由进化系统自动维护_

<!-- 进化: 2026-04-28 — 检查到项目新增 SecurityConfig 过滤器链模式（RateLimitFilter→ApiKeyAuthFilter with FilterRegistrationBean 防重复注册），补充到最佳实践中；零违规，推动原因是规则定期刷新 -->
