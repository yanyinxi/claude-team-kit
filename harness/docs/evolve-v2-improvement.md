# 自进化系统 V2 — 行业最佳实践融合与技术改进方案

> 本文档描述如何借鉴 no-no-debug、skill-self-evolution、phantom、Hone 等热门开源项目的最佳实践，对 claude-harness-kit 的自进化系统进行深度优化。

## 1. 背景与目标

### 1.1 现有系统架构

当前 evolve-daemon 已实现的核心组件：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Hook 层（数据采集）                            │
│                                                                      │
│  PostToolUse[Agent]   → collect-agent.py  → agent_calls.jsonl      │
│  PostToolUse[Skill]   → collect-skill.py  → skill_calls.jsonl       │
│  PostToolUseFailure   → collect-failure.py → failures.jsonl         │
│  Stop                 → collect-session.py → sessions.jsonl          │
│                                                                      │
│  （异步）extract-semantics.py → Haiku 语义提取 → 回填 corrections    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Daemon 层（分析决策）                            │
│                                                                      │
│  daemon.py                                                           │
│    ├── check_thresholds()    # 检查触发条件                          │
│    ├── run_analysis()         # 执行分析                              │
│    └── 触发条件: 5会话 / 3次同pattern / 6h间隔                        │
│                                                                      │
│  analyzer.py                                                         │
│    └── aggregate_and_analyze()  # 统计纠正热点、失败模式               │
│                                                                      │
│  proposer.py                                                         │
│    └── generate_proposal()     # Claude API 生成改进提案             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Instinct 层（记忆存储）                           │
│                                                                      │
│  instinct-record.json                                                │
│    └── records: [{pattern, confidence, source, ...}]                 │
│                                                                      │
│  instinct_updater.py                                                 │
│    └── add_pattern()  # 添加新记录，固定 confidence=0.3              │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 五大核心差距

对比 GitHub 热门项目（phantom、no-no-debug、skill-self-evolution、Hone），当前系统存在以下不足：

| 维度 | 当前状态 | 行业实践 | 项目借鉴 |
|------|---------|---------|---------|
| **时间衰减** | 所有数据等权重，历史数据不衰减 | 60-90 天半衰期 exponential decay | skill-self-evolution |
| **语义去重** | 相似 pattern 重复统计 | 语义相似度合并 + SAGE confidence | Hone |
| **验证闭环** | 提案生成后无反馈 | A/B 测试 + accept/reject 追踪 | phantom |
| **预防机制** | 被动记录已发生错误 | PreToolUse 安全门控 + 三门禁 | no-no-debug |
| **主动复盘** | 等待触发条件 | 周期性 8 维 review | no-no-debug + Sibyl |

---

## 2. 改进方案详细设计

### 2.1 时间衰减机制（Time Decay）

#### 2.1.1 设计原理

借鉴 **skill-self-evolution** 的 60 天半衰期设计：

```
confidence(t) = base × 0.5^(days_since_reinforcement / half_life)
```

**核心原则**：
- 新数据权重高，反映近期行为模式
- 老数据逐渐衰减，避免 stale pattern 主导
- 被反复验证的 pattern 可以"refresh"，恢复权重
- seed 数据不受衰减影响（人工验证过的高置信度知识）

#### 2.1.2 数据模型变更

```python
# instinct-record.json 新增字段
{
  "records": [
    {
      "id": "auto-xxx",
      "pattern": "testing skill 在事务场景建议 mock",
      "context": "",
      "correction": "使用集成测试",
      "root_cause": "缺少事务场景判断",
      "confidence": 0.6,           # 可衰减
      "last_reinforced_at": "2026-05-01T10:00:00",  # 新增：最后一次被验证的时间
      "reinforcement_count": 3,    # 新增：被验证次数
      "decay_status": "active",    # active | decaying | archived
      "applied_count": 0,
      "source": "auto-detected",
      "created_at": "2026-04-28T08:00:00",
      "updated_at": "2026-05-01T10:00:00"
    }
  ]
}
```

#### 2.1.3 实现代码

