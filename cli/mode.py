#!/usr/bin/env python3
"""
chk mode — 切换 Claude Code 执行模式。

用法: chk mode [solo|auto|team|ultra|pipeline|ralph|ccg|default]

模式说明:
  solo     — 直接对话，不用 Agent，零开销
  auto     — 全自动端到端，5 分钟搞定
  team     — 默认模式，5 阶段流程
  ultra    — 极限并行，3-5 个 Agent 同时工作
  pipeline — 严格阶段顺序，TaskFile 协议
  ralph    — TDD 强制，不通过不停止
  ccg      — Claude + Codex + Gemini 三方审查
  default  — 兼容旧名，等同 team

切换时更新 .claude/settings.local.json 的 hooks 配置。
"""
import json
import os
import shutil
import sys
from pathlib import Path


MODES_DIR = Path(__file__).parent / "modes"

MODE_DESCRIPTIONS = {
    "solo":     "Solo 模式 — 直接对话，不用 Agent，零开销",
    "auto":     "Autopilot 模式 — 全自动端到端，5 分钟搞定",
    "team":     "Team 模式 — 默认模式，5 阶段流程（功能开发）",
    "ultra":    "Ultrawork 模式 — 极限并行，3-5 个 Agent 同时工作",
    "pipeline": "Pipeline 模式 — 严格阶段顺序，上一步输出喂下一步",
    "ralph":    "Ralph TDD 模式 — 实现代码必须先有测试，不通过不停止",
    "ccg":      "CCG 模式 — Claude + Codex + Gemini 三方独立审查",
    "default": "默认模式 — 平衡生产力与安全（兼容旧名）",
}


def load_mode_template(mode_name: str) -> dict | None:
    """加载指定模式的 hook 配置模板"""
    template_path = MODES_DIR / f"{mode_name}.json"
    if not template_path.exists():
        return None
    try:
        return json.loads(template_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_settings(root: Path) -> dict:
    """加载或初始化 settings.local.json"""
    settings_path = root / ".claude" / "settings.local.json"
    if settings_path.exists():
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(root: Path, settings: dict):
    """保存 settings.local.json"""
    settings_path = root / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def switch_mode(mode_name: str, root: Path) -> bool:
    """切换到指定模式"""
    if mode_name not in MODE_DESCRIPTIONS:
        return False

    template = load_mode_template(mode_name)
    settings = load_settings(root)

    # 备份当前配置
    backup_path = root / ".claude" / f"settings.local.json.backup"
    current = settings_path = root / ".claude" / "settings.local.json"
    if current.exists():
        shutil.copy(current, backup_path)

    # 更新 hooks 配置
    settings["hooks"] = template.get("hooks", {}) if template else {}
    settings["mode"] = mode_name
    settings["mode_description"] = MODE_DESCRIPTIONS.get(mode_name, "")

    save_settings(root, settings)
    return True


def show_current_mode(root: Path):
    """显示当前模式"""
    settings = load_settings(root)
    current = settings.get("mode", "default")
    desc = settings.get("mode_description", MODE_DESCRIPTIONS.get(current, ""))
    print(f"当前模式: {current}")
    if desc:
        print(f"  {desc}")
    print()
    print("可用模式:")
    for name, desc in MODE_DESCRIPTIONS.items():
        marker = " ← 当前" if name == current else ""
        print(f"  {name:10s} — {desc}{marker}")


def main():
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()

    # 无参数 → 显示当前模式
    if len(sys.argv) == 1:
        show_current_mode(root)
        return

    subcommand = sys.argv[1]

    if subcommand in ("-h", "--help", "help"):
        print("用法: chk mode [solo|auto|team|ultra|pipeline|ralph|ccg]")
        print("      chk mode          # 查看当前模式")
        for name, desc in MODE_DESCRIPTIONS.items():
            print(f"  {name:10s} — {desc}")
        return

    # default 别名 team
    if subcommand == "default":
        subcommand = "team"

    if subcommand not in MODE_DESCRIPTIONS:
        if subcommand == "":
            show_current_mode(root)
            return
        print(f"错误: 未知模式 '{subcommand}'")
        print(f"可用模式: {', '.join(MODE_DESCRIPTIONS.keys())}")
        sys.exit(1)

    if not switch_mode(subcommand, root):
        print(f"错误: 模式配置文件 {MODES_DIR / subcommand}.json 不存在")
        sys.exit(1)

    # 验证
    settings = load_settings(root)
    if settings.get("mode") == subcommand:
        print(f"✅ 已切换到 {subcommand} 模式")
        if settings.get("hooks"):
            hook_count = len(settings["hooks"])
            print(f"   活跃 Hook: {hook_count} 个事件")
        print(f"   配置位置: {root / '.claude' / 'settings.local.json'}")
    else:
        print(f"❌ 模式切换失败")
        sys.exit(1)


if __name__ == "__main__":
    main()