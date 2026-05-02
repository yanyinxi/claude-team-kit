#!/usr/bin/env python3
"""Generate INDEX.md for all skills"""
import os
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"

INDEX_TEMPLATE = '''# {title}

## 一句话描述
{description}

## 适用场景
{scenarios}

## 关键能力
{capabilities}

## 触发词
{triggers}

## 依赖
{dependencies}

---
详细文档见 [SKILL.md](./SKILL.md)
'''

SKILL_DATA = {
    "karpathy-guidelines": {
        "title": "Karpathy Guidelines",
        "description": "LLM 编码最佳实践，避免常见 AI 编程错误",
        "scenarios": "- 任何代码编写任务前\n- 代码审查时",
        "capabilities": "- 提供编码原则\n- 检查常见反模式",
        "triggers": "编码规范、最佳实践、karpathy",
        "dependencies": "无"
    },
    "requirement-analysis": {
        "title": "Requirement Analysis",
        "description": "需求分析与 PRD 生成，将用户需求转化为技术规格",
        "scenarios": "- 新项目启动\n- 新功能开发前",
        "capabilities": "- 用户故事分解\n- 验收标准定义\n- PRD 文档生成",
        "triggers": "需求分析、PRD、用户故事",
        "dependencies": "无"
    },
    "architecture-design": {
        "title": "Architecture Design",
        "description": "系统架构设计，技术选型与模块划分",
        "scenarios": "- 系统整体设计\n- 技术方案评审",
        "capabilities": "- 架构模式推荐\n- 技术选型决策树",
        "triggers": "架构设计、技术选型、系统设计",
        "dependencies": "无"
    },
    "task-distribution": {
        "title": "Task Distribution",
        "description": "任务拆分与并行计划，优化多 Agent 协作",
        "scenarios": "- 复杂功能开发\n- 多 Agent 并行任务",
        "capabilities": "- 任务依赖分析\n- 并行策略制定",
        "triggers": "任务拆分、并行执行、task distribution",
        "dependencies": "无"
    },
    "tdd": {
        "title": "TDD",
        "description": "测试驱动开发，RED-GREEN-REFACTOR 循环",
        "scenarios": "- 新功能开发\n- Bug 修复",
        "capabilities": "- 测试先行\n- 增量开发",
        "triggers": "TDD、测试驱动、单元测试",
        "dependencies": "testing"
    },
    "database-designer": {
        "title": "Database Designer",
        "description": "数据库设计、迁移、索引优化",
        "scenarios": "- 数据模型设计\n- 数据库迁移",
        "capabilities": "- Schema 设计\n- 索引优化\n- 迁移脚本生成",
        "triggers": "数据库设计、schema、migration",
        "dependencies": "无"
    },
    "api-designer": {
        "title": "API Designer",
        "description": "RESTful API 设计规范与最佳实践",
        "scenarios": "- API 接口设计\n- API 文档生成",
        "capabilities": "- RESTful 规范\n- OpenAPI 生成",
        "triggers": "API设计、RESTful、接口设计",
        "dependencies": "无"
    },
    "code-quality": {
        "title": "Code Quality",
        "description": "代码审查流程与质量门禁",
        "scenarios": "- 代码审查\n- 质量评估",
        "capabilities": "- 5 维度审查\n- 质量报告生成",
        "triggers": "代码审查、code review、质量",
        "dependencies": "无"
    },
    "testing": {
        "title": "Testing",
        "description": "测试策略和测试用例生成",
        "scenarios": "- 测试计划\n- 用例生成",
        "capabilities": "- 单元测试\n- 集成测试\n- E2E 测试",
        "triggers": "测试、test、用例",
        "dependencies": "无"
    },
    "security-audit": {
        "title": "Security Audit",
        "description": "安全审计清单与漏洞检测",
        "scenarios": "- 安全审查\n- 敏感代码检查",
        "capabilities": "- OWASP 检查\n- 漏洞扫描",
        "triggers": "安全、security、审计",
        "dependencies": "无"
    },
    "performance": {
        "title": "Performance",
        "description": "性能分析和优化建议",
        "scenarios": "- 性能瓶颈分析\n- 优化建议",
        "capabilities": "- 性能剖析\n- 优化策略",
        "triggers": "性能、performance、优化",
        "dependencies": "无"
    },
    "git-master": {
        "title": "Git Master",
        "description": "Git 工作流管理与提交规范",
        "scenarios": "- 提交代码\n- 分支管理",
        "capabilities": "- Conventional Commits\n- 分支策略",
        "triggers": "git、commit、分支",
        "dependencies": "无"
    },
    "ship": {
        "title": "Ship",
        "description": "发布检查清单与交付流程",
        "scenarios": "- 代码发布\n- 交付检查",
        "capabilities": "- 发布检查\n- 回滚准备",
        "triggers": "发布、ship、deploy",
        "dependencies": "无"
    },
    "debugging": {
        "title": "Debugging",
        "description": "系统化根因分析与调试",
        "scenarios": "- Bug 排查\n- 故障分析",
        "capabilities": "- 根因分析\n- 调试策略",
        "triggers": "调试、debug、排查",
        "dependencies": "无"
    },
    "migration": {
        "title": "Migration",
        "description": "框架/依赖升级指南",
        "scenarios": "- 版本升级\n- 迁移改造",
        "capabilities": "- 升级规划\n- 兼容处理",
        "triggers": "迁移、upgrade、升级",
        "dependencies": "无"
    },
    "docker-compose": {
        "title": "Docker Compose",
        "description": "容器化部署与编排",
        "scenarios": "- 容器化\n- 本地开发环境",
        "capabilities": "- Compose 编排\n- 服务定义",
        "triggers": "docker、compose、容器",
        "dependencies": "无"
    },
    "multi-model-review": {
        "title": "Multi-Model Review",
        "description": "多模型交叉审查",
        "scenarios": "- 关键代码审查\n- 架构决策",
        "capabilities": "- 多模型对比\n- 差异分析",
        "triggers": "多模型、review、交叉审查",
        "dependencies": "无"
    },
    "context-compaction": {
        "title": "Context Compaction",
        "description": "上下文压缩策略",
        "scenarios": "- 长对话压缩\n- 上下文管理",
        "capabilities": "- 智能压缩\n- 关键信息保留",
        "triggers": "压缩、compact、上下文",
        "dependencies": "无"
    },
    "parallel-dispatch": {
        "title": "Parallel Dispatch",
        "description": "并行任务分派策略",
        "scenarios": "- 多 Agent 并行\n- 批量处理",
        "capabilities": "- 任务分派\n- 结果汇聚",
        "triggers": "并行、parallel、分派",
        "dependencies": "task-distribution"
    },
}

def generate_index(skill_dir: Path, data: dict):
    index_path = skill_dir / "INDEX.md"
    content = INDEX_TEMPLATE.format(**data)
    index_path.write_text(content, encoding="utf-8")
    print(f"✅ Created: {index_path}")

def main():
    created = 0
    for skill_name, data in SKILL_DATA.items():
        skill_dir = SKILLS_DIR / skill_name
        if skill_dir.exists():
            generate_index(skill_dir, data)
            created += 1
        else:
            print(f"⚠️  Skill not found: {skill_name}")

    print(f"\n📊 Total INDEX.md created: {created}/{len(SKILL_DATA)}")

if __name__ == "__main__":
    main()
