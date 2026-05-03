# 废弃 smart_evolution_engine — 方案

## 背景

`smart_evolution_engine.py` 和 `smart_evolve.py` 的功能已全部迁移到新系统：
- `integrated_evolution.py` — 会话级进化（LLM 泛化分析）
- `generalize.py` — LLM 泛化判断逻辑
- `kb_shared.py` — 共享函数库

当前只有 `smart_evolve.py` 内部引用了 `smart_evolution_engine`，daemon.py 不引用。

## 废弃范围

| 文件 | 状态 | 说明 |
|------|------|------|
| `smart_evolution_engine.py` | **废弃** | 逻辑已合并到 integrated_evolution |
| `smart_evolve.py` | **废弃** | 入口工具，已被 integrated_evolution 取代 |
| `evolution_log.jsonl` | **已不存在** | 无需处理 |

## 执行步骤

### Step 1: 确认无外部依赖 ✅

- [x] grep 全项目 `smart_evolution_engine` 或 `SmartEvolutionEngine`
- [x] 确认 daemon.py、集成进化流程均无引用
- [x] 确认测试文件（test_full_evolution.py）已更新为使用新系统

> 任务: #7 ✅ 已完成

### Step 2: 检查并迁移遗留数据 ✅

- [x] 检查两个旧文件格式：`knowledge_base.jsonl`（45条）vs `knowledge_base.json`（45条摘要）
- [x] 两个文件 ID 完全一致，合并为统一格式
- [x] 已迁移 45 条知识到新 `knowledge_base.jsonl`（添加 status/confidence/dimension/source 字段）
- [x] 原文件已备份为 `knowledge_base.json.bak`

> 任务: #8 ✅ 已完成

### Step 3: 删除废弃文件 ✅

- [x] 删除 `smart_evolution_engine.py`
- [x] 删除 `smart_evolve.py`
- [x] `test_full_evolution.py` 已更新为使用新版 `kb_shared` + `effect_tracker`
- [x] `compare_before_after.py` 已更新文件清单

> 任务: #9 ✅ 已完成

### Step 4: 验证 ✅

- [x] 运行 `npm test` → 131 passed ✅
- [x] `integrated_evolution.py` 独立运行正常
- [x] 知识库格式正确（45条，字段完整）

## Why

`smart_evolution_engine.py` 是旧架构的产物，写入独立的知识库文件，数据无人使用。新架构统一使用 `knowledge_base.jsonl`，所有进化流程共享。

## How to apply

按步骤执行，每步后验证。