```python
# instinct_updater.py 新增

from datetime import datetime, timedelta
from typing import Optional

HALF_LIFE_DAYS = 90  # 90 天半衰期
DECAY_FLOOR = 0.1   # 衰减下限
REINFORCEMENT_BONUS = 0.05  # 每次验证通过 +5% 半衰期


def time_decay_weight(created_at: str, last_reinforced: Optional[str], half_life_days: int = HALF_LIFE_DAYS) -> float:
    """
    计算时间衰减权重。

    如果有 last_reinforced，以它为准计算衰减。
    如果没有，以 created_at 计算。

    返回值范围: (0, 1]
    """
    reference_time = last_reinforced if last_reinforced else created_at

    try:
        ref_dt = datetime.fromisoformat(reference_time)
    except (ValueError, TypeError):
        return 1.0  # 无法解析时间，默认不衰减

    age_days = (datetime.now() - ref_dt).total_seconds() / 86400
    return 0.5 ** (age_days / half_life_days)


def apply_decay_to_record(record: dict) -> dict:
    """
    对单条 record 应用时间衰减。

    规则：
    1. seed 记录不衰减
    2. 有 reinforcement_count 的记录，reinforcement_count >= 3 时半衰期延长 50%
    3. confidence 最低衰减到 DECAY_FLOOR
    """
    if record.get("source") == "seed":
        return record  # seed 数据不衰减

    half_life = HALF_LIFE_DAYS
    reinforcement_count = record.get("reinforcement_count", 0)

    # 多次验证的记录半衰期延长
    if reinforcement_count >= 3:
        half_life = int(half_life * 1.5)
    elif reinforcement_count >= 5:
        half_life = int(half_life * 2)

    weight = time_decay_weight(
        record.get("created_at", ""),
        record.get("last_reinforced_at"),
        half_life
    )

    # 衰减 confidence，但不低于 FLOOR
    original_confidence = record.get("confidence", 0.3)
    decayed_confidence = max(DECAY_FLOOR, original_confidence * weight)

    record["confidence"] = round(decayed_confidence, 3)
    record["decay_status"] = "decaying" if weight < 0.8 else "active"

    return record


def apply_decay_to_all(instinct: dict) -> dict:
    """
    对所有 records 应用时间衰减。
    保留 seed 数据，只衰减 auto-detected 和 proposal-generated 数据。
    """
    if "records" not in instinct:
        return instinct

    for i, record in enumerate(instinct["records"]):
        instinct["records"][i] = apply_decay_to_record(record)

    # 清理已衰减到 floor 且超过 180 天的记录
    instinct["records"] = [
        r for r in instinct["records"]
        if not (
            r.get("confidence", 1) <= DECAY_FLOOR
            and (datetime.now() - datetime.fromisoformat(r.get("last_reinforced_at", r.get("created_at", "2000-01-01")))).days > 180
        )
    ]

    return instinct


def reinforce_pattern(instinct: dict, pattern_id: str, delta: float = 0.1) -> dict:
    """
    增强已存在 pattern 的置信度。

    调用场景：
    1. 提案被 accept → +0.2
    2. 再次检测到同类纠正 → +0.05
    3. 连续 3 次无纠正 → +0.1
    """
    for record in instinct.get("records", []):
        if record.get("id") == pattern_id:
            old_conf = record.get("confidence", 0.3)
            record["confidence"] = min(0.95, old_conf + delta)
            record["reinforcement_count"] = record.get("reinforcement_count", 0) + 1
            record["last_reinforced_at"] = datetime.now().isoformat()
            record["decay_status"] = "active"
            break

    return instinct
```

#### 2.1.4 衰减曲线示意

```
Day 0:     confidence = 0.6  ████████████████████
Day 45:    confidence = 0.42  ██████████████░░░░░░
Day 90:    confidence = 0.30  █████████░░░░░░░░░░░
Day 180:   confidence = 0.15  ████░░░░░░░░░░░░░░░░
Day 270:   confidence = 0.10  ███░░░░░░░░░░░░░░░░░ (floor)
```

### 2.2 语义去重机制（Semantic Deduplication）

#### 2.2.1 设计原理

借鉴 **Hone** 的 SAGE confidence decay 和语义去重思想：

```
问题：
  "testing skill 被纠正 3 次" 和 "testing skill: 缺少事务规则被纠正 2 次"
  可能描述的是同一个问题，但被分开统计

解决：
  1. 归一化 pattern key（target:hint 标准化）
  2. 语义相似度检测（embedding similarity > 0.85 → 合并）
  3. 合并时保留高 confidence 的那个，累加计数
```

#### 2.2.2 归一化函数

```python
# analyzer.py 新增

import re
from typing import Optional


def normalize_pattern_key(target: str, hint: str = "") -> str:
    """
    归一化 pattern key。

    示例：
      target="skill:testing", hint="缺少事务测试规则"
      → "skill:testing:transaction-test"

      target="agent:code-reviewer", hint="review 时没有检查边界条件"
      → "agent:code-reviewer:boundary-check"
    """
    # 提取 target 类型和名称
    parts = target.split(":", 1)
    entity_type = parts[0] if len(parts) > 0 else "unknown"
    entity_name = parts[1] if len(parts) > 1 else target

    # 归一化 hint
    normalized_hint = normalize_hint(hint)

    return f"{entity_type}:{entity_name}:{normalized_hint}"


def normalize_hint(hint: str) -> str:
    """
    将各种表述归一化为统一的关键词。

    规则：
    1. 转小写
    2. 移除标点符号
    3. 移除停用词
    4. 提取核心动作词
    """
    if not hint:
        return "general"

    # 转小写
    hint = hint.lower()

    # 移除标点
    hint = re.sub(r'[^\w\s]', ' ', hint)

    # 停用词列表
    stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to',
                 'in', 'on', 'at', 'for', 'with', 'and', 'or', 'but', 'that',
                 'this', 'it', 'as', 'be', 'have', 'has', 'had', 'do', 'does',
                 'did', 'will', 'would', 'should', 'could', 'may', 'can'}

    words = [w for w in hint.split() if w not in stopwords and len(w) > 2]

    if not words:
        return "general"

    # 保留最重要的 2 个词
    return "-".join(words[:2])


def group_similar_patterns(corrections: list[dict]) -> dict[str, list[dict]]:
    """
    将相似的 corrections 合并分组。

    返回：{normalized_key: [corrections...]}
    """
    groups: dict[str, list[dict]] = {}

    for c in corrections:
        target = c.get("target", "unknown")
        hint = c.get("root_cause_hint", "unknown")
        key = normalize_pattern_key(target, hint)

        groups.setdefault(key, []).append(c)

    return groups
```

