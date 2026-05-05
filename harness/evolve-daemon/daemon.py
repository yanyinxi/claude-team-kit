#!/usr/bin/env python3
"""
进化守护进程入口 — 支持外部触发和内置定时任务。

用法:
  python3 daemon.py check          # 仅检查触发条件
  python3 daemon.py run            # 检查并执行分析（外部触发模式）
  python3 daemon.py start          # 启动内置调度器（内部定时触发）
  python3 daemon.py stop           # 停止内置调度器
  python3 daemon.py status         # 查看系统状态
  python3 daemon.py rollback-check # 检查回滚状态（观察期到期检查）
  python3 daemon.py install-launchd # macOS: 安装 LaunchAgent（外部触发）
  python3 daemon.py health         # 健康检查

触发条件（满足任一即触发）:
  - 累计 >= 5 个新会话未分析
  - 同一 target 被纠正 >= 3 次
  - 距上次分析 >= 6 小时

内置调度器配置（config.yaml）:
  daemon:
    mode: internal           # external/internal/both
    scheduler_interval: 30 minutes
    run_on_startup: true

回滚机制:
  - apply_change.py 记录 applied 状态的提案到 proposal_history.json
  - rollback.py 检查观察期（observation_days），到期后评估指标并回滚/固化
  - daemon.py 的 run/rollback-check 命令自动触发回滚检查
  - 调度器每次心跳检测都会自动调用回滚检查
  - 回滚事件会记录到 instinct-record.json
"""
import json
import logging
import os
import signal
import sys
import time
try:
    import yaml
except ImportError:
    yaml = None
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from _find_root import find_root
import kb_shared


def handle_exception(e, context, reraise=False, default_return=None, log_level="error"):
    """统一异常处理包装函数（本地定义避免循环依赖）"""
    error_msg = f"{context}: {type(e).__name__}: {e}"
    log_func = getattr(logger, log_level.lower(), logger.error)
    log_func(error_msg)
    if reraise:
        raise
    return default_return


# 信号处理标记
_shutdown_requested = False
_graceful_restart_requested = False
_open_files = []
_pid_file = None

def graceful_shutdown(signum, frame):
    """优雅退出处理函数"""
    global _shutdown_requested
    signame = signal.Signals(signum).name
    print(f"\n[{datetime.now().isoformat()}] 收到 {signame} 信号，正在优雅关闭...")
    _shutdown_requested = True

    # 停止调度器（如果正在运行）
    try:
        from scheduler import _manager
        if _manager.is_running():
            print("正在停止调度器...")
            _manager.stop()
            print("调度器已停止")
    except Exception as e:
        print(f"停止调度器失败: {e}")

    # 关闭打开的文件
    for f in _open_files:
        try:
            if f and not f.closed:
                f.close()
        except OSError:
            pass  # 文件已关闭或不存在
        except Exception:
            pass  # 其他错误忽略

    # 保存状态（确保分析状态不丢失）
    try:
        root = find_root()
        config = load_config()
        data_dir = root / config["paths"]["data_dir"]
        state_file = data_dir / "analysis_state.json"
        if state_file.exists():
            # 更新时间戳表明最后一次检查
            try:
                state = json.loads(state_file.read_text())
                state["last_shutdown_time"] = datetime.now().isoformat()
                state["shutdown_signal"] = signame
                state_file.write_text(json.dumps(state, indent=2))
                print(f"状态已保存: {state_file}")
            except (json.JSONDecodeError, OSError) as e:
                handle_exception(e, f"解析/写入分析状态失败", log_level="warning")
    except Exception as e:
        handle_exception(e, "保存关闭状态失败", log_level="warning")
        print(f"保存状态失败: {e}")

    print("[退出] 优雅关闭完成")
    sys.exit(0)

