#!/usr/bin/env python3
"""
kit init — 自动分析项目，生成高质量 CLAUDE.md 和 .claude/ 配置。

流程:
  1. 扫描项目结构，识别技术栈 + 版本号
  2. 发现关键目录和入口文件
  3. 从 git log 提取常见模式和陷阱
  4. 生成 Map Not Manual 风格 CLAUDE.md（<100 行）
  5. 创建 .claude/ 目录骨架（rules/, knowledge/, settings.local.json, .claudeignore）
"""
import os, re, sys, json, subprocess
from pathlib import Path
from datetime import datetime

# ── 技术栈检测 ────────────────────────────────────────────

LANG_DETECT = {
    "pom.xml":        ("Java", "Maven", "mvn", "xml"),
    "build.gradle":   ("Java/Kotlin", "Gradle", "gradle", "groovy"),
    "build.gradle.kts": ("Java/Kotlin", "Gradle", "gradle", "kotlin-dsl"),
    "package.json":   ("Node.js", "npm/yarn/pnpm", "npm", "json"),
    "go.mod":         ("Go", "Go Modules", "go", "gomod"),
    "Cargo.toml":     ("Rust", "Cargo", "cargo", "toml"),
    "requirements.txt":("Python", "pip", "python", "txt"),
    "pyproject.toml": ("Python", "pip/poetry", "python", "toml"),
    "Gemfile":        ("Ruby", "Bundler", "bundle", "ruby"),
    "composer.json":  ("PHP", "Composer", "composer", "json"),
    "CMakeLists.txt": ("C/C++", "CMake", "cmake", "cmake"),
    "Makefile":       ("C/C++", "Make", "make", "make"),
}

FRAMEWORK_HINTS = {
    "spring": "Spring Boot", "django": "Django", "flask": "Flask",
    "fastapi": "FastAPI", "react": "React", "vue": "Vue.js",
    "angular": "Angular", "express": "Express", "next": "Next.js",
    "nuxt": "Nuxt.js", "gin": "Gin", "echo": "Echo", "fiber": "Fiber",
    "laravel": "Laravel", "rails": "Ruby on Rails", "svelte": "Svelte",
    "nestjs": "NestJS", "fastify": "Fastify",
}

KEY_DIR_PATTERNS = [
    ("src/main/java", "Java 主源码"),
    ("src/main/resources", "Java 资源文件"),
    ("src/test/java", "Java 测试"),
    ("src/components", "前端组件"),
    ("src/pages", "前端页面"),
    ("src/api", "API 路由"),
    ("src/services", "服务层"),
    ("src/utils", "工具函数"),
    ("pkg/", "Go 包"),
    ("cmd/", "Go 入口"),
    ("internal/", "内部包"),
    ("migrations/", "数据库迁移"),
    ("db/migrate", "数据库迁移(Rails)"),
    ("tests/", "测试目录"),
    ("__tests__/", "测试目录(JS)"),
    ("spec/", "测试目录(Ruby)"),
    ("docker/", "Docker 配置"),
    ("k8s/", "K8s 配置"),
    (".github/workflows", "GitHub Actions"),
]

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".idea", "dist", "build",
               "target", "vendor", ".venv", "venv", ".next", ".cache", "coverage"}

# ── 依赖解析 ──────────────────────────────────────────────

