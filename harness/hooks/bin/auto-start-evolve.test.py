#!/usr/bin/env python3
"""
auto-start-evolve.py 测试文件
"""
import unittest
import os


class TestAutoStartEvolve(unittest.TestCase):
    """测试自动启动进化调度器"""

    def test_env_vars_handling(self):
        """测试环境变量处理"""
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        # 代码应该能处理这些变量为 None 的情况
        self.assertTrue(plugin_root is None or isinstance(plugin_root, str))
        self.assertTrue(project_dir is None or isinstance(project_dir, str))


if __name__ == "__main__":
    unittest.main()