def graceful_restart(signum, frame):
    """优雅重启处理函数（SIGUSR1）"""
    global _graceful_restart_requested
    signame = signal.Signals(signum).name
    print(f"\n[{datetime.now().isoformat()}] 收到 {signame} 信号，正在优雅重启...")

    # 标记需要重启
    _graceful_restart_requested = True

    # 停止调度器（如果正在运行）
    try:
        from scheduler import _manager
        if _manager.is_running():
            print("正在停止调度器...")
            _manager.stop()
            print("调度器已停止")
    except Exception as e:
        print(f"停止调度器失败: {e}")

    # 保存当前状态
    try:
        root = find_root()
        config = load_config()
        data_dir = root / config["paths"]["data_dir"]
        state_file = data_dir / "analysis_state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                state["last_restart_time"] = datetime.now().isoformat()
                state["restart_signal"] = signame
                state_file.write_text(json.dumps(state, indent=2))
                print(f"状态已保存: {state_file}")
            except (json.JSONDecodeError, OSError):
                pass
    except Exception as e:
        print(f"保存状态失败: {e}")

    print("[重启] 优雅重启完成，准备重新启动调度器")
    sys.exit(0)  # 外部可以用启动脚本重新启动


# 注册信号处理器
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGHUP, graceful_shutdown)
signal.signal(signal.SIGUSR1, graceful_restart)  # 优雅重启信号


def _health_check() -> dict:
    """
    健康检查方法 - 检查进程状态和关键文件

    返回:
        dict: 健康状态 {"healthy": bool, "checks": [...], "message": str}
    """
    checks = []
    is_healthy = True
    root = None
    config = None

    try:
        root = find_root()
        config = load_config()
    except Exception as e:
        checks.append({
            "name": "config_load",
            "status": "error",
            "message": f"配置加载失败: {e}"
        })
        is_healthy = False
        return {"healthy": is_healthy, "checks": checks, "message": "配置加载失败"}

    # 检查 1: 配置文件存在性
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        checks.append({"name": "config_exists", "status": "ok", "message": "配置文件存在"})
    else:
        checks.append({"name": "config_exists", "status": "error", "message": "配置文件不存在"})
        is_healthy = False

    # 检查 2: 数据目录存在性
    data_dir = root / config["paths"]["data_dir"]
    if data_dir.exists():
        checks.append({"name": "data_dir_exists", "status": "ok", "message": f"数据目录存在: {data_dir}"})
    else:
        checks.append({"name": "data_dir_exists", "status": "warning", "message": f"数据目录不存在，将自动创建: {data_dir}"})

    # 检查 3: sessions.jsonl 可读性
    sessions_file = data_dir / "sessions.jsonl"
    if sessions_file.exists():
        try:
            with open(sessions_file, 'r', encoding='utf-8') as f:
                f.read(100)  # 尝试读取前100字符
            checks.append({"name": "sessions_readable", "status": "ok", "message": "sessions.jsonl 可读"})
        except Exception as e:
            checks.append({"name": "sessions_readable", "status": "error", "message": f"sessions.jsonl 读取失败: {e}"})
            is_healthy = False
    else:
        checks.append({"name": "sessions_readable", "status": "warning", "message": "sessions.jsonl 不存在（首次运行）"})

    # 检查 4: 调度器状态
    try:
        from scheduler import _manager
        if _manager.is_running():
            checks.append({"name": "scheduler_running", "status": "ok", "message": "调度器运行中"})
        else:
            checks.append({"name": "scheduler_running", "status": "warning", "message": "调度器未运行"})
    except Exception as e:
        checks.append({"name": "scheduler_running", "status": "warning", "message": f"无法检查调度器: {e}"})

    # 检查 5: 分析状态文件
    state_file = data_dir / "analysis_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            last_analyze = state.get("last_analyze_time")
            if last_analyze:
                last_time = datetime.fromisoformat(last_analyze)
                hours_since = (datetime.now() - last_time).total_seconds() / 3600
                checks.append({
                    "name": "last_analysis",
                    "status": "ok",
                    "message": f"上次分析: {hours_since:.1f} 小时前"
                })
            else:
                checks.append({"name": "last_analysis", "status": "warning", "message": "无上次分析记录"})
        except Exception as e:
            checks.append({"name": "last_analysis", "status": "warning", "message": f"无法读取分析状态: {e}"})
    else:
        checks.append({"name": "last_analysis", "status": "warning", "message": "无分析状态文件（首次运行）"})

    # 检查 6: 路径验证
    try:
        # 简单路径验证：检查关键目录是否存在
        required_dirs = ["data_dir", "proposals_dir", "skills_dir", "agents_dir", "rules_dir"]
        invalid_paths = []
        for dir_key in required_dirs:
            dir_path = root / config["paths"].get(dir_key, "")
            if dir_path and not dir_path.exists():
                invalid_paths.append(dir_key)

        if not invalid_paths:
            checks.append({"name": "paths_valid", "status": "ok", "message": "所有关键路径有效"})
        else:
            checks.append({"name": "paths_valid", "status": "warning", "message": f"部分路径不存在: {invalid_paths}（将在需要时创建）"})
    except Exception as e:
        checks.append({"name": "paths_valid", "status": "warning", "message": f"路径验证失败: {e}"})

    # 检查 7: 备份目录存在性
    backup_dir = root / ".claude/data/backups"
    if backup_dir.exists():
        backup_files = list(backup_dir.glob("config.yaml.*.bak"))
        checks.append({
            "name": "backup_dir",
            "status": "ok",
            "message": f"备份目录存在，{len(backup_files)} 个配置文件备份"
        })
    else:
        checks.append({
            "name": "backup_dir",
            "status": "warning",
            "message": "备份目录不存在（将在下次运行时创建）"
        })

    # 构建消息
    if is_healthy:
        message = "所有健康检查通过"
    else:
        failed = [c["name"] for c in checks if c["status"] == "error"]
        message = f"健康检查失败: {', '.join(failed)}"

    return {"healthy": is_healthy, "checks": checks, "message": message}