def parse_package_json(path: Path) -> dict:
    """从 package.json 提取依赖和版本"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        deps = {}
        for field in ("dependencies", "devDependencies"):
            for name, ver in data.get(field, {}).items():
                deps[name] = str(ver).lstrip("^~>= ")
        return deps
    except Exception:
        return {}

def parse_pom_xml(path: Path) -> dict:
    """从 pom.xml 提取关键依赖"""
    deps = {}
    try:
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>\s*(?:<version>([^<]+)</version>)?', text):
            gid, aid, ver = m.group(1), m.group(2), m.group(3) or "?"
            if gid.startswith("org.springframework") or gid.startswith("com."):
                deps[f"{gid}:{aid}"] = ver
    except Exception:
        pass
    return deps

def parse_go_mod(path: Path) -> dict:
    """从 go.mod 提取依赖"""
    deps = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("//") and not line.startswith("module "):
                parts = line.split()
                if len(parts) >= 2 and not parts[0] in ("go", "require", "replace", "exclude", "retract", "require", "toolchain"):
                    deps[parts[0]] = parts[1] if len(parts) > 1 else "?"
    except Exception:
        pass
    return deps

# ── 目录发现 ──────────────────────────────────────────────

def discover_structure(root: Path) -> dict:
    """发现关键目录、入口文件、模块边界"""
    key_dirs = []
    entry_files = []
    modules = []

    seen = set()
    # 深度 2 遍历
    for depth in (1, 2):
        for item in sorted(root.iterdir()):
            if item.name in IGNORE_DIRS or item.name.startswith("."):
                continue
            if item.is_dir():
                rel = str(item.relative_to(root))
                # 匹配关键目录模式
                for pattern, label in KEY_DIR_PATTERNS:
                    clean = pattern.rstrip("/")
                    if (rel == clean or item.name == clean.split("/")[-1]) and rel not in seen:
                        key_dirs.append((rel, label))
                        seen.add(rel)
                        break
                if depth == 1:
                    modules.append(item.name)

    # 识别入口文件
    entry_patterns = [
        "main.go", "main.py", "app.py", "index.ts", "index.tsx", "index.js",
        "App.tsx", "App.vue", "server.js", "server.ts", "Application.java",
        "manage.py", "wsgi.py", "asgi.py",
    ]
    for pattern in entry_patterns:
        candidates = list(root.glob(f"**/{pattern}"))
        for c in candidates[:3]:  # 最多取 3 个
            rel = str(c.relative_to(root))
            if not any(d in rel for d in IGNORE_DIRS) and not "/." in rel:
                entry_files.append(rel)

    return {
        "key_dirs": key_dirs[:15],
        "entry_files": entry_files[:5],
        "modules": modules[:10],
    }

# ── Git 历史提取 ──────────────────────────────────────────

def extract_git_insights(root: Path) -> list[str]:
    """从 git log 提取最近的 fix/refactor 关键词热点"""
    insights = []
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline", "-50", "--no-merges"],
            capture_output=True, text=True, timeout=5
        )
        fix_count = 0
        refactor_count = 0
        for line in result.stdout.splitlines():
            if re.search(r'\bfix(ed)?\b', line, re.IGNORECASE):
                fix_count += 1
            if re.search(r'\brefactor\b', line, re.IGNORECASE):
                refactor_count += 1

        if fix_count > 5:
            insights.append(f"近期 {fix_count}/50 个提交为 bug 修复")
        if refactor_count > 3:
            insights.append(f"近期 {refactor_count}/50 个提交为重构")
    except Exception:
        pass
    return insights

# ── CLAUDE.md 生成 ────────────────────────────────────────

def generate_claude_md(root: Path, tech: dict, structure: dict) -> str:
    """Map Not Manual 风格 — <100 行，含关键信息 + 指针"""
    name = root.name
    now = datetime.now().strftime("%Y-%m-%d")

    lines = [
        "# CLAUDE.md",
        "",
        "本文件为 Claude Code 提供项目上下文指导。",
        "",
        f"<!-- 由 kit init 生成于 {now} — 人工补充 TODO 项 -->",
        "",
        "## 技术栈",
        f"- 语言/构建: {tech['language']} / {tech['build_tool']}",
    ]
    if tech.get("frameworks"):
        lines.append(f"- 框架: {', '.join(tech['frameworks'])}")
    if tech.get("version"):
        lines.append(f"- 版本: {tech['version']}")
    if tech.get("key_deps") and len(tech["key_deps"]) <= 10:
        deps_str = ", ".join(f"{k}@{v}" for k, v in list(tech["key_deps"].items())[:8])
        lines.append(f"- 关键依赖: {deps_str}")

    lines += [
        "",
        "## 构建命令",
        f"```bash",
        f"{tech['build_cmd']} install   # 安装依赖",
        f"{tech['build_cmd']} test      # 运行测试",
        f"{tech['build_cmd']} build     # 构建",
        f"```",
        "",
        "## 关键路径",
    ]
    for rel, label in structure.get("key_dirs", [])[:8]:
        lines.append(f"- `{rel}/` — {label}")

    if structure.get("entry_files"):
        lines.append("")
        lines.append("### 入口文件")
        for f in structure["entry_files"][:5]:
            lines.append(f"- `{f}`")

    if structure.get("modules") and len(structure["modules"]) > 3:
        lines.append("")
        lines.append("### 模块")
        for m in structure["modules"]:
            lines.append(f"- `{m}/`")

    lines += [
        "",
        "## 架构约定",
        "<!-- TODO: 补充项目架构模式、分层约定、命名规范 -->",
        "",
        "## 已知陷阱",
        "<!-- TODO: 补充已知的坑、历史遗留问题、易错点 -->",
    ]
    for insight in tech.get("git_insights", []):
        lines.append(f"- {insight}")

    lines += [
        "",
        "## 相关知识",
        "- 项目知识: `.claude/knowledge/INDEX.md`",
        "- 团队规范: `.claude/rules/`",
        "- 设计文档: `docs/`",
    ]

    return "\n".join(lines)


# ── 骨架生成 ──────────────────────────────────────────────

def create_skeleton(root: Path):
    """创建 .claude/ 完整骨架"""
    claude_dir = root / ".claude"
    dirs = [
        claude_dir,
        claude_dir / "rules",
        claude_dir / "knowledge",
        claude_dir / "data",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # .claudeignore
    ignore_path = root / ".claudeignore"
    if not ignore_path.exists():
        ignore_path.write_text("""# Claude Code — 排除扫描
