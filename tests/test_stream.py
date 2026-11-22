# -*- coding: utf-8 -*-
"""流式对话：ThinkStripper 状态机 / demo provider / /api/chat/stream SSE。"""
import asyncio
import json
from pathlib import Path

import pytest

from backend.core import memory
from backend.core.config import AppConfig, ProviderCfg, load_config
from backend.core.llm import LLMClient, LLMError, ThinkStripper

from conftest import MockLLM


# ---------------- ThinkStripper：跨 chunk 边界安全剥离 <think> ----------------
def test_stripper_plain_passthrough():
    s = ThinkStripper()
    assert s.feed("你好，") + s.feed("学员！") + s.flush() == "你好，学员！"


def test_think_stripper_split_tag():
    s = ThinkStripper()
    out = s.feed("<th") + s.feed("ink>hidden") + s.feed("</th") + s.feed("ink>visible")
    assert out == "visible"


def test_think_stripper_unclosed_dropped():
    s = ThinkStripper()
    assert s.feed("前文<think>思考中") == "前文"
    assert s.feed("更多思考") == ""
    assert s.flush() == ""                 # 未闭合的思考块整体丢弃，与 strip_think 语义一致


def test_think_stripper_partial_then_close():
    s = ThinkStripper()
    out = s.feed("a<th") + s.feed("ink>x</think>b") + s.flush()
    assert out == "ab"


def test_think_stripper_multiple_blocks():
    s = ThinkStripper()
    out = s.feed("<think>1</think>A<think>2</think>B")
    assert out == "AB"


# ---------------- demo provider（演示模式） ----------------
def test_demo_mode_env_injection(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    cfg = load_config()
    assert cfg.demo_mode is True
    assert any(p.kind == "demo" for p in cfg.providers)


def test_demo_answer_extracts_knowledge():
    cfg = AppConfig(providers=[ProviderCfg(name="demo-offline", kind="demo", base_url="", enabled="true")])
    llm = LLMClient(cfg)
    msgs = [{"role": "system", "content": "sys"},
            {"role": "user", "content":
             "什么是 BM25？\n\n【知识库资料】\n【资料 1】来源: 01-rag.md · 检索\nBM25 是经典排序算法。"
             "它基于词频与文档长度。\n【资料 2】来源: 02.md · 索引\n倒排索引用于快速定位。"}]
    out = asyncio.run(llm.chat(msgs))
    assert "演示模式" in out
    assert "BM25 是经典排序算法" in out
    assert "01-rag.md" in out


def test_demo_json_mode_rejected():
    cfg = AppConfig(providers=[ProviderCfg(name="demo-offline", kind="demo", base_url="", enabled="true")])
    llm = LLMClient(cfg)
    with pytest.raises(LLMError):
        asyncio.run(llm.chat([{"role": "user", "content": "规划"}], json_mode=True))


def test_demo_last_in_chain():
    """demo 无论何种策略都排在降级链末位，真实模型优先。"""
    cfg = AppConfig(strategy="local_first", providers=[
        ProviderCfg(name="demo-offline", kind="demo", base_url="", enabled="true"),
        ProviderCfg(name="ollama-local", kind="ollama", base_url="http://127.0.0.1:1", enabled="true"),
    ])
    order = LLMClient(cfg)._order()
    assert [p.kind for p in order] == ["ollama", "demo"]


# ---------------- /api/chat/stream SSE ----------------
class StreamMock(MockLLM):
    def __init__(self, stream_script=None, **kw):
        super().__init__(**kw)
        self.stream_script = list(stream_script or [])

    async def chat_stream(self, messages, **kw):
        for d in self.stream_script:
            yield d


def test_chat_stream_sse(client, monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "PROGRESS_DIR", tmp_path)
    llm = StreamMock(stream_script=["你好", "，学员"])
    original = client.app.state.llm
    client.app.state.llm = llm
    try:
        r = client.post("/api/chat/stream", json={"message": "打个招呼", "learner_id": "stream-test"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        events = [json.loads(line[6:]) for line in r.text.split("\n\n") if line.startswith("data: ")]
        deltas = "".join(e["text"] for e in events if e["type"] == "delta")
        assert deltas == "你好，学员"
        done = [e for e in events if e["type"] == "done"]
        assert done and done[0]["reply"] == "你好，学员"
        # 历史落盘（含学员侧问题与完整应答）
        hist = memory.chat_history("stream-test")
        assert [h["role"] for h in hist[-2:]] == ["user", "assistant"]
    finally:
        client.app.state.llm = original


def test_chat_stream_llm_error_event(client, monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "PROGRESS_DIR", tmp_path)

    class ErrMock(MockLLM):
        async def chat_stream(self, messages, **kw):
            raise LLMError("所有模型流式调用失败")
            yield  # pragma: no cover

    original = client.app.state.llm
    client.app.state.llm = ErrMock()
    try:
        r = client.post("/api/chat/stream", json={"message": "hi", "learner_id": "stream-err"})
        assert r.status_code == 200
        events = [json.loads(line[6:]) for line in r.text.split("\n\n") if line.startswith("data: ")]
        assert any(e["type"] == "error" and "流式调用失败" in e["text"] for e in events)
    finally:
        client.app.state.llm = original


def test_legacy_chat_endpoint_still_works(client, monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "PROGRESS_DIR", tmp_path)
    llm = StreamMock(chat_script=["一次性回答"])
    original = client.app.state.llm
    client.app.state.llm = llm
    try:
        r = client.post("/api/chat", json={"message": "hi", "learner_id": "legacy"})
        assert r.status_code == 200
        assert r.json()["reply"] == "一次性回答"
    finally:
        client.app.state.llm = original
