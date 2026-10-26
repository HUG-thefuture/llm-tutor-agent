# -*- coding: utf-8 -*-
"""开发工作流 Agent 测试：正常流水线 + 审查驳回回炉 + 安全路径。"""
import asyncio
import json

from backend.core.agent import DevAgent, _safe_join
from backend.core.config import DevAgentCfg
from conftest import MockLLM

GOOD_PLAN = {
    "summary": "实现问候模块",
    "files": [{"path": "hello.py", "purpose": "问候函数"}],
    "steps": ["写 hello.py"],
    "tests": [], "acceptance": ["hello() 返回 hi"], "risks": [],
}
GOOD_FILE = {"path": "hello.py", "content": "def hello():\n    return 'hi'\n"}


def _happy_llm():
    return MockLLM(
        chat_script=["拆分两个模块：问候与测试。"],
        json_script=[
            GOOD_PLAN,
            {"verdict": "pass", "issues": [], "suggestions": []},
            GOOD_FILE,
            {"verdict": "pass", "issues": []},
            {"summary": "一切顺利", "knowledge_points": ["函数"], "next_steps": ["进阶"]},
        ],
    )


def test_dev_agent_happy_path(tmp_path):
    llm = _happy_llm()
    agent = DevAgent(llm, tmp_path, DevAgentCfg(cmd_timeout=30))
    events = asyncio.run(_collect(agent, "实现问候函数"))
    phases = [(e["phase"], e["status"]) for e in events if e["type"] == "phase"]
    assert ("THINK", "start") in phases and ("TEST", "end") in phases
    assert (tmp_path / events[-1]["project"] / "hello.py").exists()
    done = [e for e in events if e["type"] == "done"][0]
    assert done["ok"] is True
    assert any(e["type"] == "retro" for e in events)
    # 过程留痕落盘
    assert (tmp_path / done["project"] / ".agent_run.json").exists()


def test_dev_agent_review_revise_loops_back(tmp_path):
    llm = MockLLM(
        chat_script=["第一轮思考。", "第二轮思考（吸收审查意见）。"],
        json_script=[
            GOOD_PLAN,
            {"verdict": "revise", "issues": ["缺少错误处理计划"], "suggestions": []},  # 审查驳回
            GOOD_PLAN,                                                                 # 重做计划
            {"verdict": "pass", "issues": [], "suggestions": []},
            GOOD_FILE,
            {"verdict": "pass", "issues": []},
            {"summary": "复盘", "knowledge_points": [], "next_steps": []},
        ],
    )
    agent = DevAgent(llm, tmp_path, DevAgentCfg(cmd_timeout=30))
    events = asyncio.run(_collect(agent, "实现问候函数"))
    plan_starts = [e for e in events if e["type"] == "phase" and e["phase"] == "PLAN" and e["status"] == "start"]
    assert len(plan_starts) == 2                      # 审查不过 → 计划重做了一次
    review_ends = [e for e in events if e["type"] == "phase" and e["phase"] == "REVIEW" and e["status"] == "end"]
    assert any("错误处理" in i for e in review_ends for i in e.get("issues", []))
    done = [e for e in events if e["type"] == "done"][0]
    assert done["ok"] is True


def test_dev_agent_test_failure_reworks(tmp_path):
    bad_file = {"path": "hello.py", "content": "def hello(:\n    return 'hi'\n"}  # 语法错误
    llm = MockLLM(
        chat_script=["思考1", "思考2"],
        json_script=[
            GOOD_PLAN,
            {"verdict": "pass", "issues": [], "suggestions": []},
            bad_file,
            {"path": "hello.py", "content": "def hello(:\n    return 1\n"},  # 重试仍语法错误
            GOOD_PLAN,
            {"verdict": "pass", "issues": [], "suggestions": []},
            GOOD_FILE,
            {"verdict": "pass", "issues": []},
            {"summary": "复盘", "knowledge_points": [], "next_steps": []},
        ],
    )
    agent = DevAgent(llm, tmp_path, DevAgentCfg(cmd_timeout=30, max_total_cycles=6))
    events = asyncio.run(_collect(agent, "实现问候函数"))
    think_starts = [e for e in events if e["type"] == "phase" and e["phase"] == "THINK" and e["status"] == "start"]
    assert len(think_starts) >= 2                     # 开发失败 → 回到最初“思考”阶段
    done = [e for e in events if e["type"] == "done"][0]
    assert done["ok"] is True


def test_safe_join_rejects_escape(tmp_path):
    assert _safe_join(tmp_path, "a/b.py") is not None
    assert _safe_join(tmp_path, "../x.py") is None
    assert _safe_join(tmp_path, "C:/evil.py") is None
    assert _safe_join(tmp_path, "") is None


async def _collect(agent, goal):
    events = []
    async for ev in agent.run(goal):
        events.append(ev)
    return events
