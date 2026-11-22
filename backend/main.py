"""FastAPI 应用入口：装配配置/LLM/知识库/课程/题库，挂载 API 与前端。

启动：python -m uvicorn backend.main:app --host 127.0.0.1 --port 8787
公网部署：config.yaml app.access_token（或环境变量 LLM_TUTOR_TOKEN）非空时，
/api/* 需携带 X-Access-Token / Authorization: Bearer / ?token= 之一，前端静态资源不受限。
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import api
from .core.config import (CURRICULUM_DIR, FRONTEND_DIR, KB_INDEX_DIR,
                          LEETCODE_FILE, USERDOCS_DIR, AppConfig, load_config)
from .core.llm import LLMClient
from .core.rag import KnowledgeBase


def _extract_token(request: Request) -> str:
    """从请求中提取访问令牌：X-Access-Token 头 > Authorization: Bearer > ?token= 查询参数。"""
    tok = request.headers.get("x-access-token", "")
    if tok:
        return tok
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token", "")


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    from .tutors.coding import ProblemBank
    from .tutors.curriculum import load_lessons

    cfg = cfg or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 后台补建向量索引（有 embedding 模型时），不阻塞启动
        if cfg.rag.use_ollama_embeddings and not kb.vectors:
            warmup = asyncio.create_task(kb.ensure_embeddings())
            yield
            warmup.cancel()
        else:
            yield

    app = FastAPI(title="LLM Tutor Agent", version="1.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    kb = KnowledgeBase([CURRICULUM_DIR, USERDOCS_DIR], KB_INDEX_DIR, cfg.rag)
    if not kb.load_existing():
        kb.build()
    lessons = load_lessons()
    bank = ProblemBank(json.loads(LEETCODE_FILE.read_text(encoding="utf-8"))
                       if LEETCODE_FILE.exists() else {})

    app.state.cfg = cfg
    app.state.llm = LLMClient(cfg)
    app.state.kb = kb
    app.state.lessons = lessons
    app.state.bank = bank

    # 可选访问令牌（公网部署安全底线）：默认空 = 完全开放（本地使用零配置）
    if cfg.access_token:
        @app.middleware("http")
        async def token_gate(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                if _extract_token(request) != cfg.access_token:
                    return JSONResponse({"detail": "访问令牌缺失或不正确"}, status_code=401)
            return await call_next(request)

    app.include_router(api)

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=app.state.cfg.host, port=app.state.cfg.port)
