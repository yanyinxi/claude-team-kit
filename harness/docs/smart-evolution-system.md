# CHK 智能进化系统 v2.0 设计文档

> 版本: v2.0
> 日期: 2026-05-03
> 状态: 已实现

---

## 一、设计思想

### 1.1 核心理念

**从"统计驱动"到"学习驱动"**

| 维度 | 改进前 (伪智能) | 改进后 (真智能) |
|------|-----------------|-----------------|
| 触发方式 | 等阈值(3-5次错误) | 每次错误都分析 |
| 学习方式 | 计数 + 参数调整 | LLM深度分析 + 知识沉淀 |
| 知识形式 | 版本号++ | 可执行规则 |
| 效果验证 | 无 | 跟踪 + 验证 |
| 闭环 | 无 | 自我优化 |

### 1.2 为什么要改？

```
问题场景：
  第1次错误 → 不分析
  第2次错误 → 不分析
  第3次错误 → 终于分析，但只是调整参数

结果：
  "越用越聪明" = "越用参数越多"
  实际上：没有理解为什么错，没有积累知识
```

### 1.3 设计目标

1. **实时学习**: 每次错误都分析，不错过任何学习机会
2. **知识沉淀**: 把经验变成可执行规则，而不是版本号
3. **效果验证**: 跟踪改进是否有效，不是改了就完事
4. **自我优化**: 无效知识自动回滚，有效知识持续强化

---

## 二、核心原理

### 2.1 闭环理论

真正的智能进化需要完整闭环：

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Error ──→ Capture ──→ Analyze ──→ Store ──→ Apply          │
│     ↑                                        │                  │
│     │                                        ↓                  │
│     └────────────── Verify ←─────────── Track                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| 步骤 | 名称 | 说明 |
|------|------|------|
| 1 | Error | 错误发生 |
| 2 | Capture | 捕获错误上下文 |
| 3 | Analyze | LLM深度根因分析 |
| 4 | Store | 知识沉淀为规则 |
| 5 | Apply | 应用知识到实际场景 |
| 6 | Verify | 验证效果 |
| 7 | Track | 跟踪成功率 |
| → | Loop | 形成闭环 |

### 2.2 知识表示

**改进前:**
```python
# 只是参数调整
threshold = 3
threshold += 1  # 3 → 4
version = "v1"
version = "v2"  # 只是版本号++
```

**改进后:**
```python
# 可执行规则
rule = {
    "id": "k001",
    "type": "pre_check",
    "description": "执行前检查权限",
    "condition": "tool == 'Bash' and 'permission' in error",
    "action": "check_permissions",
    "auto_fix": "chmod +x or request_permission",
    "confidence": 0.9,
    "status": "verified"  # 有状态管理
}
```

### 2.3 效果验证原理

```python
class EffectTracker:
    """效果跟踪器"""

    def track(self, knowledge_id, outcome):
        # outcome: success | failure | partial
        # 统计成功率

        if apply_count >= 3:
            if success_rate >= 0.8:
                status = "verified"  # 有效，保留
            elif success_rate < 0.3:
                status = "failed"    # 无效，回滚
            else:
                status = "active"    # 继续观察
```

---

## 三、系统架构

### 3.1 组件架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SmartEvolver (统一入口)                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────┐    ┌──────────────────────┐                │
│  │ SmartEvolutionEngine │    │   EffectTracker      │                │
│  ├──────────────────────┤    ├──────────────────────┤                │
│  │ • capture_error()    │    │ • track()           │                │
│  │ • analyze_with_llm() │    │ • generate_report() │                │
│  │ • store_knowledge()  │    │ • get_verified()    │                │
│  │ • apply_knowledge()  │    │ • get_failed()      │                │
│  └──────────────────────┘    └──────────────────────┘                │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                        Knowledge Base                          │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │  evolution_history.jsonl   - 进化历史                        │    │
│  │  effect_tracking.jsonl    - 效果跟踪                        │    │
│  │  effect_summary.json      - 效果摘要                        │    │
│  │  knowledge_base.json      - 知识库索引                      │    │
│  │  knowledge_base.jsonl     - 知识详情                        │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 文件结构

