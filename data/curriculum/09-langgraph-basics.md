---
id: langgraph-basics
title: LangGraph：有状态的图式编排
level: intermediate
track: langchain
prereq: [langchain-lcel]
est_minutes: 60
tags: [langgraph, stategraph, agent, checkpoint]
---

# LangGraph 基础

## 什么时候需要 LangGraph
LCEL 是**管道**（数据单向流）；LangGraph 是**状态机**（可分支、可循环、可人工介入）。
凡是"不通过就重来""多角色协作""中途等用户确认"的流程，都该上图。

pip 安装：`pip install -U langgraph`

## 最小状态图
```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    question: str
    draft: str
    quality: str

def write_node(state: State) -> dict:
    return {"draft": llm.invoke(f"写一段关于'{state['question']}'的短文")}

def review_node(state: State) -> dict:
    verdict = llm.invoke(f"评价质量高低，只回 good/bad：{state['draft']}")
    return {"quality": "good" if "good" in verdict else "bad"}

def route(state: State) -> str:
    return END if state["quality"] == "good" else "write"    # 不合格回炉重写

g = StateGraph(State)
g.add_node("write", write_node)
g.add_node("review", review_node)
g.add_edge(START, "write")
g.add_edge("write", "review")
g.add_conditional_edges("review", route)          # 条件边实现循环
app = g.compile()

print(app.invoke({"question": "向量数据库", "draft": "", "quality": ""}))
```

## 三个核心概念
1. **State**：共享内存，节点返回 dict 做**增量合并**（可自定义 reducer，如列表 append）；
2. **条件边**：函数返回下一节点名，实现分支/循环；
3. **Checkpoint**：`compile(checkpointer=...)` 持久化每步状态 → 断点恢复、时间旅行、人工审批（interrupt）。

## 与 Agent 的关系
LangChain 1.x 的 `create_agent` 底层就是 LangGraph 的预构建图。
需要自定义循环策略（如"审查不通过重写最多 3 次"）时，直接手写图更可控——
本助手 backend/core/agent.py 的"思考→计划→审查→开发→测试"状态机就是这种模式的手写实现。

## 常见坑
1. 节点返回**全量 State** 覆盖了别的字段 —— 只返回要更新的键；
2. 条件边忘了处理所有分支 → 图无法终止；
3. 循环无上限 → 生产必须配 recursion_limit。

## 自测
1. StateGraph 与 LCEL 管道的本质区别？
2. 如何让"写稿-审稿"循环最多跑 3 轮？

## 练习
```yaml
- id: lg-1
  type: code
  prompt: |
    把讲义中的 write→review 图补全为可运行代码，并给 route 增加"最多重写 2 次"：
    State 增加 attempts: int，review_node 里 attempts += 1，route 在 attempts >= 3 时强制 END。
  starter: |
    class State(TypedDict):
        question: str
        draft: str
        quality: str
        attempts: int
    # TODO: review_node 中返回 {"quality": ..., "attempts": state["attempts"] + 1}
  hints:
    - "route 里先判 attempts 再判 quality"
- id: lg-2
  type: quiz
  prompt: |
    需要实现"客服 Agent：先查知识库，查不到转人工，人工回复后继续会话"，适合用 LCEL 还是 LangGraph？
    关键理由是什么？
  hints:
    - "LangGraph。存在条件分支（查到/查不到）与人工介入（interrupt/checkpoint），是状态机不是单向管道"
```