node_modules/
dist/
build/
target/
__pycache__/
*.pyc
.venv/
vendor/
.git/
*.lock
*.log
coverage/
.next/
.cache/
*.min.js
""")

    # knowledge INDEX
    idx = claude_dir / "knowledge" / "INDEX.md"
    if not idx.exists():
        idx.write_text(f"# {root.name} — 知识库\n\n"
                        "## 架构决策\n\n<!-- 技术选型理由、架构权衡 -->\n\n"
                        "## 已知陷阱\n\n<!-- bug 模式、反模式、历史教训 -->\n\n"
                        "## 操作流程\n\n<!-- 发布流程、回滚步骤、常见操作 -->\n",
                        encoding="utf-8")

    # settings.local.json
    local = claude_dir / "settings.local.json"
    if not local.exists():
        local.write_text("{}\n")


# ── 主入口 ────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="kit init — 分析项目，生成 CLAUDE.md + .claude/ 配置")
    parser.add_argument("target", nargs="?", default=None, help="目标目录（默认当前目录）")
    parser.add_argument("--force", "-f", action="store_true", help="强制覆盖已存在的 CLAUDE.md")
    parser.add_argument("--dry-run", "-n", action="store_true", help="仅预览，不写入文件")
    args = parser.parse_args()

    target = args.target if args.target else os.getcwd()
    root = Path(target).resolve()
    print(f"chk init: {root.name}")

    # 1. 技术栈
    tech = {"language": "unknown", "build_tool": "unknown", "build_cmd": "",
            "frameworks": [], "version": "", "key_deps": {}}

    for filename, (lang, build, cmd, fmt) in LANG_DETECT.items():
        if (root / filename).exists():
            tech["language"] = lang
            tech["build_tool"] = build
            tech["build_cmd"] = cmd

            # 解析版本号
            if fmt == "json":
                deps = parse_package_json(root / filename)
                tech["key_deps"] = deps
            elif fmt == "xml":
                deps = parse_pom_xml(root / filename)
                tech["key_deps"] = deps
            elif fmt == "gomod":
                deps = parse_go_mod(root / filename)
                tech["key_deps"] = deps
            break

    # 框架检测
    for candidate in [root / "go.mod", root / "pom.xml", root / "build.gradle", root / "package.json"]:
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8").lower()
                for hint, framework in FRAMEWORK_HINTS.items():
                    if re.search(r'\b' + hint + r'\b', content) and framework not in tech["frameworks"]:
                        tech["frameworks"].append(framework)
            except Exception:
                pass

    print(f"  检测到: {tech['language']} / {tech['build_tool']}")
    if tech["frameworks"]:
        print(f"  框架: {', '.join(tech['frameworks'])}")
    if tech["key_deps"]:
        print(f"  依赖: {len(tech['key_deps'])} 个")

    # 2. 目录结构
    structure = discover_structure(root)
    print(f"  关键目录: {len(structure['key_dirs'])} 个")
    print(f"  入口文件: {len(structure['entry_files'])} 个")

    # 3. Git 洞察
    tech["git_insights"] = extract_git_insights(root)

    # 4. 生成 CLAUDE.md
    claude_path = root / "CLAUDE.md"
    if args.dry_run:
        print(f"  🔍 [dry-run] 会生成 CLAUDE.md: {claude_path}")
        content = generate_claude_md(root, tech, structure)
        print(f"  🔍 [dry-run] 内容预览 ({content.count(chr(10))+1} 行)")
        print(f"  🔍 [dry-run] 会创建骨架: .claude/rules/, .claude/knowledge/, .claude/data/")
        return

    if claude_path.exists() and not args.force:
        print(f"  ⚠ CLAUDE.md 已存在，跳过生成（用 --force 覆盖）")
    else:
        content = generate_claude_md(root, tech, structure)
        claude_path.write_text(content, encoding="utf-8")
        line_count = content.count("\n")
        action = "覆盖" if claude_path.exists() else "生成"
        print(f"  ✅ CLAUDE.md 已{action} ({line_count} 行)")

    # 5. 骨架
    create_skeleton(root)
    print(f"  ✅ .claude/ 骨架已生成")

    # Next steps
    print(f"""
下一步:
  1. 编辑 {claude_path} 补充 TODO 项（架构约定、已知陷阱）
  2. 运行 chk team 确认执行模式
  3. 运行 chk gc 扫描知识漂移
  4. git add CLAUDE.md .claude/ .claudeignore && git commit -m "chore: chk init"
""")


if __name__ == "__main__":
    main()