```
harness/evolve-daemon/
├── smart_evolution_engine.py  # 智能进化引擎 (核心)
├── effect_tracker.py           # 效果跟踪器
├── smart_evolve.py            # 统一入口
├── knowledge/                  # 知识库目录
│   ├── evolution_history.jsonl # 进化历史
│   ├── effect_tracking.jsonl  # 效果跟踪
│   ├── effect_summary.json    # 效果摘要
│   ├── knowledge_base.json    # 知识库索引
│   └── knowledge_base.jsonl   # 知识详情
├── evolve_dispatcher.py       # 原有分发器
├── analyzer.py               # 原有分析器
├── llm_decision.py           # 原有LLM决策
└── ...
```

---

## 四、详细流程

### 4.1 完整闭环流程图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│  1️⃣ ERROR (错误发生)                                                              │
│      │                                                                          │
│      │  {"error": "Permission denied", "context": "...", "tool": "Bash"}         │
│      ↓                                                                          │
│  2️⃣ CAPTURE (错误捕获)                                                           │
│      │                                                                          │
│      │  生成 error_id, 记录 timestamp                                            │
│      ↓                                                                          │
│  3️⃣ ANALYZE (LLM分析)                                                            │
│      │                                                                          │
│      │  ┌─────────────────────────────────────────────────────────┐             │
│      │  │ 调用 LLM 进行深度根因分析                              │             │
│      │  │                                                         │             │
│      │  │ 输入: 错误信息 + 上下文                                 │             │
│      │  │ 输出: {                                                 │             │
│      │  │   "root_cause": "工具缺少执行权限",                    │             │
│      │  │   "error_type": "permission",                         │             │
│      │  │   "confidence": 0.9,                                  │             │
│      │  │   "suggestion": "检查文件权限",                        │             │
│      │  │   "auto_fixable": false                              │             │
│      │  │ }                                                      │             │
│      │  └─────────────────────────────────────────────────────────┘             │
│      ↓                                                                          │
│  4️⃣ STORE (知识沉淀)                                                             │
│      │                                                                          │
│      │  ┌─────────────────────────────────────────────────────────┐             │
│      │  │ 构建可执行规则                                         │             │
│      │  │                                                         │             │
│      │  │ {                                                       │             │
│      │  │   "id": "k001",                                       │             │
│      │  │   "type": "pre_check",                                 │             │
│      │  │   "description": "执行前检查权限",                      │             │
│      │  │   "action": "check_permissions",                       │             │
│      │  │   "auto_fix": "chmod +x",                            │             │
│      │  │   "status": "pending"  ← 待验证                       │             │
│      │  │ }                                                      │             │
│      │  └─────────────────────────────────────────────────────────┘             │
│      ↓                                                                          │
│  5️⃣ APPLY (应用知识)                                                             │
│      │                                                                          │
│      │  根据规则类型执行:                                                        │
│      │  • pre_check: 执行前检查                                                 │
│      │  • config_adjust: 调整配置                                               │
│      │  • post_check: 执行后检查                                                │
│      ↓                                                                          │
│  6️⃣ VERIFY (效果验证)                                                           │
│      │                                                                          │
│      │  ┌─────────────────────────────────────────────────────────┐             │
│      │  │ 跟踪应用效果                                           │             │
│      │  │                                                         │             │
│      │  │ apply_count: 0 → 1 → 2 → 3...                         │             │
│      │  │ success_count: 0 → 1 → 2...                           │             │
│      │  │ success_rate = success_count / apply_count            │             │
│      │  │                                                         │             │
│      │  │ if apply_count >= 3:                                   │             │
│      │  │   if success_rate >= 0.8: status = "verified"          │             │
│      │  │   elif success_rate < 0.3: status = "failed"          │             │
│      │  └─────────────────────────────────────────────────────────┘             │
│      ↓                                                                          │
│  7️⃣ LOOP (持续迭代)                                                             │
│      │                                                                          │
│      │  verified → 保留，继续使用                                               │
│      │  failed → 回滚，移除无效知识                                              │
│      │  active → 继续观察，积累数据                                              │
│      ↓                                                                          │
│  🔄 回到步骤1，继续学习                                                         │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 各步骤详解

#### 步骤1: ERROR (错误发生)

```python
def capture_error(self, error_data: dict) -> dict:
    """捕获错误"""
    error_id = hashlib.md5(
        f"{error_data['error']}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:8]

    capture = {
        "id": error_id,
        "error": error_data.get("error", ""),
        "context": error_data.get("context", ""),
        "tool": error_data.get("tool", ""),
        "timestamp": datetime.now().isoformat(),
        "stage": "captured",
    }

    return capture
```

