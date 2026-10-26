# -*- coding: utf-8 -*-
"""RAG 检索质量离线评估（无需 LLM 在线）。

对 data/curriculum 的 20 门课程构建中文问法评估集，计算 hit@1 / hit@3 / hit@5 与 MRR；
本机有 Ollama embedding 模型时自动追加「BM25 vs 混合检索」对照，量化混合检索的增益。

运行:
    python evals/eval_retrieval.py            # 终端报告
    python evals/eval_retrieval.py --save     # 结果另存 evals/report_retrieval.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.config import load_config, CURRICULUM_DIR, USERDOCS_DIR, KB_INDEX_DIR  # noqa: E402
from backend.core.rag import KnowledgeBase  # noqa: E402

# 评估集：贴近真实学习者的中文问法 → 期望命中的课程文件（按 stem 子串匹配；
# 期望值以课程真实覆盖面为准，评估集本身也经过内容核对）
CASES = [
    ("Python 的 asyncio 异步为什么 LLM 应用离不开它", "02-python-essentials"),
    ("dataclass 怎么定义结构化数据", "02-python-essentials"),
    ("OpenAI 兼容接口怎么配置 api_key 和 base_url", "03-llm-api-basics"),
    ("怎么用 few-shot 示例让模型稳定输出 JSON", "04-prompt-engineering"),
    ("想查某个库某个版本的官方文档去哪查", "05-doc-lookup"),
    ("LangChain 第一个程序怎么跑起来", "06-langchain-quickstart"),
    ("function calling 的工具函数怎么定义给模型", "06b-function-calling"),
    ("LCEL 的管道符 | 把组件串起来是怎么回事", "07-langchain-lcel"),
    ("怎么用 Pydantic 让 LLM 输出结构化结果", "08-langchain-structured-output"),
    ("LangGraph 的 StateGraph 状态图怎么定义", "09-langgraph-basics"),
    ("Agent 框架有哪些，ReAct 模式是什么", "14-agents-and-tools"),
    ("embedding 模型怎么选，向量库有哪些", "11-embeddings-vectorstores"),
    ("RAG 切块的 chunk_size 和 overlap 怎么定", "12-rag-pipeline"),
    ("混合检索怎么做，BM25 和向量结果怎么融合重排", "13-rag-advanced"),
    ("怎么给 Agent 注册自定义工具", "14-agents-and-tools"),
    ("多轮会话的记忆怎么持久化", "15-memory-and-sessions"),
    ("FastAPI 怎么定义 POST 接口接收 Pydantic 请求体", "16-fastapi-backend"),
    ("前端 fetch 怎么调用后端接口", "17-frontend-basics"),
    ("前后端一体的项目目录怎么组织", "18-fullstack-project"),
    ("FastAPI 应用怎么用 Docker 部署", "19-deployment-and-ops"),
    ("pytest 的单元测试和参数化怎么写", "20-testing-and-quality"),
]


def make_kb(cfg) -> KnowledgeBase:
    kb = KnowledgeBase([CURRICULUM_DIR, USERDOCS_DIR], KB_INDEX_DIR, cfg.rag)
    if not kb.load_existing():
        n = kb.build()
        print(f"[index] 未找到索引，已重建：{n} chunks")
    return kb


async def eval_kb(kb: KnowledgeBase, label: str, k: int = 10) -> dict:
    hits = {1: 0, 3: 0, 5: 0}
    rr, rows = 0.0, []
    for query, expect in CASES:
        res = await kb.search(query, k=k)
        rank = next((i + 1 for i, (c, _) in enumerate(res)
                     if expect in Path(c.source).stem), None)
        for kk in hits:
            hits[kk] += bool(rank and rank <= kk)
        rr += (1.0 / rank) if rank else 0.0
        rows.append({"query": query, "expect": expect, "rank": rank,
                     "top1": res[0][0].source if res else "(无命中)"})
    n = len(CASES)
    return {"label": label, "cases": n,
            "hit@1": hits[1] / n, "hit@3": hits[3] / n, "hit@5": hits[5] / n,
            "mrr": rr / n, "rows": rows}


def report(r: dict) -> None:
    print(f"\n=== {r['label']}（{r['cases']} 条评估集，k=10）===")
    print(f"hit@1={r['hit@1']:.1%}  hit@3={r['hit@3']:.1%}  "
          f"hit@5={r['hit@5']:.1%}  MRR={r['mrr']:.3f}")
    for row in r["rows"]:
        mark = f"#{row['rank']}" if row["rank"] else "✗"
        print(f"  [{mark:>2}] {row['query']}  →  {row['top1']}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="结果写入 evals/report_retrieval.json")
    args = ap.parse_args()

    cfg = load_config()
    t0 = time.time()

    kb = make_kb(cfg)
    kb.vectors, kb.embed_model = None, None          # ① 纯 BM25
    bm25_report = await eval_kb(kb, "纯 BM25")
    report(bm25_report)

    hybrid_report = None
    if await kb.ensure_embeddings():                  # ② 混合（本机有 embedding 模型才测）
        hybrid_report = await eval_kb(kb, f"混合检索（BM25+向量 · {kb.embed_model}）")
        report(hybrid_report)
    else:
        print("\n[skip] 本机无 Ollama embedding 模型，跳过混合检索对照")

    out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "chunks": len(kb.chunks), "elapsed_sec": round(time.time() - t0, 1),
           "bm25": {k: v for k, v in bm25_report.items() if k != "rows"},
           "bm25_rows": bm25_report["rows"]}
    if hybrid_report:
        out["hybrid"] = {k: v for k, v in hybrid_report.items() if k != "rows"}
        out["hybrid_rows"] = hybrid_report["rows"]
        out["delta"] = {k: round(hybrid_report[k] - bm25_report[k], 4)
                        for k in ("hit@1", "hit@3", "hit@5", "mrr")}

    print(f"\n[done] {len(kb.chunks)} chunks，耗时 {out['elapsed_sec']}s")
    if args.save:
        dest = Path(__file__).resolve().parent / "report_retrieval.json"
        dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
