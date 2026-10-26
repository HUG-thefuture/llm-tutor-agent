# -*- coding: utf-8 -*-
"""RAG 检索质量回归门：纯 BM25 路径（无需 Ollama / 外部模型，CI 可跑）。

阈值取自 evals/eval_retrieval.py 实测基线（hit@3=81.0%、MRR=0.789，2026-10-27），
留出充分裕量防止数据微调误伤；若检索实现退化到此阈值以下则 CI 拦截。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.config import load_config  # noqa: E402
from evals.eval_retrieval import make_kb, eval_kb  # noqa: E402


def test_retrieval_quality_baseline():
    async def run():
        kb = make_kb(load_config())
        kb.vectors, kb.embed_model = None, None  # 强制纯 BM25，CI 环境零依赖
        return await eval_kb(kb, "bm25-regression")

    r = asyncio.run(run())
    assert r["hit@3"] >= 0.60, f"hit@3 退化: {r['hit@3']:.1%}（基线 81.0%）"
    assert r["mrr"] >= 0.50, f"MRR 退化: {r['mrr']:.3f}（基线 0.789）"
    assert r["hit@5"] >= 0.70, f"hit@5 退化: {r['hit@5']:.1%}（基线 90.5%）"
