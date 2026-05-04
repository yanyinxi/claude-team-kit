#!/usr/bin/env python3
"""
Knowledge Recommender Engine — 知识推荐引擎

基于用户任务、Skill、错误模式和 Agent 类型推荐相关知识。
与 context-injector.py 集成：在 SessionStart Hook 中被调用，
将推荐结果注入到上下文中。

推荐算法:
  1. 关键词匹配 (任务类型、工具名、文件路径)
  2. 上下文相关度计算 (语义相似度)
  3. 历史使用频率加权 (usage_count)
  4. 生命周期状态过滤 (跳过 draft 未验证的知识)

使用方式:
  python3 knowledge_recommender.py recommend --task "修复 JSON 写入错误"
  python3 knowledge_recommender.py recommend --skill testing
  python3 knowledge_recommender.py recommend --agent code-reviewer
  python3 knowledge_recommender.py recommend --failure "json encoding"
  python3 knowledge_recommender.py inject  # 仅输出推荐上下文 (供 hook 调用)
"""

import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_KEYWORD_PATTERN = re.compile(r"[a-zA-Z0-9\+\#]+")

# ── 路径配置 ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
# 知识库 1: 手工维护的知识 (harness/knowledge/)
KNOWLEDGE_DIR = PROJECT_ROOT / "harness" / "knowledge"
# 知识库 2: 进化生成的知识 (harness/knowledge/evolved/)
EVOLVE_KNOWLEDGE_DIR = PROJECT_ROOT / "harness" / "knowledge" / "evolved"
INSTINCT_DIR = PROJECT_ROOT / "harness" / "memory"
DATA_DIR = PROJECT_ROOT / ".claude" / "data"
RECOMMENDATIONS_FILE = DATA_DIR / "knowledge_recommendations.json"

# 知识目录 → 类型映射
KNOWLEDGE_SUBDIRS = {
    "decision": "decision",
    "guideline": "guideline",
    "pitfall": "pitfall",
    "process": "process",
    "model": "model",
}

# Skill → 知识类型/关键词映射表
SKILL_KNOWLEDGE_MAP = {
    "testing": ["guideline", "pitfall", "process"],
    "debugging": ["pitfall", "guideline"],
    "tdd": ["process", "guideline"],
    "security-review": ["pitfall", "guideline"],
    "security-audit": ["pitfall", "guideline"],
    "architecture-design": ["decision", "guideline"],
    "api-designer": ["decision", "guideline", "pitfall"],
    "migration": ["pitfall", "guideline", "process"],
    "database-designer": ["decision", "guideline", "pitfall"],
    "ml-engineer": ["decision", "guideline", "process"],
    "data-engineer": ["process", "guideline", "decision"],
    "sre": ["process", "pitfall"],
    "performance": ["pitfall", "guideline"],
    "mobile-dev": ["guideline", "decision"],
    "iac": ["guideline", "decision"],
    "docker-essentials": ["guideline", "pitfall"],
    "code-quality": ["guideline", "pitfall"],
    "requirement-analysis": ["process", "guideline"],
    "git-master": ["pitfall", "process"],
    "ship": ["process", "guideline"],
    "review": ["guideline", "pitfall"],
}

# Agent 类型 → 优先知识类型
AGENT_KNOWLEDGE_PRIORITY = {
    "code-reviewer": ["pitfall", "guideline", "process"],
    "security-auditor": ["pitfall", "guideline", "decision"],
    "architect": ["decision", "guideline"],
    "planner": ["process", "guideline"],
    "qa-tester": ["pitfall", "process", "guideline"],
    "debugger": ["pitfall", "guideline"],
    "database-dev": ["decision", "pitfall", "guideline"],
    "backend-dev": ["guideline", "pitfall", "decision"],
    "frontend-dev": ["guideline", "pitfall"],
    "ml-engineer": ["decision", "guideline", "process"],
    "devops": ["process", "guideline", "pitfall"],
    "tester": ["pitfall", "guideline", "process"],
}

# 常见错误模式关键词 → 知识匹配
ERROR_PATTERNS = {
    "json": "pitfall",
    "encoding": "pitfall",
    "utf-8": "pitfall",
    "unicode": "pitfall",
    "import": "pitfall",
    "path": "pitfall",
    "permission": "pitfall",
    "auth": "pitfall",
    "sql": "pitfall",
    "injection": "pitfall",
    "memory": "pitfall",
    "performance": "pitfall",
    "timeout": "pitfall",
    "race": "pitfall",
    "deadlock": "pitfall",
    "null": "pitfall",
    "undefined": "pitfall",
    "async": "pitfall",
    "promise": "pitfall",
    "concurrency": "pitfall",
}


# ── 知识库加载 ────────────────────────────────────────────────────────────────

