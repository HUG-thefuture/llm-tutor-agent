# -*- coding: utf-8 -*-
"""测试公共设施：项目路径 + MockLLM（脚本化应答，无需真实模型）。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class MockLLM:
    """按脚本顺序应答：chat 取 chat_script，chat_json 取 json_script。"""

    available = True

    def __init__(self, chat_script=None, json_script=None):
        self.chat_script = list(chat_script or [])
        self.json_script = list(json_script or [])
        self.chat_calls = []
        self.json_calls = []

    async def chat(self, messages, **kw):
        self.chat_calls.append(messages)
        item = self.chat_script.pop(0)
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)

    async def chat_json(self, messages, **kw):
        self.json_calls.append(messages)
        item = self.json_script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def probe(self):
        return [{"name": "mock", "kind": "ollama", "model": "mock", "ok": True, "detail": ""}]


@pytest.fixture
def mock_llm():
    return MockLLM()
