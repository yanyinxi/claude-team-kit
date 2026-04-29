---
name: workflow-pause
description: |
  This skill should be used when the user says "pause", "suspend", "save progress",
  "checkpoint", or wants to stop and resume later.
user-invocable: true
---

# Pause Workflow

保存当前工作流状态为书签。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow pause "<备注>"
```