#### 2.2.3 语义相似度检测（进阶）

```python
# analyzer.py 新增（可选，需要 embedding 模型）

def compute_semantic_similarity(text1: str, text2: str, api_key: str) -> float:
    """
    使用 embedding 计算两个文本的语义相似度。

    返回：0.0 ~ 1.0
    """
    try:
        import urllib.request

        body = json.dumps({
            "model": "claude-embedding-3",
            "texts": [text1, text2],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/embeddings",
            data=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            # 计算余弦相似度（简化版）
            emb1 = result["data"][0]["embedding"]
            emb2 = result["data"][1]["embedding"]

            dot = sum(a * b for a, b in zip(emb1, emb2))
            norm1 = sum(a * a for a in emb1) ** 0.5
            norm2 = sum(b * b for b in emb2) ** 0.5

            return dot / (norm1 * norm2)
    except Exception:
        return 0.0


def merge_similar_records(records: list[dict], similarity_threshold: float = 0.85) -> list[dict]:
    """
    合并语义相似的 instinct records。

    规则：
    1. 计算两两相似度
    2. 相似度 > threshold 的合并
    3. 保留高 confidence 的，累加 applied_count
    4. 合并后的 pattern 包含两个原文的摘要
    """
    if len(records) <= 1:
        return records

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # 简单的 key 匹配 + 语义验证
    merged = []
    used = set()

    for i, rec1 in enumerate(records):
        if i in used:
            continue

        group = [rec1]

        for j, rec2 in enumerate(records[i + 1:], i + 1):
            if j in used:
                continue

            sim = compute_semantic_similarity(
                rec1.get("pattern", "") + " " + rec1.get("correction", ""),
                rec2.get("pattern", "") + " " + rec2.get("correction", ""),
                api_key
            )

            if sim >= similarity_threshold:
                group.append(rec2)
                used.add(j)

        # 合并这一组
        if len(group) == 1:
            merged.append(rec1)
        else:
            # 保留 confidence 最高的
            best = max(group, key=lambda x: x.get("confidence", 0))
            best["merged_from"] = [g["id"] for g in group if g["id"] != best["id"]]
            best["applied_count"] = max(r.get("applied_count", 0) for r in group)
            best["reinforcement_count"] = max(r.get("reinforcement_count", 0) for r in group)
            merged.append(best)

        used.add(i)

    return merged
```

### 2.3 验证闭环（Proposal Outcome Tracking）

#### 2.3.1 设计原理

借鉴 **phantom** 的 5-gate validation 和 **skill-self-evolution** 的 A/B 测试思想：

```
当前问题：
  提案生成后不知道是否有效
  accepted/rejected 没有反馈到 instinct

解决：
  1. 追踪提案处理状态（pending/accepted/rejected/auto-closed）
  2. 根据处理结果更新 instinct confidence
  3. accepted → confidence += 0.2，上限 0.95
  4. rejected → confidence -= 0.1，或移入 archive
  5. auto-closed（7天未处理）→ confidence -= 0.15
```

#### 2.3.2 提案状态追踪

