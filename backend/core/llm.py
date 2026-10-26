"""LLM 客户端：本机 Ollama + 外部 OpenAI 兼容接口，按策略路由、失败自动降级。

- qwen3 等思考模型会输出 <think>...</think>，统一剥离
- json_mode：Ollama 走 format=json；OpenAI 走 response_format，不支持时自动降级重试
- Ollama 模型自动探测：配置的模型不存在时取列表中最匹配/第一个
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

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
            return sorted(ps, key=lambda p: p.kind != "openai")
        return sorted(ps, key=lambda p: p.kind != "ollama")   # local_first / 默认

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
