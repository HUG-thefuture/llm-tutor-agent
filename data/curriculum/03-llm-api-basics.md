---
id: llm-api-basics
title: 大模型 API 基础（OpenAI 兼容协议 + 本机 Ollama）
level: beginner
track: llm-core
prereq: [python-essentials]
est_minutes: 60
tags: [api, ollama, openai, streaming]
---

# 大模型 API 基础

## 一个协议统天下
OpenAI 的 `/chat/completions` 已成为事实标准：智谱、DeepSeek、通义、SiliconFlow、vLLM、Ollama(兼容层) 都支持。学会一次，处处可用。

## 消息模型：四种角色
```python
messages = [
    {"role": "system",    "content": "你是一位严谨的算法教练。"},   # 人设与规则
    {"role": "user",      "content": "解释一下二分查找"},
    {"role": "assistant", "content": "……上一轮回答……"},           # 历史轮次
    {"role": "user",      "content": "给个 Python 例子"},          # 追问
]
```
模型是**无状态**的：所谓多轮对话，就是把历史每次重新发一遍。

## 直接调本机 Ollama（不装任何 SDK）
```python
import httpx

def chat(prompt: str, model: str = "qwen3:8b", temperature: float = 0.7) -> str:
    r = httpx.post("http://127.0.0.1:11434/api/chat", timeout=120, json={
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature},
    })
    r.raise_for_status()
    return r.json()["message"]["content"]

print(chat("用一句话解释 temperature 参数"))
```

## OpenAI 兼容外部模型
```python
r = httpx.post("https://api.deepseek.com/chat/completions", timeout=120,
               headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
               json={"model": "deepseek-chat",
                     "messages": [{"role": "user", "content": "你好"}]})
print(r.json()["choices"][0]["message"]["content"])
```

## 关键参数
| 参数 | 作用 | 建议 |
|---|---|---|
| temperature | 随机性 | 事实/代码 0~0.3，创作 0.7~1.0 |
| max_tokens | 输出上限 | 防跑飞、控成本 |
| stream | 流式 | 聊天界面必开，首字延迟从秒级降到毫秒级 |

## 流式输出（SSE）
```python
with httpx.stream("POST", "http://127.0.0.1:11434/api/chat",
                  json={"model": "qwen3:8b", "messages": [...], "stream": True}) as r:
    for line in r.iter_lines():
        if line:
            import json
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            print(piece, end="", flush=True)
```

## 错误处理三件套
- **超时**：永远设 timeout（网络挂起 = 服务假死）；
- **重试**：429/5xx 指数退避重试 2~3 次；
- **降级**：外部失败 → 换本地模型（本助手 LLMClient 就是这样实现的）。

## 自测
1. 为什么多轮对话越聊越贵？（历史都进 context）
2. temperature=0 时输出一定完全一致吗？（近似确定，仍受并行/浮点影响）

## 练习
```yaml
- id: api-1
  type: code
  prompt: |
    封装函数 `chat_with_retry(messages, retries=3, timeout=30) -> str`：
    调用本机 Ollama /api/chat；对网络错误与 5xx 做指数退避重试（1s/2s/4s）；
    全部失败抛 RuntimeError 并附最后一次错误信息。
  starter: |
    import httpx, time

    def chat_with_retry(messages: list[dict], retries: int = 3, timeout: int = 30) -> str:
        # TODO: for i in range(retries): try ... except ...: time.sleep(2 ** i)
        ...
  hints:
    - "httpx.HTTPStatusError 由 raise_for_status() 抛出，HTTPStatusError.response.status_code >= 500 或 429 才值得重试"
    - "指数退避：time.sleep(2 ** i)"
  solution: |
    import httpx, time

    def chat_with_retry(messages, retries=3, timeout=30):
        last = None
        for i in range(retries):
            try:
                r = httpx.post("http://127.0.0.1:11434/api/chat",
                               json={"model": "qwen3:8b", "messages": messages, "stream": False},
                               timeout=timeout)
                r.raise_for_status()
                return r.json()["message"]["content"]
            except (httpx.HTTPError, KeyError) as e:
                last = e
                time.sleep(2 ** i)
        raise RuntimeError(f"重试 {retries} 次仍失败: {last}")
```