def load_evolved_knowledge() -> list[dict]:
    """加载进化知识库 (JSONL 格式)"""
    entries = []
    kb_file = EVOLVE_KNOWLEDGE_DIR / "knowledge_base.jsonl"
    if not kb_file.exists():
        return entries

    try:
        lines = kb_file.read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                # 标准化格式
                analysis = data.get("analysis", {})
                rule = data.get("rule", {})
                entry = {
                    "id": data.get("id", ""),
                    "name": analysis.get("suggestion", analysis.get("root_cause", ""))[:50],
                    "description": analysis.get("root_cause", ""),
                    "type": analysis.get("knowledge_type", "pitfall"),
                    "maturity": "verified" if data.get("success_count", 0) > 0 else "draft",
                    "usage_count": data.get("apply_count", 0),
                    "_source_type": "evolved",
                    "_source_file": "harness/knowledge/evolved/knowledge_base.jsonl",
                    "content": {
                        "pattern": analysis.get("pattern", ""),
                        "suggestion": analysis.get("suggestion", ""),
                        "confidence": analysis.get("confidence", 0),
                        "auto_fixable": analysis.get("auto_fixable", False),
                        "risk_level": analysis.get("risk_level", "low"),
                    },
                    "error_type": analysis.get("error_type", ""),
                    "trigger": rule.get("trigger", ""),
                    "action": rule.get("action", ""),
                }
                entries.append(entry)
            except (json.JSONDecodeError, OSError, KeyError):
                continue
    except (OSError, json.JSONDecodeError):
        pass
    return entries


def load_knowledge_base() -> list[dict]:
    """加载所有知识条目（双知识库合并）

    知识库 1: harness/knowledge/ — 手工维护的专家知识
    知识库 2: harness/knowledge/evolved/ — 进化系统生成的知识
    """
    entries = []

    # 知识库 1: 手工维护的 JSON 文件
    if KNOWLEDGE_DIR.exists():
        for subdir, ktype in KNOWLEDGE_SUBDIRS.items():
            subdir_path = KNOWLEDGE_DIR / subdir
            if not subdir_path.exists():
                continue
            for f in subdir_path.rglob("*.json"):
                if f.name == "INDEX.md":
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    data["_source_file"] = str(f.relative_to(KNOWLEDGE_DIR))
                    data["_type"] = ktype
                    data["_source_type"] = "manual"
                    entries.append(data)
                except (json.JSONDecodeError, OSError):
                    continue

    # 知识库 2: 进化生成的 JSONL
    entries.extend(load_evolved_knowledge())

    return entries


def load_instinct_usage() -> dict[str, int]:
    """从 instinct 数据读取历史使用频率"""
    usage = {}
    instinct_file = INSTINCT_DIR / "instinct-record.json"
    if instinct_file.exists():
        try:
            data = json.loads(instinct_file.read_text(encoding="utf-8"))
            # 支持 { "records": [...] } 或直接的 [...]
            records = data.get("records", data) if isinstance(data, dict) else data
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                key = rec.get("skill") or rec.get("agent") or rec.get("domain") or rec.get("pattern", "")
                if key:
                    usage[key] = usage.get(key, 0) + 1
        except (json.JSONDecodeError, OSError):
            pass
    return usage


# ── 推荐算法核心 ──────────────────────────────────────────────────────────────

def extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词（过滤停用词）"""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "and", "or", "but", "if",
        "not", "no", "so", "than", "then", "also", "it", "this", "that",
        "i", "you", "we", "he", "she", "they", "what", "which", "who",
        "how", "when", "where", "why", "all", "each", "every", "both",
        "few", "more", "most", "other", "some", "such", "only", "own",
        "same", "just", "my", "your", "our", "their", "its", "any", "one",
        "two", "three", "new", "old", "use", "used", "using", "file", "files",
    }
    # 提取字母和数字组合
    tokens = _KEYWORD_PATTERN.findall(text.lower())
    return {t for t in tokens if len(t) >= 2 and t not in stop_words}


def compute_score(entry: dict, keywords: set[str], usage_weight: float) -> float:
    """计算单条知识的推荐分数"""
    content_text = json.dumps(entry.get("content", {}), ensure_ascii=False).lower()
    name_text = entry.get("name", "").lower()
    desc_text = entry.get("description", "").lower()

    # 1. 关键词命中 (名称权重更高)
    name_kw = extract_keywords(name_text)
    desc_kw = extract_keywords(desc_text)
    content_kw = extract_keywords(content_text)

    name_hits = len(keywords & name_kw)
    desc_hits = len(keywords & desc_kw)
    content_hits = len(keywords & content_kw)

    # 加权: 名称 3x, 描述 2x, 内容 1x
    keyword_score = name_hits * 3.0 + desc_hits * 2.0 + content_hits * 1.0

    # 2. 历史使用频率加权 (log 平滑)
    usage_count = entry.get("usage_count", 0)
    usage_score = math.log1p(usage_count) * 0.5

    # 3. 成熟度奖励
    maturity = entry.get("maturity", "draft")
    maturity_score = {"proven": 2.0, "verified": 1.0, "draft": 0.0}.get(maturity, 0.0)

    # 4. 外部传入的使用加权 (来自 instinct)
    external_weight = usage_weight

    return keyword_score + usage_score + maturity_score + external_weight


def filter_lifecycle(entries: list[dict], allow_draft: bool = False) -> list[dict]:
    """过滤掉 lifecycle 为 draft 的条目（除非显式允许）"""
    if allow_draft:
        return entries
    return [e for e in entries if e.get("maturity", "draft") != "draft"]


def recommend(
    entries: list[dict],
    keywords: set[str],
    target_types: Optional[list[str]] = None,
    usage_weight: float = 0.0,
    top_n: int = 5,
) -> list[dict]:
    """通用推荐：按关键词 + 类型过滤 + 排序"""
    candidates = entries
    if target_types:
        candidates = [e for e in candidates if e.get("_type") in target_types]

    scored = []
    for entry in candidates:
        score = compute_score(entry, keywords, usage_weight)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, entry in scored[:top_n]:
        results.append({
            "id": entry.get("id", entry.get("_source_file", "unknown")),
            "name": entry.get("name", ""),
            "type": entry.get("_type", entry.get("type", "")),
            "description": entry.get("description", ""),
            "score": round(score, 2),
            "maturity": entry.get("maturity", "unknown"),
            "source": entry.get("_source_file", ""),
            "source_type": entry.get("_source_type", "unknown"),  # manual 或 evolved
            "usage_count": entry.get("usage_count", 0),
            "content_preview": _preview_content(entry.get("content", {})),
        })
    return results


def _preview_content(content: dict) -> str:
    """生成内容摘要（取前 120 字符）"""
    if isinstance(content, str):
        return content[:120]
    if isinstance(content, list):
        items = content[:3]
        text = "; ".join(str(i) for i in items)
        return text[:120]
    if isinstance(content, dict):
        # 取第一个有意义的字段
        for key in ["recommend", "steps", "problem", "decision", "schema"]:
            if key in content:
                val = content[key]
                if isinstance(val, list):
                    text = "; ".join(str(i) for i in val[:3])
                else:
                    text = str(val)
                return text[:120]
        text = json.dumps(content, ensure_ascii=False)[:120]
        return text
    return str(content)[:120]


# ── 场景化推荐接口 ────────────────────────────────────────────────────────────

def recommend_by_task(task: str) -> list[dict]:
    """基于任务描述推荐知识"""
    entries = load_knowledge_base()
    keywords = extract_keywords(task)
    return recommend(entries, keywords, top_n=5)


def recommend_by_skill(skill_name: str) -> list[dict]:
    """基于当前 Skill 推荐相关知识"""
    entries = load_knowledge_base()
    keywords = extract_keywords(skill_name)
    target_types = SKILL_KNOWLEDGE_MAP.get(skill_name.lower(), ["guideline", "pitfall"])
    usage_weight = 0.0
    instinct_usage = load_instinct_usage()
    usage_weight = math.log1p(instinct_usage.get(skill_name, 0)) * 0.5
    return recommend(entries, keywords, target_types=target_types, usage_weight=usage_weight, top_n=4)


def recommend_by_failure(failure_text: str) -> list[dict]:
    """基于错误/失败模式推荐 pitfall 知识"""
    entries = load_knowledge_base()
    keywords = extract_keywords(failure_text)

    # 错误模式优先匹配 pitfall
    target_types = ["pitfall"]
    for pattern, ktype in ERROR_PATTERNS.items():
        if pattern in failure_text.lower():
            target_types = [ktype]
            break

    return recommend(entries, keywords, target_types=target_types, top_n=4)


def recommend_by_agent(agent_type: str) -> list[dict]:
    """基于当前 Agent 类型推荐相关指导"""
    entries = load_knowledge_base()
    keywords = extract_keywords(agent_type)
    target_types = AGENT_KNOWLEDGE_PRIORITY.get(agent_type.lower(), ["guideline", "pitfall"])

    instinct_usage = load_instinct_usage()
    usage_weight = math.log1p(instinct_usage.get(agent_type, 0)) * 0.5

    return recommend(entries, keywords, target_types=target_types, usage_weight=usage_weight, top_n=4)


# ── 聚合推荐 + 存储 ────────────────────────────────────────────────────────────

def generate_recommendations(
    task: Optional[str] = None,
    skill: Optional[str] = None,
    agent: Optional[str] = None,
    failure: Optional[str] = None,
) -> dict:
    """聚合所有场景的推荐，生成完整推荐报告"""
    result = {
        "generated_at": datetime.now().isoformat(),
        "input": {
            "task": task,
            "skill": skill,
            "agent": agent,
            "failure": failure,
        },
        "recommendations": {},
    }

    if task:
        result["recommendations"]["task_based"] = recommend_by_task(task)
    if skill:
        result["recommendations"]["skill_based"] = recommend_by_skill(skill)
    if agent:
        result["recommendations"]["agent_based"] = recommend_by_agent(agent)
    if failure:
        result["recommendations"]["failure_based"] = recommend_by_failure(failure)

    # 合并去重：综合推荐
    all_recs = []
    for recs in result["recommendations"].values():
        all_recs.extend(recs)
    # 按分数去重（id 相同的保留最高分）
    seen = {}
    for rec in all_recs:
        key = rec["id"]
        if key not in seen or rec["score"] > seen[key]["score"]:
            seen[key] = rec
    merged = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:6]
    result["recommendations"]["merged"] = merged

    return result


def save_recommendations(data: dict):
    """保存推荐结果到 JSON 文件"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECOMMENDATIONS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ── CLI & Hook 集成 ────────────────────────────────────────────────────────────

