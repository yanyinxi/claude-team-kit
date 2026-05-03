#!/bin/bash
# checkpoint-verify.sh - 验证 Checkpoint 文件是否完整

BACKUP_DIR=".claude/data/backups"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$PROJECT_ROOT" || exit 1

# 检查备份目录是否存在
if [ ! -d "$BACKUP_DIR" ]; then
    echo "WARN: Backup directory $BACKUP_DIR does not exist"
    exit 0
fi

# 关键文件列表
KEY_FILES=(
    "package.json"
    "CLAUDE.md"
    ".claude/settings.json"
)

missing=0
for f in "${KEY_FILES[@]}"; do
    if [ ! -f "$f" ] && [ ! -f "$BACKUP_DIR/$(basename "$f")" ]; then
        echo "WARN: Missing backup for critical file: $f"
        missing=$((missing + 1))
    fi
done

if [ $missing -gt 0 ]; then
    echo "WARN: $missing critical files missing backup"
fi

exit 0