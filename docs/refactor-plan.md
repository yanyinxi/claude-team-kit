# CHK 重构设计方案
## 发现问题：700+ 行重复代码，5 轮扫描后完整汇总

---

## 一、已修复的问题

### ✅ 迭代 1：`load_config()` 重复（6 个文件，~200 行）
- 新建 `evolve-daemon/_daemon_config.py` 统一配置管理
- 各模块：`from _daemon_config import load_config, _default_config`
- **状态**：✅ 全部修复

### ✅ 迭代 2：`find_root()` 重复（9 处，~18 行）
- 新建 `harness/_find_root.py` 统一路径解析
- 导出：`find_root()`, `get_project_root()`, `get_harness_root()`, `get_data_dir()`
- **状态**：✅ 全部修复

### ✅ 迭代 3：hooks `get_session_id()` 重复
- `collect_session.py` 改用 `from _session_utils import get_session_id, get_project_root`
- **状态**：✅ 已修复

### ✅ 迭代 4-5：幽灵目录根因修复
- `test_instinct_add_and_read`: patch `find_root` 而非 `Path`（lambda 无法处理 `Path.__truediv__` 的参数传递）
- `test_instinct_load_init`: 添加 `patch.object(find_root)` 防止 CWD 影响
- `test_evolve.py`: `os.environ[]` 替换 `setdefault` 强制覆盖；添加 `harness/` 到 sys.path
- `extract_semantics.py`、`evolve_dispatcher.py`、`effect_tracker.py`: 改用 `_find_root.find_root`
- **状态**：✅ 连续 3 次测试无幽灵目录

---

## 二、修复进度总览

| # | 问题 | 涉及文件 | 估计行数 | 状态 |
|---|------|---------|---------|------|
| A | sessions.jsonl 加载统一 | 8 个文件 | ~80 | ✅ 已修复 |
| B | LLM API 调用模式重复 | 4 处 | ~120 | 🔲 未修复（高风险） |
| C | classify_error_type 重复 | 2 处 | ~16 | ✅ 已修复 |
| D | stdin JSON 解析重复 | 6 个 collect_*.py | ~24 | ✅ 已修复 |
| E | 异常静默处理模式 | 7 个 hook | ~84 | 🔲 设计选择不改 |
| F | graceful_shutdown/restart 重复 | daemon.py | ~20 | ✅ 已修复 |
| G | parse_iso_time 同文件重复 | analyzer.py | ~12 | ✅ 已修复 |
| H | _path() 重复（未使用） | 3 个 evolution | ~12 | ✅ 已修复 |
| I | conftest.py 缺失 | tests/ | - | ✅ 已修复 |
| J | kb_shared.py 职责过重 | kb_shared.py | - | 🔲 低优先级 |

**完成：8/10 ✅ | 剩余：2 项（1 高风险 + 1 低优先级）**

---

## 六、额外修复（迭代过程中发现）

| 修复内容 | 文件 | 说明 |
|---------|------|------|
| `read_jsonl` 容错性 | kb_shared.py | 跳过损坏行，避免 JSONL 部分损坏导致整文件读取失败 |
| `test_evolution_triggers.py` sys.path | test_evolution_triggers.py | 添加 `os.environ["CLAUDE_PROJECT_DIR"]` + `harness/` 到 sys.path |
| 幽灵目录根因 | test_evolve.py | patch `find_root` 而非 `Path` |
| stdin 解析统一 | collect_agent/skill.py | 改用 `load_hook_context()` |
| 配置备份去重 | daemon.py | 提取 `_ensure_config_backup()` |
| conftest.py 新建 | tests/conftest.py | 新建共享 fixtures，提供 `make_session/make_correction/get_module` |

---

## 三、文件名命名问题

| 当前 | 问题 | 建议 |
|------|------|------|
| `evolve-daemon/_daemon_config.py` | 下划线私有命名但被多模块导入 | 改为 `daemon_config.py` |
| `harness/_find_root.py` | 同上 | 改为 `find_root.py` |
| `_core/config_loader.py` | 已存在同名但不同职责 | 合并或重命名 |
| `kb_shared.py` | 职责过重 | 拆分为 `llm.py` + `file_ops.py` |

---

## 四、如何避免后续犯同样的错误

### 方案 1：代码审查 Checklist（强制）

在 PR 模板中添加：
```
## 代码质量自查
- [ ] 新代码是否有 2+ 处重复的逻辑？（是 → 抽取为共享函数）
- [ ] 新函数是否和现有函数功能重叠？（是 → 复用或删除）
- [ ] 路径解析是否用了 find_root/get_project_root？（否 → 使用 _find_root.py）
- [ ] 配置加载是否用了 load_config？（否 → 使用 _daemon_config.py）
- [ ] 测试是否 patch 了 find_root 而非 Path？
```

### 方案 2：pre-commit hook（自动化检测）

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: no-getcwd-in-modules
        name: "禁止在 evolve-daemon 模块中使用 os.getcwd()"
        entry: bash -c
        args: ["grep -rn 'os.getcwd()' harness/evolve-daemon/ | grep -v test || exit 0"]
        language: system
```

### 方案 3：CLAUDE.md 规则强化

在"已知陷阱"中添加：
```
- 所有路径解析必须使用 harness/_find_root.py 的 find_root()，禁止内联定义
- 所有 evolve-daemon 配置加载必须使用 evolve-daemon/_daemon_config.py 的 load_config()
- 测试中 patch 路径解析时必须 patch find_root() 而非 Path 对象
```

---

## 五、推荐实施顺序

```
Phase 1（共享基础设施完善）
  1. sessions.jsonl 加载 → 统一到 kb_shared.load_sessions()
  2. 重命名 _daemon_config.py → daemon_config.py
  3. 重命名 _find_root.py → find_root.py
  4. 清理 kb_shared.py，拆分 LLM 调用到 llm.py

Phase 2（业务逻辑重复消除）
  5. classify_error_type → _session_utils.py
  6. stdin 解析 → _session_utils.load_hook_context()
  7. hook 异常处理 → _session_utils.run_hook_main()

Phase 3（测试基础设施）
  8. 创建 tests/conftest.py 共享 fixtures
  9. 更新 CLAUDE.md 和代码审查 checklist
```

**预期收益：消除重复代码 700+ 行，幽灵目录问题彻底解决，架构清晰可维护**
