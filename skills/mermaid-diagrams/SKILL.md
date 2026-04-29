---
name: mermaid-diagrams
description: 自动生成架构图、流程图、时序图、ER 图。用于技术文档、架构设计、API 文档、数据库设计。触发词：架构图、流程图、时序图、ER图、mermaid
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Write
context: fork
---

# Mermaid 图表技能

Mermaid 是一种基于文本的图表生成工具，通过简单的声明式语法创建各种类型的图表。本技能提供 Mermaid 图表的编写指南、最佳实践和常用示例。

## 何时使用

在以下场景中应优先使用 Mermaid 图表：

1. **技术文档编写** — 需要在 Markdown 文档中嵌入图表时，Mermaid 可与文档源码无缝集成
2. **架构设计** — 描述系统组件、模块交互和数据流向
3. **流程建模** — 展示业务流程、算法流程或用户操作流程
4. **API 文档** — 绘制请求响应时序和接口依赖关系
5. **数据库设计** — 表达实体关系和数据模型
6. **项目管理** — 创建甘特图展示项目里程碑和进度
7. **团队协作** — 通过代码版本控制图表，便于协作和审阅

## 支持的图表类型

Mermaid 支持多种图表类型，以下按使用场景分类说明。

### 流程图（Flowchart）

流程图用于展示业务流程、算法逻辑或决策路径。

```mermaid
graph TD
    A[开始] --> B{判断条件}
    B -->|是| C[处理分支1]
    B -->|否| D[处理分支2]
    C --> E[结束]
    D --> E
```

**常用布局方向**：

- `TB` — 从上到下（Top-Bottom）
- `BT` — 从下到上（Bottom-Top）
- `LR` — 从左到右（Left-Right）
- `RL` — 从右到左（Right-Left）

**常用节点形状**：

- `[ ]` — 矩形（普通节点）
- `( )` — 圆角矩形（ rounded rectangle）
- `{ }` — 菱形（判断/条件）
- `[[ ]]` — 圆柱形（数据库/存储）
- `[/ /]` 或 `[\\ \\]` — 梯形（输入/输出）

### 时序图（Sequence Diagram）

时序图用于展示对象之间的交互顺序和时间关系。

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as API网关
    participant Service as 业务服务
    participant DB as 数据库
    
    Client->>API: 发起请求
    API->>Service: 转发请求
    Service->>DB: 查询数据
    DB-->>Service: 返回结果
    Service-->>API: 返回响应
    API-->>Client: 响应结果
```

**常用语法元素**：

- `participant` — 定义参与者
- `->>` — 实线箭头（异步消息）
- `-->>` — 虚线箭头（响应）
- `activate` / `deactivate` — 激活与销毁
- `loop` — 循环区域
- `alt` / `else` — 条件分支

### 类图（Class Diagram）

类图用于展示面向对象设计中的类、接口及其关系。

```mermaid
classDiagram
    class Animal {
        +String name
        +int age
        +makeSound()
    }
    class Dog {
        +String breed
        +bark()
    }
    class Cat {
        +String color
        +meow()
    }
    
    Animal <|-- Dog
    Animal <|-- Cat
    Animal : +eat()
```

**关系类型**：

- `<|--` — 继承（Inheritance）
- `*--` — 组合（Composition）
- `o--` — 聚合（Aggregation）
- `-->` — 关联（Association）
- `--` — 实线（无箭头）
| `-->` | 依赖（Dependency） |

### 状态图（State Diagram）

状态图用于描述对象或系统的状态转换过程。

```mermaid
stateDiagram-v2
    [*] --> 待处理
    待处理 --> 处理中: 开始处理
    处理中 --> 已完成: 处理成功
    处理中 --> 失败: 处理异常
    失败 --> 待处理: 重试
    已完成 --> [*]
