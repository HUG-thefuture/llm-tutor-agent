"""静态代码检查：语法校验 + 常见编码问题启发式扫描（内存泄漏/资源未关闭/危险调用）。"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_SECRET_RE = re.compile(r"""(api[_-]?key|secret|password|token)\s*=\s*["'][^"']{8,}["']""", re.I)
_SK_RE = re.compile(r"sk-[A-Za-z0-9]{16,}")


def check_syntax(path: str, content: str) -> list[str]:
    """单文件快速校验，返回错误列表（空=通过）。"""
    p = path.lower()
    try:
        if p.endswith(".py"):
            ast.parse(content)
        elif p.endswith(".json"):
            json.loads(content or "null")
        elif p.endswith((".js", ".mjs", ".ts")) and shutil.which("node"):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(content)
                tmp = f.name
            try:
                r = subprocess.run(["node", "--check", tmp], capture_output=True,
                                   text=True, timeout=30, encoding="utf-8", errors="ignore")
                if r.returncode != 0:
                    return [f"{path}: JS 语法错误: {(r.stderr or r.stdout).strip()[:400]}"]
            finally:
                Path(tmp).unlink(missing_ok=True)
    except SyntaxError as e:
        return [f"{path}: 语法错误 第{e.lineno}行: {e.msg}"]
    except json.JSONDecodeError as e:
        return [f"{path}: JSON 错误: {e}"]
    except Exception as e:
        return [f"{path}: 检查失败 {type(e).__name__}: {e}"]
    return []


# ---------- Python AST 启发式规则 ----------
class _PyScanner(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.file = filename
        self.issues: list[dict] = []

    def _add(self, severity: str, kind: str, lineno: int, text: str):
        self.issues.append({"file": self.file, "line": lineno, "severity": severity,
                            "kind": kind, "text": text})

    def visit_FunctionDef(self, node):
        for d in node.args.defaults + [a for a in node.args.kw_defaults if a]:
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                self._add("medium", "logic", d.lineno,
                          f"函数 {node.name} 使用可变默认参数（多次调用会共享同一对象）")
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_While(self, node: ast.While):
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            has_exit = any(isinstance(x, (ast.Break, ast.Return, ast.Raise))
                           for x in ast.walk(node))
            if not has_exit:
                self._add("high", "logic", node.lineno, "while True 无 break/return（疑似死循环）")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.type is None:
            self._add("medium", "logic", node.lineno,
                      "裸 except 会吞掉 KeyboardInterrupt 等异常，建议 except Exception")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name in ("eval", "exec", "compile") or (isinstance(f, ast.Name) and f.id == "__import__"):
            self._add("high", "security", node.lineno, f"使用了 {name}()，存在代码注入风险")
        if name == "open" and not getattr(node, "_in_with", False):
            self._add("low", "memory", node.lineno, "open() 未包在 with 中，异常路径可能不关闭文件句柄")
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "requests":
            if not any(kw.arg == "timeout" for kw in node.keywords):
                self._add("medium", "memory", node.lineno, f"requests.{name} 未设置 timeout，可能永久挂起")
        self.generic_visit(node)

    def visit_With(self, node):
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                n._in_with = True
        self.generic_visit(node)

    visit_AsyncWith = visit_With


def scan_python(content: str, filename: str) -> list[dict]:
    issues: list[dict] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        if _SECRET_RE.search(line) or _SK_RE.search(line):
            issues.append({"file": filename, "line": lineno, "severity": "high",
                           "kind": "security", "text": "疑似硬编码密钥，请改用环境变量"})
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return issues
    issues.extend(_PyScanner(filename).visit_result(tree))
    return issues


def _visit_result(self, tree):
    self.visit(tree)
    return self.issues


_PyScanner.visit_result = _visit_result  # type: ignore[attr-defined]


def deep_scan(files: dict[str, str]) -> list[dict]:
    """对全部生成文件做跨文件扫描。"""
    issues: list[dict] = []
    for path, content in files.items():
        issues.extend(check_syntax(path, content))
        if path.lower().endswith(".py"):
            issues.extend(scan_python(content, path))
    return issues
