#!/usr/bin/env python3
"""Knowledge 模块测试套件

测试:
- knowledge_recommender.py: 知识推荐引擎
- lifecycle.py: 知识生命周期管理
- paths.py: 全局路径配置服务
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 测试 fixtures
# ─────────────────────────────────────────────────────────────────────────────

# 获取 harness 目录路径
HARNESS_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(HARNESS_DIR))

@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目结构"""
    # 项目根
    (tmp_path / "CLAUDE.md").write_text("# Test Project\n")
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "data").mkdir(parents=True)

    # 知识库目录结构
    knowledge_dir = tmp_path / "harness" / "knowledge"
    for subdir in ["decision", "guideline", "pitfall", "process", "model"]:
        (knowledge_dir / subdir).mkdir(parents=True)

    # 进化知识目录 (新路径)
    evolve_dir = tmp_path / "harness" / "knowledge" / "evolved"
    evolve_dir.mkdir(parents=True)

    # 本能记录目录
    instinct_dir = tmp_path / "harness" / "memory"
    instinct_dir.mkdir(parents=True)

    return tmp_path


@pytest.fixture
def mock_knowledge_base(temp_project):
    """创建模拟知识库数据"""
    knowledge_dir = temp_project / "harness" / "knowledge"

    # pitfall 示例
    (knowledge_dir / "pitfall" / "json_encoding.json").write_text(json.dumps({
        "id": "pitfall-json-001",
        "name": "JSON Encoding Error",
        "description": "JSON 序列化时遇到非 UTF-8 字符导致失败",
        "type": "pitfall",
        "maturity": "verified",
        "usage_count": 5,
        "content": {
            "problem": "UnicodeEncodeError when dumping JSON",
            "solution": "Use ensure_ascii=False"
        }
    }))

    # guideline 示例
    (knowledge_dir / "guideline" / "git_commit.json").write_text(json.dumps({
        "id": "guideline-git-001",
        "name": "Git Commit Style Guide",
        "description": "使用 conventional commits 格式",
        "type": "guideline",
        "maturity": "proven",
        "usage_count": 10,
        "content": {"format": "type(scope): message"}
    }))

    # process 示例
    (knowledge_dir / "process" / "tdd_flow.json").write_text(json.dumps({
        "id": "process-tdd-001",
        "name": "TDD Workflow",
        "description": "测试驱动开发流程",
        "type": "process",
        "maturity": "verified",
        "usage_count": 3,
        "content": {"steps": ["red", "green", "refactor"]}
    }))

    return knowledge_dir


@pytest.fixture
def mock_evolved_knowledge(temp_project):
    """创建模拟进化知识数据"""
    evolve_dir = temp_project / "harness" / "knowledge" / "evolved"
    kb_file = evolve_dir / "knowledge_base.jsonl"

    # JSONL 格式
    lines = [
        json.dumps({
            "id": "evolved-001",
            "analysis": {
                "pattern": "async/await in loop",
                "root_cause": "在 for 循环中使用 await 导致顺序执行",
                "suggestion": "使用 Promise.all 或 asyncio.gather",
                "knowledge_type": "pitfall",
                "confidence": 0.85,
                "auto_fixable": False,
                "risk_level": "medium"
            },
            "rule": {
                "trigger": "for+await",
                "action": "parallelize"
            },
            "success_count": 3,
            "apply_count": 5
        }),
        json.dumps({
            "id": "evolved-002",
            "analysis": {
                "pattern": "null check missing",
                "root_cause": "未检查 null/undefined 导致运行时错误",
                "suggestion": "使用可选链和空值合并",
                "knowledge_type": "pitfall",
                "confidence": 0.92,
                "auto_fixable": True,
                "risk_level": "high"
            },
            "rule": {
                "trigger": "access property",
                "action": "optional chaining"
            },
            "success_count": 8,
            "apply_count": 12
        })
    ]
    kb_file.write_text("\n".join(lines), encoding="utf-8")
    return evolve_dir


@pytest.fixture
def mock_instinct_record(temp_project):
    """创建模拟本能记录"""
    instinct_file = temp_project / "harness" / "memory" / "instinct-record.json"
    instinct_file.write_text(json.dumps({
        "records": [
            {"skill": "testing", "timestamp": "2024-01-01T00:00:00"},
            {"skill": "testing", "timestamp": "2024-01-02T00:00:00"},
            {"agent": "code-reviewer", "timestamp": "2024-01-01T00:00:00"},
            {"domain": "security", "timestamp": "2024-01-01T00:00:00"},
        ]
    }), encoding="utf-8")
    return instinct_file


