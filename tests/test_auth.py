# -*- coding: utf-8 -*-
"""访问令牌门禁 + 题库多学员参数。"""
import pytest
from fastapi.testclient import TestClient

from backend.core import memory
from backend.core.config import load_config
from backend.main import create_app


def _client_with_token():
    cfg = load_config()
    cfg.access_token = "secret123"
    return TestClient(create_app(cfg))


def test_api_requires_token():
    c = _client_with_token()
    assert c.get("/api/health").status_code == 401
    assert c.post("/api/chat", json={"message": "hi"}).status_code == 401


def test_api_accepts_token_variants():
    c = _client_with_token()
    assert c.get("/api/health", headers={"X-Access-Token": "secret123"}).status_code == 200
    assert c.get("/api/health", headers={"Authorization": "Bearer secret123"}).status_code == 200
    assert c.get("/api/health?token=secret123").status_code == 200
    assert c.get("/api/health", headers={"X-Access-Token": "wrong"}).status_code == 401


def test_static_frontend_not_gated():
    """静态前端不拦（SPA 需要先加载页面，由前端引导输入令牌）。"""
    c = _client_with_token()
    assert c.get("/").status_code == 200


def test_no_token_open_by_default():
    """默认配置（无令牌）完全开放，本地使用零改动。"""
    client = TestClient(create_app())
    assert client.get("/api/health").status_code == 200


def test_lc_problems_per_learner(client, monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "PROGRESS_DIR", tmp_path)
    r = client.get("/api/leetcode/problems", params={"learner_id": "lc-param"})
    assert r.status_code == 200
    assert all(p["solved"] is False for p in r.json())
    memory.record_attempt("lc-param", "two-sum", "accepted")
    solved = {p["id"]: p["solved"]
              for p in client.get("/api/leetcode/problems", params={"learner_id": "lc-param"}).json()}
    assert solved["two-sum"] is True
    others = {p["id"]: p["solved"]
              for p in client.get("/api/leetcode/problems", params={"learner_id": "someone-else"}).json()}
    assert others["two-sum"] is False
