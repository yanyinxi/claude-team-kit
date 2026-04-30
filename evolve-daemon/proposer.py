#!/usr/bin/env python3
"""
提案生成器 — 调用 Claude API 进行深度分析，生成结构化改进提案。

输入: analyzer.py 产出的聚合数据
输出: proposals/YYYY-MM-DD_target_description.md

原则:
  - 只提出有数据支撑的建议
  - 建议必须具体、可执行（精确到文件的章节/步骤）
  - 必须评估风险
  - 不修改文件，只生成提案
"""
import json
import os
from pathlib import Path
from datetime import datetime


def generate_proposal(analysis: dict, config: dict, root: Path) -> Path:
    """
    生成改进提案。调用 Claude API 进行深度分析。
    如果 API Key 未配置，降级为模板提案。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            return _generate_with_claude(analysis, config, root, api_key)
        except Exception:
            pass

    return _generate_from_template(analysis, config, root)


def _generate_with_claude(analysis: dict, config: dict, root: Path, api_key: str) -> Path:
    """使用 Claude API 生成高质量提案"""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    api_config = config["claude_api"]

    system_prompt = """你是 AI 工程规范优化器。分析 Claude Code 使用数据，找出 Agent/Skill/Rule 中的可改进点。

原则:
1. 只提出有数据支撑的建议，不臆测
2. 建议必须具体可执行（精确到文件、章节、步骤）
3. 评估每个建议的风险（low/medium/high）
4. 不提出涉及安全策略或权限的改动
5. 如果数据不足以支撑建议，诚实说"无需改进"

输出格式:
# 改进提案: [主题]

## 数据依据
- 来自 N 个会话的 M 次纠正

## 发现
### [具体问题]
- 现象
- 根因
- 证据

## 建议改动
### 文件: [path] 章节: [section]
- 当前: ...
- 改为: ...
- 风险: [low/medium/high]

## 验证计划
- 如何验证改动有效
"""

    user_message = json.dumps(analysis, ensure_ascii=False, indent=2)

    response = client.messages.create(
        model=api_config["analyze_model"],
        max_tokens=api_config["analyze_max_tokens"],
        temperature=api_config["analyze_temperature"],
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    content = response.content[0].text
    return _save_proposal(content, analysis, config, root)


def _generate_from_template(analysis: dict, config: dict, root: Path) -> Path:
    """降级：使用模板生成提案（无需 API Key）"""
    hotspots = analysis.get("correction_hotspots", {})
    if not hotspots:
        return Path()

    patterns = analysis.get("correction_patterns", {})

    content = f"""# 改进提案: 自动检测到需优化的模式

## 数据依据
- 来自 {analysis['total_sessions']} 个会话
- 发现 {len(hotspots)} 个纠正热点

## 发现

"""
    for target, count in sorted(hotspots.items(), key=lambda x: -x[1])[:5]:
        content += f"### {target} ({count} 次纠正)\n"
        if target in patterns or f"{target}:unknown" in patterns:
            key = target if target in patterns else f"{target}:unknown"
            examples = patterns.get(key, {}).get("examples", [])
            for ex in examples[:2]:
                content += f"- 上下文: {ex.get('context', '?')}\n"
                content += f"- 纠正: {ex.get('correction', '?')}\n"
        content += "\n"

    content += """## 建议
<!-- Claude API Key 未配置，使用模板提案。配置 ANTHROPIC_API_KEY 后获得精准分析 -->

请 Review 上述纠正模式，手动更新对应的 Skill/Agent/Rule 文件。

## 验证计划
- 观察后续 5 个会话中同场景的纠正率变化
"""

    return _save_proposal(content, analysis, config, root)


def _save_proposal(content: str, analysis: dict, config: dict, root: Path) -> Path:
    """保存提案文件"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    target = analysis.get("primary_target", "general").replace(":", "-").replace("/", "-")

    proposals_dir = root / config["paths"]["proposals_dir"]
    proposals_dir.mkdir(parents=True, exist_ok=True)

    proposal_path = proposals_dir / f"{date_str}_{target}_optimize.md"
    proposal_path.write_text(content, encoding="utf-8")

    return proposal_path
