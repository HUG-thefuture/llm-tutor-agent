---
id: python-essentials
title: Python 快速通关（面向大模型开发）
level: beginner
track: python
prereq: [env-and-tools]
est_minutes: 60
tags: [python, typing, async, dataclass]
---

# Python 快速通关

## 目标
不求全，只过大模型开发**天天用到**的 20%：类型注解、dataclass、f-string、异常、文件、异步。

## 类型注解：现代 Python 的标配
```python
def chat(messages: list[dict], model: str = "qwen3:8b") -> str:
    """messages 形如 [{"role": "user", "content": "..."}]"""
    ...
```
注解不改变运行时行为，但让 IDE 补全、静态检查、协作者都受益。

## dataclass：结构化数据的正确姿势
```python
from dataclasses import dataclass, field

@dataclass
class Message:
    role: str                 # system | user | assistant | tool
    content: str
    meta: dict = field(default_factory=dict)   # 注意：可变默认值必须用 default_factory
```

## 异常与资源管理
```python
try:
    resp = call_llm(payload, timeout=30)
except TimeoutError:
    resp = fallback()          # 降级
finally:
    log("done")                # 无论成败都执行
```

## 异步：为什么 LLM 应用离不开它
一次模型调用动辄数秒，同步代码会把服务卡死。`async/await` 让一个进程服务多个并发请求：
```python
import asyncio, httpx

async def ask(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("http://127.0.0.1:11434/api/chat",
                              json={"model": "qwen3:8b", "messages": [{"role": "user", "content": prompt}], "stream": False})
        return r.json()["message"]["content"]

asyncio.run(ask("你好"))
```

## 常见坑
1. 可变默认参数 `def f(x=[])` —— 多次调用共享同一个 list。
2. Windows 下文件读写忘写 `encoding="utf-8"` → 中文乱码。
3. `except:` 裸捕获吞掉 KeyboardInterrupt，至少写 `except Exception`。
4. 循环里反复 `open()` 大文件 —— 移到循环外或用 with。

## 自测
1. `list[dict]` 与 `List[Dict]` 的区别？（前者 3.9+ 内置泛型）
2. 什么场景必须用 async？

## 练习
```yaml
- id: py-1
  type: bugfix
  prompt: |
    修复下面的代码（有 3 处问题：可变默认参数、未关闭文件、裸 except）：
    ```python
    def save(rows=[]):
        try:
            f = open("out.json", "w")
            f.write(str(rows))
        except:
            pass
        return rows
    ```
  hints:
    - "默认值改 None，函数内 rows = rows if rows is not None else []"
    - "用 with open(...) as f: 并指定 encoding='utf-8'"
    - "except 至少写 Exception，并且要处理而不是静默吞掉"
  solution: |
    import json
    def save(rows=None):
        rows = rows if rows is not None else []
        try:
            with open("out.json", "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
        except OSError as e:
            raise RuntimeError(f"写入失败: {e}") from e
        return rows
- id: py-2
  type: code
  prompt: 用 async + httpx 写一个 `ask_all(prompts: list[str]) -> list[str]`，并发调用本机 Ollama
    （http://127.0.0.1:11434/api/chat），任一失败返回空字符串且不影响其他。
  starter: |
    import asyncio, httpx

    async def ask_all(prompts: list[str]) -> list[str]:
        # TODO: asyncio.gather + 每个任务内部 try/except
        ...
  hints:
    - "先写单个协程 ask(prompt)，内部 try/except Exception 返回 ''"
    - "asyncio.gather(*[ask(p) for p in prompts])"
```
