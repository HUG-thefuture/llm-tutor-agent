"""API 路由：对话 / 学习 / 力扣 / 开发工作流 / 系统管理。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core import judge, memory, websearch
from ..core.agent import DevAgent
from ..core.config import KB_INDEX_DIR, USERDOCS_DIR, WORKSPACE_DIR
from ..core.llm import LLMError
from ..schemas import (AnswerReq, ChatReq, DevRunReq, ExplainReq, HintReq,
                       KBUploadReq, PathReq, RunReq, SubmitReq, TeachReq)
from ..tutors import chat as chat_tutor
from ..tutors import coding, learning

api = APIRouter(prefix="/api")


# ---------------- 系统 ----------------
@api.get("/health")
async def health(request: Request):
    st = request.app.state
    llm_status = await st.llm.probe()
    return {
        "status": "ok",
        "llm": llm_status,
        "kb": st.kb.stats(),
        "lessons": len(st.lessons),
        "problems": len(st.bank.problems),
        "web_search": st.cfg.web_search_enabled,
    }


@api.get("/progress/{learner_id}")
async def progress(learner_id: str):
    return memory.load(learner_id)


# ---------------- 对话 ----------------
@api.post("/chat")
async def chat(req: ChatReq, request: Request):
    st = request.app.state
    web_fn = websearch.web_search if (req.use_web and st.cfg.web_search_enabled) else None
    try:
        return await chat_tutor.chat(st.llm, st.kb, req.message,
                                     req.learner_id, req.use_web, web_fn)
    except LLMError as e:
        raise HTTPException(503, str(e))


# ---------------- 学习 ----------------
@api.get("/lessons")
async def lessons(request: Request):
    st = request.app.state
    return [
        {**l.to_dict(), "body": l.body}
        for l in sorted(st.lessons.values(), key=lambda x: (x.track, x.id))
    ]


@api.post("/learn/path")
async def learn_path(req: PathReq, request: Request):
    st = request.app.state
    try:
        return await learning.plan_path(st.llm, st.kb, st.lessons, req.goal, req.learner_id)
    except LLMError as e:
        raise HTTPException(503, str(e))


@api.post("/learn/teach")
async def learn_teach(req: TeachReq, request: Request):
    st = request.app.state
    lesson = st.lessons.get(req.lesson_id)
    if not lesson:
        raise HTTPException(404, f"课程不存在: {req.lesson_id}")
    try:
        body = await learning.teach(st.llm, st.kb, lesson, req.learner_id)
    except LLMError as e:
        body = f"（模型暂不可用：{e}）\n\n以下是课程讲义原文：\n\n{lesson.body}"
    return {"lesson": lesson.to_dict(), "teaching": body}


@api.post("/learn/submit")
async def learn_submit(req: SubmitReq, request: Request):
    st = request.app.state
    lesson = st.lessons.get(req.lesson_id)
    if not lesson:
        raise HTTPException(404, f"课程不存在: {req.lesson_id}")
    submission = (req.code + ("\n\n" + req.notes if req.notes else "")).strip()
    if not submission:
        raise HTTPException(400, "提交内容为空")
    try:
        return await learning.grade_submission(st.llm, lesson, req.exercise_id,
                                               submission, req.learner_id)
    except LLMError as e:
        raise HTTPException(503, str(e))


@api.post("/learn/answer")
async def learn_answer(req: AnswerReq, request: Request):
    st = request.app.state
    web_fn = websearch.web_search if (req.use_web and st.cfg.web_search_enabled) else None
    try:
        return {"answer": await learning.answer(st.llm, st.kb, req.question,
                                                req.learner_id, req.use_web, web_fn)}
    except LLMError as e:
        raise HTTPException(503, str(e))


# ---------------- 力扣 ----------------
@api.get("/leetcode/problems")
async def lc_problems(request: Request):
    st = request.app.state
    prog = memory.load("default")["leetcode"]
    solved = set(prog["solved"])
    return [{**p, "solved": p["id"] in solved} for p in st.bank.list()]


@api.get("/leetcode/problems/{pid}")
async def lc_problem(pid: str, request: Request):
    st = request.app.state
    p = st.bank.get(pid)
    if not p:
        raise HTTPException(404, f"题目不存在: {pid}")
    return {"id": p["id"], "title": p["title"], "difficulty": p["difficulty"],
            "tags": p["tags"], "description": p["description"],
            "signature": p.get("signature", ""), "starter": coding.starter_code(p),
            "hint_count": len(p.get("hints", [])),
            "followup": p.get("followup", "")}


@api.post("/leetcode/run")
async def lc_run(req: RunReq, request: Request):
    st = request.app.state
    p = st.bank.get(req.problem_id)
    if not p:
        raise HTTPException(404, f"题目不存在: {req.problem_id}")
    result = judge.run_tests(p, req.code, timeout=st.cfg.leetcode_timeout)
    result["solved"] = memory.record_attempt(req.learner_id, p["id"], result["verdict"])["solved"]
    return result


@api.post("/leetcode/hint")
async def lc_hint(req: HintReq, request: Request):
    st = request.app.state
    p = st.bank.get(req.problem_id)
    if not p:
        raise HTTPException(404, f"题目不存在: {req.problem_id}")
    text = await coding.hint(st.llm, p, req.level, req.code)
    return {"level": req.level, "text": text,
            "has_more": req.level < len(p.get("hints", []))}


@api.post("/leetcode/review")
async def lc_review(req: RunReq, request: Request):
    st = request.app.state
    p = st.bank.get(req.problem_id)
    if not p:
        raise HTTPException(404, f"题目不存在: {req.problem_id}")
    try:
        return await coding.review(st.llm, p, req.code, st.cfg.leetcode_timeout, req.learner_id)
    except LLMError as e:
        return {"judge": judge.run_tests(p, req.code, timeout=st.cfg.leetcode_timeout),
                "coach": {"complexity": {"time": "", "space": ""}, "issues": [],
                          "style_tips": [], "edge_cases": [],
                          "summary": f"（AI 点评暂不可用：{e}）", "score": -1}}


@api.post("/leetcode/explain")
async def lc_explain(req: ExplainReq, request: Request):
    st = request.app.state
    p = st.bank.get(req.problem_id)
    if not p:
        raise HTTPException(404, f"题目不存在: {req.problem_id}")
    try:
        return {"text": await coding.explain_solution(st.llm, p, req.code)}
    except LLMError as e:
        raise HTTPException(503, str(e))


# ---------------- 开发工作流（SSE） ----------------
@api.post("/dev/run")
async def dev_run(req: DevRunReq, request: Request):
    st = request.app.state
    if not req.goal.strip():
        raise HTTPException(400, "目标不能为空")
    agent = DevAgent(st.llm, WORKSPACE_DIR, st.cfg.dev_agent)

    async def gen():
        try:
            async for ev in agent.run(req.goal, req.project or None):
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:  # 兜底，避免流中断无提示
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@api.get("/dev/projects")
async def dev_projects():
    WORKSPACE_DIR.mkdir(exist_ok=True)
    out = []
    for d in sorted(WORKSPACE_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            report = d / ".agent_run.json"
            meta = {}
            if report.exists():
                try:
                    meta = json.loads(report.read_text(encoding="utf-8")).get("report", {})
                except Exception:
                    pass
            files = [str(f.relative_to(d)).replace("\\", "/")
                     for f in d.rglob("*") if f.is_file() and not f.name.startswith(".")]
            out.append({"project": d.name, "files": files, "report": meta})
    return out


@api.get("/dev/file")
async def dev_file(project: str, path: str):
    from ..core.agent import _safe_join
    root = (WORKSPACE_DIR / project).resolve()
    if not str(root).startswith(str(WORKSPACE_DIR.resolve())):
        raise HTTPException(400, "非法项目名")
    target = _safe_join(root, path)
    if target is None or not target.is_file():
        raise HTTPException(404, "文件不存在")
    return {"path": path, "content": target.read_text(encoding="utf-8", errors="ignore")}


# ---------------- 知识库 / 设置 ----------------
@api.post("/kb/reindex")
async def kb_reindex(request: Request):
    st = request.app.state
    n = st.kb.build()
    embedded = await st.kb.ensure_embeddings()
    return {"chunks": n, "embeddings": embedded, **st.kb.stats()}


@api.post("/kb/upload")
async def kb_upload(req: KBUploadReq, request: Request):
    USERDOCS_DIR.mkdir(parents=True, exist_ok=True)
    import re
    slug = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", "-", req.title)[:40] or "doc"
    target = USERDOCS_DIR / f"{slug}.md"
    target.write_text(f"# {req.title}\n\n{req.text}", encoding="utf-8")
    st = request.app.state
    n = st.kb.build()
    return {"saved": target.name, "chunks": n}


@api.get("/config")
async def get_config(request: Request):
    st = request.app.state
    return {
        "strategy": st.cfg.strategy,
        "providers": [{"name": p.name, "kind": p.kind, "model": p.model,
                       "enabled": p.resolved_enabled()} for p in st.cfg.providers],
        "dev_agent": {"max_plan_cycles": st.cfg.dev_agent.max_plan_cycles,
                      "max_dev_cycles": st.cfg.dev_agent.max_dev_cycles,
                      "max_total_cycles": st.cfg.dev_agent.max_total_cycles},
        "web_search": st.cfg.web_search_enabled,
    }


@api.post("/config/test-llm")
async def test_llm(request: Request):
    st = request.app.state
    results = []
    for p in st.llm.providers:
        item = {"name": p.name, "ok": False, "detail": ""}
        try:
            text = await st.llm.chat(
                [{"role": "user", "content": "只回复两个字：在线"}],
                prefer=p.name, temperature=0.0, max_tokens=512, timeout=60)
            item["ok"], item["detail"] = True, text[:50]
        except Exception as e:
            item["detail"] = f"{type(e).__name__}: {e}"
        results.append(item)
    return {"results": results}