```python
# daemon.py 新增

from enum import Enum
from datetime import datetime, timedelta


class ProposalStatus(Enum):
    PENDING = "pending"          # 创建 < 7 天
    ACCEPTED = "accepted"        # 人工 accept
    REJECTED = "rejected"        # 人工 reject
    AUTO_CLOSED = "auto-closed"  # 7 天未处理
    APPLIED = "applied"          # 改动已应用


def get_proposal_status(proposal_path: Path, auto_close_days: int = 7) -> ProposalStatus:
    """
    判断提案的处理状态。
    """
    if not proposal_path.exists():
        return ProposalStatus.PENDING

    mtime = datetime.fromtimestamp(proposal_path.stat().st_mtime)
    age_days = (datetime.now() - mtime).days

    # 读取提案内容判断状态
    try:
        content = proposal_path.read_text(encoding="utf-8")

        if "<!-- STATUS: accepted -->" in content:
            return ProposalStatus.ACCEPTED
        elif "<!-- STATUS: rejected -->" in content:
            return ProposalStatus.REJECTED
        elif "<!-- STATUS: applied -->" in content:
            return ProposalStatus.APPLIED
    except Exception:
        pass

    # 根据年龄判断
    if age_days > auto_close_days:
        return ProposalStatus.AUTO_CLOSED

    return ProposalStatus.PENDING


def update_instinct_from_proposal_outcomes(config: dict, root: Path) -> dict:
    """
    根据所有提案的处理结果更新 instinct。

    返回：{accepted: N, rejected: N, auto_closed: N}
    """
    proposals_dir = root / config["paths"]["proposals_dir"]
    instinct_path = root / config["paths"]["instinct_dir"] / "instinct-record.json"

    if not proposals_dir.exists():
        return {"accepted": 0, "rejected": 0, "auto_closed": 0}

    # 加载 instinct
    instinct = {"records": []}
    if instinct_path.exists():
        try:
            instinct = json.loads(instinct_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    outcomes = {"accepted": 0, "rejected": 0, "auto_closed": 0}

    # 遍历所有提案
    for p in proposals_dir.glob("*.md"):
        status = get_proposal_status(p, config.get("safety", {}).get("auto_close_days", 7))

        if status == ProposalStatus.ACCEPTED:
            outcomes["accepted"] += 1
            # 从文件名提取 target
            target = extract_target_from_filename(p.name)
            _boost_instinct_confidence(instinct, target, delta=0.2)

        elif status == ProposalStatus.REJECTED:
            outcomes["rejected"] += 1
            target = extract_target_from_filename(p.name)
            _reduce_instinct_confidence(instinct, target, delta=0.1)

        elif status == ProposalStatus.AUTO_CLOSED:
            outcomes["auto_closed"] += 1
            target = extract_target_from_filename(p.name)
            _reduce_instinct_confidence(instinct, target, delta=0.15)

    # 应用时间衰减
    instinct = apply_decay_to_all(instinct)

    # 保存
    instinct_path.parent.mkdir(parents=True, exist_ok=True)
    instinct_path.write_text(json.dumps(instinct, ensure_ascii=False, indent=2))

    return outcomes


def _boost_instinct_confidence(instinct: dict, target: str, delta: float):
    """增强匹配 target 的 instinct record"""
    for record in instinct.get("records", []):
        if target.lower() in record.get("pattern", "").lower():
            record["confidence"] = min(0.95, record.get("confidence", 0.3) + delta)
            record["last_reinforced_at"] = datetime.now().isoformat()
            record["reinforcement_count"] = record.get("reinforcement_count", 0) + 1


def _reduce_instinct_confidence(instinct: dict, target: str, delta: float):
    """降低匹配 target 的 instinct record"""
    for record in instinct.get("records", []):
        if target.lower() in record.get("pattern", "").lower():
            record["confidence"] = max(0.1, record.get("confidence", 0.3) - delta)


def extract_target_from_filename(filename: str) -> str:
    """从提案文件名提取 target"""
    # 格式: 2026-05-01_skill-testing_optimize.md
    match = re.search(r'(\w+-\w+)', filename)
    return match.group(1) if match else filename
```

#### 2.3.3 改进的提案生成流程

```python
# proposer.py 改动

def _save_proposal(content: str, analysis: dict, config: dict, root: Path) -> Path:
    """保存提案文件，包含状态标记"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    target = analysis.get("primary_target", "general").replace(":", "-").replace("/", "-")

    proposals_dir = root / config["paths"]["proposals_dir"]
    proposals_dir.mkdir(parents=True, exist_ok=True)

    proposal_path = proposals_dir / f"{date_str}_{target}_optimize.md"

    # 添加状态标记（方便后续追踪）
    status_header = f"""---
status: pending
created_at: {datetime.now().isoformat()}
analysis_version: 2
---

"""
    proposal_path.write_text(status_header + content, encoding="utf-8")

    # 记录到 instinct
    _record_to_instinct(analysis, proposal_path, confidence=0.5, source="proposal-generated")

    return proposal_path


def mark_proposal(proposal_path: Path, status: str):
    """
    标记提案状态（accepted/rejected/applied）。

    用法：
      from proposer import mark_proposal
      mark_proposal(Path("proposals/2026-05-01_skill-testing_optimize.md"), "accepted")
    """
    if not proposal_path.exists():
        return

    content = proposal_path.read_text(encoding="utf-8")

    # 替换或添加 status 行
    if "<!-- STATUS:" in content:
        content = re.sub(r'<!-- STATUS: \w+ -->', f'<!-- STATUS: {status} -->', content)
    else:
        # 在开头添加
        content = f"<!-- STATUS: {status} -->\n\n{content}"

    # 更新 updated_at
    if "updated_at:" in content:
        content = re.sub(r'updated_at: .*', f'updated_at: {datetime.now().isoformat()}', content)
    else:
        content = content.replace("created_at:", "updated_at:\n", 1)

    proposal_path.write_text(content, encoding="utf-8")

    print(f"✅ 提案已标记为 {status}")
```

### 2.4 预防性安全门控（PreToolUse Safety Gate）

#### 2.4.1 设计原理

借鉴 **no-no-debug** 的三门控（Gate 1: 影响评估 / Gate 2: 验证确认 / Gate 3: 非管理员确认）：

```
当前问题：
  只有错误发生后才记录，无法阻止高风险操作

解决：
  PreToolUse[Bash] hook 增加安全检查
  高风险命令需要用户确认或直接阻止
```

#### 2.4.2 风险命令分类