def _backup_config(config_path: Path, backup_dir: Path, max_backups: int = 5) -> str | None:
    """
    备份配置文件

    参数:
        config_path: 配置文件路径
        backup_dir: 备份目录
        max_backups: 最大保留备份数

    返回:
        str: 备份文件路径，失败返回 None
    """
    if not config_path.exists():
        return None

    # 创建备份目录
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"config.yaml.{timestamp}.bak"

    try:
        import shutil
        shutil.copy2(config_path, backup_file)
        print(f"[备份] 配置文件已备份: {backup_file}")

        # 清理旧备份，保留最近 max_backups 个
        existing_backups = sorted(
            backup_dir.glob("config.yaml.*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if len(existing_backups) > max_backups:
            for old_backup in existing_backups[max_backups:]:
                old_backup.unlink()
                print(f"[备份] 已删除旧备份: {old_backup}")

        return str(backup_file)
    except Exception as e:
        print(f"[备份] 配置文件备份失败: {e}")
        return None


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    if yaml is not None:
        with open(config_path) as f:
            return yaml.safe_load(f)
    # Fallback: inline default config when PyYAML is not installed
    return {
        "daemon": {"schedule": "*/30 * * * *", "idle_trigger_minutes": 120, "extract_timeout_seconds": 5},
        "thresholds": {"min_new_sessions": 1, "min_same_pattern_corrections": 2, "max_hours_since_last_analyze": 6},
        "safety": {"max_proposals_per_day": 3, "auto_close_days": 7, "breaker": {"max_consecutive_rejects": 3, "pause_days": 30}},
        "paths": {"data_dir": ".claude/data", "proposals_dir": ".claude/proposals", "skills_dir": "skills", "agents_dir": "agents", "rules_dir": "rules", "instinct_dir": "memory"},
    }


def load_new_sessions(data_dir: Path, last_analyzed_id: str | None = None) -> list[dict]:
    """加载自上次分析以来的新会话"""
    sessions = kb_shared.load_sessions(data_dir)

    if last_analyzed_id:
        try:
            idx = next(i for i, s in enumerate(sessions)
                       if s.get("session_id") == last_analyzed_id)
            sessions = sessions[idx + 1:]
        except StopIteration:
            pass

    return sessions


def check_thresholds(sessions: list[dict], config: dict, last_analyze_time: datetime | None = None) -> list[str]:
    """检查是否满足触发条件"""
    thresholds = config["thresholds"]
    triggers = []

    # 条件1: 新会话数达标
    if len(sessions) >= thresholds["min_new_sessions"]:
        triggers.append(f"new_sessions: {len(sessions)} >= {thresholds['min_new_sessions']}")

    # 条件2: 距上次分析超过最大间隔
    if last_analyze_time:
        hours_since = (datetime.now() - last_analyze_time).total_seconds() / 3600
        if hours_since >= thresholds["max_hours_since_last_analyze"]:
            triggers.append(f"time_elapsed: {hours_since:.1f}h >= {thresholds['max_hours_since_last_analyze']}h")

    # 条件3: 同一 target 被同一模式多次纠正
    pattern_groups: dict[str, list] = {}
    for s in sessions:
        for c in s.get("corrections", []):
            key = f"{c.get('target', 'unknown')}:{c.get('root_cause_hint', 'unknown')}"
            pattern_groups.setdefault(key, []).append(c)

    for key, corrections in pattern_groups.items():
        if len(corrections) >= thresholds["min_same_pattern_corrections"]:
            triggers.append(
                f"pattern: {key} corrected {len(corrections)}x >= "
                f"{thresholds['min_same_pattern_corrections']}"
            )

    return triggers


def run_analysis(config: dict, root: Path, sessions: list[dict]):
    """执行分析并生成提案（4维度进化闭环）"""

    # ── 新增：会话级进化 ────────────────────────────────
    # 会话结束后自动调用 integrated_evolution.py
    try:
        from integrated_evolution import run_session_evolution
        run_session_evolution(max_age_hours=0)  # 不限制会话，分析所有未知错误
    except Exception:
        pass  # 会话级进化失败不影响主流程

    # ── 改动：分析前过滤已知错误 ──────────────────────
    # 覆盖两个信号源：corrections (用户纠正) + failure_stats (工具失败)
    from kb_shared import load_active_kb, is_covered_by_kb
    kb = load_active_kb(root)
    kb_by_dimension = {}
    for entry in kb:
        dim = entry.get("dimension", "unknown")
        kb_by_dimension.setdefault(dim, []).append(entry)

    # 统计两个信号源
    original_corrections = sum(len(s.get("corrections", [])) for s in sessions)
    original_tool_failures = sum(
        s.get("rich_context", {}).get("failure_stats", {}).get("total", 0)
        for s in sessions
    )

    # 过滤 corrections
    filtered_sessions = []
    filtered_corrections = 0
    for session in sessions:
        original_corrections = session.get("corrections", [])
        new_corrections = []
        for corr in original_corrections:
            corr_text = corr.get("user_correction", "")
            covered, matched_id = is_covered_by_kb(corr_text, root)
            if covered:
                filtered_corrections += 1
            else:
                new_corrections.append(corr)
        session["corrections"] = new_corrections
        if new_corrections:
            filtered_sessions.append(session)

    # 检查 failure_stats 覆盖（按失败类型 + 工具）
    # 双轨兼容：rich_context.failure_stats + 直接字段
    all_failure_types = []
    all_failure_tools = []
    for s in sessions:
        # 新版 rich_context 格式
        fs = s.get("rich_context", {}).get("failure_stats", {})
        for et in fs.get("failure_types", {}).keys():
            all_failure_types.append(et)
        for tool in fs.get("failure_tools", {}).keys():
            all_failure_tools.append(tool)
        # 兼容旧格式：直接从字段读取
        for et in s.get("failure_types", {}).keys():
            if et not in all_failure_types:
                all_failure_types.append(et)
        tf = s.get("tool_failures", 0)
        if tf > 0:
            all_failure_tools.append(f"unknown_tool({tf})")

    covered_failure_count = 0
    for ft in all_failure_types:
        covered, _ = is_covered_by_kb(ft, root)
        if covered:
            covered_failure_count += 1
    for ft in all_failure_tools:
        covered, _ = is_covered_by_kb(ft, root)
        if covered:
            covered_failure_count += 1

    total_filtered = filtered_corrections + covered_failure_count

    if total_filtered > 0:
        print(f"  [KB过滤] corrections: {filtered_corrections}, failure_stats: {covered_failure_count}, 总计: {total_filtered}")

    # ── BUG 修复：不能仅凭 corrections 为空就跳过分析 ──────────────────
    # analyzer.py 有双轨信号：corrections + rich_context.failure_stats
    # failure_stats 中的失败类型（如 tool:not_found_error）也需要分析
    # 必须检查：会话是否还有 failure_stats 数据
    has_any_failure_stats = any(
        s.get("rich_context", {}).get("failure_stats", {}).get("total", 0) > 0
        for s in sessions
    )
    if not filtered_sessions and not has_any_failure_stats:
        print("所有错误已被知识库覆盖，跳过 daemon 分析")
        return
    elif not filtered_sessions and has_any_failure_stats:
        print(f"  [KB过滤] corrections 已全部覆盖，但仍有 failure_stats 需要分析")

    if filtered_sessions:
        sessions = filtered_sessions

    # ── 原有流程 ───────────────────────────────────
    # 1. 语义提取（每个新会话）
    try:
        from extract_semantics import analyze_sessions
        analyze_sessions(sessions, root)
    except Exception:
        pass  # 语义提取失败不影响主流程

    # 2. 数据聚合分析
    from analyzer import aggregate_and_analyze
    analysis = aggregate_and_analyze(sessions, config, root)

    if not analysis.get("should_propose"):
        print("分析完成，当前无需提案")
        return

    # 3. 4维度分发
    try:
        from evolve_dispatcher import dispatch_evolution
        decisions = dispatch_evolution(analysis, config, root, sessions)
    except ImportError:
        decisions = []

    # 4. 执行决策
    applied_count = 0
    proposed_count = 0
    skipped_count = 0

    for decision in decisions:
        dimension = decision.get("dimension", "")
        action = decision.get("action", "")
        target = decision.get("target", "")

        try:
            if action == "auto_apply":
                _execute_auto_apply(decision, analysis, config, root)
                applied_count += 1
            elif action == "propose":
                _execute_propose(decision, analysis, config, root)
                proposed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"⚠️  [{dimension}] {target} 执行失败: {e}")

    # 更新分析状态
    if not sessions:
        print("⚠️ 无会话数据可分析")
        return
    state_file = root / config["paths"]["data_dir"] / "analysis_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "last_analyzed_session_id": sessions[-1]["session_id"],
        "last_analyze_time": datetime.now().isoformat(),
        "total_sessions_analyzed": len(sessions),
        "decisions_applied": applied_count,
        "decisions_proposed": proposed_count,
    }
    state_file.write_text(json.dumps(state, indent=2))

    print(f"✅ 分析完成: auto_apply={applied_count}, propose={proposed_count}, skip={skipped_count}")