# ─────────────────────────────────────────────────────────────────────────────
# knowledge_recommender.py 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeRecommender:
    """知识推荐引擎测试"""

    def test_recommend_by_task(self, temp_project, mock_knowledge_base, mock_instinct_record):
        """测试任务推荐功能"""
        # 设置环境变量
        os.environ["CLAUDE_PROJECT_DIR"] = str(temp_project)

        try:
            from knowledge.knowledge_recommender import recommend_by_task, load_knowledge_base

            # 执行任务推荐
            results = recommend_by_task("修复 JSON 写入错误")

            # 验证结果
            assert isinstance(results, list), "应返回列表"
            if results:
                # 验证返回结构
                for rec in results:
                    assert "id" in rec, "应有 id 字段"
                    assert "name" in rec, "应有 name 字段"
                    assert "type" in rec, "应有 type 字段"
                    assert "score" in rec, "应有 score 字段"

            # 验证知识库加载
            entries = load_knowledge_base()
            assert len(entries) >= 3, "应加载至少3条知识"
        finally:
            if "CLAUDE_PROJECT_DIR" in os.environ:
                del os.environ["CLAUDE_PROJECT_DIR"]

    def test_recommend_by_skill(self, temp_project, mock_knowledge_base, mock_instinct_record):
        """测试 Skill 推荐功能"""
        os.environ["CLAUDE_PROJECT_DIR"] = str(temp_project)

        try:
            from knowledge.knowledge_recommender import recommend_by_skill

            # 测试 testing skill 推荐
            results = recommend_by_skill("testing")

            assert isinstance(results, list), "应返回列表"
            # 验证知识类型过滤
            if results:
                # testing skill 应优先返回 guideline, pitfall, process 类型
                for rec in results:
                    assert rec["type"] in ["guideline", "pitfall", "process"], \
                        f"类型应为 guideline/pitfall/process，实际: {rec['type']}"
        finally:
            if "CLAUDE_PROJECT_DIR" in os.environ:
                del os.environ["CLAUDE_PROJECT_DIR"]

    def test_recommend_by_failure(self, temp_project, mock_knowledge_base):
        """测试错误模式推荐功能"""
        os.environ["CLAUDE_PROJECT_DIR"] = str(temp_project)

        try:
            from knowledge.knowledge_recommender import recommend_by_failure

            # 测试 json 错误模式
            results = recommend_by_failure("json encoding error")

            assert isinstance(results, list), "应返回列表"
            # json 错误应优先匹配 pitfall 类型
            if results:
                assert results[0]["type"] == "pitfall", "json 错误应匹配 pitfall 类型"
        finally:
            if "CLAUDE_PROJECT_DIR" in os.environ:
                del os.environ["CLAUDE_PROJECT_DIR"]

    def test_recommend_by_agent(self, temp_project, mock_knowledge_base, mock_instinct_record):
        """测试 Agent 推荐功能"""
        os.environ["CLAUDE_PROJECT_DIR"] = str(temp_project)

        try:
            from knowledge.knowledge_recommender import recommend_by_agent

            # 测试 code-reviewer agent 推荐
            results = recommend_by_agent("code-reviewer")

            assert isinstance(results, list), "应返回列表"
            # code-reviewer 应优先返回 pitfall 类型
            if results:
                assert results[0]["type"] in ["pitfall", "guideline", "process"], \
                    f"类型应为 pitfall/guideline/process，实际: {results[0]['type']}"
        finally:
            if "CLAUDE_PROJECT_DIR" in os.environ:
                del os.environ["CLAUDE_PROJECT_DIR"]

    def test_load_evolved_knowledge(self, temp_project, mock_evolved_knowledge):
        """测试进化知识加载功能"""
        os.environ["CLAUDE_PROJECT_DIR"] = str(temp_project)

        try:
            import sys
            import importlib
            sys.path.insert(0, str(temp_project / "harness"))

            # 强制重新加载模块以使用新的 PROJECT_ROOT
            if "knowledge.knowledge_recommender" in sys.modules:
                del sys.modules["knowledge.knowledge_recommender"]

            from knowledge.knowledge_recommender import load_evolved_knowledge

            entries = load_evolved_knowledge()

            assert isinstance(entries, list), "应返回列表"
            assert len(entries) == 2, f"应加载2条进化知识，实际: {len(entries)}"

            # 验证条目结构
            for entry in entries:
                assert "id" in entry, "应有 id 字段"
                assert "name" in entry, "应有 name 字段"
                assert "maturity" in entry, "应有 maturity 字段"
                assert entry["_source_type"] == "evolved", "来源类型应为 evolved"
                assert "content" in entry, "应有 content 字段"

            # 验证成熟度判断 (success_count > 0 -> verified)
            assert entries[0]["maturity"] == "verified", "有成功记录的应为 verified"
        finally:
            if "CLAUDE_PROJECT_DIR" in os.environ:
                del os.environ["CLAUDE_PROJECT_DIR"]

    def test_merge_recommendations(self, temp_project, mock_knowledge_base, mock_instinct_record):
        """测试推荐合并去重功能"""
        os.environ["CLAUDE_PROJECT_DIR"] = str(temp_project)

        try:
            from knowledge.knowledge_recommender import generate_recommendations

            # 生成多场景推荐
            result = generate_recommendations(
                task="测试驱动开发流程",
                skill="testing",
                agent="code-reviewer"
            )

            assert "recommendations" in result, "应有 recommendations 字段"
            assert "merged" in result["recommendations"], "应有 merged 字段"

            # 验证去重: merged 中不应有重复 id
            merged = result["recommendations"]["merged"]
            ids = [rec["id"] for rec in merged]
            assert len(ids) == len(set(ids)), "merged 中不应有重复 id"

            # 验证按分数排序
            if len(merged) > 1:
                scores = [rec["score"] for rec in merged]
                assert scores == sorted(scores, reverse=True), "应按分数降序排列"

        finally:
            if "CLAUDE_PROJECT_DIR" in os.environ:
                del os.environ["CLAUDE_PROJECT_DIR"]