```python
# safety-gate.py 新增

import re
from dataclasses import dataclass
from typing import Literal


RiskLevel = Literal["blocked", "warn", "safe"]


@dataclass
class RiskCheck:
    pattern: re.Pattern
    risk_level: RiskLevel
    message: str
    suggestion: str = ""


RISKY_PATTERNS = [
    # 最高风险：直接阻止
    RiskCheck(
        pattern=re.compile(r'^\s*rm\s+-rf\s+/(?!proc|sys|dev)'),
        risk_level="blocked",
        message="危险：递归删除根目录",
        suggestion="使用 rm -rf ./ 删除当前目录，或使用 find -delete"
    ),
    RiskCheck(
        pattern=re.compile(r'^\s*rm\s+-rf\s+/\*'),
        risk_level="blocked",
        message="危险：递归删除根目录（glob 模式）",
        suggestion="使用 rm -rf ./* 删除当前目录内容"
    ),
    RiskCheck(
        pattern=re.compile(r'^\s*dd\s+.*of=/dev/(sd|hd|nvme)'),
        risk_level="blocked",
        message="危险：直接写入物理磁盘",
        suggestion="使用虚拟磁盘或镜像文件"
    ),
    RiskCheck(
        pattern=re.compile(r'^\s*mkfs\s+'),
        risk_level="blocked",
        message="危险：格式化分区",
        suggestion="确认分区号，使用 mkfs.ext4 /dev/xxxN"
    ),

    # 高风险：警告
    RiskCheck(
        pattern=re.compile(r'git\s+push\s+--force'),
        risk_level="warn",
        message="危险：强制推送会覆盖远程历史",
        suggestion="使用 git push --force-with-lease 更安全"
    ),
    RiskCheck(
        pattern=re.compile(r'git\s+push\s+-f'),
        risk_level="warn",
        message="危险：强制推送",
        suggestion="考虑使用 --force-with-lease"
    ),
    RiskCheck(
        pattern=re.compile(r'drop\s+(table|database)'),
        risk_level="warn",
        message="危险：删除数据库对象",
        suggestion="使用 DROP TABLE IF EXISTS 或先备份"
    ),
    RiskCheck(
        pattern=re.compile(r'truncate\s+--size=0'),
        risk_level="warn",
        message="警告：清空文件",
        suggestion="确认文件不需要备份"
    ),
    RiskCheck(
        pattern=re.compile(r'shutdown|reboot|init\s+0|init\s+6'),
        risk_level="warn",
        message="警告：系统关机/重启",
        suggestion="确认无其他用户在使用"
    ),
    RiskCheck(
        pattern=re.compile(r'chmod?\s+[47]000'),
        risk_level="warn",
        message="警告：设置危险权限（setuid root）",
        suggestion="确认这是必要的"
    ),

    # 中等风险：提示
    RiskCheck(
        pattern=re.compile(r'yarn\s+remove\s+.*--dev|--save-dev'),
        risk_level="warn",
        message="提示：删除 dev 依赖可能影响构建",
        suggestion="确认是否还需要开发"
    ),
]


def check_command_safety(command: str) -> tuple[RiskLevel, str]:
    """
    检查命令安全性。

    返回: (risk_level, message)
    """
    for check in RISKY_PATTERNS:
        if check.pattern.search(command):
            return check.risk_level, f"{check.message}\n建议: {check.suggestion}"

    return "safe", ""


def get_protected_paths() -> list[str]:
    """
    返回需要保护的路径模式。
    """
    return [
        r'/etc/passwd',
        r'/etc/shadow',
        r'/etc/sudoers',
        r'\.ssh/authorized_keys',
        r'\.git/hooks',
        r'/var/log/',
        r'/usr/local/bin/',
        r'node_modules/.*/bin/',  # 避免误删全局工具
    ]


def check_protected_paths(command: str) -> tuple[bool, str]:
    """
    检查是否涉及受保护路径。
    """
    protected = get_protected_paths()
    for path_pattern in protected:
        if re.search(path_pattern, command):
            return True, f"操作涉及受保护路径: {path_pattern}"

    return False, ""
```

#### 2.4.3 集成到 Hook

```bash
# hooks/bin/safety-check.sh 增强版

#!/bin/bash
# PreToolUse[Bash] Hook: 安全门控

COMMAND="$1"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"

# 调用 Python 安全检查
RESULT=$(python3 "$PLUGIN_ROOT/hooks/bin/safety-check.py" "$COMMAND" 2>/dev/null)
RISK_LEVEL=$(echo "$RESULT" | jq -r '.risk_level')
MESSAGE=$(echo "$RESULT" | jq -r '.message')

if [ "$RISK_LEVEL" = "blocked" ]; then
    echo "🚫 BLOCKED: $MESSAGE"
    exit 1
elif [ "$RISK_LEVEL" = "warn" ]; then
    echo "⚠️  WARNING: $MESSAGE"
    echo ""
    echo "按 Enter 继续执行，或 Ctrl+C 取消..."
    read -r
fi

exit 0
```

```python
# hooks/bin/safety-check.py 新增文件

#!/usr/bin/env python3
"""
安全门控检查脚本。
由 safety-check.sh 调用，输出 JSON 结果。
"""
import json
import sys
from pathlib import Path

# 导入安全检查模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "evolve-daemon"))
from safety_gate import check_command_safety, check_protected_paths


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"risk_level": "safe", "message": ""}))
        return

    command = sys.argv[1]

    # 检查风险命令
    risk_level, message = check_command_safety(command)

    # 检查受保护路径
    if risk_level == "safe":
        is_protected, protected_msg = check_protected_paths(command)
        if is_protected:
            risk_level = "warn"
            message = protected_msg

    result = {
        "risk_level": risk_level,
        "message": message
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

### 2.5 周期性主动复盘（Periodic Review）

#### 2.5.1 设计原理

借鉴 **no-no-debug** 的周期性 review（每 3 天）和 **Sibyl** 的 8 维度分析：

```
当前问题：
  等待触发条件（5 会话 / 3 纠正 / 6h）才会分析
  没有主动发现问题的机制