def _execute_auto_apply(decision: dict, analysis: dict, config: dict, root: Path):
    """执行 auto_apply 决策"""
    dimension = decision.get("dimension", "")
    target = decision.get("target", "")
    target_file = decision.get("target_file", "")
    suggested_change = decision.get("suggested_change", "")

    if not target_file or not suggested_change:
        return

    # ── 新增：KB 置信度检查 ──────────────────────────
    from kb_shared import (
        load_active_kb, find_kb_by_dimension,
        should_auto_apply, update_kb_confidence
    )

    kb = load_active_kb(root)
    matching_kb = find_kb_by_dimension(dimension, target, root)
    kb_id = matching_kb.get("id") if matching_kb else None

    if matching_kb:
        should_apply, reason = should_auto_apply(matching_kb)
        if not should_apply:
            # 置信度不够，降级为 propose
            decision["action"] = "propose"
            print(f"  [KB] {dimension}:{target} 降级为 propose ({reason})")
            _execute_propose(decision, analysis, config, root)
            return

    # 各维度执行
    if dimension == "agent":
        from agent_evolution import evolve_agent
        corrections = analysis.get("correction_patterns", {}).get(f"{target}:unknown", {}).get("examples", [])
        result = evolve_agent(target, corrections, config, root)
        if result.get("success"):
            _apply_file_change(target_file, result.get("suggested_change", ""), config, root)
            print(f"✅ [Agent] {target}: {result.get('change_type')}")
            # 关联 KB 条目
            if kb_id:
                update_kb_confidence(kb_id, "applied", root)

    elif dimension == "instinct":
        from instinct_updater import add_pattern
        from extract_semantics import _record_to_instinct
        # instinct 已在 extract_semantics 中记录
        print(f"✅ [Instinct] {target}: 已记录")


