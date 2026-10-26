# -*- coding: utf-8 -*-
"""烟测：用题库自带参考解法过一遍判题器。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.core.judge import run_tests  # noqa: E402

probs = json.load(open(Path(__file__).resolve().parents[1] / "data" / "leetcode" / "problems.json", encoding="utf-8"))["problems"]
allok = True
for p in probs:
    r = run_tests(p, p["reference"], timeout=10)
    ok = r["verdict"] == "accepted"
    allok = allok and ok
    print(p["id"], "PASS" if ok else "FAIL", f"{r.get('passed')}/{r.get('total')} {r.get('duration_ms')}ms", "" if ok else r)
print("ALL OK" if allok else "SOME FAILED")
sys.exit(0 if allok else 1)
