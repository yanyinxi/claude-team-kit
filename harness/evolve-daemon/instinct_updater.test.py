#!/usr/bin/env python3
"""instinct_updater 测试"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_core"))
sys.path.insert(0, str(Path(__file__).parent))

from instinct_updater import load_instinct, save_instinct


def test_load_instinct_uses_harness_path():
    """验证 load_instinct 使用 harness/memory/ 路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 创建 harness/memory/ 目录
        instinct_dir = root / "harness" / "memory"
        instinct_dir.mkdir(parents=True)

        # 写入测试数据
        test_data = {"description": "Test", "records": [{"id": "test-001"}]}
        instinct_file = instinct_dir / "instinct-record.json"
        instinct_file.write_text(json.dumps(test_data))

        # 加载
        result = load_instinct(root)

        assert result["records"][0]["id"] == "test-001"


def test_save_instinct_uses_harness_path():
    """验证 save_instinct 保存到 harness/memory/ 路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        test_data = {"description": "Test Save", "records": [{"id": "save-001"}]}
        save_instinct(test_data, root)

        # 验证文件存在于正确位置
        instinct_file = root / "harness" / "memory" / "instinct-record.json"
        assert instinct_file.exists(), f"文件应存在于 {instinct_file}"

        # 验证内容正确
        with open(instinct_file) as f:
            loaded = json.load(f)
        assert loaded["records"][0]["id"] == "save-001"


if __name__ == "__main__":
    test_load_instinct_uses_harness_path()
    test_save_instinct_uses_harness_path()
    print("所有测试通过")
