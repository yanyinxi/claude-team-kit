#!/usr/bin/env python3
"""
智能检索模块 - 基于上下文检索相关知识

功能：
1. 基于上下文的智能检索
2. 多维度相关性计算
3. 结果排序和过滤
4. 与 Hooks 集成
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Optional

# 添加脚本目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from knowledge_graph import KnowledgeGraph


class KnowledgeRetriever:
    """知识检索器"""

    def __init__(self, graph_file: str = ".claude/data/knowledge_graph.json"):
        """
        初始化检索器

        Args:
            graph_file: 知识图谱文件路径
        """
        self.kg = KnowledgeGraph(graph_file)

    def retrieve_relevant_knowledge(
        self,
        context: str,
        domain: Optional[str] = None,
        node_type: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        基于上下文检索相关知识

        Args:
            context: 上下文文本（如任务描述、问题描述）
            domain: 领域过滤（如 backend, frontend）
            node_type: 节点类型过滤（如 best_practice, improvement）
            top_k: 返回前 k 个结果

        Returns:
            list: 相关知识节点列表
        """
        # 提取关键词
        keywords = self._extract_keywords(context)

        # 搜索相关节点
        all_results = []
        for keyword in keywords:
            results = self.kg.search_nodes(keyword, domain, node_type)
            all_results.extend(results)

        # 去重（基于节点 ID）
        seen_ids = set()
        unique_results = []
        for node in all_results:
            if node["id"] not in seen_ids:
                seen_ids.add(node["id"])
                unique_results.append(node)

        # 重新计算相关性分数
        for node in unique_results:
            node["_final_score"] = self._calculate_relevance(node, context, keywords)

        # 排序
        unique_results.sort(key=lambda x: x.get("_final_score", 0), reverse=True)

        # 返回 top-k
        return unique_results[:top_k]

    def _extract_keywords(self, text: str) -> List[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本

        Returns:
            list: 关键词列表
        """
        import re

        # 简单实现：提取长度 >= 3 的单词
        words = re.findall(r'\w+', text.lower())
        keywords = [w for w in words if len(w) >= 3]

        # 去重并保持顺序
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:10]  # 最多 10 个关键词

    def _calculate_relevance(self, node: Dict, context: str, keywords: List[str]) -> float:
        """
        计算节点与上下文的相关性

        Args:
            node: 知识节点
            context: 上下文文本
            keywords: 关键词列表

        Returns:
            float: 相关性分数
        """
        score = 0.0

        # 1. 关键词匹配分数
        title = node.get("title", "").lower()
        description = node.get("description", "").lower()
        tags = [t.lower() for t in node.get("tags", [])]

        for keyword in keywords:
            if keyword in title:
                score += 3.0
            if keyword in description:
                score += 1.5
            if any(keyword in tag for tag in tags):
                score += 2.0

        # 2. 成功率加权
        success_rate = node.get("success_rate", 0)
        score += success_rate * 5.0

        # 3. 平均奖励加权
        avg_reward = node.get("avg_reward", 0)
        score += avg_reward * 0.5

        # 4. 证据数量加权
        evidence_count = len(node.get("evidence", []))
        score += min(evidence_count * 0.5, 2.0)  # 最多加 2 分

        return score

    def retrieve_by_domain(self, domain: str, top_k: int = 10) -> List[Dict]:
        """
        按领域检索知识

        Args:
            domain: 领域名称
            top_k: 返回前 k 个结果

        Returns:
            list: 知识节点列表
        """
        results = []
        for node in self.kg.graph["nodes"]:
            if node.get("domain") == domain:
                results.append(node)

        # 按成功率排序
        results.sort(key=lambda x: x.get("success_rate", 0), reverse=True)

        return results[:top_k]

    def retrieve_by_type(self, node_type: str, top_k: int = 10) -> List[Dict]:
        """
        按类型检索知识

        Args:
            node_type: 节点类型
            top_k: 返回前 k 个结果

        Returns:
            list: 知识节点列表
        """
        results = []
        for node in self.kg.graph["nodes"]:
            if node.get("type") == node_type:
                results.append(node)

        # 按成功率排序
        results.sort(key=lambda x: x.get("success_rate", 0), reverse=True)

        return results[:top_k]

    def retrieve_related(self, node_id: str, relation: Optional[str] = None) -> List[Dict]:
        """
        检索相关节点

        Args:
            node_id: 节点 ID
            relation: 关系类型（可选）

        Returns:
            list: 相关节点列表
        """
        return self.kg.find_related_nodes(node_id, relation)

    def format_results(self, results: List[Dict], include_score: bool = True) -> str:
        """
        格式化检索结果为可读文本

        Args:
            results: 检索结果列表
            include_score: 是否包含分数

        Returns:
            str: 格式化后的文本
        """
        if not results:
            return "未找到相关知识"

        lines = ["📚 相关知识：\n"]

        for i, node in enumerate(results, 1):
            title = node.get("title", "Untitled")
            description = node.get("description", "")
            success_rate = node.get("success_rate", 0)
            avg_reward = node.get("avg_reward", 0)

            lines.append(f"{i}. **{title}**")

            if include_score and "_final_score" in node:
                lines.append(f" (相关性: {node['_final_score']:.1f})")

            lines.append(f"\n   - 描述: {description}")
            lines.append(f"\n   - 成功率: {success_rate:.0%}")
            lines.append(f"\n   - 平均奖励: {avg_reward:.1f}/10")

            tags = node.get("tags", [])
            if tags:
                lines.append(f"\n   - 标签: {', '.join(tags)}")

            lines.append("\n\n")

        return "".join(lines)


def main():
    """命令行入口"""
    # 从 stdin 读取输入
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    context = input_data.get("context", "")
    domain = input_data.get("domain")
    node_type = input_data.get("type")
    top_k = input_data.get("top_k", 5)

    if not context:
        print("Error: 'context' field is required", file=sys.stderr)
        sys.exit(1)

    # 检索知识
    retriever = KnowledgeRetriever()
    results = retriever.retrieve_relevant_knowledge(context, domain, node_type, top_k)

    # 输出结果
    if results:
        output = retriever.format_results(results)
        print(output)
    else:
        print("未找到相关知识")

    sys.exit(0)


if __name__ == "__main__":
    main()
