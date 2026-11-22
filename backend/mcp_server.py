"""MCP（Model Context Protocol）服务器：把本学习助手的能力暴露为标准工具。

零依赖实现（仅标准库），stdio + JSON-RPC 2.0，兼容 MCP 2024-11-05 规范子集：
initialize / notifications/initialized / tools/list / tools/call / ping。

接入示例（Claude Desktop / ZCode 等 MCP 客户端的配置）：
    {
      "mcpServers": {
        "llm-tutor": {
          "command": "py",
          "args": ["-3", "-m", "backend.mcp_server"],
          "cwd": "D:/llm-tutor-agent"
        }
      }
    }

启动：在项目根目录执行  py -3 -m backend.mcp_server
提示：协议输出走 stdout（ensure_ascii 纯 ASCII），诊断信息一律走 stderr。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .core import judge, memory, websearch
from .core.config import (CURRICULUM_DIR, KB_INDEX_DIR, LEETCODE_FILE,
                          USERDOCS_DIR, load_config)
from .core.llm import LLMError, LLMClient
from .core.rag import KnowledgeBase

SERVER_NAME = "llm-tutor-agent"
SERVER_VERSION = "1.1.0"
PROTOCOL_VERSION = "2024-11-05"

_jsonrpc = {"jsonrpc": "2.0"}


# ---------------- 上下文 ----------------
class TutorContext:
    """MCP 工具共享的运行时（与 backend.main.create_app 装配同一批组件，但不依赖 FastAPI）。"""

    def __init__(self) -> None:
        self.cfg = load_config()
        self.llm = LLMClient(self.cfg)
        self.kb = KnowledgeBase([CURRICULUM_DIR, USERDOCS_DIR], KB_INDEX_DIR, self.cfg.rag)
        if not self.kb.load_existing():
            self.kb.build()
        from .tutors.coding import ProblemBank
        from .tutors.curriculum import load_lessons
        self.lessons = load_lessons()
        self.bank = ProblemBank(
            json.loads(LEETCODE_FILE.read_text(encoding="utf-8")) if LEETCODE_FILE.exists() else {})


# ---------------- 工具清单 ----------------
def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


TOOLS: list[dict] = [
    {
        "name": "search_knowledge",
        "description": "在学习助手知识库（20+ 门 LLM 开发中文课程）中做混合检索（BM25+向量），返回最相关的知识块及来源",
        "inputSchema": _schema({
            "query": {"type": "string", "description": "检索问题，如『RAG 切分策略怎么选』"},
            "top_k": {"type": "integer", "description": "返回条数，默认 5", "minimum": 1, "maximum": 20},
        }, ["query"]),
    },
    {
        "name": "list_courses",
        "description": "列出全部课程（id/标题/级别/方向/预计时长）",
        "inputSchema": _schema({}),
    },
    {
        "name": "get_course",
        "description": "读取一门课程的完整讲义正文（Markdown）",
        "inputSchema": _schema({
            "course_id": {"type": "string", "description": "课程 id，如 03-prompt-basics"},
        }, ["course_id"]),
    },
    {
        "name": "list_problems",
        "description": "列出力扣题库（id/标题/难度/标签）",
        "inputSchema": _schema({}),
    },
    {
        "name": "judge_code",
        "description": "对一道题库题目的提交代码做本地沙箱判题（AST 防护 + 子进程隔离 + 用例比对），无需在线判题服务",
        "inputSchema": _schema({
            "problem_id": {"type": "string", "description": "题目 id，如 two-sum"},
            "code": {"type": "string", "description": "提交的 Python 代码"},
        }, ["problem_id", "code"]),
    },
    {
        "name": "get_progress",
        "description": "读取学员学习进度：已完成课程、力扣战绩、错题本、技能矩阵",
        "inputSchema": _schema({
            "learner_id": {"type": "string", "description": "学员 id，默认 default"},
        }),
    },
    {
        "name": "chat",
        "description": "与 LLM 学习助手对话（自动携带知识库检索与学员进度画像；需要本机 Ollama 或已配置外部 API Key）",
        "inputSchema": _schema({
            "question": {"type": "string", "description": "问题"},
            "learner_id": {"type": "string", "description": "学员 id，默认 default"},
        }, ["question"]),
    },
]


# ---------------- 工具实现 ----------------
async def call_tool(name: str, arguments: dict[str, Any], ctx: TutorContext) -> str:
    if name == "search_knowledge":
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query 不能为空")
        top_k = int(arguments.get("top_k") or 5)
        hits = await ctx.kb.search(query, k=max(1, min(top_k, 20)))
        if not hits:
            return "知识库中未命中相关内容。"
        out = []
        for i, (c, score) in enumerate(hits, 1):
            out.append(f"【{i}】得分 {score:.3f} · 来源: {c.source} · {c.heading}\n{c.text}")
        return "\n\n".join(out)

    if name == "list_courses":
        lines = []
        for l in sorted(ctx.lessons.values(), key=lambda x: (x.track, x.id)):
            lines.append(f"- {l.id} | {l.title} | 级别 {l.level} | 方向 {l.track} | 约 {l.est_minutes} 分钟")
        return "\n".join(lines) or "（课程库为空）"

    if name == "get_course":
        lesson = ctx.lessons.get(str(arguments.get("course_id", "")))
        if not lesson:
            known = ", ".join(sorted(ctx.lessons.keys())[:30])
            raise ValueError(f"课程不存在；可用 id: {known}")
        return f"# {lesson.title}\n\n{lesson.body}"

    if name == "list_problems":
        lines = []
        for p in ctx.bank.list():
            lines.append(f"- {p['id']} | {p['title']} | {p['difficulty']} | 标签: {','.join(p.get('tags', []))}")
        return "\n".join(lines) or "（题库为空）"

    if name == "judge_code":
        p = ctx.bank.get(str(arguments.get("problem_id", "")))
        if not p:
            known = ", ".join(x["id"] for x in ctx.bank.list())
            raise ValueError(f"题目不存在；可用 id: {known}")
        code = str(arguments.get("code", ""))
        timeout = getattr(ctx.cfg, "leetcode_timeout", 10)
        result = await asyncio.to_thread(judge.run_tests, p, code, timeout)
        return json.dumps(result, ensure_ascii=False, default=str)

    if name == "get_progress":
        prog = memory.load(str(arguments.get("learner_id") or "default"))
        done = [k for k, v in prog["lessons"].items() if v.get("passed_at")]
        lc = prog["leetcode"]
        lines = [
            f"已完成课程: {', '.join(done) if done else '（无）'}",
            f"力扣已解出: {len(lc['solved'])} 题 {lc['solved']}",
            f"错题本: {len(prog.get('wrong_book', []))} 条",
        ]
        sm = prog.get("skill_matrix") or {}
        lines += [f"技能 {t}: L{v.get('level', 0)}（通过 {v.get('passed', 0)} 讲）"
                  for t, v in list(sm.items())[:10]]
        return "\n".join(lines)

    if name == "chat":
        from .tutors import chat as chat_tutor
        question = str(arguments.get("question", "")).strip()
        if not question:
            raise ValueError("question 不能为空")
        learner_id = str(arguments.get("learner_id") or "default")
        web_fn = websearch.web_search if ctx.cfg.web_search_enabled else None
        answer = await chat_tutor.chat(ctx.llm, ctx.kb, question, learner_id, False, web_fn)
        return answer["reply"]

    raise ValueError(f"未知工具: {name}")


# ---------------- JSON-RPC 调度 ----------------
async def handle(msg: dict, ctx: TutorContext) -> dict | None:
    """处理一条 JSON-RPC 消息；通知类（无 id）返回 None。"""
    method = msg.get("method", "")
    _id = msg.get("id")
    is_notification = "id" not in msg

    if method == "initialize":
        return {**_jsonrpc, "id": _id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {**_jsonrpc, "id": _id, "result": {}}
    if method == "tools/list":
        return {**_jsonrpc, "id": _id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        tool = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        try:
            text = await call_tool(tool, arguments, ctx)
            return {**_jsonrpc, "id": _id, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}}
        except (LLMError, ValueError) as e:
            return {**_jsonrpc, "id": _id, "result": {
                "content": [{"type": "text", "text": str(e)}], "isError": True}}
        except Exception as e:  # 工具内部异常也按 MCP 约定放进结果，不让连接崩掉
            return {**_jsonrpc, "id": _id, "result": {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True}}
    if is_notification:
        return None                      # 未知通知：静默
    return {**_jsonrpc, "id": _id, "error": {"code": -32601, "message": f"未知方法: {method}"}}


async def run_stdio(ctx: TutorContext | None = None) -> None:
    """stdio 主循环：逐行读 JSON-RPC 请求，逐条回写响应。"""
    ctx = ctx or TutorContext()
    try:                                  # Windows 管道编码兜底
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"[mcp] {SERVER_NAME} v{SERVER_VERSION} 就绪，{len(TOOLS)} 个工具",
          file=sys.stderr, flush=True)
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break                          # EOF：客户端关闭
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            resp = {**_jsonrpc, "id": None,
                    "error": {"code": -32700, "message": f"解析错误: {e}"}}
        else:
            if not isinstance(msg, dict):
                resp = {**_jsonrpc, "id": None,
                        "error": {"code": -32600, "message": "请求必须是 JSON 对象"}}
            else:
                try:
                    resp = await handle(msg, ctx)
                except Exception as e:     # 调度层兜底
                    resp = {**_jsonrpc, "id": msg.get("id"),
                            "error": {"code": -32603, "message": f"内部错误: {e}"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=True) + "\n")
            sys.stdout.flush()


def main() -> None:
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
