# -*- coding: utf-8 -*-
"""MCP 服务器：JSON-RPC 调度单测 + stdio 子进程集成测试。"""
import asyncio
import json
import queue
import subprocess
import sys
import threading

import pytest

from backend.core.config import AppConfig
from backend.mcp_server import TOOLS, TutorContext, handle


# ---------------- JSON-RPC 调度单测 ----------------
@pytest.fixture(scope="module")
def ctx():
    return TutorContext()


def _rpc(method, _id=None, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if _id is not None:
        msg["id"] = _id
    if params is not None:
        msg["params"] = params
    return msg


def test_initialize(ctx):
    resp = asyncio.run(handle(_rpc("initialize", _id=1), ctx))
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in resp["result"]["capabilities"]
    assert resp["result"]["serverInfo"]["name"] == "llm-tutor-agent"


def test_notification_returns_none(ctx):
    assert asyncio.run(handle(_rpc("notifications/initialized"), ctx)) is None


def test_ping(ctx):
    assert asyncio.run(handle(_rpc("ping", _id=2), ctx))["result"] == {}


def test_tools_list(ctx):
    resp = asyncio.run(handle(_rpc("tools/list", _id=3), ctx))
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"search_knowledge", "list_courses", "get_course",
            "list_problems", "judge_code", "get_progress", "chat"} <= names
    for t in resp["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_unknown_method_error(ctx):
    resp = asyncio.run(handle(_rpc("resources/list", _id=4), ctx))
    assert resp["error"]["code"] == -32601


def test_tools_call_search(ctx):
    resp = asyncio.run(handle(_rpc("tools/call", _id=5, params={
        "name": "search_knowledge", "arguments": {"query": "RAG 切分策略", "top_k": 2}}), ctx))
    content = resp["result"]["content"][0]["text"]
    assert resp["result"]["isError"] is False
    assert len(content) > 0


def test_tools_call_search_empty_query(ctx):
    resp = asyncio.run(handle(_rpc("tools/call", _id=6, params={
        "name": "search_knowledge", "arguments": {"query": "  "}}), ctx))
    assert resp["result"]["isError"] is True


def test_tools_call_get_course(ctx):
    any_id = sorted(ctx.lessons.keys())[0]
    resp = asyncio.run(handle(_rpc("tools/call", _id=7, params={
        "name": "get_course", "arguments": {"course_id": any_id}}), ctx))
    assert resp["result"]["isError"] is False
    assert len(resp["result"]["content"][0]["text"]) > 50


def test_tools_call_get_course_unknown(ctx):
    resp = asyncio.run(handle(_rpc("tools/call", _id=8, params={
        "name": "get_course", "arguments": {"course_id": "no-such-course"}}), ctx))
    assert resp["result"]["isError"] is True
    assert "不存在" in resp["result"]["content"][0]["text"]


def test_tools_call_judge_code_accepted(ctx):
    p = ctx.bank.get("two-sum")
    resp = asyncio.run(handle(_rpc("tools/call", _id=9, params={
        "name": "judge_code", "arguments": {"problem_id": "two-sum", "code": p["reference"]}}), ctx))
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["verdict"] == "accepted"


def test_tools_call_judge_code_blocked(ctx):
    resp = asyncio.run(handle(_rpc("tools/call", _id=10, params={
        "name": "judge_code", "arguments": {"problem_id": "two-sum", "code": "import os"}}), ctx))
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["verdict"] == "blocked"


def test_tools_call_judge_code_unknown_problem(ctx):
    resp = asyncio.run(handle(_rpc("tools/call", _id=11, params={
        "name": "judge_code", "arguments": {"problem_id": "no-such", "code": "x=1"}}), ctx))
    assert resp["result"]["isError"] is True


def test_tools_call_get_progress(ctx):
    resp = asyncio.run(handle(_rpc("tools/call", _id=12, params={
        "name": "get_progress", "arguments": {"learner_id": "mcp-test"}}), ctx))
    text = resp["result"]["content"][0]["text"]
    assert "力扣" in text


# ---------------- stdio 子进程集成 ----------------
class _Reader(threading.Thread):
    def __init__(self, stream):
        super().__init__(daemon=True)
        self.q: queue.Queue = queue.Queue()
        self.stream = stream

    def run(self):
        for line in self.stream:
            self.q.put(line)


def _drain(reader, n, timeout=120):
    out = []
    for _ in range(n):
        out.append(json.loads(reader.q.get(timeout=timeout)))
    return out


def test_stdio_roundtrip():
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.mcp_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
    )
    try:
        reader = _Reader(proc.stdout)
        reader.start()
        reqs = [
            _rpc("initialize", _id=1, params={}),
            _rpc("notifications/initialized"),
            _rpc("ping", _id=2),
            _rpc("tools/list", _id=3),
            _rpc("tools/call", _id=4, params={"name": "list_problems", "arguments": {}}),
            _rpc("tools/call", _id=5, params={
                "name": "search_knowledge", "arguments": {"query": "prompt 提示词工程", "top_k": 1}}),
        ]
        proc.stdin.write("\n".join(json.dumps(r, ensure_ascii=True) for r in reqs) + "\n")
        proc.stdin.flush()
        resp = _drain(reader, 5, timeout=120)     # 通知不回包，共 5 条响应
        by_id = {r["id"]: r for r in resp}
        assert by_id[1]["result"]["protocolVersion"] == "2024-11-05"
        assert by_id[2]["result"] == {}
        assert len(by_id[3]["result"]["tools"]) == len(TOOLS)
        assert "two-sum" in by_id[4]["result"]["content"][0]["text"]
        assert by_id[5]["result"]["isError"] is False
        # 坏 JSON 不崩，返回 -32700
        proc.stdin.write("not-json\n")
        proc.stdin.flush()
        bad = _drain(reader, 1, timeout=30)[0]
        assert bad["error"]["code"] == -32700
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