#### 步骤2: ANALYZE (LLM分析)

```python
def _build_analysis_prompt(self, error_capture: dict) -> str:
    """构建分析prompt"""
    return f"""分析以下错误：

错误: {error_capture.get('error')}
上下文: {error_capture.get('context')}
工具: {error_capture.get('tool')}

输出JSON:
{{
  "root_cause": "根本原因",
  "error_type": "syntax|logic|design|context|timeout|permission",
  "confidence": 0.0-1.0,
  "suggestion": "改进建议",
  "pattern": "错误模式",
  "auto_fixable": true/false
}}"""
```

#### 步骤3: STORE (知识沉淀)

```python
def _build_executable_rule(self, analysis: dict, rule_id: str) -> dict:
    """构建可执行规则"""
    rules_map = {
        "permission": {
            "type": "pre_check",
            "description": "执行前检查权限",
            "action": "check_permissions",
            "auto_fix": "chmod +x"
        },
        "context": {
            "type": "pre_check",
            "description": "执行前检查资源存在",
            "action": "validate_path"
        },
        "timeout": {
            "type": "config_adjust",
            "description": "增加超时配置",
            "action": "increase_timeout",
            "auto_fix": "timeout * 2"
        },
        "syntax": {
            "type": "post_check",
            "description": "语法检查",
            "action": "syntax_validate"
        },
    }

    return rules_map.get(
        analysis["analysis"].get("error_type"),
        {"type": "general", "description": "通用规则"}
    )
```

#### 步骤4: VERIFY (效果验证)

```python
def _update_summary(self, knowledge_id: str, outcome: str):
    """更新效果摘要"""
    stats = summary["knowledge_stats"][knowledge_id]
    stats["apply_count"] += 1

    if outcome == "success":
        stats["success_count"] += 1
    elif outcome == "failure":
        stats["failure_count"] += 1

    # 计算成功率
    success_rate = stats["success_count"] / stats["apply_count"]

    # 判断状态
    if stats["apply_count"] >= 3:
        if success_rate >= 0.8:
            stats["status"] = "verified"   # 有效
        elif success_rate < 0.3:
            stats["status"] = "failed"     # 回滚
        else:
            stats["status"] = "active"      # 观察
```

---

## 五、API 接口

### 5.1 SmartEvolver (主入口)

```python
class SmartEvolver:
    def evolve(self, error_data: dict, apply_rule: bool = True) -> dict:
        """执行完整进化闭环"""
        # Error → LLM分析 → 知识沉淀
        pass

    def verify(self, knowledge_id: str, outcome: str, context: dict = None):
        """验证效果"""
        pass

    def report(self):
        """生成效果报告"""
        pass

    def get_knowledge_base(self) -> dict:
        """获取知识库"""
        pass
```

### 5.2 EffectTracker (效果跟踪)

```python
class EffectTracker:
    def track(self, knowledge_id: str, outcome: str, context: dict = None):
        """跟踪效果"""
        pass

    def get_summary(self) -> dict:
        """获取效果摘要"""
        pass

    def get_all_verified(self) -> List[str]:
        """获取已验证有效的知识ID"""
        pass

    def get_all_failed(self) -> List[str]:
        """获取验证失败的知识ID"""
        pass

    def generate_report(self) -> dict:
        """生成效果报告"""
        pass
```

### 5.3 使用示例

```python
from smart_evolve import SmartEvolver

# 初始化
evolver = SmartEvolver()

# 1. 捕获错误并分析
error_data = {
    "error": "Permission denied: /path/to/file",
    "context": "执行 chmod 命令",
    "tool": "Bash"
}
result = evolver.evolve(error_data)

# 2. 验证效果
evolver.verify(result["knowledge_id"], "success")

# 3. 生成报告
evolver.report()
```

---

## 六、数据结构

### 6.1 进化历史 (evolution_history.jsonl)

```json
{
  "id": "aad5ec08",
  "error": "Permission denied: /path/to/file",
  "context": "执行 chmod 命令",
  "tool": "Bash",
  "timestamp": "2026-05-03T10:30:00.000000",
  "stage": "analyzed",
  "analysis": {
    "root_cause": "工具缺少执行权限",
    "error_type": "permission",
    "confidence": 0.9,
    "suggestion": "检查文件权限或使用 sudo",
    "auto_fixable": false
  },
  "analyzed_at": "2026-05-03T10:30:00.100000"
}
```

