---
name: file_write_parent_directory_check
description: 文件写入前必须确保父目录存在
type: feedback
originSessionId: 0e8c0a25-9785-433c-ac68-1449b3b9332e
---
所有文件写入操作前必须确保父目录存在，否则会抛出 FileNotFoundError。

**错误代码**:
```python
metrics_file = project_root / ".claude" / "data" / "evolution_metrics.json"
metrics_file.write_text(json.dumps(metrics))  # ❌ data 目录不存在时崩溃
```

**正确代码**:
```python
metrics_file = project_root / ".claude" / "data" / "evolution_metrics.json"
metrics_file.parent.mkdir(parents=True, exist_ok=True)  # ← 确保目录存在
metrics_file.write_text(json.dumps(metrics))
```

**Why:** Python 的 write_text() 不会自动创建父目录，这是常见的新手错误，也是容易被忽视的边界情况。

**How to apply:** 任何 write_text/write_json/写文件操作前，加上 `path.parent.mkdir(parents=True, exist_ok=True)`。