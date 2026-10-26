"""力扣判题器：AST 静态防护 → 子进程隔离运行 → 逐用例比对。

判题结果 verdict: accepted / wrong / error / blocked / timeout
安全边界：本工具面向本地学习场景；防护拦截危险导入与调用，超时拦截死循环。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BANNED_IMPORTS = {
    "os", "subprocess", "socket", "shutil", "ctypes", "urllib", "requests", "httpx",
    "pathlib", "multiprocessing", "threading", "asyncio", "importlib", "webbrowser",
    "signal", "pickle",
}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input",
                "breakpoint", "exit", "quit", "globals", "locals", "vars"}

MAX_CODE_LEN = 60_000

HARNESS = '''

# ===== judge runner（自动生成，勿改） =====
import json as _j
import sys as _sys
_sys.setrecursionlimit(20000)

def _norm(x):
    return _j.loads(_j.dumps(x))

def _cmp(g, e, mode):
    if mode == "sorted":
        if isinstance(g, list): g = sorted(g)
        if isinstance(e, list): e = sorted(e)
        return g == e
    if mode == "any":
        return any(g == x for x in e)
    return g == e

if __name__ == "__main__":
    _cases = _j.loads(r"""__CASES__""")
    _res = []
    for _i, _c in enumerate(_cases):
        try:
            _args = [_norm(a) for a in _c["args"]]
__BUILDER__
            _got = __FUNC__(*_args)
__SERIALIZER__
            _ok = _cmp(_got, _norm(_c["expected"]), _c.get("match", "__MATCH__"))
            _res.append({"i": _i, "pass": bool(_ok), "got": str(_got)[:200]})
        except Exception as _e:
            _res.append({"i": _i, "pass": False, "error": type(_e).__name__ + ": " + str(_e)[:200]})
        _res[-1]["expected"] = str(_c["expected"])[:200]
    print("__JUDGE__" + _j.dumps({"results": _res}, ensure_ascii=False, default=str))
'''


def guard(code: str) -> list[str]:
    """AST 扫描用户代码，返回违规列表。"""
    if len(code) > MAX_CODE_LEN:
        return [f"代码过长（>{MAX_CODE_LEN} 字符）"]
    violations: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"语法错误 第{e.lineno}行: {e.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in BANNED_IMPORTS:
                    violations.append(f"第{node.lineno}行: 不允许 import {a.name}（判题沙箱限制）")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in BANNED_IMPORTS:
                violations.append(f"第{node.lineno}行: 不允许 from {node.module} import …（判题沙箱限制）")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (
                f.attr if isinstance(f, ast.Attribute) else "")
            if name in BANNED_CALLS:
                violations.append(f"第{node.lineno}行: 不允许调用 {name}()（判题沙箱限制）")
    return violations


def build_source(problem: dict, code: str) -> str:
    setup = problem.get("setup") or ""
    harness = HARNESS.replace("__CASES__", _json_for_embed(problem["tests"]))
    harness = harness.replace("__FUNC__", problem["func"])
    harness = harness.replace("__MATCH__", problem.get("match", "exact"))
    builders = problem.get("arg_builders") or []
    if builders:
        exprs = [f"({b}(_args[{i}]) if _args[{i}] is not None else None)" if b else f"_args[{i}]"
                 for i, b in enumerate(builders)]
        harness = harness.replace("__BUILDER__",
                                  f"            _args = [{', '.join(exprs)}]")
    else:
        harness = harness.replace("__BUILDER__", "            pass")
    ser = problem.get("result_serializer")
    harness = harness.replace("__SERIALIZER__",
                              f"            _got = {ser}(_got)" if ser else "            pass")
    return f"{setup}\n\n{code}\n{harness}"


def _json_for_embed(obj) -> str:
    """把 JSON 塞进 r'''…'''：避免三引号冲突（题库数据不含 '''）。"""
    return json.dumps(obj, ensure_ascii=False)


def run_tests(problem: dict, code: str, timeout: float = 10.0) -> dict:
    started = time.time()
    violations = guard(code)
    if violations:
        syntax_errs = [v for v in violations if v.startswith("语法错误")]
        if syntax_errs and len(syntax_errs) == len(violations):
            return {"verdict": "error", "passed": 0, "total": len(problem.get("tests", [])),
                    "stderr_tail": "\n".join(syntax_errs),
                    "duration_ms": int((time.time() - started) * 1000)}
        return {"verdict": "blocked", "passed": 0, "total": len(problem.get("tests", [])),
                "violations": violations, "duration_ms": 0}
    src = build_source(problem, code)
    with tempfile.TemporaryDirectory(prefix="lc_judge_") as td:
        path = Path(td) / "solution.py"
        path.write_text(src, encoding="utf-8")
        try:
            r = subprocess.run(
                [sys.executable, "-I", "-X", "utf8", str(path)],
                capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="ignore",
                cwd=td,
            )
        except subprocess.TimeoutExpired:
            return {"verdict": "timeout", "passed": 0, "total": len(problem.get("tests", [])),
                    "stderr_tail": f"运行超过 {timeout}s 被强制终止（检查死循环/复杂度过高）",
                    "duration_ms": int((time.time() - started) * 1000)}
        except Exception as e:
            return {"verdict": "error", "passed": 0, "total": len(problem.get("tests", [])),
                    "stderr_tail": f"{type(e).__name__}: {e}", "duration_ms": 0}
        out, err = r.stdout or "", r.stderr or ""
        marker = None
        for line in reversed(out.splitlines()):
            if line.startswith("__JUDGE__"):
                marker = line[len("__JUDGE__"):]
                break
        if marker is None:
            return {"verdict": "error", "passed": 0, "total": len(problem.get("tests", [])),
                    "stderr_tail": (err or out)[-800:] or f"退出码 {r.returncode}，无输出",
                    "duration_ms": int((time.time() - started) * 1000)}
        try:
            data = json.loads(marker)
        except Exception:
            return {"verdict": "error", "passed": 0, "total": len(problem.get("tests", [])),
                    "stderr_tail": "判题输出解析失败", "duration_ms": 0}
        results = data.get("results", [])
        passed = sum(1 for x in results if x.get("pass"))
        verdict = "accepted" if passed == len(results) and results else "wrong"
        return {"verdict": verdict, "passed": passed, "total": len(results), "results": results,
                "stderr_tail": err[-500:], "duration_ms": int((time.time() - started) * 1000)}
