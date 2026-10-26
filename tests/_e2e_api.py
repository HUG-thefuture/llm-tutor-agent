# -*- coding: utf-8 -*-
"""端到端验证：判题 API / 学习路径 / 知识库 /（可选）开发工作流 SSE。"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:8787"


def main():
    ok = True

    # 1. 健康
    h = httpx.get(f"{BASE}/api/health", timeout=10).json()
    print("[1] health:", h["status"], "lessons:", h["lessons"], "problems:", h["problems"], "kb:", h["kb"])
    ok &= h["lessons"] >= 20 and h["problems"] == 12

    # 2. 判题 API（two-sum 正确解 → accepted）
    code = "def two_sum(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        if target - x in seen:\n            return [seen[target - x], i]\n        seen[x] = i\n    return []\n"
    j = httpx.post(f"{BASE}/api/leetcode/run", json={"problem_id": "two-sum", "code": code}, timeout=30).json()
    print("[2] judge:", j["verdict"], f"{j['passed']}/{j['total']}")
    ok &= j["verdict"] == "accepted"

    # 3. 课程 + 教学（走真实 Ollama）
    lesson = httpx.get(f"{BASE}/api/lessons", timeout=10).json()[0]
    print("[3] first lesson:", lesson["id"], "exercises:", len(lesson["exercises"]))

    # 4. 学习路径（真实 LLM 规划）
    try:
        p = httpx.post(f"{BASE}/api/learn/path", json={"goal": "从零掌握 LangChain 与 RAG，能开发知识库问答应用"}, timeout=300).json()
        steps = p.get("steps", [])
        print("[4] path:", p.get("assessment", "")[:60], "| steps:", len(steps), [s["lesson_id"] for s in steps])
        ok &= len(steps) >= 3
    except Exception as e:
        print("[4] path FAILED:", e)
        ok = False

    # 5. 对话（真实 LLM，RAG 检索）
    try:
        c = httpx.post(f"{BASE}/api/chat", json={"message": "一句话说明 chunk_overlap 的作用"}, timeout=300).json()
        print("[5] chat grounded:", c.get("grounded"), "| reply:", c.get("reply", "")[:80])
    except Exception as e:
        print("[5] chat FAILED:", e)
        ok = False

    print("E2E RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
