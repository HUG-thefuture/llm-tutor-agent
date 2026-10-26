# -*- coding: utf-8 -*-
"""判题器测试：通过/错误/拦截/超时 + 全题库参考解法自洽。"""
import json
from pathlib import Path

from backend.core.judge import run_tests

ROOT = Path(__file__).resolve().parents[1]
PROBLEMS = json.loads((ROOT / "data" / "leetcode" / "problems.json").read_text(encoding="utf-8"))["problems"]
BY_ID = {p["id"]: p for p in PROBLEMS}


def test_reference_solutions_all_accepted():
    for p in PROBLEMS:
        r = run_tests(p, p["reference"], timeout=15)
        assert r["verdict"] == "accepted", f"{p['id']} 参考解法未通过: {r}"


def test_wrong_solution():
    p = BY_ID["two-sum"]
    r = run_tests(p, "def two_sum(nums, target):\n    return [0, 0]\n")
    assert r["verdict"] == "wrong" and r["passed"] < r["total"]


def test_syntax_error_reported():
    p = BY_ID["two-sum"]
    r = run_tests(p, "def two_sum(nums, target):\n    return [0, 0\n")
    assert r["verdict"] == "error" and "语法" in (r.get("stderr_tail") or "")


def test_banned_import_blocked():
    p = BY_ID["two-sum"]
    r = run_tests(p, "import os\n\ndef two_sum(nums, target):\n    return [0, 1]\n")
    assert r["verdict"] == "blocked" and "os" in r["violations"][0]


def test_dangerous_call_blocked():
    p = BY_ID["two-sum"]
    r = run_tests(p, "def two_sum(nums, target):\n    eval('1+1')\n    return [0, 1]\n")
    assert r["verdict"] == "blocked"


def test_infinite_loop_timeout():
    p = BY_ID["two-sum"]
    r = run_tests(p, "def two_sum(nums, target):\n    while True:\n        pass\n", timeout=3)
    assert r["verdict"] == "timeout"
