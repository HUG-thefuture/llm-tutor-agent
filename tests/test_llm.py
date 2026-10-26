# -*- coding: utf-8 -*-
"""LLM 工具函数测试：think 标签清洗 + JSON 提取。"""
import pytest

from backend.core.llm import LLMError, extract_json, strip_think


def test_strip_think_complete():
    assert strip_think("<think>内部推理</think>答案是 42") == "答案是 42"


def test_strip_think_unclosed():
    assert strip_think("前言<think>没闭合的思考……") == "前言"


def test_extract_json_direct():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "好的，如下：\n```json\n{\"a\": [1, 2]}\n```\n以上。"
    assert extract_json(text) == {"a": [1, 2]}


def test_extract_json_with_think_and_prose():
    text = '<think>让我想想…</think>输出如下：{"verdict": "pass", "issues": []}'
    assert extract_json(text) == {"verdict": "pass", "issues": []}


def test_extract_json_nested_braces_in_strings():
    text = '{"code": "def f():\\n    return {\\"x\\": 1}"}'
    assert extract_json(text)["code"].startswith("def f()")


def test_extract_json_failure_raises():
    with pytest.raises(LLMError):
        extract_json("完全没有结构化内容的回答")
