"""LLM 客户端：本机 Ollama + 外部 OpenAI 兼容接口，按策略路由、失败自动降级。

- qwen3 等思考模型会输出 <think>...</think>，统一剥离（含流式场景的状态机版）
- json_mode：Ollama 走 format=json；OpenAI 走 response_format，不支持时自动降级重试
- Ollama 模型自动探测：配置的模型不存在时取列表中最匹配/第一个
- 流式：chat_stream() 支持 Ollama NDJSON 与 OpenAI SSE 两种增量协议
- demo kind：演示模式 provider，无任何模型/Key 时从知识库摘录作答
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, AsyncIterator, Optional

import httpx

from .config import AppConfig, ProviderCfg


class LLMError(RuntimeError):
    """所有模型均不可用或输出不可解析。"""


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text: str) -> str:
    text = _THINK_RE.sub("", text)
    if "<think>" in text:                     # 未闭合的思考块：丢弃其之前内容
        text = text.split("<think>")[0]
    return text.strip()


class ThinkStripper:
    """流式版 <think> 剥离：跨 chunk 边界安全。

    规则与 strip_think 对齐：完整 <think>…</think> 内容丢弃；
    流结束时仍未闭合的 think 内容同样丢弃（不把思考过程漏给用户）。
    """

    _OPEN, _CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.in_think = False
        self._buf = ""                        # 尾部缓冲：可能构成半个标签

    def _partial_len(self, tag: str) -> int:
        """_buf 尾部与 tag 前缀的最大重叠长度（可能是被截断的标签）。"""
        for k in range(min(len(tag) - 1, len(self._buf)), 0, -1):
            if self._buf[-k:] == tag[:k]:
                return k
        return 0

    def feed(self, delta: str) -> str:
        """喂入一个增量，返回其中可直接展示的部分。"""
        if not delta:
            return ""
        self._buf += delta
        out: list[str] = []
        while self._buf:
            if self.in_think:
                i = self._buf.find(self._CLOSE)
                if i >= 0:
                    self.in_think = False
                    self._buf = self._buf[i + len(self._CLOSE):]
                    continue
                keep = self._partial_len(self._CLOSE)
                self._buf = self._buf[-keep:] if keep else ""   # think 内容本身丢弃
                return "".join(out)
            i = self._buf.find(self._OPEN)
            if i >= 0:
                out.append(self._buf[:i])
                self.in_think = True
                self._buf = self._buf[i + len(self._OPEN):]
                continue
            keep = self._partial_len(self._OPEN)
            if len(self._buf) > keep:
                out.append(self._buf[: len(self._buf) - keep])
                self._buf = self._buf[len(self._buf) - keep:]
            break                                     # 剩余可能是半个标签，等下一块
        return "".join(out)

    def flush(self) -> str:
        """流结束：放出残留缓冲（未闭合 think 的残留直接丢弃）。"""
        if self.in_think:
            self._buf = ""
            return ""
        out, self._buf = self._buf, ""
        return out


def extract_json(text: str) -> Any:
    """从模型输出中稳健提取 JSON：直接解析 → 代码块 → 花括号/方括号平衡扫描。"""
    t = strip_think(text).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start == -1:
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start : i + 1])
                        except Exception:
                            break
    raise LLMError(f"无法从模型输出解析 JSON：{t[:200]!r}")


def resolve_providers(cfg: AppConfig) -> list[ProviderCfg]:
    return [p for p in cfg.providers if p.resolved_enabled()]


class LLMClient:
    def __init__(self, cfg: AppConfig, timeout: float = 300.0):
        self.cfg = cfg
        self.providers = resolve_providers(cfg)
        self.timeout = timeout
        self._ollama_models: dict[str, tuple[float, list[str]]] = {}

    # ---------- provider 顺序 ----------
    def _order(self, prefer: Optional[str] = None) -> list[ProviderCfg]:
        ps = list(self.providers)
        if not ps:
            return []
        if prefer:
            hit = [p for p in ps if p.name == prefer]
            rest = [p for p in ps if p.name != prefer]
            return hit + rest
        if self.cfg.strategy == "only" and self.cfg.strategy_only:
            hit = [p for p in ps if p.name == self.cfg.strategy_only]
            return hit if hit else ps[:1]
        if self.cfg.strategy == "external_first":
            return sorted(ps, key=lambda p: (p.kind == "demo", p.kind != "openai"))
        return sorted(ps, key=lambda p: (p.kind == "demo", p.kind != "ollama"))   # local_first / 默认；demo 永远殿后

    def _sort_ollama_models(self, wanted: str, models: list[str]) -> list[str]:
        """配置名 qwen3 优先匹配 qwen3:*，其次任意同前缀，最后原顺序。"""
        if not wanted:
            return models
        base = wanted.split(":")[0].lower()
        ranked = sorted(
            models,
            key=lambda m: (
                0 if m.lower() == wanted.lower()
                else 1 if m.lower().startswith(base.lower())
                else 2,
            ),
        )
        return ranked

    async def _ollama_list(self, base_url: str) -> list[str]:
        cached = self._ollama_models.get(base_url)
        now = time.time()
        if cached and now - cached[0] < 120:
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"{base_url.rstrip('/')}/api/tags")
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            models = cached[1] if cached else []
        self._ollama_models[base_url] = (now, models)
        return models

    # ---------- 单次调用 ----------
    async def _call_ollama(
        self, client: httpx.AsyncClient, p: ProviderCfg,
        messages: list[dict], temperature: float, json_mode: bool,
        max_tokens: Optional[int], model_override: Optional[str] = None,
    ) -> str:
        models = await self._ollama_list(p.base_url)
        if models:
            wanted = model_override or p.model
            model = wanted if wanted in models else (self._sort_ollama_models(wanted, models)[0])
        else:
            model = model_override or p.model or "qwen3:8b"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if json_mode:
            payload["format"] = "json"
        r = await client.post(f"{p.base_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise LLMError(str(data["error"]))
        return strip_think(data.get("message", {}).get("content", ""))

    async def _call_openai(
        self, client: httpx.AsyncClient, p: ProviderCfg,
        messages: list[dict], temperature: float, json_mode: bool,
        max_tokens: Optional[int], model_override: Optional[str] = None,
    ) -> str:
        if not p.api_key():
            raise LLMError(f"provider {p.name} 未配置 API Key")
        headers = {"Authorization": f"Bearer {p.api_key()}"}
        payload: dict[str, Any] = {
            "model": model_override or p.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        url = f"{p.base_url.rstrip('/')}/chat/completions"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = await client.post(url, json=payload, headers=headers)
        if json_mode and r.status_code == 400 and "response_format" in r.text:
            payload.pop("response_format", None)      # 网关不支持时降级重试
            r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "") or ""
        return strip_think(content)

    # ---------- 演示模式（无模型降级） ----------
    def _call_demo(self, messages: list[dict]) -> str:
        """演示模式应答：从提示内嵌的【知识库资料】做提取式摘录，零依赖确定性输出。"""
        user_q, context = "", ""
        for m in messages:
            content = m.get("content", "") if isinstance(m, dict) else ""
            if m.get("role") == "user":
                user_q = content
            if "【知识库资料】" in content:
                context = content.split("【知识库资料】", 1)[1]
        lines = ["（演示模式：未配置模型 API Key，以下为知识库原文摘录，配置后可获得完整对话能力）"]
        picked = 0
        for b in context.split("【资料 "):
            b = b.strip()
            if not b:
                continue
            head, _, body = b.partition("】")
            body = body.strip()
            if not body:
                continue
            first = re.split(r"(?<=[。！？.!?])\s*", body)[0][:160]
            lines.append(f"- {head.strip()}：{first}")
            picked += 1
            if picked >= 4:
                break
        if not picked:
            lines.append("- 本次未命中知识库资料。在本机启动 Ollama 或在 .env 配置任一 API Key 即可获得完整回答。")
        if user_q:
            lines.append(f"\n你的问题：{user_q[-200:]}")
        return "\n".join(lines)

    # ---------- 流式调用 ----------
    async def _stream_ollama(
        self, client: httpx.AsyncClient, p: ProviderCfg,
        messages: list[dict], temperature: float,
        max_tokens: Optional[int], model_override: Optional[str] = None,
    ) -> AsyncIterator[str]:
        models = await self._ollama_list(p.base_url)
        if models:
            wanted = model_override or p.model
            model = wanted if wanted in models else (self._sort_ollama_models(wanted, models)[0])
        else:
            model = model_override or p.model or "qwen3:8b"
        payload: dict[str, Any] = {
            "model": model, "messages": messages, "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        async with client.stream("POST", f"{p.base_url.rstrip('/')}/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if data.get("error"):
                    raise LLMError(str(data["error"]))
                delta = data.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if data.get("done"):
                    break

    async def _stream_openai(
        self, client: httpx.AsyncClient, p: ProviderCfg,
        messages: list[dict], temperature: float,
        max_tokens: Optional[int], model_override: Optional[str] = None,
    ) -> AsyncIterator[str]:
        if not p.api_key():
            raise LLMError(f"provider {p.name} 未配置 API Key")
        headers = {"Authorization": f"Bearer {p.api_key()}"}
        payload: dict[str, Any] = {
            "model": model_override or p.model, "messages": messages,
            "temperature": temperature, "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        async with client.stream("POST", f"{p.base_url.rstrip('/')}/chat/completions",
                                 json=payload, headers=headers) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    data = json.loads(body)
                except Exception:
                    continue
                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("delta", {}).get("content", "") or ""
                if delta:
                    yield delta

    async def chat_stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: Optional[int] = None,
        prefer: Optional[str] = None,
        timeout: Optional[float] = None,
        model_override: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """流式对话：按降级链尝试；某 provider 已产出增量后中断则就地收尾（不重复换源）。"""
        order = self._order(prefer)
        if not order:
            raise LLMError(
                "没有可用的模型提供方：请先启动 Ollama（ollama serve），"
                "或在 config.yaml / .env 中配置外部 API Key"
            )
        errors: list[str] = []
        timeout = timeout or self.timeout
        async with httpx.AsyncClient(timeout=timeout) as client:
            for p in order:
                if p.kind == "demo":
                    text = self._call_demo(messages)
                    if text:
                        yield text
                        return
                    errors.append("[demo-offline] 无可摘录内容")
                    continue
                try:
                    stripper = ThinkStripper()
                    emitted = 0
                    stream = (self._stream_ollama(client, p, messages, temperature, max_tokens, model_override)
                              if p.kind == "ollama"
                              else self._stream_openai(client, p, messages, temperature, max_tokens, model_override))
                    async for delta in stream:
                        visible = stripper.feed(delta)
                        if visible:
                            emitted += len(visible)
                            yield visible
                    tail = stripper.flush()
                    if tail:
                        yield tail
                    if emitted:
                        return                          # 该 provider 成功流完
                    errors.append(f"[{p.name}] 输出流为空")
                except Exception as e:
                    if emitted:                         # 已给用户流出部分内容：就地收尾，不换源重放
                        return
                    errors.append(f"[{p.name}] {type(e).__name__}: {e}")
        raise LLMError("所有模型流式调用失败 → " + " ； ".join(errors))

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        prefer: Optional[str] = None,
        timeout: Optional[float] = None,
        model_override: Optional[str] = None,
    ) -> str:
        order = self._order(prefer)
        if not order:
            raise LLMError(
                "没有可用的模型提供方：请先启动 Ollama（ollama serve），"
                "或在 config.yaml / .env 中配置外部 API Key"
            )
        errors: list[str] = []
        timeout = timeout or self.timeout
        async with httpx.AsyncClient(timeout=timeout) as client:
            for p in order:
                try:
                    if p.kind == "demo":
                        if json_mode:
                            errors.append("[demo-offline] 演示模式不支持 JSON 结构化任务")
                            continue
                        return self._call_demo(messages)
                    if p.kind == "ollama":
                        return await self._call_ollama(client, p, messages, temperature, json_mode, max_tokens, model_override)
                    return await self._call_openai(client, p, messages, temperature, json_mode, max_tokens, model_override)
                except Exception as e:  # 降级到下一个 provider
                    errors.append(f"[{p.name}] {type(e).__name__}: {e}")
        raise LLMError("所有模型调用失败 → " + " ； ".join(errors))

    async def chat_json(self, messages: list[dict], **kw) -> Any:
        text = await self.chat(messages, json_mode=True, **kw)
        return extract_json(text)

    # ---------- 健康探测 ----------
    async def probe(self) -> list[dict]:
        out = []
        for p in self.providers:
            item = {"name": p.name, "kind": p.kind, "model": p.model, "ok": False, "detail": ""}
            try:
                if p.kind == "demo":
                    item["ok"] = True
                    item["detail"] = "演示模式（知识库摘录，无需模型）"
                    out.append(item)
                    continue
                if p.kind == "ollama":
                    models = await self._ollama_list(p.base_url)
                    item["ok"] = bool(models)
                    item["detail"] = f"{len(models)} 个模型: {', '.join(models[:6])}"
                else:
                    item["ok"] = bool(p.api_key())
                    item["detail"] = "已配置 Key" if p.api_key() else "缺少 API Key"
            except Exception as e:
                item["detail"] = f"{type(e).__name__}: {e}"
            out.append(item)
        return out

    @property
    def available(self) -> bool:
        return bool(self.providers)
