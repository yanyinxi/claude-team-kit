#!/usr/bin/env python3
"""
test_error_comprehensive.py — 错误收集系统全面测试 (40 场景)
"""
import json, os, sys, tempfile, shutil, threading, time, traceback as tb_module
from pathlib import Path
from io import StringIO
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "bin"))


class TempProject:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="chk-test-")
        self.root = Path(self.tmp)
        self.data_dir = self.root / ".claude" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._orig = {k: os.environ.get(k) for k in ["CLAUDE_PROJECT_DIR", "CLAUDE_SESSION_ID", "CLAUDE_MODE", "CLAUDE_HOOK_EVENT", "CLAUDE_PLUGIN_ROOT"]}
        # 必须在设置环境变量之前保存 _orig，然后立即设置
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)
        os.environ["CLAUDE_SESSION_ID"] = f"test-{self.root.name}"
        os.environ["CLAUDE_MODE"] = "team"
        os.environ.pop("CLAUDE_HOOK_EVENT", None)
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)

    def set_env(self, k, v): os.environ[k] = v
    def cleanup(self):
        for k, v in self._orig.items():
            if v: os.environ[k] = v
            else: os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)


# 场景 01-10: 边界值
def test_01_empty_error_message():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="", source="test.py:1")
        assert r["error"] == ""
        assert write_error(r, p.tmp) is True
        print("  ✓ 01: 空错误消息")
    finally:
        p.cleanup()

def test_02_unicode_error():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="中文🚀emoji", source="test.py:1")
        assert write_error(r, p.tmp) is True
        with open(p.data_dir / "error.jsonl") as f:
            e = json.loads(f.readline())
        assert "中文" in e["error"]
        print("  ✓ 02: Unicode 错误")
    finally:
        p.cleanup()

def test_03_1mb_error():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="x" * 1024*1024, source="test.py:1")
        assert len(r["error"]) < 1024*1024  # 应被截断
        assert write_error(r, p.tmp) is True
        print("  ✓ 03: 1MB 超长消息")
    finally:
        p.cleanup()

def test_04_special_chars():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="a\tb\nc\rd\x00e", source="test.py:1")
        assert write_error(r, p.tmp) is True
        print("  ✓ 04: 特殊字符")
    finally:
        p.cleanup()

def test_05_empty_tool():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1", tool="")
        assert r["tool"] == ""
        print("  ✓ 05: 空工具名")
    finally:
        p.cleanup()

def test_06_none_tool():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1", tool=None)
        assert r["tool"] is None
        print("  ✓ 06: None 工具名")
    finally:
        p.cleanup()

def test_07_empty_project_path():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = ""
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1")
        assert write_error(r, p.tmp) is True
        print("  ✓ 07: 空项目路径")
    finally:
        p.cleanup()

def test_08_auto_create_dir():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        nonexistent = "/tmp/chk_nonexistent_12345"
        if Path(nonexistent).exists(): shutil.rmtree(nonexistent)
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1")
        assert write_error(r, nonexistent) is True
        shutil.rmtree(nonexistent, ignore_errors=True)
        print("  ✓ 08: 自动创建目录")
    finally:
        p.cleanup()

def test_09_empty_tool_input():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1", tool_input={})
        assert r["context"]["tool_input"] == {}
        print("  ✓ 09: 空 tool_input")
    finally:
        p.cleanup()

def test_10_none_tool_input():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1", tool_input=None)
        assert r["context"]["tool_input"] == {}
        print("  ✓ 10: None tool_input")
    finally:
        p.cleanup()

# 场景 11-20: 正向测试
def test_11_all_error_types():
    from error_writer import write_error, build_error_record, ErrorType
    p = TempProject()
    try:
        for et in [ErrorType.TOOL_FAILURE, ErrorType.HOOK_ERROR, ErrorType.CHK_INTERNAL_ERROR, ErrorType.API_ERROR, ErrorType.VALIDATION_ERROR]:
            r = build_error_record(error_type=et, error_message="e", source="test.py:1")
            assert write_error(r, p.tmp) is True
        print("  ✓ 11: 所有错误类型")
    finally:
        p.cleanup()