def _execute_propose(decision: dict, analysis: dict, config: dict, root: Path):
    """执行 propose 决策"""
    dimension = decision.get("dimension", "")
    target = decision.get("target", "")
    target_file = decision.get("target_file", "")
    suggested_change = decision.get("suggested_change", "")

    from proposer import generate_proposal

    # 构建带维度的分析
    dimension_analysis = {**analysis, "dimension": dimension, "target_file": target_file, "suggested_change": suggested_change}
    proposal_path = generate_proposal(dimension_analysis, config, root)
    if proposal_path:
        print(f"📋 [{dimension}] {target}: 提案已生成")
        # 关联 KB 条目（新增知识关联）
        try:
            from kb_shared import load_active_kb, find_kb_by_dimension, save_kb_entry, generate_kb_id, now_iso
            kb = load_active_kb(root)
            # 查找或创建对应的 KB 条目
            matching_kb = find_kb_by_dimension(dimension, target, root)
            if not matching_kb:
                new_entry = {
                    "id": generate_kb_id(),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "status": "unconfirmed",
                    "error_type": f"{dimension}:{target}",
                    "root_cause": decision.get("reason", ""),
                    "solution": suggested_change[:200],
                    "specific_examples": [],
                    "generalized_from": [],
                    "superseded_by": None,
                    "confidence": 0.5,
                    "validation_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "source": "daemon_propose",
                    "dimension": dimension,
                    "target_file": target_file,
                    "proposal_path": str(proposal_path),
                }
                save_kb_entry(new_entry, root)
        except Exception:
            pass
    else:
        print(f"⚠️ [{dimension}] {target}: 提案生成失败")