解决：
  增加周期性 review 模式
  每 3 天执行一次 8 维度全量分析
  生成 review 报告，更新 instinct
```

#### 2.5.2 8 维度定义

```python
# review_engine.py 新增

from enum import Enum
from typing import Optional
from dataclasses import dataclass


class ReviewDimension(Enum):
    DATA_ACCURACY = "data_accuracy"      # 数据准确性
    ENVIRONMENT_SAFETY = "env_safety"     # 环境安全
    FORESIGHT = "foresight"              # 前瞻性（permission/cache/migration）
    USER_PERSPECTIVE = "user_perspective" # 用户视角
    VERIFICATION = "verification"        # 验证完整性
    MEMORY_CONSISTENCY = "memory"        # 记忆一致性
    TOOL_JUDGMENT = "tool_judgment"      # 工具选择判断
    REVIEW_COMPLETENESS = "review"       # review 完整性


@dataclass
class DimensionScore:
    dimension: ReviewDimension
    score: float          # 0.0 ~ 1.0
    observations: list[str]
    recommendations: list[str]


# 维度评分规则
DIMENSION_RULES = {
    ReviewDimension.DATA_ACCURACY: {
        "positive": ["数据验证通过", "类型检查通过", "边界条件处理正确"],
        "negative": ["数据精度丢失", "浮点数比较问题", "null 未检查"],
        "weight": 0.15
    },
    ReviewDimension.ENVIRONMENT_SAFETY: {
        "positive": ["环境变量正确加载", "依赖版本兼容", "配置分离"],
        "negative": ["hardcoded 凭证", "依赖版本冲突", "环境不一致"],
        "weight": 0.20
    },
    ReviewDimension.FORESIGHT: {
        "positive": ["预留扩展点", "接口版本兼容", "错误码覆盖完整"],
        "negative": ["硬编码 magic number", "缺少 error handling", "无 timeout"],
        "weight": 0.10
    },
    ReviewDimension.USER_PERSPECTIVE: {
        "positive": ["用户输入验证", "友好的错误提示", "合理的默认值"],
        "negative": ["输入无验证", "错误信息不友好", "默认值不合理"],
        "weight": 0.10
    },
    ReviewDimension.VERIFICATION: {
        "positive": ["测试覆盖充分", "集成测试通过", "验证步骤完整"],
        "negative": ["缺少测试", "测试跳过", "验证不完整"],
        "weight": 0.15
    },
    ReviewDimension.MEMORY_CONSISTENCY: {
        "positive": ["遵循项目惯例", "命名一致", "代码风格统一"],
        "negative": ["违反项目惯例", "命名不一致", "风格混乱"],
        "weight": 0.10
    },
    ReviewDimension.TOOL_JUDGMENT: {
        "positive": ["工具选择恰当", "参数使用正确", "效率最优"],
        "negative": ["工具使用不当", "参数错误", "效率低下"],
        "weight": 0.10
    },
    ReviewDimension.REVIEW_COMPLETENESS: {
        "positive": ["review 覆盖全面", "关键路径检查", "安全漏洞扫描"],
        "negative": ["review 遗漏关键点", "缺少安全检查", "边界条件未覆盖"],
        "weight": 0.10
    }
}
```

#### 2.5.3 Review Engine 实现

```python
# review_engine.py 完整实现

