---
id: frameworks-survey
title: 框架全景与选型（LlamaIndex / Haystack / Semantic Kernel / AutoGen / CrewAI / Dify）
level: intermediate
track: langchain
prereq: [langchain-quickstart]
est_minutes: 45
tags: [选型, llamaindex, haystack, autogen, crewai, dify]
---

# 框架全景与选型

## 一张图看懂生态位
| 框架 | 生态位 | 适合 |
|---|---|---|
| **LangChain / LCEL** | 通用编排组件库 | 大多数 LLM 应用的默认起点 |
| **LangGraph** | 有状态图编排 | 多步 Agent、需要循环/审批 |
| **LlamaIndex** | 数据接入 + 检索专精 | RAG 密集型、文档种类多 |
| **Haystack** | 生产级检索管线（deepset） | 搜索/问答系统、 pipelines 可声明式配置 |
| **Semantic Kernel** | 微软系，.NET/Python | 企业 .NET 生态、Office 集成 |
| **AutoGen** | 多 Agent 会话框架 | 多角色讨论、代码生成协作 |
| **CrewAI** | 角色分工多 Agent | 模拟团队协作（研究员/写手/审查） |
| **Dify / Coze / FastGPT** | 低代码平台 | 快速搭建、非程序员运营 |

## 选型三问
1. **主要矛盾是"检索"还是"编排"？** 检索复杂 → LlamaIndex；流程复杂 → LangGraph；
2. **团队语言栈？** .NET → Semantic Kernel；全栈 JS → LangChain.js 同概念迁移；
3. **要交付速度还是要可控性？** 演示/PoC → Dify 平台拖拽；生产核心系统 → 代码框架。

## 同一件事的三种写法（以"文档问答"为例）
```python
# LangChain：链式组合
chain = {"context": retriever, "question": RunnablePassthrough()} | prompt | llm

# LlamaIndex：查询引擎抽象
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
index = VectorStoreIndex.from_documents(SimpleDirectoryReader("docs").load_data())
resp = index.as_query_engine().query("总结这份文档")

# Haystack：声明式管线
from haystack import Pipeline
p = Pipeline()
p.add_component("retriever", ...)
p.add_component("reader", ...)
p.connect("retriever", "reader")
```
概念互通：加载→切分→向量化→检索→生成。学透一个，其余触类旁通。

## 现实建议
1. 别追新：LangChain + 一个向量库能覆盖 80% 场景；
2. 多 Agent 框架（AutoGen/CrewAI）演示惊艳，生产要评估成本与可控性；
3. 低代码平台适合内部工具与验证期，不要把核心业务锁死在平台上。

## 自测
1. LlamaIndex 相对 LangChain 的优势赛道是什么？
2. 为什么说"低代码平台别承载核心业务"？

## 练习
```yaml
- id: fs-1
  type: quiz
  prompt: |
    场景选型：某律所要做"合同条款风险问答"，文档 2 万页、PDF/Word 混合、要求引用原文条款号。
    你选哪个框架组合？说明理由与风险。
  hints:
    - "RAG 密集 + 文档格式多样 → LlamaIndex 或 LangChain + 深度定制的解析切分"
    - "引用溯源要求高 → 检索层必须保留页码/条款号元数据（metadata filtering）"
- id: fs-2
  type: code
  prompt: |
    用纯 Python（不装框架）写一个 30 行以内的"迷你 RAG"原型：3 个文本文档、
    词频打分检索、拼 prompt 调本机 Ollama。目的：体会框架帮你省掉了什么。
  hints:
    - "打分：query 与每个文档算共同词数；检索 top1 拼进 prompt"
    - "复用课程 03 的 chat() 函数调用 Ollama"
```