def _apply_file_change(target_file: str, suggested_change: str, config: dict, root: Path):
    """将改动应用到文件"""
    from apply_change import apply_change

    decision = {
        "target_file": target_file,
        "suggested_change": suggested_change,
        "id": f"auto-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    }
    try:
        apply_change(decision, root)
    except Exception:
        # fallback: 直接追加内容
        try:
            file_path = Path(target_file)
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                content += suggested_change
                file_path.write_text(content, encoding="utf-8")
        except Exception:
            pass


def _record_rollback_to_instinct(proposal: dict, root: Path, reason: str, config: dict):
    """
    将回滚事件记录到 instinct-record.json。

    回滚被视为"负向验证"，降低关联本能的置信度，
    同时更新知识库的置信度。
    """
    try:
        from instinct_updater import demote_confidence, link_instinct_to_target
        from kb_shared import update_kb_confidence

        linked_id = proposal.get("linked_instinct_id")
        linked_kb_id = proposal.get("linked_kb_id")
        target_file = proposal.get("target_file", "")
        dimension = proposal.get("dimension", "unknown")

        pattern = f"[回滚] {dimension}:{target_file}"
        correction = reason[:200] if reason else proposal.get("suggested_change", "观察期指标恶化")
        root_cause = reason

        # 更新知识库置信度（优先使用 linked_kb_id）
        if linked_kb_id:
            update_kb_confidence(linked_kb_id, "failure", root)
        elif linked_id:
            # 没有 KB 条目则降级 instinct
            demote_confidence(linked_id, delta=0.2, root=root)
            link_instinct_to_target(linked_id, target_file, root=root)
        else:
            from instinct_updater import add_pattern
            add_pattern(
                pattern=pattern,
                correction=correction,
                root_cause=root_cause,
                confidence=0.2,
                source="rollback-event",
                root=root,
            )
    except Exception:
        pass


def run_rollback_check(config: dict, root: Path) -> dict:
    """
    执行回滚检查：观察期到期的提案评估并回滚/固化。

    返回检查结果。
    """
    rollback_config = config.get("rollback", {})
    if not rollback_config.get("auto_enabled", True):
        return {"status": "skipped", "reason": "rollback.auto_enabled=false"}

    try:
        from rollback import run_rollback_check as do_check

        result = do_check(root, config)

        # 如果有回滚发生，同步记录到 instinct
        if result.get("rolled_back", 0) > 0:
            history_file = root / config["paths"]["data_dir"] / "proposal_history.json"
            if history_file.exists():
                try:
                    history = json.loads(history_file.read_text())
                    for p in history[-result["rolled_back"]:]:
                        if p.get("status") == "rolled_back":
                            _record_rollback_to_instinct(p, root, p.get("rollback_reason", ""), config)
                except (json.JSONDecodeError, OSError):
                    pass

        return result
    except ImportError:
        return {"status": "error", "reason": "rollback module not available"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def install_launchd(root: Path):
    """macOS: 生成 LaunchAgent plist 并安装"""
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-harness-kit.evolve</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{Path(__file__).resolve()}</string>
        <string>run</string>
    </array>
    <key>StartInterval</key>
    <integer>14400</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CLAUDE_PROJECT_DIR</key>
        <string>{root}</string>
    </dict>
</dict>
</plist>"""

    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.claude-harness-kit.evolve.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist)
    print(f"✅ LaunchAgent 已安装: {plist_path}")
    print(f"   加载: launchctl load {plist_path}")
    print(f"   卸载: launchctl unload {plist_path}")


def main():
    config = load_config()
    root = find_root()
    data_dir = root / config["paths"]["data_dir"]

    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    # 健康检查命令
    if cmd == "health":
        result = _health_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        # 根据健康状态返回退出码
        sys.exit(0 if result.get("healthy", False) else 1)

    # 读取分析状态
    state_file = data_dir / "analysis_state.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    last_analyzed_id = state.get("last_analyzed_session_id")
    last_analyze_time = None
    if state.get("last_analyze_time"):
        try:
            last_analyze_time = datetime.fromisoformat(state["last_analyze_time"])
        except (ValueError, TypeError):
            pass

    sessions = load_new_sessions(data_dir, last_analyzed_id)

    if cmd == "check":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        print(json.dumps({
            "new_sessions": len(sessions),
            "last_analyze_time": str(last_analyze_time),
            "triggers": triggers,
            "should_run": len(triggers) > 0,
        }, indent=2, ensure_ascii=False))

    elif cmd == "run":
        # 外部触发模式 - 启动前自动备份配置
        config_path = Path(__file__).parent / "config.yaml"
        backup_dir = root / ".claude/data/backups"
        _backup_config(config_path, backup_dir, max_backups=5)

        triggers = check_thresholds(sessions, config, last_analyze_time)
        if not triggers:
            print("无触发条件，跳过分析")
            return
        print(f"触发条件: {', '.join(triggers)}")
        run_analysis(config, root, sessions)

        # 分析完成后自动执行回滚检查
        print("\n--- 回滚状态检查 ---")
        rb_result = run_rollback_check(config, root)
        print(json.dumps(rb_result, indent=2, ensure_ascii=False))

    elif cmd == "rollback-check":
        # 独立运行回滚检查（不依赖触发条件）
        print("执行回滚检查...")
        result = run_rollback_check(config, root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("status") == "paused":
            print(f"⚠️ 系统暂停: {result.get('reason')}")

    elif cmd == "status":
        triggers = check_thresholds(sessions, config, last_analyze_time)
        proposals_dir = root / config["paths"]["proposals_dir"]
        proposals = list(proposals_dir.glob("*.md")) if proposals_dir.exists() else []
        print(json.dumps({
            "total_sessions_file": str(data_dir / "sessions.jsonl"),
            "new_sessions_since_last_analyze": len(sessions),
            "pending_proposals": len(proposals),
            "will_trigger": len(triggers) > 0,
            "triggers": triggers,
        }, indent=2, ensure_ascii=False))

    elif cmd == "install-launchd":
        install_launchd(root)

    elif cmd == "start":
        # 内置调度器模式 - 启动前自动备份配置
        config_path = Path(__file__).parent / "config.yaml"
        backup_dir = root / ".claude/data/backups"
        _backup_config(config_path, backup_dir, max_backups=5)

        from scheduler import _manager
        result = _manager.start()
        if result.get("success"):
            print(f"调度器已启动")
            print(f"   模式: {result.get('mode')}")
            print(f"   间隔: {result.get('interval')} ({result.get('interval_seconds')}s)")
            if result.get("run_on_startup"):
                print(f"   启动时立即运行: 是")
            print("\n后台运行中，按 Ctrl+C 或发送 SIGTERM/SIGHUP 停止")
            try:
                import time as time_module
                while True:
                    time_module.sleep(60)
            except KeyboardInterrupt:
                print("\n正在停止调度器...")
                _manager.shutdown(wait=True)
                print("已停止")
        else:
            print(f"启动失败: {result.get('error')}")
            print("提示：确保 config.yaml 中 daemon.mode 包含 'internal'")
            print("提示：确保已安装 APScheduler: pip install APScheduler")

    elif cmd == "stop":
        # 停止内置调度器
        from scheduler import _manager
        result = _manager.stop()
        if result.get("success"):
            print("调度器已停止")
        else:
            print(f"停止失败: {result.get('error')}")

    else:
        print(f"未知命令: {cmd}")
        print("用法: python3 daemon.py [check|run|start|stop|status|rollback-check|install-launchd|health]")
        print("")
        print("命令说明：")
        print("  check            - 仅检查触发条件")
        print("  run              - 检查并执行分析 + 回滚检查（外部触发模式）")
        print("  rollback-check   - 仅检查观察期到期的提案并执行回滚/固化")
        print("  start            - 启动内置调度器（内部定时触发）")
        print("  stop             - 停止内置调度器")
        print("  status           - 查看系统状态")
        print("  install-launchd  - macOS: 安装 LaunchAgent")
        print("  health           - 健康检查")
        print("")
        print("示例：")
        print("  python3 daemon.py check           # 检查触发条件")
        print("  python3 daemon.py run             # 分析 + 回滚检查")
        print("  python3 daemon.py rollback-check  # 仅回滚检查")
        print("  python3 daemon.py start           # 启动内置调度器")
        print("  python3 daemon.py health          # 健康检查")


if __name__ == "__main__":
    main()
