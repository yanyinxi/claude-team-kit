#!/usr/bin/env python3
"""
策略变体生成器 — 基于任务描述分析复杂度，生成并行策略变体

职责:
  1. 分析任务描述，评估复杂度 (1-10)
  2. 识别任务领域和依赖关系
  3. 生成 3-4 个策略变体
  4. 读取策略权重，输出推荐方案

用法:
  python3 .claude/lib/strategy_generator.py                          # 查看当前权重
  python3 .claude/lib/strategy_generator.py "实现用户认证系统"        # 分析任务并推荐
  python3 .claude/lib/strategy_generator.py --variants               # 列出所有策略变体
"""
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any


# ═══════════════════════════════════════════════════════════════
# 策略变体定义
# ═══════════════════════════════════════════════════════════════

STRATEGY_VARIANTS = {
    "parallel_high": {
        "name": "高并行度",
        "parallelism": 5,
        "granularity": "coarse",
        "description": "最大化并行执行，5 个并行 Agent，粗粒度任务分解",
        "suitable_complexity": (8, 10),
    },
    "hybrid": {
        "name": "混合策略",
        "parallelism": 3,
        "granularity": "adaptive",
        "description": "根据任务复杂度动态调整，3 个并行 Agent，自适应分解",
        "suitable_complexity": (6, 8),
    },
    "granular": {
        "name": "细粒度分解",
        "parallelism": 3,
        "granularity": "fine",
        "description": "更小的任务单元，便于控制和调试，3 个并行 Agent",
        "suitable_complexity": (3, 6),
    },
    "sequential": {
        "name": "顺序执行",
        "parallelism": 1,
        "granularity": "medium",
        "description": "确保依赖关系，1 个 Agent 顺序执行",
        "suitable_complexity": (1, 3),
    },
}


# ═══════════════════════════════════════════════════════════════
# 任务分析
# ═══════════════════════════════════════════════════════════════

# 领域关键词
DOMAIN_KEYWORDS = {
    "backend": [
        "认证", "权限", "API", "接口", "数据库", "SQL", "查询", "数据",
        "缓存", "队列", "消息", "事务", "后端", "服务", "auth", "api",
        "endpoint", "database", "migration", "etl", "导入", "spring",
    ],
    "frontend": [
        "页面", "组件", "UI", "样式", "交互", "表单", "按钮", "弹窗",
        "路由", "导航", "响应式", "前端", "vue", "react", "chart",
        "图表", "可视化", "modal", "dialog", "css", "html",
    ],
    "fullstack": [
        "全栈", "前后端", "登录", "注册", "CRUD", "功能", "模块",
        "系统", "平台", "用户", "角色", "权限管理",
    ],
    "testing": [
        "测试", "单测", "集成测试", "E2E", "覆盖率", "mock",
        "test", "unittest", "junit", "pytest",
    ],
    "devops": [
        "部署", "CI", "CD", "构建", "打包", "容器", "docker",
        "k8s", "流水线", "release", "deploy",
    ],
}

# 复杂度信号词
COMPLEXITY_SIGNALS_HIGH = [
    "微服务", "分布式", "事务", "一致性", "异步", "并发",
    "权限", "角色", "RBAC", "审批", "工作流", "实时",
    "multiple.*module", "complex.*business.*logic",
]
COMPLEXITY_SIGNALS_MEDIUM = [
    "CRUD", "表单", "过滤", "分页", "查询", "导入导出",
    "统计", "图表", "dashboard",
]
COMPLEXITY_SIGNALS_LOW = [
    "文档", "注释", "格式", "重命名", "修复", "typo",
    "简单", "配置", "config",
]


def analyze_task(task_description: str) -> dict:
    """分析任务描述，提取领域、复杂度、依赖关系"""
    text = task_description.lower()

    # 识别领域
    domain_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            domain_scores[domain] = score

    primary_domain = max(domain_scores, key=domain_scores.get) if domain_scores else "fullstack"
    secondary_domains = [d for d, s in domain_scores.items() if d != primary_domain and s > 0]

    # 评估复杂度
    complexity = 5  # 默认中等
    high_hits = sum(1 for kw in COMPLEXITY_SIGNALS_HIGH if re.search(kw.lower(), text))
    medium_hits = sum(1 for kw in COMPLEXITY_SIGNALS_MEDIUM if re.search(kw.lower(), text))
    low_hits = sum(1 for kw in COMPLEXITY_SIGNALS_LOW if re.search(kw.lower(), text))

    complexity += high_hits * 2 + medium_hits * 1 - low_hits * 1
    complexity = max(1, min(10, complexity))

    # 识别依赖关系
    has_dependencies = any(kw in text for kw in ["依赖", "必须先", "之后才能", "depends", "blocked by"])

    return {
        "task": task_description[:200],
        "primary_domain": primary_domain,
        "secondary_domains": secondary_domains,
        "complexity": complexity,
        "has_dependencies": has_dependencies,
        "complexity_signals": {
            "high": high_hits,
            "medium": medium_hits,
            "low": low_hits,
        },
    }


# ═══════════════════════════════════════════════════════════════
# 策略选择
# ═══════════════════════════════════════════════════════════════

