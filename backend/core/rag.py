"""轻量 RAG 知识库：纯 Python BM25 + 可选 Ollama embedding 混合检索。

设计意图：它既是本 Agent 的知识底座，本身也是一份“可运行的 RAG 教材”——
data/curriculum 里有对应的 LangChain/FAISS 版本课程，两相对照学习。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import httpx
import yaml

from .config import RagCfg


# ---------------- 切块 ----------------
@dataclass
class Chunk:
    id: str
    source: str          # 相对文件路径
    title: str
    heading: str
    text: str


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


def split_markdown(text: str, source: str, title: str,
                   chunk_size: int = 700, overlap: int = 120) -> list[Chunk]:
    """按标题分节、按段落聚合；标题作为 chunk 元数据，检索命中可溯源。"""
    chunks: list[Chunk] = []
    heading, buf, idx = "", [], 0

    def flush():
        nonlocal buf, idx
        body = "\n".join(buf).strip()
        if body:
            idx += 1
            chunks.append(Chunk(f"{source}#{idx}", source, title, heading or "(开头)", body))
        buf = []

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:                                   # 新章节：先落盘上一节
            flush()
            heading = m.group(2).strip()
            buf.append(line)
            continue
        buf.append(line)
        if sum(len(x) for x in buf) >= chunk_size:
            tail = "\n".join(buf)[-overlap:]
            flush()
            buf = [f"（承接 {heading}）", tail] if overlap > 0 else []
    flush()
    return chunks


# ---------------- 分词（中文 bigram + 英文单词） ----------------
_ASCII_RE = re.compile(r"[a-zA-Z0-9_+#.]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for w in _ASCII_RE.findall(text.lower()):
        tokens.append(w)
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


# ---------------- BM25 ----------------
class BM25:
    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(docs_tokens)
        self.avgdl = (sum(len(d) for d in docs_tokens) / self.N) if self.N else 0.0
        self.tfs: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for toks in docs_tokens:
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            self.tfs.append(tf)
            for t in tf:
                df[t] = df.get(t, 0) + 1
        self.df = df

    def idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = []
        for tf in self.tfs:
            dl = sum(tf.values())
            s = 0.0
            for t in set(query_tokens):
                f = tf.get(t, 0)
                if f == 0:
                    continue
                s += self.idf(t) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
                )
            out.append(s)
        return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (na * nb)


# ---------------- 知识库 ----------------
def _frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except Exception:
                meta = {}
            return (meta if isinstance(meta, dict) else {}), parts[2]
    return {}, text


class KnowledgeBase:
    """目录集合 → 切块 → 索引；支持 BM25，且本机有 embedding 模型时叠加向量检索。"""

    def __init__(self, dirs: list[Path], index_dir: Path, rag_cfg: RagCfg, ollama_base: str = "http://127.0.0.1:11434"):
        self.dirs = [d for d in dirs if d.exists()]
        self.index_dir = index_dir
        self.cfg = rag_cfg
        self.ollama_base = ollama_base
        self.chunks: list[Chunk] = []
        self.bm25: Optional[BM25] = None
        self.vectors: Optional[list[list[float]]] = None
        self.embed_model: Optional[str] = None

    # ---- 索引构建 ----
    def build(self) -> int:
        self.chunks = []
        for d in self.dirs:
            for f in sorted(d.rglob("*")):
                if f.suffix.lower() not in (".md", ".txt", ".json") or not f.is_file():
                    continue
                rel = f.relative_to(d.parent).as_posix() if d != f.parent else f.name
                try:
                    text = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                if f.suffix.lower() == ".md":
                    meta, body = _frontmatter(text)
                    title = str(meta.get("title") or f.stem)
                    if meta.get("tags"):
                        body = f"标签: {', '.join(map(str, meta['tags']))}\n" + body
                else:
                    title, body = f.stem, text
                self.chunks.extend(split_markdown(
                    body, rel, title, self.cfg.chunk_size, self.cfg.chunk_overlap))
        self.bm25 = BM25([tokenize(c.text) for c in self.chunks])
        self._save()
        return len(self.chunks)

    def _chunks_file(self) -> Path:
        return self.index_dir / "chunks.jsonl"

    def _save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with self._chunks_file().open("w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

    def load_existing(self) -> bool:
        f = self._chunks_file()
        if not f.exists():
            return False
        try:
            self.chunks = [Chunk(**json.loads(x)) for x in
                           f.read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception:
            return False
        if not self.chunks:
            return False
        self.bm25 = BM25([tokenize(c.text) for c in self.chunks])
        vfile = self.index_dir / "embeddings.json"
        if vfile.exists():
            try:
                data = json.loads(vfile.read_text(encoding="utf-8"))
                if len(data.get("vectors", [])) == len(self.chunks):
                    self.vectors = data["vectors"]
                    self.embed_model = data.get("model")
            except Exception:
                self.vectors = None
        return True

    # ---- embedding ----
    async def _pick_embed_model(self) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"{self.ollama_base}/api/tags")
                names = {m["name"] for m in r.json().get("models", [])}
        except Exception:
            return None
        for cand in self.cfg.embed_candidates:
            for n in names:
                if n.split(":")[0] == cand.split(":")[0]:
                    return n
        return None

    async def _embed(self, texts: list[str], model: str, batch: int = 16) -> Optional[list[list[float]]]:
        vecs: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for i in range(0, len(texts), batch):
                    r = await client.post(
                        f"{self.ollama_base}/api/embed",
                        json={"model": model, "input": texts[i : i + batch]},
                    )
                    r.raise_for_status()
                    vecs.extend(r.json()["embeddings"])
            return vecs
        except Exception:
            return None

    async def ensure_embeddings(self) -> bool:
        """本机有 embedding 模型且未建向量时补建；失败静默退化为纯 BM25。"""
        if not self.cfg.use_ollama_embeddings or not self.chunks:
            return False
        vfile = self.index_dir / "embeddings.json"
        if self.vectors and len(self.vectors) == len(self.chunks):
            return True
        model = await self._pick_embed_model()
        if not model:
            return False
        vecs = await self._embed([c.text[:2000] for c in self.chunks], model)
        if not vecs or len(vecs) != len(self.chunks):
            return False
        self.vectors, self.embed_model = vecs, model
        self.index_dir.mkdir(parents=True, exist_ok=True)
        vfile.write_text(json.dumps({"model": model, "vectors": vecs}), encoding="utf-8")
        return True

    # ---- 检索 ----
    async def _query_vector(self, query: str) -> Optional[list[float]]:
        if not self.vectors or not self.embed_model:
            return None
        vecs = await self._embed([query], self.embed_model)
        return vecs[0] if vecs else None

    async def search(self, query: str, k: Optional[int] = None) -> list[tuple[Chunk, float]]:
        k = k or self.cfg.top_k
        if not self.bm25 or not self.chunks:
            return []
        bm = self.bm25.scores(tokenize(query))
        qv = await self._query_vector(query)
        if qv:
            cs = [cosine(qv, v) for v in self.vectors]
            max_bm = max(bm) or 1.0
            max_cs = max(cs) or 1.0
            combined = [0.5 * (b / max_bm) + 0.5 * (c / max_cs) for b, c in zip(bm, cs)]
        else:
            combined = bm
        order = sorted(range(len(self.chunks)), key=lambda i: combined[i], reverse=True)[:k]
        return [(self.chunks[i], combined[i]) for i in order if combined[i] > 0]

    async def context_async(self, query: str, k: Optional[int] = None) -> tuple[str, list[Chunk]]:
        """检索并拼装成可直接塞进 prompt 的资料块（含来源标注）。"""
        hits = await self.search(query, k)
        if not hits:
            return "", []
        parts, used = [], []
        for c, s in hits:
            parts.append(f"【资料 {len(used)+1}】来源: {c.source} · {c.heading}\n{c.text}")
            used.append(c)
        return "\n\n".join(parts), used

    def stats(self) -> dict:
        return {
            "chunks": len(self.chunks),
            "sources": len({c.source for c in self.chunks}),
            "embeddings": bool(self.vectors),
            "embed_model": self.embed_model or "",
        }
