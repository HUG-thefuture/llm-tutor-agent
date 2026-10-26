"""FastAPI 应用入口：装配配置/LLM/知识库/课程/题库，挂载 API 与前端。

启动：python -m uvicorn backend.main:app --host 127.0.0.1 --port 8787
"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import api
from .core.config import (CURRICULUM_DIR, FRONTEND_DIR, KB_INDEX_DIR,
                          LEETCODE_FILE, USERDOCS_DIR, AppConfig, load_config)
from .core.llm import LLMClient
from .core.rag import KnowledgeBase


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    from .tutors.coding import ProblemBank
    from .tutors.curriculum import load_lessons

    cfg = cfg or load_config()
    app = FastAPI(title="LLM Tutor Agent", version="1.0.0")
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

    app.include_router(api)

    @app.on_event("startup")
    async def _warmup():
        # 后台补建向量索引（有 embedding 模型时），不阻塞启动
        if cfg.rag.use_ollama_embeddings and not kb.vectors:
            asyncio.create_task(kb.ensure_embeddings())

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=app.state.cfg.host, port=app.state.cfg.port)
