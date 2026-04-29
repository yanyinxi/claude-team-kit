---
name: claude_code_platform_patterns
description: Claude Code 平台特性与常见陷阱
type: reference
---

## Claude Code 平台特性

### 导入机制
`.claude/` 目录会被自动添加到 `sys.path`。即使 `lib/` 没有 `__init__.py`，也可以直接使用：
```python
from lib.evolution_orchestrator import compute_priority
# 而不是 from evolution_orchestrator import
```

### Python 陷阱：三元表达式 else 返回 None

Python 三元表达式 `a if condition else b` 中，else 分支不能使用返回 None 的函数：
```python
# ❌ 错误
return shutil.copy2(f, dest) if os.path.exists(f) else self._ensure_lib(f)

# ✅ 正确
if os.path.exists(f):
    shutil.copy2(f, dest)
else:
    raise FileNotFoundError(f"Source {f} does not exist")
```

**Why:** 条件表达式必须有确定的值，不能用返回 None 的函数作为后备。
