#!/usr/bin/env python3
# similarity-scorer.py — Skill 相似度评分工具
# 用于 skill-factory：判断新 Skill 应创建、合并还是跳过
# 阈值：>=0.8 SKIP / 0.6-0.8 MERGE / <0.3 CREATE
# 依赖：仅 stdlib（json/re/re/sys）

import json
import re
import sys
import os
from typing import Any


def tokenize(text: str) -> set:
    """将文本分词为小写集合"""
    if not text:
        return set()
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return set(tokens)


def jaccard(a: set, b: set) -> float:
    """Jaccard 相似度：|A∩B| / |A∪B|"""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Levenshtein 编辑距离比（0-1，越大越相似）"""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    dist = dp[m][n]
    max_len = max(m, n)
    return 1.0 - dist / max_len if max_len > 0 else 1.0


def score_pair(new: dict, existing: dict) -> dict:
    """
    计算新 Skill 与已有 Skill 的相似度得分（4 维）。
    new/existing: {'name': str, 'description': str, 'domain': str, 'keywords': [str]}
    返回: {'name': float, 'description': float, 'domain': float, 'keywords': float, 'total': float}
    """
    n_name = tokenize(new.get("name", ""))
    e_name = tokenize(existing.get("name", ""))
    n_desc = tokenize(new.get("description", ""))
    e_desc = tokenize(existing.get("description", ""))
    n_kw = set(k.lower() for k in new.get("keywords", []))
    e_kw = set(k.lower() for k in existing.get("keywords", []))
    n_domain = new.get("domain", "").lower().strip()
    e_domain = existing.get("domain", "").lower().strip()

    name_sim = jaccard(n_name, e_name)
    desc_sim = jaccard(n_desc, e_desc)
    kw_sim = jaccard(n_kw, e_kw)
    domain_sim = 1.0 if n_domain and n_domain == e_domain else 0.0

    weights = {"name": 0.3, "description": 0.3, "domain": 0.2, "keywords": 0.2}
    total = (
        name_sim * weights["name"]
        + desc_sim * weights["description"]
        + domain_sim * weights["domain"]
        + kw_sim * weights["keywords"]
    )

    return {
        "name_sim": round(name_sim, 3),
        "desc_sim": round(desc_sim, 3),
        "domain_sim": round(domain_sim, 3),
        "kw_sim": round(kw_sim, 3),
        "total": round(total, 3),
    }


def suggest_action(score: float) -> str:
    """根据总得分建议动作"""
    if score >= 0.8:
        return "SKIP"
    elif score >= 0.6:
        return "MERGE"
    else:
        return "CREATE"


def score_all(new_skill: dict, existing_skills: list) -> list:
    """对新 Skill 与已有 Skills 逐一评分"""
    results = []
    for idx, existing in enumerate(existing_skills):
        sc = score_pair(new_skill, existing)
        sc["existing_idx"] = idx
        sc["existing_name"] = existing.get("name", f"skill-{idx}")
        sc["action"] = suggest_action(sc["total"])
        results.append(sc)
    results.sort(key=lambda x: x["total"], reverse=True)
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 similarity-scorer.py <new-skill.json> [--existing=<skills.json>]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        new_skill = json.load(f)

    existing_path = None
    for arg in sys.argv[2:]:
        if arg.startswith("--existing="):
            existing_path = arg.split("=", 1)[1]

    if existing_path and os.path.exists(existing_path):
        with open(existing_path, encoding="utf-8") as f:
            existing_skills = json.load(f)
    else:
        existing_skills = []

    if not existing_skills:
        print(f"CREATE — No existing skills to compare against.")
        print(f"Total score: 0.000")
        sys.exit(0)

    results = score_all(new_skill, existing_skills)

    best = results[0] if results else None

    print(f"New Skill: {new_skill.get('name', 'unknown')}")
    print(f"Best match: {best['existing_name']} (score={best['total']})")
    print()
    for r in results:
        print(
            f"  [{r['action']:5}] {r['existing_name']:<30} "
            f"total={r['total']:.3f}  "
            f"name={r['name_sim']:.3f}  "
            f"desc={r['desc_sim']:.3f}  "
            f"domain={r['domain_sim']:.3f}  "
            f"kw={r['kw_sim']:.3f}"
        )

    print()
    action = suggest_action(best["total"]) if best else "CREATE"
    print(f"Action: {action}")

    sys.exit(0 if action == "CREATE" else 0)


if __name__ == "__main__":
    main()
