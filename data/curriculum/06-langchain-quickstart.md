---
id: langchain-quickstart
title: LangChain 快速上手
level: beginner
track: langchain
prereq: [llm-api-basics]
est_minutes: 60
tags: [langchain, prompt, chain, lcel]
---

# LangChain 快速上手

## LangChain 是什么
把"调模型"工程化：**模型接入 + 提示模板 + 输出解析 + 工具/检索/记忆** 的标准组件库。
本课程以 langchain 1.x 为准（`pip install -U langchain langchain-openai langchain-ollama`）。

## 第一个链：prompt | model | parser
```python
# pip install -U langchain langchain-openai   # 本机模型用 langchain-ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI          # 任何 OpenAI 兼容服务

llm = ChatOpenAI(
    model="glm-4-flash",
    api_key="你的key",
    base_url="https://open.bigmodel.cn/api/paas/v4",
)
# 本机 Ollama：from langchain_ollama import ChatOllama; llm = ChatOllama(model="qwen3:8b")

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位资深大模型开发导师，用中文回答，先结论后展开。"),
    ("human", "{question}"),
])

chain = prompt | llm | StrOutputParser()          # LCEL：用 | 串联组件

print(chain.invoke({"question": "什么是 RAG？"}))
```

## 流式输出
```python
for chunk in chain.stream({"question": "用三句话介绍 LangChain"}):
    print(chunk, end="", flush=True)
```

## 换模型只改一处
LangChain 的价值之一：业务代码与模型解耦。`init_chat_model` 支持按配置切换：
```python
from langchain.chat_models import init_chat_model
llm = init_chat_model("qwen3:8b", model_provider="ollama")
```

## 概念地图（后续课程逐一展开）
- **PromptTemplate**：变量化提示；
- **Runnable / LCEL**：一切皆 Runnable，`|` 组合、`.invoke/.stream/.batch`；
- **OutputParser / with_structured_output**：把自由文本变成结构化数据；
- **Retriever / VectorStore**：RAG 的检索层；
- **Agent / Tool**：让模型决定"做什么"。

## 常见坑
1. 版本错位：0.x 与 1.x 的导入路径差异大，报 ImportError 先查版本 `pip show langchain`；
2. `ChatOpenAI` 忘配 `base_url` → 默认打到 OpenAI 官方，报 401；
3. 模板变量 `{question}` 与字面大括号冲突时用双大括号转义。

## 自测
1. LCEL 的 `|` 在 Python 层面是什么机制？（`__or__` 返回组合 Runnable）
2. `chain.invoke` 与 `chain.stream` 返回类型差异？

## 练习
```yaml
- id: lc-1
  type: code
  prompt: |
    用 LCEL 构建一个"翻译链" translate_chain：
    system 提示"你是专业翻译，只输出译文"；human 模板含 {lang} 与 {text} 两个变量；
    输出经 StrOutputParser。写出完整代码（可用任意 OpenAI 兼容模型或 ChatOllama）。
  starter: |
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    prompt = ChatPromptTemplate.from_messages([
        # TODO: system + human(含 {lang}, {text})
    ])
    # translate_chain = prompt | ... | ...
  hints:
    - "human 消息写 ('human', '把下面文本翻译成{lang}：\n{text}')"
    - "链为 prompt | llm | StrOutputParser()，调用：translate_chain.invoke({'lang':'日语','text':'你好'})"
- id: lc-2
  type: quiz
  prompt: |
    chain.invoke({"question": "hi"}) 中传入的 dict 键名必须与什么对应？
  hints:
    - "与 ChatPromptTemplate 中的模板变量名一一对应，缺变量会抛 KeyError"
```
