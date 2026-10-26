---
id: embeddings-vectorstores
title: 向量与向量数据库（Embedding / FAISS / Chroma / Milvus）
level: intermediate
track: rag
prereq: [langchain-quickstart]
est_minutes: 60
tags: [embedding, faiss, chroma, milvus, qdrant, pgvector]
---

# 向量与向量数据库

## Embedding：把语义变成坐标
Embedding 模型把文本映射为高维向量，**语义相近 → 余弦相似度高**。
"退款政策" 与 "退货流程" 字面不同，向量却很近 —— 这是关键词检索做不到的。

```python
# 本机 Ollama embedding
import httpx
r = httpx.post("http://127.0.0.1:11434/api/embed",
               json={"model": "nomic-embed-text", "input": ["退款政策", "退货流程"]})
v1, v2 = r.json()["embeddings"]
cos = sum(a*b for a, b in zip(v1, v2)) / (
    sum(a*a for a in v1) ** 0.5 * sum(b*b for b in v2) ** 0.5)
```
先 `ollama pull nomic-embed-text`（约 270MB）。

## 向量数据库选型
| 库 | 定位 | 场景 |
|---|---|---|
| **FAISS** | Meta 的向量检索库（进程内） | 单机、亿级向量、要自己管持久化 |
| **Chroma** | 开箱即用的嵌入式向量库 | 原型/小项目，类 SQLite 体验 |
| **Milvus / Qdrant** | 独立服务、分布式 | 生产、多副本、过滤查询 |
| **PGVector** | PostgreSQL 插件 | 已有 PG、想少一个组件 |
| **Elasticsearch** | 全文+向量混合 | 已有 ES 运维体系 |

经验：**原型用 Chroma，单机生产用 FAISS/Chroma，已有 PG 加 PGVector，大规模再上 Milvus。**

## LangChain 下的标准用法
```python
# pip install -U langchain-community faiss-cpu langchain-ollama
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="nomic-embed-text")
vs = FAISS.from_documents(chunks, embeddings)   # chunks 见下一讲
vs.save_local("kb_index")                        # 持久化
vs2 = FAISS.load_local("kb_index", embeddings, allow_dangerous_deserialization=True)

hits = vs.similarity_search("退款要几天？", k=4)           # 普通相似度
hits = vs.max_marginal_relevance_search("退款要几天？", k=4)  # MMR：相关且多样
```

## 元数据过滤：向量检索的"WHERE 子句"
```python
hits = vs.similarity_search("违约责任", k=4, filter={"source": "合同A.pdf"})
```
入库时给每个 chunk 挂 `metadata={"source": ..., "page": ...}`，检索时按条件过滤——
多租户/多文档隔离的标配。

## 常见坑
1. **查询与文档要用同一个 embedding 模型**，混用等于乱码坐标；
2. 忘记持久化，重启服务索引丢失（FAISS 不自动落盘）；
3. cosine 不归一化 / 用内积当相似度，数值没法跨库比较。

## 自测
1. 为什么"同义不同词"向量检索能命中？
2. MMR 解决什么问题？

## 练习
```yaml
- id: ev-1
  type: code
  prompt: |
    不用任何库，写 cosine_similarity(a: list[float], b: list[float]) -> float，
    处理零向量（返回 0.0），并用 [1,0,1]/[1,0,1]≈1、[1,0]/[0,1]=0 两组数据自测。
  solution: |
    import math
    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
- id: ev-2
  type: code
  prompt: |
    调用本机 Ollama /api/embed 计算"如何申请退款"与"退货流程说明"、"今天天气"的余弦相似度，
    验证语义相关性排序正确（退款-退货 > 退款-天气）。
  hints:
    - "先 ollama pull nomic-embed-text；POST /api/embed {model, input: [三句话]}"
    - "复用 ev-1 的 cosine_similarity"
```