### 6.2 效果跟踪 (effect_tracking.jsonl)

```json
{
  "knowledge_id": "9aa01460",
  "outcome": "success",
  "context": {},
  "timestamp": "2026-05-03T10:35:00.000000"
}
```

### 6.3 效果摘要 (effect_summary.json)

```json
{
  "knowledge_stats": {
    "9aa01460": {
      "apply_count": 5,
      "success_count": 4,
      "failure_count": 1,
      "partial_count": 0,
      "success_rate": 0.8,
      "status": "verified"
    }
  },
  "updated": "2026-05-03T10:40:00.000000"
}
```

### 6.4 知识库 (knowledge_base.json)

```json
{
  "version": "1.0",
  "created": "2026-05-03T10:00:00.000000",
  "rules": [
    {
      "id": "9aa01460",
      "type": "pre_check",
      "target": "rule",
      "description": "执行前检查权限"
    }
  ],
  "patterns": ["permission_denied"],
  "solutions": [],
  "verified_effects": []
}
```

---

## 七、效果评估

### 7.1 评估指标

| 指标 | 说明 | 目标 |
|------|------|------|
| 知识数量 | 沉淀了多少条知识 | 越多越好 |
| 验证率 | verified / total | > 60% |
| 成功率 | success / apply | > 70% |
| 闭环率 | 有效 + 失败 / total | > 80% |

### 7.2 报告示例

```
╔══════════════════════════════════════════════════════════════════╗
║                  进化效果跟踪报告                              ║
╠══════════════════════════════════════════════════════════════════╣
║  📊 总体统计                                                ║
║     知识总数:        5                                      ║
║     已验证有效:      3                                      ║
║     验证失败:        1                                      ║
║     测试中:          1                                      ║
║                                                                  ║
║  📈 应用统计                                                ║
║     总应用次数:      25                                     ║
║     成功次数:        20                                     ║
║     整体成功率:      80.0%                                   ║
║                                                                  ║
║  🏆 最佳表现知识                                            ║
║     1. k001 成功率: 100.0%  应用:  5次                     ║
║     2. k002 成功率:  80.0%  应用:  5次                     ║
║     3. k003 成功率:  60.0%  应用:  5次                     ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 八、与原有系统集成

### 8.1 集成方式

```python
# 在 hooks/bin/collect_error.py 中集成

from smart_evolve import SmartEvolver

def collect_error_handler(error_data):
    evolver = SmartEvolver()

    # 1. 执行进化
    result = evolver.evolve(error_data)

    # 2. 记录知识ID供后续验证
    return {
        "success": True,
        "knowledge_id": result["knowledge_id"]
    }
```

### 8.2 兼容性

- 原有 `evolve_dispatcher.py` 保持不变
- 新增 `smart_evolution_engine.py` 提供实时分析
- 两者可以共存，逐步迁移

---

## 九、改进计划

### 9.1 已完成 ✅

- [x] 每次错误都触发分析
- [x] LLM 深度根因分析
- [x] 知识沉淀为可执行规则
- [x] 效果跟踪和验证
- [x] 状态管理 (verified/active/failed)

### 9.2 待实现

- [ ] 真实 LLM API 集成 (当前为本地模拟)
- [ ] 规则自动应用
- [ ] 回滚机制
- [ ] 多维度分析
- [ ] 知识推荐

---

## 十、总结

### 10.1 核心价值

| 维度 | 改进前 | 改进后 |
|------|--------|--------|
| 学习时机 | 错3-5次才学 | **每次都学** |
| 理解深度 | 计数 | **LLM分析** |
| 知识形式 | 版本号 | **可执行规则** |
| 效果验证 | 无 | **跟踪+验证** |
| 闭环 | 无 | **自我优化** |

### 10.2 一句话总结

> **从"统计驱动"到"学习驱动"，从"参数调整"到"知识沉淀"，让 CHK 真正越用越聪明。**

---

## 附录: 文件清单

```
harness/evolve-daemon/
├── smart_evolution_engine.py  # 智能进化引擎
├── effect_tracker.py          # 效果跟踪器
├── smart_evolve.py           # 统一入口
└── knowledge/                # 知识库目录
    ├── evolution_history.jsonl
    ├── effect_tracking.jsonl
    ├── effect_summary.json
    ├── knowledge_base.json
    └── knowledge_base.jsonl
```
