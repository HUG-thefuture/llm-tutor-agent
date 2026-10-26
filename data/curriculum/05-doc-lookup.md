---
id: doc-lookup
title: 查文档与读源码（自主进阶核心能力）
level: beginner
track: llm-core
prereq: [llm-api-basics]
est_minutes: 40
tags: [文档, 源码, 调试, 搜索]
---

# 查文档与读源码

## 为什么单独开一讲
大模型生态 API 迭代极快（LangChain 一年大版本数个），**教程会过期，查文档的能力不会**。本讲练的是"授人以渔"。

## 三层信息源（优先级从高到低）
1. **官方文档**：python.langchain.com / docs.llamaindex.ai / docs.rs —— 有版本切换器，注意选你装的版本；
2. **源码**：`import inspect; inspect.getsource(fn)` 或直接去 site-packages / GitHub 读实现；
3. **错误检索**：把完整报错（含堆栈最后一行）丢进搜索引擎/问 AI，比描述现象准确十倍。

## 查 API 的标准动作
```python
# 1) 这个对象有什么方法？
print(type(retriever), dir(retriever))

# 2) 这个函数怎么用？
help(retriever.invoke)          # 或 inspect.signature(retriever.invoke)

# 3) 看源码实现
import inspect
print(inspect.getsource(type(retriever).invoke))
```

## 读报错的技巧
从**最后一行**往上读：异常类型 → 消息 → 自己代码所在帧（不是库内部帧）。
```text
TypeError: ChatOpenAI.__init__() got an unexpected keyword argument 'model_name'
→ 说明装的版本参数名变了，去文档查当前版本的参数列表
```

## AI 时代的查文档姿势
1. 让 AI 生成代码后，**用文档验证关键 API 是否存在**（AI 会编造不存在的参数）；
2. 把报错 + 相关源码片段一起给 AI，让它基于事实而非猜测修 bug；
3. 官方文档搜不到时，去 GitHub issues 搜报错原文。

## 本项目就是活教材
本助手 `backend/core/llm.py` 手写了 Ollama 与 OpenAI 两种协议的调用、降级与 JSON 提取——
对照官方 API 文档读它的源码，是最快的学习方式。

## 自测
1. 装的是 langchain 1.x，网上教程是 0.2 的写法，报错 ImportError，怎么办？
2. `inspect.signature` 与 `help` 的区别？

## 练习
```yaml
- id: doc-1
  type: code
  prompt: |
    用 inspect 写一个函数 `api_of(obj, keyword: str) -> list[str]`：
    列出对象上名字包含 keyword 的所有公开方法/属性（不含下划线开头的私有成员）。
    例如 api_of("abc", "up") 应包含 "upper"。
  starter: |
    import inspect

    def api_of(obj, keyword: str) -> list[str]:
        # TODO: dir(obj) 过滤 + keyword in name
        ...
  solution: |
    def api_of(obj, keyword: str) -> list[str]:
        return [n for n in dir(obj) if not n.startswith("_") and keyword.lower() in n.lower()]
- id: doc-2
  type: quiz
  prompt: |
    遇到报错 ModuleNotFoundError: No module named 'langchain_community'，正确的排查顺序是？
    A. 直接 pip install langchain_community
    B. 先确认当前 venv 与 Python 版本，再确认包名是否随版本拆分变化，然后安装并核对文档导入路径
  hints:
    - "答案 B。先确认环境再动手，避免装错环境/装错包；langchain 生态曾多次拆分包名"
```
