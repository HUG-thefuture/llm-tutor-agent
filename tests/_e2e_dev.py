# -*- coding: utf-8 -*-
"""开发工作流 SSE 端到端验证：真实模型跑一个完整小项目。"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:8787"
GOAL = "用 Python 实现模块 fizzbuzz.py（函数 fizzbuzz(n): 3 的倍数返回 Fizz, 5 的倍数返回 Buzz, 15 的倍数返回 FizzBuzz, 否则返回数字）并附 tests/test_fizzbuzz.py pytest 测试"

phases = []
files = []
done = None
errors = []

with httpx.stream("POST", f"{BASE}/api/dev/run", json={"goal": GOAL, "project": "e2e-fizzbuzz"},
                  timeout=900.0) as r:
    print("status:", r.status_code)
    buf = ""
    for chunk in r.iter_text():
        buf += chunk
        while "\n\n" in buf:
            frame, buf = buf.split("\n\n", 1)
            if not frame.startswith("data: "):
                continue
            ev = json.loads(frame[6:])
            t = ev.get("type")
            if t == "phase":
                phases.append((ev.get("phase"), ev.get("status"), ev.get("verdict", "")))
                print(f"[{ev.get('ts')}] {ev.get('phase')} {ev.get('status')} {ev.get('verdict','')} {str(ev.get('note',''))[:60]}")
            elif t == "file":
                files.append(ev.get("path"))
                print(f"[{ev.get('ts')}] FILE {ev.get('path')} ({ev.get('bytes')}B)")
            elif t == "tests":
                print(f"[{ev.get('ts')}] TESTS ok={ev.get('ok')} {str(ev.get('summary'))[:80]}")
            elif t == "issue":
                print(f"[{ev.get('ts')}] ISSUE [{ev.get('severity')}] {str(ev.get('text'))[:100]}")
            elif t == "retro":
                print(f"[{ev.get('ts')}] RETRO {str(ev.get('retro', {}).get('summary', ''))[:100]}")
            elif t == "done":
                done = ev
                print(f"[{ev.get('ts')}] DONE ok={ev.get('ok')} project={ev.get('project')} cycles={ev.get('report', {}).get('cycles')}")
            elif t == "error":
                errors.append(ev.get("text"))
                print(f"[{ev.get('ts')}] ERROR {ev.get('text')}")
            elif t == "log":
                print(f"[{ev.get('ts')}] LOG {str(ev.get('text'))[:90]}")

print("\nphases:", len(phases), "files:", files, "errors:", errors)
ok = bool(done and done.get("ok") and not errors and files)
print("DEV E2E RESULT:", "PASS" if ok else "PARTIAL/FAIL")
sys.exit(0 if ok else 1)
