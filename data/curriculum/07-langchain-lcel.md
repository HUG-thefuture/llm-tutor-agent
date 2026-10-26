---
id: langchain-lcel
title: LCEL 深入：Runnable 组合的艺术
level: intermediate
track: langchain
prereq: [langchain-quickstart]
est_minutes: 60
tags: [lcel, runnable, 并行, fallback, 流式]
---

# LCEL 深入

## 一切皆 Runnable
Prompt、Model、Parser、Retriever 都是 Runnable，统一接口：`invoke / stream / batch / ainvoke`。
组合方式：`|`（顺序）、`RunnableParallel`（并行）、`.assign`（增量扩展）。

## 顺序 + 并行：RAG 链的标准形态
```python
from langchain_core.runnables import RunnableParallel, RunnablePassthrough, RunnableLambda

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

rag_chain = RunnableParallel(
    context=(retriever | RunnableLambda(format_docs)),   # 检索 → 拼接
    question=RunnablePassthrough(),                       # 原样透传问题
) | prompt | llm | StrOutputParser()

print(rag_chain.invoke("什么是混合检索？"))
```
`RunnableParallel` 让检索与"透传问题"同时进行，最终 dict 再流入 prompt。

## .assign：链中间插一杠
```python
chain = RunnablePassthrough() \
    .assign(upper=lambda x: x["text"].upper()) \
    .assign(length=lambda x: len(x["upper"]))
chain.invoke({"text": "hello"})   # {'text': 'hello', 'upper': 'HELLO', 'length': 5}
```

## 失败回退：with_fallbacks
```python
reliable = primary_chain.with_fallbacks([backup_chain])
reliable.invoke(...)     # primary 挂了自动换 backup
```
生产必备：外部模型失败降级到本地模型。

## 调试三件套
```python
chain.get_graph().print_ascii()   # 打印链结构
chain.invoke(x, config={"tags": ["debug"]})
for ev in chain.stream_log(x):    # 中间步骤流式日志
    ...
```

## 常见坑
1. `RunnableLambda` 里放同步重活会阻塞事件循环 —— 用 `ainvoke` 或让函数本身是 async；
2. 并行分支的输出键名与 prompt 变量不一致 → KeyError；
3. `|` 两侧类型不匹配（把 str 传给需要 dict 的组件）—— 用 `RunnableLambda` 做适配。

## 自测
1. `RunnablePassthrough()` 与 `RunnableLambda(lambda x: x)` 的区别？
2. 什么时候用 RunnableParallel 而不是两次顺序调用？

## 练习
```yaml
- id: lcel-1
  type: code
  prompt: |
    用 RunnableParallel + RunnableLambda 组装一个链：
    输入 {"text": "..."}，并行产出 word_count（按空格分词数）与 char_count（去空格字符数），
    最后由一个 RunnableLambda 汇总为字符串 "words=X chars=Y"。不调用模型。
  starter: |
    from langchain_core.runnables import RunnableParallel, RunnableLambda

    stats = RunnableParallel(
        word_count=...,      # TODO
        char_count=...,      # TODO
    ) | RunnableLambda(lambda d: f"words={d['word_count']} chars={d['char_count']}")

    print(stats.invoke({"text": "hello lang chain"}))   # words=3 chars=14
  hints:
    - "word_count=RunnableLambda(lambda d: len(d['text'].split()))"
    - "char_count 用 d['text'].replace(' ', '') 后取 len"
  solution: |
    from langchain_core.runnables import RunnableParallel, RunnableLambda

    stats = RunnableParallel(
        word_count=RunnableLambda(lambda d: len(d["text"].split())),
        char_count=RunnableLambda(lambda d: len(d["text"].replace(" ", ""))),
    ) | RunnableLambda(lambda d: f"words={d['word_count']} chars={d['char_count']}")

    assert stats.invoke({"text": "hello lang chain"}) == "words=3 chars=14"
- id: lcel-2
  type: code
  prompt: |
    为上面 stats 链加一个 fallback：主链抛异常时回退到
    `RunnableLambda(lambda d: "fallback")`，并用一个必抛异常的假主链验证回退生效。
  hints:
    - "good_chain.with_fallbacks([RunnableLambda(lambda d: 'fallback')])"
```