def select_strategy(analysis: dict, weights: dict) -> dict:
    """基于任务分析和领域权重选择最优策略"""
    complexity = analysis["complexity"]
    domain = analysis["primary_domain"]

    # 根据复杂度映射到基线策略
    if complexity >= 8:
        baseline = "parallel_high"
    elif complexity >= 6:
        baseline = "hybrid"
    elif complexity >= 3:
        baseline = "granular"
    else:
        baseline = "sequential"

    # 领域权重做温和偏置
    domain_weight = weights.get(domain, 5.0)
    if isinstance(domain_weight, dict):
        domain_weight = domain_weight.get("weight", 5.0)

    # 高权重领域（>7.0）且有依赖 → 降一档并行度
    # 高权重领域（>7.0）且无依赖 → 升一档并行度
    adjusted = baseline
    order = ["sequential", "granular", "hybrid", "parallel_high"]
    idx = order.index(baseline)

    if domain_weight > 7.0:
        if analysis["has_dependencies"]:
            idx = max(0, idx - 1)  # 降档
        else:
            idx = min(len(order) - 1, idx + 1)  # 升档
        adjusted = order[idx]

    variant = STRATEGY_VARIANTS[adjusted]

    # 生成 Agent 配置
    agent_config = _generate_agent_config(analysis, variant)

    return {
        "baseline_strategy": baseline,
        "final_strategy": adjusted,
        "strategy_name": variant["name"],
        "complexity": complexity,
        "primary_domain": domain,
        "domain_weight": round(domain_weight, 1),
        "parallelism": variant["parallelism"],
        "agents": agent_config,
        "reasoning": _generate_reasoning(analysis, adjusted, variant),
    }


def _generate_agent_config(analysis: dict, variant: dict) -> dict:
    """根据策略变体和领域生成 Agent 数量配置"""
    parallelism = variant["parallelism"]
    domain = analysis["primary_domain"]

    if parallelism == 1:
        return {domain_to_agent(domain): 1}

    if domain == "backend":
        config = {"backend-developer": max(1, parallelism - 1)}
    elif domain == "frontend":
        config = {"frontend-developer": max(1, parallelism - 1)}
    elif domain == "fullstack":
        fe = parallelism // 2
        be = parallelism - fe
        config = {"frontend-developer": fe, "backend-developer": be}
    elif domain == "testing":
        config = {"test": parallelism}
    else:
        config = {"backend-developer": parallelism // 2, "frontend-developer": parallelism - parallelism // 2}

    # 始终包含 code-reviewer（如果并行度允许）
    if parallelism >= 3 and "code-reviewer" not in config:
        config["code-reviewer"] = 1
        # 调整其他数量
        for k in list(config.keys()):
            if k != "code-reviewer" and config[k] > 1:
                config[k] -= 1
                break

    return config


def domain_to_agent(domain: str) -> str:
    return {
        "backend": "backend-developer",
        "frontend": "frontend-developer",
        "fullstack": "backend-developer",
        "testing": "test",
        "devops": "backend-developer",
    }.get(domain, "backend-developer")


def _generate_reasoning(analysis: dict, strategy: str, variant: dict) -> str:
    parts = [f"复杂度 {analysis['complexity']}/10"]
    parts.append(f"主领域: {analysis['primary_domain']}")
    parts.append(f"并行度: {variant['parallelism']}")
    if analysis["has_dependencies"]:
        parts.append("存在依赖关系，已调整并行策略")
    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════
# 策略权重管理
# ═══════════════════════════════════════════════════════════════

def _find_data_dir() -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    return Path(root) / ".claude" / "data"


def load_weights() -> dict:
    weights_file = _find_data_dir() / "strategy_weights.json"
    if weights_file.exists():
        try:
            return json.loads(weights_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return _default_weights()


def _default_weights() -> dict:
    return {
        "_comment": "策略领域权重，由 Stop hook 的 EMA 更新维护",
        "backend": 5.0,
        "frontend": 5.0,
        "fullstack": 5.0,
        "testing": 5.0,
        "docs": 5.0,
        "config": 5.0,
        "metadata": {},
    }


def save_weights(weights: dict):
    weights_file = _find_data_dir() / "strategy_weights.json"
    weights_file.parent.mkdir(parents=True, exist_ok=True)
    import fcntl
    with open(weights_file, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()
            f.write(json.dumps(weights, indent=2, ensure_ascii=False))
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def ensure_strategy_weights():
    """确保 strategy_weights.json 存在且有初始值"""
    weights_file = _find_data_dir() / "strategy_weights.json"
    if not weights_file.exists():
        save_weights(_default_weights())
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    ensure_strategy_weights()
    weights = load_weights()

    if len(sys.argv) > 1 and sys.argv[1] == "--variants":
        print(json.dumps(STRATEGY_VARIANTS, indent=2, ensure_ascii=False))
        return

    if len(sys.argv) > 1 and sys.argv[1] not in ("--help", "-h"):
        task = " ".join(sys.argv[1:])
    else:
        # 无参数时显示当前状态
        print("📊 当前策略权重:")
        for k, v in weights.items():
            if k not in ("_comment", "metadata") and not k.startswith("_"):
                meta = weights.get("metadata", {}).get(k, {})
                count = meta.get("execution_count", 0)
                print(f"  {k}: {v} (执行 {count} 次)")
        print()
        print("用法: python3 .claude/lib/strategy_generator.py '<任务描述>'")
        print("      python3 .claude/lib/strategy_generator.py --variants")
        return

    analysis = analyze_task(task)
    result = select_strategy(analysis, weights)

    print(f"🎯 任务分析:")
    print(f"   任务: {analysis['task']}")
    print(f"   领域: {analysis['primary_domain']}")
    print(f"   复杂度: {analysis['complexity']}/10")
    print(f"   依赖: {'有' if analysis['has_dependencies'] else '无'}")
    print()
    print(f"📋 策略推荐:")
    print(f"   基线: {result['baseline_strategy']}")
    print(f"   最终: {result['final_strategy']} ({result['strategy_name']})")
    print(f"   并行度: {result['parallelism']}")
    print(f"   领域权重: {result['domain_weight']}")
    print(f"   Agent 配置: {json.dumps(result['agents'], ensure_ascii=False)}")
    print(f"   理由: {result['reasoning']}")

    # 输出完整 JSON
    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