def format_as_context(recs: list[dict], title: str) -> str:
    """将推荐结果格式化为可注入上下文的 Markdown"""
    if not recs:
        return ""
    lines = [f"\n### {title}\n"]
    for rec in recs:
        type_icon = {"pitfall": "⚠️", "guideline": "📋", "process": "📌",
                     "decision": "🏗️", "model": "📐"}.get(rec.get("type", ""), "📄")
        lines.append(
            f"- [{type_icon} {rec['name']}]({rec['source']}) "
            f"| {rec['description'][:80]}"
        )
        if rec.get("content_preview"):
            lines.append(f"  > {rec['content_preview'][:100]}")
    return "\n".join(lines)


def cmd_recommend(args: list[str]):
    """recommend 子命令"""
    task = None
    skill = None
    agent = None
    failure = None

    i = 0
    while i < len(args):
        if args[i] == "--task" and i + 1 < len(args):
            task = args[i + 1]
            i += 2
        elif args[i] == "--skill" and i + 1 < len(args):
            skill = args[i + 1]
            i += 2
        elif args[i] == "--agent" and i + 1 < len(args):
            agent = args[i + 1]
            i += 2
        elif args[i] == "--failure" and i + 1 < len(args):
            failure = args[i + 1]
            i += 2
        else:
            i += 1

    result = generate_recommendations(task=task, skill=skill, agent=agent, failure=failure)
    save_recommendations(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_inject():
    """
    inject 子命令 — 输出推荐上下文（供 SessionStart Hook 调用）。
    读取上次推荐结果，格式化为 Markdown 注入。
    """
    if RECOMMENDATIONS_FILE.exists():
        try:
            data = json.loads(RECOMMENDATIONS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
    else:
        data = None

    if data and data.get("recommendations"):
        recs = data["recommendations"].get("merged", [])
        if recs:
            print("# Knowledge Recommendations\n")
            print(format_as_context(recs, "Recommended Knowledge"))
    else:
        print("# Knowledge Recommendations\n")
        print("_No recommendations yet. Trigger via `--task`, `--skill`, `--agent`, or `--failure`._")


def cmd_status():
    """status 子命令 — 输出推荐引擎状态"""
    entries = load_knowledge_base()
    instinct_usage = load_instinct_usage()
    stats = {
        "total_entries": len(entries),
        "by_type": {},
        "by_maturity": {"proven": 0, "verified": 0, "draft": 0},
        "instinct_records": len(instinct_usage),
        "last_recommendation": None,
    }
    for e in entries:
        t = e.get("_type", "unknown")
        m = e.get("maturity", "draft")
        stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
        stats["by_maturity"][m] = stats["by_maturity"].get(m, 0) + 1

    if RECOMMENDATIONS_FILE.exists():
        mtime = RECOMMENDATIONS_FILE.stat().st_mtime
        stats["last_recommendation"] = datetime.fromtimestamp(mtime).isoformat()

    print(json.dumps(stats, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 2:
        print("用法: knowledge_recommender.py <command> [options]")
        print("  recommend --task TEXT [--skill SKILL] [--agent AGENT] [--failure TEXT]")
        print("  inject   — 输出推荐上下文（供 SessionStart Hook 调用）")
        print("  status   — 输出推荐引擎状态")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "recommend":
        cmd_recommend(sys.argv[2:])
    elif cmd == "inject":
        cmd_inject()
    elif cmd == "status":
        cmd_status()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()