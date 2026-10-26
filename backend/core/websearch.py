"""联网检索（DuckDuckGo HTML 双通道），无 Key、失败静默返回空列表。"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _unwrap_uddg(href: str) -> str:
    if "uddg=" in href:
        try:
            q = parse_qs(urlparse(href).query)
            return unquote(q.get("uddg", [href])[0])
        except Exception:
            return href
    return href


def _parse_html(body: str, limit: int) -> list[dict]:
    out: list[dict] = []
    # html.duckduckgo.com: <a rel="nofollow" class="result__a" href="...">标题</a>
    for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]*class="result__a"|$)',
            body, re.S):
        url = _unwrap_uddg(m.group(1))
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        snippet_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
        snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)).strip() if snippet_m else ""
        if title and url.startswith("http"):
            out.append({"title": title, "url": url, "snippet": snippet[:300]})
        if len(out) >= limit:
            break
    return out


def _parse_lite(body: str, limit: int) -> list[dict]:
    # lite.duckduckgo.com: 结果行 <a rel="nofollow" href="...">标题</a> + 紧随的 snippet td
    out: list[dict] = []
    for m in re.finditer(r'<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>', body, re.S):
        url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "duckduckgo.com" in url or not title:
            continue
        out.append({"title": title, "url": url, "snippet": ""})
        if len(out) >= limit:
            break
    return out


async def web_search(query: str, max_results: int = 5, timeout: float = 8.0) -> list[dict]:
    headers = {"User-Agent": _UA}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        try:
            r = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            if r.status_code == 200:
                hits = _parse_html(r.text, max_results)
                if hits:
                    return hits
            r = await client.get("https://lite.duckduckgo.com/lite/", params={"q": query})
            if r.status_code == 200:
                return _parse_lite(r.text, max_results)
        except Exception:
            pass
    return []