# ─────────────────────────────────────────────────────────────────────────────
# lifecycle.py 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycle:
    """知识生命周期管理测试"""

    def test_lifecycle_promote(self):
        """测试升级逻辑"""
        from knowledge.lifecycle import check_maturity_promotion, load_lifecycle_config

        config = load_lifecycle_config()

        # draft -> verified: usage_count >= 1
        entry_draft = {"maturity": "draft", "usage_count": 1, "project_count": 0}
        result = check_maturity_promotion(entry_draft, config)
        assert result == "verified", f"draft+usage>=1 应升级为 verified，实际: {result}"

        # verified -> proven: project_count >= 2
        entry_verified = {"maturity": "verified", "usage_count": 5, "project_count": 2}
        result = check_maturity_promotion(entry_verified, config)
        assert result == "proven", f"verified+project>=2 应升级为 proven，实际: {result}"

        # 条件不满足时不升级
        entry_no_promote = {"maturity": "draft", "usage_count": 0, "project_count": 0}
        result = check_maturity_promotion(entry_no_promote, config)
        assert result is None, "不满足条件时应返回 None"

        # proven 最高级不再升级
        entry_top = {"maturity": "proven", "usage_count": 100, "project_count": 10}
        result = check_maturity_promotion(entry_top, config)
        assert result is None, "proven 最高级应返回 None"

    def test_lifecycle_demote(self):
        """测试降级逻辑"""
        from knowledge.lifecycle import check_maturity_promotion

        # 测试不满足升级条件时返回 None
        entry = {"maturity": "draft", "usage_count": 0, "project_count": 0}
        config = {
            "maturity": {
                "levels": ["draft", "verified", "proven"],
                "promotion": {
                    "draft_to_verified": {"condition": "usage_count >= 1"},
                    "verified_to_proven": {"condition": "project_count >= 2"},
                }
            }
        }
        result = check_maturity_promotion(entry, config)
        assert result is None, "不满足升级条件应返回 None"

    def test_decay(self):
        """测试衰减逻辑"""
        from knowledge.lifecycle import apply_decay, load_lifecycle_config

        config = load_lifecycle_config()
        now = datetime.now()

        # proven 超过 12 个月未使用 -> verified
        entry_proven_old = {
            "maturity": "proven",
            "last_used_at": (now - timedelta(days=400)).isoformat()
        }
        result = apply_decay(entry_proven_old, config)
        assert result == "verified", f"proven 12个月未用应降为 verified，实际: {result}"

        # verified 超过 6 个月未使用 -> draft
        entry_verified_old = {
            "maturity": "verified",
            "last_used_at": (now - timedelta(days=200)).isoformat()
        }
        result = apply_decay(entry_verified_old, config)
        assert result == "draft", f"verified 6个月未用应降为 draft，实际: {result}"

        # 未超阈值时不衰减
        entry_fresh = {
            "maturity": "proven",
            "last_used_at": (now - timedelta(days=30)).isoformat()
        }
        result = apply_decay(entry_fresh, config)
        assert result is None, "未超阈值应返回 None"

        # 无 last_used_at 时不衰减
        entry_no_time = {"maturity": "proven"}
        result = apply_decay(entry_no_time, config)
        assert result is None, "无时间戳应返回 None"


