#!/usr/bin/env python3
"""
跨项目全链路验证脚本 — 在多个真实项目中跑通 kit init 完整流程。
用法: python3 tests/verify_cross_project.py [--projects-dir /tmp/verify-projects]
"""

import json

import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INIT_PY = PROJECT_ROOT / "cli" / "init.py"
KIT_SH = PROJECT_ROOT / "cli" / "kit.sh"
HOOKS_BIN = PROJECT_ROOT / "hooks" / "bin"

REPOS = [
    # (name, url, branch_or_tag, expected_lang)
    ("vuejs/core", "https://github.com/vuejs/core.git", "v3.5.13", "TypeScript"),
    ("denoland/deno", "https://github.com/denoland/deno.git", "v2.2.10", "TypeScript"),
    (
        "sindresorhus/pure",
        "https://github.com/sindresorhus/pure.git",
        "v4.0.0",
        "JavaScript",
    ),
    ("go-chi/chi", "https://github.com/go-chi/chi.git", "v5.2.1", "Go"),
    ("labstack/echo", "https://github.com/labstack/echo.git", "v4.12.0", "Go"),
    ("fastapi/fastapi", "https://github.com/fastapi/fastapi.git", "0.115.6", "Python"),
    ("tiangolo/fastapi", "https://github.com/tiangolo/fastapi.git", "master", "Python"),
    (
        "microsoft/playwright",
        "https://github.com/microsoft/playwright.git",
        "v1.51.0",
        "TypeScript",
    ),
    (
        "elastic/elasticsearch",
        "https://github.com/elastic/elasticsearch.git",
        "main",
        "Java",
    ),
    (
        "kubernetes/client-java",
        "https://github.com/kubernetes-client/java.git",
        "master",
        "Java",
    ),
]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def git_clone(url: str, dest: Path, branch: str = "main", depth: int = 1) -> bool:
    """Clone with token if available, depth=1 for speed"""
    token_url = url
    if (
        GITHUB_TOKEN
        and "github.com" in url
        and not url.startswith("https://")
        or GITHUB_TOKEN
        and "github.com" in url
    ):
        token_url = url.replace(
            "https://github.com/", f"https://{GITHUB_TOKEN}@github.com/"
        )

    cmd = [
        "git",
        "clone",
        "--depth",
        str(depth),
        "--branch",
        branch,
        "--single-branch",
        url,
        str(dest),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            # Try without branch
            cmd2 = ["git", "clone", "--depth", str(depth), url, str(dest)]
            result = subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception:
        return False


def run_kit_init(project_dir: Path) -> dict:
    """运行 kit init 并收集结果"""
    result = {
        "success": False,
        "claude_md": None,
        "claudeignore": False,
        "skeleton": {},
        "tech_stack": None,
        "key_dirs": 0,
        "entry_files": 0,
        "next_steps": False,
        "error": None,
        "output": "",
    }

    try:
        proc = subprocess.run(
            [sys.executable, str(INIT_PY), str(project_dir)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=PROJECT_ROOT,
        )
        result["output"] = proc.stdout + proc.stderr
        result["success"] = proc.returncode == 0

        if result["success"]:
            # 检查 CLAUDE.md
            cm = project_dir / "CLAUDE.md"
            if cm.exists():
                result["claude_md"] = cm.read_text()
                lines = result["claude_md"].splitlines()
                result["claude_md_lines"] = len(lines)

            # 检查 .claudeignore
            result["claudeignore"] = (project_dir / ".claudeignore").exists()

            # 检查骨架
            claude_dir = project_dir / ".claude"
            result["skeleton"] = {
                "rules": (claude_dir / "rules").exists(),
                "knowledge": (claude_dir / "knowledge").exists(),
                "data": (claude_dir / "data").exists(),
                "settings": (claude_dir / "settings.local.json").exists(),
            }

            # 从输出提取信息
            for line in result["output"].splitlines():
                if "检测到:" in line:
                    result["tech_stack"] = line.strip()
                if "关键目录:" in line and "个" in line:
                    import re

                    m = re.search(r"(\d+)\s*个", line)
                    if m:
                        result["key_dirs"] = int(m.group(1))
                if "入口文件:" in line and "个" in line:
                    import re

                    m = re.search(r"(\d+)\s*个", line)
                    if m:
                        result["entry_files"] = int(m.group(1))
                if "下一步" in line or "下一步:" in line:
                    result["next_steps"] = True

    except subprocess.TimeoutExpired:
        result["error"] = "超时（60s）"
    except Exception as e:
        result["error"] = str(e)

    return result


def verify_project(
    name: str, url: str, branch: str, expected_lang: str, work_dir: Path
) -> dict:
    """验证一个项目"""
    project_dir = work_dir / name.replace("/", "_")
    start = time.time()
    score = 0
    checks = []

    print(f"\n{'='*60}")
    print(f"验证: {name} ({expected_lang})")
    print(f"URL:  {url}")
    print(f"{'='*60}")

    # 克隆
    print(f"[1/5] 克隆项目...", end=" ", flush=True)
    if project_dir.exists():
        shutil.rmtree(project_dir)
    ok = git_clone(url, project_dir, branch)
    if not ok:
        print("❌ 克隆失败")
        return {
            "name": name,
            "url": url,
            "expected_lang": expected_lang,
            "success": False,
            "error": "克隆失败",
            "score": 0,
            "elapsed": time.time() - start,
        }
    print(f"✅ ({time.time()-start:.1f}s)")

    # kit init
    print(f"[2/5] 运行 kit init...", end=" ", flush=True)
    t0 = time.time()
    r = run_kit_init(project_dir)
    print(f"✅ ({time.time()-t0:.1f}s)")

    checks.append(("克隆", ok))
    checks.append(("kit init", r["success"]))
    score += 20 if ok else 0
    score += 30 if r["success"] else 0

    # CLAUDE.md 检查
    print(f"[3/5] CLAUDE.md 质量检查...", end=" ", flush=True)
    claude_ok = r["claude_md"] is not None
    quality_ok = False
    if r["claude_md"]:
        text = r["claude_md"]
        has_sections = all(s in text for s in ["## 技术栈", "## 构建"])
        has_tokens = len(text) > 200
        lines_ok = r.get("claude_md_lines", 999) <= 150
        quality_ok = has_sections and has_tokens and lines_ok
    checks.append(("CLAUDE.md 存在", claude_ok))
    checks.append(("CLAUDE.md 质量", quality_ok))
    score += 10 if claude_ok else 0
    score += 10 if quality_ok else 0
    if claude_ok:
        print(f"✅ {r.get('claude_md_lines', '?')} 行, tech={bool(quality_ok)}")
    else:
        print("❌")

    # 骨架检查
    print(f"[4/5] .claude/ 骨架检查...", end=" ", flush=True)
    sk = r.get("skeleton", {})
    sk_ok = all(sk.values())
    for k, v in sk.items():
        checks.append((f"skeleton.{k}", v))
    score += 10 if sk_ok else (5 if sum(sk.values()) >= 3 else 0)
    if sk_ok:
        print("✅ 全部完整")
    else:
        present = [k for k, v in sk.items() if v]
        missing = [k for k, v in sk.items() if not v]
        print(f"⚠️  有 {len(present)}/4，缺: {missing}")

    # Next steps
    print(f"[5/5] Next Steps 引导...", end=" ", flush=True)
    ns_ok = r.get("next_steps", False)
    score += 5 if ns_ok else 0
    checks.append(("Next Steps", ns_ok))
    print("✅" if ns_ok else "❌")

    elapsed = time.time() - start
    return {
        "name": name,
        "url": url,
        "expected_lang": expected_lang,
        "success": r["success"],
        "score": min(score, 100),
        "elapsed": elapsed,
        "checks": checks,
        "tech_stack": r.get("tech_stack"),
        "key_dirs": r.get("key_dirs", 0),
        "entry_files": r.get("entry_files", 0),
        "claude_md_lines": r.get("claude_md_lines", 0),
        "skeleton": sk,
        "output": r["output"][:200],
        "error": r.get("error"),
    }


def main():
    work_dir = Path(__file__).resolve().parent.parent / ".verify-tmp"
    work_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("Claude Harness Kit — 跨项目全链路验证")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"工作目录: {work_dir}")
    print("=" * 70)

    results = []
    for name, url, branch, lang in REPOS:
        r = verify_project(name, url, branch, lang, work_dir)
        results.append(r)
        # 打印摘要
        status = "✅" if r["score"] >= 50 else "⚠️"
        print(f"\n  得分: {r['score']}/100 {status} | 耗时: {r['elapsed']:.0f}s")
        if r.get("tech_stack"):
            print(f"  技术栈: {r['tech_stack']}")

    # 汇总
    print(f"\n{'='*70}")
    print("汇总结果")
    print(f"{'='*70}")
    passed = sum(1 for r in results if r["score"] >= 60)
    total = len(results)
    avg = sum(r["score"] for r in results) / total if total else 0

    print(f"\n通过率: {passed}/{total} ({passed/total*100:.0f}%)")
    print(f"平均分: {avg:.1f}/100")
    print()

    print(
        f"{'项目':<30} {'语言':<12} {'分数':<6} {'耗时':<8} {'关键目录':<10} {'状态'}"
    )
    print("-" * 75)
    for r in sorted(results, key=lambda x: -x["score"]):
        elapsed_str = f"{r['elapsed']:.0f}s"
        status = (
            "✅ PASS"
            if r["score"] >= 60
            else "⚠️ WARN" if r["score"] >= 40 else "❌ FAIL"
        )
        tech = r.get("tech_stack", "")[:20]
        kdirs = str(r.get("key_dirs", 0))
        print(
            f"{r['name']:<30} {r['expected_lang']:<12} {r['score']:<6} {elapsed_str:<8} {kdirs:<10} {status}"
        )

    print(f"\n{'='*70}")

    # 保存详细报告
    report_path = (
        work_dir / f"verify_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    report_path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "summary": {"passed": passed, "total": total, "avg_score": avg},
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"详细报告: {report_path}")

    # 清理
    shutil.rmtree(work_dir)
    print(f"临时目录已清理: {work_dir}")

    return 0 if passed >= total * 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
