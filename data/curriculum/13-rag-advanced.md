---
id: rag-advanced
title: RAG 进阶：混合检索 / 重排 / 评估 / 增量更新
level: advanced
track: rag
prereq: [rag-pipeline]
est_minutes: 75
tags: [混合检索, rerank, 评估, 增量更新, 缓存]
---

# RAG 进阶

## 一、混合检索：BM25 + 向量
向量检索懂语义但弱于**精确词**（型号、编号、人名）；BM25 关键词检索相反。
两者互补，融合打分（RRF 或加权归一化）是生产标配——本助手 backend/core/rag.py
就是 BM25 + 可选向量的混合实现，可对照阅读。

```python
def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion：docs 各路排名的倒数和"""
    scores = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return dict(sorted(scores.items(), key=lambda x: -x[1]))
```

## 二、重排序（Rerank）
粗召回 top20 → 精排 top4 再进 prompt。Rerank 模型（如 bge-reranker）对
query-doc 逐对精算相关性，比向量相似度更准但更贵，所以只排头部。
无 rerank 模型时，LLM 自己也能当 reranker：把候选给模型打分排序。

## 三、查询改写
用户问题常常不适合直接检索（口语、多问合一、缺上下文）：
```text
多轮对话中把"它怎么收费"改写为"ChatGPT Plus 怎么收费"（指代消解）；
复杂问题拆成 2-3 个子问题分别检索，结果合并（multi-query）。
```

## 四、评估：没有指标就没有优化
构建 20~50 条 (问题, 标准答案出处) 的评测集，测四个指标：
| 指标 | 问什么 | 粗测方法 |
|---|---|---|
| **召回率** | 该命中的块进 top-k 了吗 | 标注出处 chunk_id，算命中率 |
| **忠实度** | 回答是否只依据资料 | 让 LLM 逐句核对引用 |
| **相关性** | 回答对题吗 | LLM 1-5 打分 |
| **拒答率** | 该拒的拒了吗 | 无关问题集上测 |
（RAGAS 等框架自动化了这套流程，原理如上。）

## 五、增量更新与缓存
```python
import hashlib
doc_hash = hashlib.md5(raw_bytes).hexdigest()
# 入库前查 metadata 里是否已有 doc_hash：有 → 跳过；文档变了 → 先删该 doc 的 chunks 再插
```
高频问题的检索结果 + 生成结果整体缓存（key=问题归一化），命中率轻松 30%+。

## 六、分块调优方法论
一次只动一个变量：chunk_size → k → rerank → query 改写，每动一次跑评测集对比。
没有评测集的调参 = 玄学。

## 自测
1. 为什么 BM25 和向量检索要混用？
2. 召回率与忠实度分别卡在哪一环？

## 练习
```yaml
- id: ra-1
  type: code
  prompt: |
    实现 rrf_fuse(rank_a: list[str], rank_b: list[str], k: int = 60) -> list[str]：
    对两路检索结果做 RRF 融合，返回融合后的文档 id 列表（降序）。
    自测：rank_a=[d1,d2,d3], rank_b=[d2,d4] → d2 应排第一。
  solution: |
    def rrf_fuse(rank_a, rank_b, k=60):
        scores = {}
        for ranking in (rank_a, rank_b):
            for rank, doc in enumerate(ranking):
                scores[doc] = scores.get(doc, 0) + 1 / (k + rank + 1)
        return [d for d, _ in sorted(scores.items(), key=lambda x: -x[1])]
- id: ra-2
  type: code
  prompt: |
    写 incremental_add(vs, doc_id, new_chunks)：入库前先删除同 doc_id 的旧 chunk 再添加。
    假设 vs 是 Chroma collection，提供 vs.delete(where={"doc_id": doc_id}) 与 vs.add_documents(...)。
  hints:
    - "先查后删：collection.get(where={'doc_id': doc_id}) 确认存在再 delete，避免报错"
  solution: |
    def incremental_add(vs, doc_id, new_chunks):
        old = vs.get(where={"doc_id": doc_id})
        if old["ids"]:
            vs.delete(ids=old["ids"])
        vs.add_documents(new_chunks, ids=[f"{doc_id}-{i}" for i in range(len(new_chunks))])
```