def test_12_hook_event():
    from collect_error import collect_tool_failure
    p = TempProject()
    try:
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO(json.dumps({"tool_name": "Bash", "error": "fail"}))
        r = collect_tool_failure()
        assert r["metadata"]["hook_event"] == "PostToolUseFailure"
        print("  ✓ 12: hook 事件记录")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__

def test_13_git_session_id():
    import subprocess
    from error_writer import _get_session_id
    p = TempProject()
    try:
        subprocess.run(["git", "init"], cwd=p.root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=p.root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=p.root, capture_output=True)
        (p.root / "README.md").write_text("test")
        subprocess.run(["git", "add", "."], cwd=p.root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=p.root, capture_output=True)
        # 当 CLAUDE_SESSION_ID 设置时优先使用（模拟真实 Claude Code 行为）
        sid = _get_session_id(p.root)
        assert sid and len(sid) > 0, f"session_id={sid}"
        # 验证 git 路径：临时删除 CLAUDE_SESSION_ID 后使用 git hash
        orig = os.environ.pop("CLAUDE_SESSION_ID", None)
        try:
            sid2 = _get_session_id(p.root)
            assert "git-" in sid2, f"没有 git- 前缀: {sid2}"
        finally:
            if orig: os.environ["CLAUDE_SESSION_ID"] = orig
        print("  ✓ 13: Git session_id")
    finally:
        p.cleanup()

def test_14_timestamp_iso():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1")
        ts = r["timestamp"]
        datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", ""))
        assert "T" in ts
        print("  ✓ 14: ISO 时间戳")
    finally:
        p.cleanup()

def test_15_version():
    from error_writer import get_chk_version
    v = get_chk_version()
    assert v and len(v) > 0
    print(f"  ✓ 15: 版本检测 v{v}")

def test_16_all_modes():
    from error_writer import build_error_record
    p = TempProject()
    try:
        for mode in ["solo", "team", "ultra", "ralph", "gc"]:
            p.set_env("CLAUDE_MODE", mode)
            r = build_error_record(error_type="tool_failure", error_message="e", source="test.py:1")
            assert r["context"]["mode"] == mode
        print("  ✓ 16: 所有运行模式")
    finally:
        p.cleanup()

def test_17_recent_tools():
    from collect_error import collect_tool_failure
    p = TempProject()
    try:
        (p.data_dir / "sessions.jsonl").write_text(json.dumps({"recent_tools": ["Read","Edit","Bash"]}) + "\n")
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO(json.dumps({"tool_name": "Bash", "error": "f"}))
        r = collect_tool_failure()
        assert r["context"]["recent_tools"] == ["Read","Edit","Bash"]
        print("  ✓ 17: Recent tools")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__

def test_18_agents_skills():
    from collect_error import collect_tool_failure
    p = TempProject()
    try:
        (p.data_dir / "agent_calls.jsonl").write_text(json.dumps({"agent": "executor"}) + "\n")
        (p.data_dir / "skill_calls.jsonl").write_text(json.dumps({"skill": "security"}) + "\n")
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO(json.dumps({"tool_name": "Agent", "error": "f"}))
        r = collect_tool_failure()
        assert "executor" in r["context"]["agents_used"]
        assert "security" in r["context"]["skills_used"]
        print("  ✓ 18: Agents/Skills 追踪")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__

def test_19_consecutive_writes():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        for i in range(10):
            write_error(build_error_record("tool_failure", f"e{i}", "test.py:1"), p.tmp)
        with open(p.data_dir / "error.jsonl") as f:
            assert len(f.readlines()) == 10
        print("  ✓ 19: 连续写入")
    finally:
        p.cleanup()

def test_20_main_success():
    from collect_error import main
    p = TempProject()
    try:
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO(json.dumps({"tool_name": "Bash", "error": "f"}))
        old = sys.stdout; sys.stdout = StringIO()
        main()
        out = sys.stdout.getvalue(); sys.stdout = old
        assert json.loads(out)["collected"] is True
        print("  ✓ 20: main() 成功")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__

# 场景 21-25: 异常测试
def test_21_invalid_json():
    from collect_error import collect_tool_failure
    p = TempProject()
    try:
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO("not json {{{")
        r = collect_tool_failure()
        assert r["tool"] == "unknown"
        print("  ✓ 21: 无效 JSON")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__