#!/usr/bin/env python3
"""
周期性 Review 引擎。
每 N 天执行一次 8 维度全量分析，生成报告，更新 instinct。
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))


def load_config():
    """加载配置"""
    config_path = Path(__file__).parent / "config.yaml"
    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception:
        return {
            "review": {
                "interval_days": 3,
                "dimensions": 8
            }
        }


def find_project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def load_sessions_for_review(data_dir: Path, days: int = 30) -> list[dict]:
    """加载最近 N 天的 sessions"""
    sessions_file = data_dir / "sessions.jsonl"
    if not sessions_file.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    sessions = []

    with open(sessions_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
                ts = datetime.fromisoformat(s.get("timestamp", "2000-01-01"))
                if ts >= cutoff:
                    sessions.append(s)
            except Exception:
                continue

    return sessions


def load_instinct_records(instinct_dir: Path) -> list[dict]:
    """加载 instinct records"""
    instinct_file = instinct_dir / "instinct-record.json"
    if not instinct_file.exists():
        return []

    try:
        data = json.loads(instinct_file.read_text(encoding="utf-8"))
        return data.get("records", [])
    except Exception:
        return []


def analyze_dimension(
    dimension: ReviewDimension,
    sessions: list[dict],
    instinct_records: list[dict]
) -> DimensionScore:
    """
    分析单个维度。
    """
    rules = DIMENSION_RULES[dimension]
    observations = []
    positive_count = 0
    negative_count = 0

    # 从 sessions 分析
    for s in sessions:
        corrections = s.get("corrections", [])

        for c in corrections:
            context = c.get("context", "").lower()
            correction = c.get("user_correction", "").lower()
            hint = c.get("root_cause_hint", "").lower()

            combined_text = f"{context} {correction} {hint}"

            for keyword in rules["positive"]:
                if keyword.lower() in combined_text:
                    positive_count += 1
                    break

            for keyword in rules["negative"]:
                if keyword.lower() in combined_text:
                    negative_count += 1
                    observations.append(f"检测到: {keyword}")
                    break

    # 从 instinct 分析（高 confidence 的 pattern）
    for rec in instinct_records:
        if rec.get("confidence", 0) >= 0.7:
            pattern_text = rec.get("pattern", "").lower()

            for keyword in rules["negative"]:
                if keyword.lower() in pattern_text:
                    negative_count += 1
                    if rec.get("pattern") not in observations:
                        observations.append(f"高置信度问题: {rec.get('pattern')}")
                    break

    # 计算分数
    total = positive_count + negative_count
    if total == 0:
        score = 1.0  # 无数据，默认满分
    else:
        score = positive_count / total

    # 生成建议
    recommendations = []
    if negative_count > 5:
        recommendations.append(f"该维度有 {negative_count} 个负面模式，建议优先处理高置信度问题")
    if positive_count > negative_count * 2:
        recommendations.append("该维度表现良好，可适当降低关注度")

    return DimensionScore(
        dimension=dimension,
        score=round(score, 3),
        observations=observations[:5],  # 最多 5 条
        recommendations=recommendations
    )


def generate_review_report(
    sessions: list[dict],
    scores: list[DimensionScore],
    config: dict,
    root: Path
) -> str:
    """生成 review 报告"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    week_num = datetime.now().isocalendar()[1]

    content = f"""# 进化 Review 报告: W{week_num}

**生成时间**: {datetime.now().isoformat()}
**分析范围**: 最近 {config.get("review", {}).get("interval_days", 30)} 天
**会话数量**: {len(sessions)}

## 维度评分

| 维度 | 分数 | 状态 |
|------|------|------|
"""

    for score in scores:
        status = "✅ 良好" if score.score >= 0.7 else "⚠️ 注意" if score.score >= 0.4 else "❌ 需改进"
        content += f"| {score.dimension.value} | {score.score:.1%} | {status} |\n"

    content += "\n## 详细分析\n\n"

    for score in scores:
        content += f"### {score.dimension.value}\n\n"
        content += f"**分数**: {score.score:.1%}\n\n"

        if score.observations:
            content += "**观察到的模式**:\n"
            for obs in score.observations:
                content += f"- {obs}\n"
            content += "\n"

        if score.recommendations:
            content += "**建议**:\n"
            for rec in score.recommendations:
                content += f"- {rec}\n"
            content += "\n"

    content += f"""## 行动项

"""

    # 高优先级问题
    low_scores = [s for s in scores if s.score < 0.5]
    if low_scores:
        content += "### 需要改进的维度\n\n"
        for s in low_scores:
            content += f"- [{s.dimension.value}] 分数 {s.score:.1%}\n"
        content += "\n"

    content += """## 下次 Review

预计 {interval} 天后自动生成。

---
*本报告由 evolve-daemon 自动生成*
""".format(interval=config.get("review", {}).get("interval_days", 3))

    return content


