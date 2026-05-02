#!/usr/bin/env python3
"""instinct_cli 测试"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from instinct_cli import INSTINCT_ROOT, INSTINCT_FILE


def test_instinct_paths_use_harness_prefix():
    """验证 instinct_cli 使用 harness/instinct/ 路径"""
    # INSTINCT_ROOT 应为 harness/instinct/
    expected_parent = "harness"
    assert INSTINCT_ROOT.parts[-2] == expected_parent, \
        f"INSTINCT_ROOT 应在 harness/ 下，实际: {INSTINCT_ROOT}"
    assert INSTINCT_ROOT.parts[-1] == "instinct", \
        f"INSTINCT_ROOT 应为 instinct，实际: {INSTINCT_ROOT}"
    print(f"INSTINCT_ROOT: {INSTINCT_ROOT} ✓")


def test_instinct_file_points_to_record():
    """验证 INSTINCT_FILE 指向 instinct-record.json"""
    assert INSTINCT_FILE.name == "instinct-record.json", \
        f"INSTINCT_FILE 应为 instinct-record.json，实际: {INSTINCT_FILE.name}"
    print(f"INSTINCT_FILE: {INSTINCT_FILE} ✓")


if __name__ == "__main__":
    test_instinct_paths_use_harness_prefix()
    test_instinct_file_points_to_record()
    print("所有测试通过")