def test_22_empty_stdin():
    from collect_error import collect_tool_failure
    p = TempProject()
    try:
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO("")
        r = collect_tool_failure()
        assert r["tool"] == "unknown"
        print("  ✓ 22: 空 stdin")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__

def test_23_readonly_dir():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        p.data_dir.chmod(0o444)
        r = build_error_record("tool_failure", "e", "test.py:1")
        # 应静默失败，不抛异常
        success = write_error(r, p.tmp)
        assert isinstance(success, bool)
        print("  ✓ 23: 只读目录")
    finally:
        p.cleanup()

def test_24_large_write():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record("tool_failure", "x" * 10000, "test.py:1")
        success = write_error(r, p.tmp)
        assert isinstance(success, bool)
        print("  ✓ 24: 大数据写入")
    finally:
        p.cleanup()

def test_25_concurrent_read_write():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        lock = threading.Lock()
        counts = []
        def writer():
            for i in range(20):
                write_error(build_error_record("tool_failure", f"e{i}", "test.py:1"), p.tmp)
        def reader():
            time.sleep(0.01)
            with lock:
                if (p.data_dir / "error.jsonl").exists():
                    counts.append(len((p.data_dir / "error.jsonl").read_text().splitlines()))
        threads = [threading.Thread(target=writer) for _ in range(5)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()
        with open(p.data_dir / "error.jsonl") as f:
            assert len(f.readlines()) == 100
        print("  ✓ 25: 并发读写")
    finally:
        p.cleanup()

# 场景 26-30: 反向测试
def test_26_invalid_source():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record("tool_failure", "e", "/bad/path.py:999")
        assert r["source"] == "/bad/path.py:999"
        print("  ✓ 26: 无效源路径")
    finally:
        p.cleanup()

def test_27_timestamp_sane():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record("tool_failure", "e", "test.py:1")
        ts = datetime.fromisoformat(r["timestamp"].replace("Z","+00:00").replace("+00:00",""))
        assert ts <= datetime.now()
        print("  ✓ 27: 时间戳合理")
    finally:
        p.cleanup()

def test_28_missing_optional():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record("tool_failure", "e", "test.py:1")
        assert all(k in r for k in ["timestamp","context","metadata"])
        print("  ✓ 28: 缺省字段有默认值")
    finally:
        p.cleanup()

def test_29_wrong_type():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record("invalid_xyz_type", "e", "test.py:1")
        assert write_error(r, p.tmp) is True
        print("  ✓ 29: 错误类型不阻断")
    finally:
        p.cleanup()

def test_30_empty_session():
    from error_writer import _get_session_id
    p = TempProject()
    try:
        os.environ.pop("CLAUDE_SESSION_ID", None)
        sid = _get_session_id(p.root)
        assert p.root.name in sid
        print("  ✓ 30: 空 session_id 兜底")
    finally:
        p.cleanup()

# 场景 31-35: 超大超小
def test_31_huge_input():
    from error_writer import build_error_record
    p = TempProject()
    try:
        r = build_error_record("tool_failure", "e", "test.py:1", tool_input={"data": "x"*100000})
        assert len(str(r["context"]["tool_input"])) < 1000
        print("  ✓ 31: 超大输入截断")
    finally:
        p.cleanup()

def test_32_long_source():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        r = build_error_record("tool_failure", "e", "x"*10000 + ".py:999")
        assert write_error(r, p.tmp) is True
        print("  ✓ 32: 超长源路径")
    finally:
        p.cleanup()

def test_33_many_sensitive():
    from error_writer import _sanitize_tool_input
    d = {f"key_{i}": f"sk-secret-{i}" for i in range(500)}
    s = _sanitize_tool_input(d)
    assert all(v == "[REDACTED]" for v in s.values())
    print("  ✓ 33: 500 敏感字段")

def test_34_100_records():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        for i in range(100):
            write_error(build_error_record("tool_failure", f"e{i}", f"test.py:{i}"), p.tmp)
        with open(p.data_dir / "error.jsonl") as f:
            assert len(f.readlines()) == 100
        print("  ✓ 34: 100 条记录")
    finally:
        p.cleanup()

def test_35_nested_json():
    from error_writer import build_error_record
    p = TempProject()
    try:
        nested = {"l1":{"l2":{"l3":{"l4":{"l5":{"deep":"value"}}}}}}
        r = build_error_record("tool_failure", "e", "test.py:1", tool_input=nested)
        assert r["context"]["tool_input"]["l1"]["l2"]["l3"]["l4"]["l5"]["deep"] == "value"
        print("  ✓ 35: 深层嵌套")
    finally:
        p.cleanup()

# 场景 36-40: 并发与集成
def test_36_100_concurrent():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        threads = [threading.Thread(target=lambda i=i: write_error(build_error_record("tool_failure", f"c{i}", "test.py:1"), p.tmp)) for i in range(100)]
        for t in threads: t.start()
        for t in threads: t.join()
        with open(p.data_dir / "error.jsonl") as f:
            assert len(f.readlines()) == 100
        print("  ✓ 36: 100 并发写入")
    finally:
        p.cleanup()

def test_37_lock_competition():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        threads = [threading.Thread(target=lambda i=i: write_error(build_error_record("tool_failure", f"l{i}", "test.py:1"), p.tmp)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        with open(p.data_dir / "error.jsonl") as f:
            assert len(f.readlines()) == 50
        print("  ✓ 37: 锁竞争")
    finally:
        p.cleanup()

def test_38_rapid_batches():
    from error_writer import write_error, build_error_record
    p = TempProject()
    try:
        for batch in range(5):
            threads = [threading.Thread(target=lambda: write_error(build_error_record("tool_failure", "batch", "test.py:1"), p.tmp)) for _ in range(20)]
            for t in threads: t.start()
            for t in threads: t.join()
        with open(p.data_dir / "error.jsonl") as f:
            assert len(f.readlines()) == 100
        print("  ✓ 38: 快速批次")
    finally:
        p.cleanup()

def test_39_session_isolation():
    from error_writer import write_error, build_error_record
    tmp1, tmp2 = tempfile.mkdtemp(prefix="s1-"), tempfile.mkdtemp(prefix="s2-")
    try:
        for i in range(10): write_error(build_error_record("tool_failure", f"s1-{i}", "test.py:1"), tmp1)
        for i in range(5): write_error(build_error_record("tool_failure", f"s2-{i}", "test.py:1"), tmp2)
        with open(Path(tmp1)/".claude"/"data"/"error.jsonl") as f: n1 = len(f.readlines())
        with open(Path(tmp2)/".claude"/"data"/"error.jsonl") as f: n2 = len(f.readlines())
        assert n1 == 10 and n2 == 5
        print("  ✓ 39: 会话隔离")
    finally:
        shutil.rmtree(tmp1, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)

def test_40_full_pipeline():
    from collect_error import main
    p = TempProject()
    try:
        p.set_env("CLAUDE_HOOK_EVENT", "PostToolUseFailure")
        sys.stdin = StringIO(json.dumps({
            "tool_name": "Bash", "error": "Permission denied",
            "tool_input": {"command": "rm /root/f.txt", "api_key": "sk-xxx"},
        }))
        old = sys.stdout; sys.stdout = StringIO()
        main()
        out = sys.stdout.getvalue(); sys.stdout = old
        result = json.loads(out)
        assert result["collected"] is True
        with open(p.data_dir / "error.jsonl") as f:
            e = json.loads(f.readline())
        assert e["tool"] == "Bash"
        assert "Permission denied" in e["error"]
        assert "hooks/bin/" in e["source"]
        assert e["context"]["tool_input"]["api_key"] == "[REDACTED]"
        assert e["context"]["tool_input"]["command"] == "rm /root/f.txt"
        print("  ✓ 40: 完整流程端到端")
    finally:
        p.cleanup(); sys.stdin = sys.__stdin__


# 运行器
def run_all():
    tests = [eval(f"test_{i:02d}") for i in range(1, 41)]
    passed = failed = 0
    print("\n" + "="*70 + "\n  错误收集系统全面测试 (40 场景)\n" + "="*70)
    for t in tests:
        try:
            t(); passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}"); failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}"); tb_module.print_exc(); failed += 1
    print("-"*70 + f"\n  结果: {passed} 通过, {failed} 失败\n" + "="*70 + "\n")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
