---
id: fastapi-backend
title: FastAPI 后端：把 LLM 能力变成服务
level: intermediate
track: fullstack
prereq: [llm-api-basics]
est_minutes: 75
tags: [fastapi, sse, 流式, 鉴权, 日志]
---

# FastAPI 后端

## 最小可用服务
```python
# pip install fastapi uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="LLM Service")

class ChatReq(BaseModel):
    message: str
    history: list[dict] = []

@app.post("/api/chat")
async def chat(req: ChatReq):
    answer = await call_llm(req.history + [{"role": "user", "content": req.message}])
    return {"reply": answer}
# 运行: uvicorn main:app --reload  →  http://127.0.0.1:8000/docs 有自动交互文档
```
Pydantic 模型 = 自动参数校验 + 自动文档，这是 FastAPI 相对 Flask 的核心优势。

## 流式输出（SSE）：聊天体验的分水岭
```python
from fastapi.responses import StreamingResponse
import json

@app.post("/api/chat/stream")
async def chat_stream(req: ChatReq):
    async def gen():
        async for piece in llm_stream(req.message):
            yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
```
前端用 `fetch` + `ReadableStream` 逐块解析（EventSource 不支持 POST）。

## 中间件：日志与耗时
```python
import time, logging

@app.middleware("http")
async def log_requests(request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    logging.info("%s %s -> %s (%.0fms)", request.method, request.url.path,
                 resp.status_code, (time.time() - t0) * 1000)
    return resp
```

## 鉴权：API Key 中间件
```python
from fastapi import Header, HTTPException

async def check_key(x_api_key: str = Header()):
    if x_api_key != os.environ["APP_API_KEY"]:
        raise HTTPException(401, "无效的 API Key")

@app.post("/api/chat", dependencies=[Depends(check_key)])
```

## 生产三件事
1. **超时与重试**：模型调用必须 async + timeout，别让一个慢请求占满 worker；
2. **并发控制**：`asyncio.Semaphore(4)` 限制同时打向模型的请求数（GPU 就那么大）；
3. **错误规范**：统一错误 JSON `{"code": ..., "message": ...}`，前端好处理。

## 自测
1. SSE 与轮询相比省了什么？
2. 为什么模型调用要限并发？

## 练习
```yaml
- id: fb-1
  type: code
  prompt: |
    写一个 FastAPI 服务：POST /api/summarize 接收 {"text": str}，
    限制 text 长度 ≤ 5000（超长返回 400），内部调用一个假的 async def fake_llm(text) -> str
    （返回前 100 字符），并用 Semaphore(2) 限并发。
  starter: |
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import asyncio

    app = FastAPI()
    sem = asyncio.Semaphore(2)

    class Req(BaseModel):
        text: str

    @app.post("/api/summarize")
    async def summarize(req: Req):
        # TODO: 校验长度 + async with sem
        ...
  hints:
    - "if len(req.text) > 5000: raise HTTPException(400, '文本过长')"
    - "async with sem: result = await fake_llm(req.text)"
- id: fb-2
  type: quiz
  prompt: |
    前端为什么不能用 EventSource 调 POST 流式接口？给出替代方案。
  hints:
    - "EventSource 只支持 GET；改用 fetch + response.body.getReader() 手动解析 SSE 帧"
```