```

### 实体关系图（ER Diagram）

ER 图用于数据库设计，展示实体及其关系。

```mermaid
erDiagram
    USER ||--o{ ORDER : "下订单"
    ORDER ||--|{ ORDER_ITEM : "包含"
    PRODUCT ||--o{ ORDER_ITEM : "关联"
    
    USER {
        int id PK
        string username
        string email
        datetime created_at
    }
    
    ORDER {
        int id PK
        int user_id FK
        decimal total_amount
        string status
        datetime created_at
    }
    
    PRODUCT {
        int id PK
        string name
        decimal price
        int stock
    }
    
    ORDER_ITEM {
        int id PK
        int order_id FK
        int product_id FK
        int quantity
        decimal subtotal
    }
```

**关系基数表示**：

- `||` — 恰好一个（Exactly one）
- `|{` — 一个或多个（One or more）
- `o{` — 零个或多个（Zero or more）
- `||--o{` — 零个或一个到多个

### 甘特图（Gantt Chart）

甘特图用于项目计划和时间管理。

```mermaid
gantt
    title 项目开发计划
    dateFormat  YYYY-MM-DD
    section 需求分析
    需求调研       :a1, 2024-01-01, 7d
    需求评审       :after a1, 3d
    section 设计
    系统设计       :a2, after a1, 5d
    详细设计       :after a2, 7d
    section 开发
    模块开发       :a3, after a2, 14d
    单元测试       :after a3, 5d
    section 测试
    集成测试       :a4, after a3, 7d
    系统验收       :after a4, 5d
```

### 饼图（Pie Chart）

饼图用于展示数据占比和分布。

```mermaid
pie
    title 技术栈使用分布
    "Vue 3" : 45
    "React" : 30
    "Angular" : 15
    "其他" : 10
```

### 用户旅程图（User Journey）

用户旅程图用于展示用户在系统中的操作路径和体验。

```mermaid
journey
    title 用户购物流程
    section 浏览商品
      搜索商品: 5: 用户
      查看详情: 4: 用户
      加入购物车: 5: 用户
    section 下单支付
      确认订单: 4: 用户
      选择支付: 3: 用户
      完成支付: 5: 用户
    section 售后
      查看物流: 3: 用户
      确认收货: 5: 用户
      评价商品: 4: 用户
```

### Git 分支图（Git Graph）

Git 分支图用于可视化展示代码分支策略和合并历史。

```mermaid
gitGraph
    commit id: "初始提交"
    branch develop
    checkout develop
    commit id: "功能A开发"
    commit id: "功能A完成"
    checkout main
    merge develop id: "合并功能A"
    branch feature-b
    checkout feature-b
    commit id: "功能B开发1"
    commit id: "功能B开发2"
    checkout main
    merge feature-b id: "合并功能B"
```

## 使用示例

### 复杂架构图示例

以下是一个典型的微服务架构图：

```mermaid
graph TB
    subgraph 客户端层
        Web[Web应用]
        Mobile[移动应用]
    end
    
    subgraph 网关层
        Gateway[API网关]
    end
    
    subgraph 服务层
        Auth[认证服务]
        Order[订单服务]
        Product[商品服务]
        User[用户服务]
    end
    
    subgraph 数据层
        Redis[(Redis缓存)]
        MySQL[(MySQL主库)]
        MongoDB[(MongoDB)]
    end
    
    subgraph 消息队列
        Kafka[Kafka]
    end
    
    Web --> Gateway
    Mobile --> Gateway
    Gateway --> Auth
    Gateway --> Order
    Gateway --> Product
    Gateway --> User
    
    Auth --> Redis
    Auth --> MySQL
    Order --> MySQL
    Order --> Kafka
    Product --> MongoDB
    Product --> Redis
    User --> MySQL
    
    classDef primary fill:#f9f,stroke:#333,stroke-width:2px;
    classDef secondary fill:#bbf,stroke:#333,stroke-width:1px;
    classDef storage fill:#ffd,stroke:#333,stroke-width:1px;
    
    class Gateway,Auth,Order,Product,User primary;
    class Web,Mobile secondary;
    class Redis,MySQL,MongoDB,Kafka storage;
```

### API 交互时序图

```mermaid
sequenceDiagram
    autonumber
    title 用户登录流程
    
    participant U as 用户
    participant FE as 前端应用
    participant API as API网关
    participant Auth as 认证服务
    participant Cache as Redis
    participant DB as 数据库
    
    U->>FE: 输入账号密码
    FE->>API: POST /api/login
    API->>Auth: 验证请求
    Auth->>Cache: 查询验证码
    alt 验证码正确
        Cache-->>Auth: 返回验证码
        Auth->>DB: 查询用户信息
        DB-->>Auth: 返回用户数据
        Auth->>Auth: 生成JWT令牌
        Auth->>Cache: 记录登录状态
        Auth-->>API: 返回令牌
        API-->>FE: 登录成功
        FE-->>U: 跳转首页
    else 验证码错误
        Cache-->>Auth: 验证码不匹配
        Auth-->>API: 返回错误
        API-->>FE: 登录失败
        FE-->>U: 提示错误信息
    end
```

### 数据库 ER 图

```mermaid
erDiagram
    COMPANY ||--o{ DEPARTMENT : "包含"
    DEPARTMENT ||--o{ EMPLOYEE : "雇佣"
    DEPARTMENT ||--o{ PROJECT : "负责"
    EMPLOYEE ||--o{ ASSIGNMENT : "分配"
    PROJECT ||--o{ ASSIGNMENT : "包含"
    
    COMPANY {
        int company_id PK
        string name
        string industry
    }
    
    DEPARTMENT {
        int dept_id PK
        int company_id FK
        string name
        string location
    }
    
    EMPLOYEE {
        int emp_id PK
        int dept_id FK
        string name
        string email
        string position
        date hire_date
    }
    
    PROJECT {
        int project_id PK
        int dept_id FK
        string name
        date start_date
        date end_date
        string status
    }
    
    ASSIGNMENT {
        int assignment_id PK
        int emp_id FK
        int project_id FK
        string role
        int hours_allocated
    }
```

## 最佳实践

### 图表设计原则

1. **清晰优先** — 图表应以传达信息为首要目标，避免过度装饰
2. **层次分明** — 使用子图（subgraph）组织复杂图表，保持逻辑分组
3. **命名规范** — 节点和边的标签应简洁明了，使用中文或中英文结合
4. **颜色运用** — 适当使用颜色区分不同类型的内容，但不要过度使用
5. **保持简洁** — 单个图表建议控制在 20 个节点以内，超出则考虑拆分

### 代码组织建议

1. **版本控制** — 将 Mermaid 代码纳入 Git 版本控制，便于追踪变更
2. **复用定义** — 频繁使用的样式可通过 `classDef` 定义后复用
3. **模块化** — 复杂图表拆分为多个子图，通过引用关系组织
4. **注释说明** — 为复杂的图表逻辑添加注释，便于后续维护

### 渲染环境

1. **Markdown 编辑器** — 大多数现代 Markdown 编辑器支持 Mermaid 预览
2. **在线编辑器** — Mermaid Live Editor（https://mermaid.live/）提供实时预览
3. **文档工具** — Notion、Obsidian、Typora 等均支持 Mermaid
4. **代码托管** — GitHub README 和 Issues 原生支持 Mermaid 渲染
5. **前端集成** — 可通过 mermaid.js 库在网页中渲染图表

### 性能注意事项

1. **避免过度连接** — 节点间的连线应尽量简化，避免交叉混乱
2. **适当使用别名** — 节点名称过长时使用别名简化渲染
3. **分页展示** — 超大型图表考虑拆分为多个子图分页展示

## 参考资料

- **Mermaid 官方文档**：https://mermaid.js.org/
- **Mermaid Live Editor**：https://mermaid.live/
- **Mermaid GitHub 仓库**：https://github.com/mermaid-js/mermaid
- **Mermaid 语法参考**：https://mermaid.js.org/intro/syntax-reference.html
- **Mermaid 示例库**：https://mermaid.js.org/examples/

## 相关技能

- **lark-whiteboard** — 飞书画板图表绘制
- **architecture-design** — 系统架构设计
- **database-designer** — 数据库设计

---

## 进化记录

_此章节由维护者按需更新，记录从实际任务执行中学到的经验和最佳实践。_

### 2025-04-26 — 初始版本

- 创建 Mermaid 图表技能文档
- 包含 9 种图表类型的语法说明和示例
- 添加最佳实践和参考资料