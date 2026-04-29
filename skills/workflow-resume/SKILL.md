---
name: workflow-resume
description: |
  This skill should be used when the user says "resume", "continue",
  "restore", or wants to continue from a saved checkpoint.
user-invocable: true
---

# Resume Workflow

恢复之前保存的工作流书签。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/evolution-cli.py workflow resume [bookmark-id]
```