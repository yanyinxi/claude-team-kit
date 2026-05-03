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
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加 harness 到 Python path
_harness_root = Path(__file__).parent.parent.parent
if str(_harness_root) not in sys.path:
    sys.path.insert(0, str(_harness_root))

from harness._core.exceptions import handle_exception, safe_execute

logger = logging.getLogger(__name__)


def generate_proposal(analysis: dict, config: dict, root: Path) -> Path:
    """
    生成改进提案。调用 Claude API 进行深度分析。
    如果 API Key 未配置，降级为模板提案。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            return _generate_with_claude(analysis, config, root, api_key)
        except Exception as e:
            handle_exception(e, "Claude API 生成提案失败，降级为模板", log_level="warning")

    return _generate_from_template(analysis, config, root)


def _call_claude_api(api_key: str, model: str, system_prompt: str, user_message: str, max_tokens: int, temperature: float) -> str | None:
    """调用 Claude API — 优先使用 SDK，降级为 REST API"""
    # 方案 1: 使用 anthropic SDK（如果已安装）
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except ImportError:
        pass

    # 方案 2: 使用标准库 urllib 直接调 REST API（零外部依赖）
    try:
        import urllib.request
        import urllib.error

        body = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except Exception:
        return None


def _generate_with_claude(analysis: dict, config: dict, root: Path, api_key: str) -> Path:
    """使用 Claude API 生成高质量提案"""
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

    content = _call_claude_api(
        api_key=api_key,
        model=api_config["analyze_model"],
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=api_config["analyze_max_tokens"],
        temperature=api_config["analyze_temperature"],
    )

    if content is None:
        raise RuntimeError("Claude API 调用失败")

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

    # 记录到 instinct（待观察状态）
    _record_to_instinct(analysis, proposal_path, confidence=0.5, source="proposal-generated")

    return proposal_path


def _record_to_instinct(analysis: dict, proposal_path: Path, confidence: float, source: str):
    """将提案内容记录到 instinct-record.json"""
    try:
        from instinct_updater import add_pattern
        hotspots = analysis.get("correction_hotspots", {})
        if hotspots:
            top_target = sorted(hotspots.items(), key=lambda x: -x[1])[0][0]
            record_id = add_pattern(
                pattern=f"检测到多纠正热点: {top_target}",
                correction="见提案文件",
                root_cause=analysis.get("primary_cause", ""),
                confidence=confidence,
                source=source,
            )
            print(f"  🧠 instinct 已记录: {record_id}")
    except ImportError as e:
        handle_exception(e, "instinct_updater 模块导入失败", log_level="warning")
    except Exception as e:
        handle_exception(e, "记录到 instinct 失败", log_level="warning")


def mark_proposal_accepted(proposal_path: Path, root: Path):
    """
    人工 accept 提案后调用 — 升级 instinct confidence 至 0.9。
    用法: python3 -c "from evolve_daemon.proposer import mark_proposal_accepted; mark_proposal_accepted(Path('proposals/xxx.md'), Path('.'))"
    """
    try:
        from instinct_updater import add_pattern
        content = proposal_path.read_text(encoding="utf-8")
        # 提取建议中的核心内容
        import re
        matches = re.findall(r"文件:\s*(\S+)", content)
        if matches:
            target = matches[0]
        else:
            # 尝试从文件名提取：proposal_xxx.md -> xxx
            import re
            name_match = re.search(r"proposal_(.+?)\.md", str(proposal_path.name))
            target = name_match.group(1) if name_match else "unknown"
        record_id = add_pattern(
            pattern=f"提案已采纳: {target}",
            correction="提案已应用，待后续验证",
            root_cause="经人工确认需要改进",
            confidence=0.9,
            source="proposal-accepted",
        )
        print(f"✅ instinct 已升级 confidence=0.9: {record_id}")
    except ImportError as e:
        logger.warning(f"instinct_updater 模块导入失败: {e}")
        print(f"⚠️ instinct 更新失败: {e}")
    except Exception as e:
        handle_exception(e, "提案 accept 标记更新 instinct 失败", log_level="warning")
        print(f"⚠️ instinct 更新失败: {e}")