# ─────────────────────────────────────────────────────────────────────────────
# paths.py 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestPaths:
    """全局路径配置测试"""

    def test_project_root(self, temp_project):
        """测试项目根路径"""
        from paths import ROOT

        # 验证路径指向正确（ROOT 应该指向 harness 的父目录，即项目根）
        assert ROOT.exists(), "ROOT 应存在"
        assert ROOT.name != "harness", "ROOT 应该是 harness 的父目录"

    def test_data_dir(self, temp_project):
        """测试数据目录"""
        from paths import DATA_DIR, CLAUDE_DIR

        # 验证目录结构
        assert DATA_DIR.name == "data", "DATA_DIR 应为 data"
        assert CLAUDE_DIR.name == ".claude", "CLAUDE_DIR 应为 .claude"
        assert DATA_DIR.parent == CLAUDE_DIR, "DATA_DIR 应在 CLAUDE_DIR 下"

    def test_validate_paths(self, temp_project):
        """测试路径验证"""
        from paths import (
            ROOT, PLUGIN_ROOT, SKILLS_DIR,
            AGENTS_DIR, RULES_DIR, HOOKS_DIR, KNOWLEDGE_DIR,
            TESTS_DIR
        )

        # 验证关键路径存在且为目录
        paths_to_check = [
            ("ROOT", ROOT),
            ("PLUGIN_ROOT", PLUGIN_ROOT),
            ("SKILLS_DIR", SKILLS_DIR),
            ("AGENTS_DIR", AGENTS_DIR),
            ("RULES_DIR", RULES_DIR),
            ("HOOKS_DIR", HOOKS_DIR),
            ("KNOWLEDGE_DIR", KNOWLEDGE_DIR),
            ("TESTS_DIR", TESTS_DIR),
        ]

        for name, path in paths_to_check:
            assert path.exists(), f"{name} ({path}) 应存在"
            assert path.is_dir(), f"{name} ({path}) 应为目录"

    def test_path_constants(self):
        """测试路径常量定义"""
        from paths import (
            DIR_CLAUDE, DIR_DATA, DIR_SKILLS, DIR_AGENTS,
            FILE_SESSIONS, FILE_ERRORS,
            ANTHROPIC_API_URL
        )

        # 验证常量类型和值
        assert isinstance(DIR_CLAUDE, str), "DIR_CLAUDE 应为字符串"
        assert DIR_CLAUDE == ".claude", f"DIR_CLAUDE 应为 .claude，实际: {DIR_CLAUDE}"

        assert isinstance(DIR_SKILLS, str), "DIR_SKILLS 应为字符串"
        assert DIR_SKILLS == "skills", f"DIR_SKILLS 应为 skills，实际: {DIR_SKILLS}"

        assert isinstance(FILE_SESSIONS, str), "FILE_SESSIONS 应为字符串"
        assert FILE_SESSIONS == "sessions.jsonl", f"FILE_SESSIONS 应为 sessions.jsonl"

        assert isinstance(ANTHROPIC_API_URL, str), "ANTHROPIC_API_URL 应为字符串"
        assert ANTHROPIC_API_URL.startswith("https://"), "应为 HTTPS URL"

    def test_hooks_scripts(self):
        """测试 Hook 脚本映射"""
        from paths import HOOK_SCRIPTS

        assert isinstance(HOOK_SCRIPTS, dict), "HOOK_SCRIPTS 应为字典"
        assert len(HOOK_SCRIPTS) > 0, "HOOK_SCRIPTS 不应为空"

        # 验证关键 hook 存在
        expected_hooks = [
            "safety-check.sh",
            "quality-gate.sh",
            "tdd-check.sh",
            "rate-limiter.sh",
            "context-injector.py",
        ]
        for hook in expected_hooks:
            assert hook in HOOK_SCRIPTS, f"{hook} 应在 HOOK_SCRIPTS 中"


# ─────────────────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])