def save_review_report(content: str, config: dict, root: Path) -> Path:
    """保存 review 报告"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    week_num = datetime.now().isocalendar()[1]

    proposals_dir = root / config.get("paths", {}).get("proposals_dir", ".claude/proposals")
    review_dir = proposals_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)

    report_path = review_dir / f"W{week_num:02d}_{date_str}_review.md"
    report_path.write_text(content, encoding="utf-8")

    return report_path


def run_review(config: dict, root: Path) -> dict:
    """
    执行完整的 review 流程。
    """
    data_dir = root / config.get("paths", {}).get("data_dir", ".claude/data")
    instinct_dir = root / config.get("paths", {}).get("instinct_dir", "instinct")

    # 1. 加载数据
    sessions = load_sessions_for_review(
        data_dir,
        days=config.get("review", {}).get("interval_days", 30)
    )
    instinct_records = load_instinct_records(instinct_dir)

    # 2. 分析每个维度
    scores = []
    for dimension in ReviewDimension:
        score = analyze_dimension(dimension, sessions, instinct_records)
        scores.append(score)

    # 3. 生成报告
    report = generate_review_report(sessions, scores, config, root)
    report_path = save_review_report(report, config, root)

    # 4. 更新 instinct（基于 review 结果）
    _update_instinct_from_review(scores, config, root)

    return {
        "sessions_analyzed": len(sessions),
        "scores": {s.dimension.value: s.score for s in scores},
        "report_path": str(report_path)
    }


def _update_instinct_from_review(scores: list[DimensionScore], config: dict, root: Path):
    """根据 review 结果更新 instinct"""
    instinct_dir = root / config.get("paths", {}).get("instinct_dir", "instinct")
    instinct_file = instinct_dir / "instinct-record.json"

    instinct = {"records": []}
    if instinct_file.exists():
        try:
            instinct = json.loads(instinct_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    for score in scores:
        if score.score < 0.5:
            # 低分维度：降低相关 instinct 的 confidence
            for record in instinct.get("records", []):
                if score.dimension.value in record.get("pattern", "").lower():
                    record["confidence"] = max(0.1, record.get("confidence", 0.3) - 0.1)
                    record["last_reinforced_at"] = datetime.now().isoformat()

    # 应用时间衰减
    instinct = apply_decay_to_all(instinct)

    instinct_file.write_text(json.dumps(instinct, ensure_ascii=False, indent=2))


def main():
    config = load_config()
    root = find_project_root()

    print("🔍 开始执行周期性 review...")

    result = run_review(config, root)

    print(f"✅ Review 完成")
    print(f"   分析会话: {result['sessions_analyzed']}")
    print(f"   报告路径: {result['report_path']}")

    for dim, score in result["scores"].items():
        print(f"   {dim}: {score:.1%}")


if __name__ == "__main__":
    main()
```

---

## 3. 实现路径

### 3.1 分阶段实施

```
Phase 1: P0 紧急改进（1-2天）
  ├─ instinct 时间衰减机制
  └─ 提案效果闭环追踪

Phase 2: P1 重要改进（2-3天）
  ├─ PreToolUse 安全门控
  └─ 语义去重基础版

Phase 3: P2 增强改进（3-5天）
  ├─ 语义去重进阶版（embedding）
  ├─ 周期性 8 维 review
  └─ UserPromptSubmit 纠正捕获
```

### 3.2 文件变更清单

```
evolve-daemon/
├── instinct_updater.py    # 新增: 时间衰减、增强/减弱 confidence
├── analyzer.py            # 新增: 归一化 key、语义去重
├── proposer.py            # 修改: 提案状态追踪
├── daemon.py              # 修改: 提案结果闭环、周期性 review 触发
├── review_engine.py       # 新增: 8 维 review 引擎
├── safety_gate.py         # 新增: 安全门控规则
└── config.yaml            # 新增: review、decay 配置

hooks/bin/
├── safety-check.py        # 新增: 安全检查脚本
└── safety-check.sh        # 修改: 增强 PreToolUse[Bash] 门控
```

---

## 4. 配置变更

### 4.1 config.yaml 新增配置

```yaml
# evolve-daemon/config.yaml

# ... 现有配置 ...

# 新增: 时间衰减
decay:
  half_life_days: 90        # 半衰期（天）
  floor: 0.1               # 最低 confidence
  reinforcement_bonus: 0.05 # 每次验证通过 +5% 半衰期

# 新增: Review 引擎
review:
  enabled: true
  interval_days: 3         # 每 3 天执行一次
  dimensions: 8             # 8 个分析维度

# 新增: 安全门控
safety_gate:
  enabled: true
  auto_confirm_risky: false # 高风险命令是否自动确认

# 新增: 语义去重
dedup:
  enabled: true
  similarity_threshold: 0.85 # 相似度阈值
```

---

## 5. 与其他系统的对比

| 维度 | claude-harness-kit | no-no-debug | skill-self-evolution | phantom |
|------|-------------------|-------------|---------------------|---------|
| **时间衰减** | ✅ 90天半衰期 | ❌ | ✅ 60天 | ✅ |
| **语义去重** | ✅ embedding | ❌ | ❌ | ❌ |
| **A/B 验证** | 提案闭环 | ❌ | A/B test | 5-gate |
| **安全门控** | PreToolUse | 三门控 | ❌ | ❌ |
| **主动复盘** | 8维/3天 | 3天 | ❌ | ❌ |
| **instinct** | ✅ | error_tracker | 权重优化 | prompt overlay |

---

## 6. 预期效果

### 6.1 量化指标

| 指标 | 改进前 | 改进后 |
|------|-------|--------|
| instinct 噪音率 | ~40% stale 数据 | < 10% stale |
| 提案接受率 | 未知 | > 60% |
| 相同问题重复发生率 | 高 | < 20% |
| 高风险操作拦截率 | 0% | > 90% |

### 6.2 主观效果

- **更精准**：相似 pattern 合并后，减少重复提案
- **更及时**：衰减机制让新问题快速浮现
- **更安全**：高风险命令被拦截或警告
- **更主动**：周期性 review 发现预防性问题

---

## 7. 附录

### 7.1 参考项目

- [no-no-debug](https://github.com/summerliuuu/no-no-debug) - 18维度跟踪 + 规则积累
- [skill-self-evolution](https://github.com/Arxchibobo/skill-self-evolution) - 60天半衰期 + A/B测试
- [phantom](https://github.com/ghostwright/phantom) - 5-gate validation
- [Hone](https://github.com/invariant-logic/hone) - SAGE confidence decay
- [Sibyl](https://github.com/Sibyl-Research-Team/AutoResearch-SibylSystem) - 8维度分析

### 7.2 术语表

| 术语 | 定义 |
|------|------|
| **半衰期** | 数据权重衰减到 50% 所需的时间 |
| **reinforcement** | pattern 被反复验证的行为 |
| **SAGE confidence** | 带有时间衰减的置信度计算 |
| **三门控** | no-no-debug 的预防性检查机制 |
| **5-gate validation** | phantom 的提案验证流程 |