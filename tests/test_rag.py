# -*- coding: utf-8 -*-
"""RAG 知识库测试：切块、BM25 检索、中英文分词。"""
import asyncio

from backend.core.config import RagCfg
from backend.core.rag import BM25, KnowledgeBase, split_markdown, tokenize


def test_tokenize_mixed():
    toks = tokenize("使用 LangChain 构建 知识库")
    assert "langchain" in toks
    assert "知识" in toks and "识库" in toks          # 中文 bigram


def test_split_markdown_headings():
    md = "# 标题\n" + "内容A。" * 50 + "\n## 第二节\n" + "内容B。" * 50
    chunks = split_markdown(md, "t.md", "T")
    assert any(c.heading == "第二节" for c in chunks)
    assert all(c.text.strip() for c in chunks)


def test_bm25_ranking():
    docs = [["rag", "检索", "向量"], ["蛋糕", "烘焙", "奶油"], ["rag", "切分", "评估"]]
    bm = BM25(docs)
    scores = bm.scores(["rag"])
    assert scores[0] > scores[1] and scores[0] >= scores[2] > 0


def test_kb_build_and_search(tmp_path):
    (tmp_path / "rag.md").write_text(
        "---\ntitle: RAG 指南\ntags: [rag]\n---\n# RAG\n检索增强生成（RAG）先检索知识库再生成回答。\n"
        "向量检索把文本变成 embedding 再算相似度。", encoding="utf-8")
    (tmp_path / "cake.md").write_text("# 烘焙\n做蛋糕需要面粉、鸡蛋和糖，烤箱预热 180 度。", encoding="utf-8")
    kb = KnowledgeBase([tmp_path], tmp_path / "idx", RagCfg())
    n = kb.build()
    assert n >= 2
    hits = asyncio.run(kb.search("RAG 检索增强 embedding", k=2))
    assert hits and hits[0][0].source == "rag.md"
    ctx, used = asyncio.run(kb.context_async("RAG 是什么", k=1))
    assert "资料" in ctx and used[0].source == "rag.md"
    assert kb.stats()["embeddings"] is False          # 无 embedding 模型时不联网
