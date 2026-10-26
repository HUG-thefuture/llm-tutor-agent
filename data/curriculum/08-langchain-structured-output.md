---
id: langchain-structured-output
title: 结构化输出：把模型回答变成可编程数据
level: intermediate
track: langchain
prereq: [langchain-quickstart]
est_minutes: 45
tags: [output-parser, pydantic, structured-output]
---

# 结构化输出

## 为什么需要
聊天回答给人看，**结构化输出给程序用**：抽取字段、路由分支、存库、调工具都依赖它。

## 首选：with_structured_output（Pydantic 校验）
```python
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

class Sentiment(BaseModel):
    label: str = Field(description="positive / negative / neutral")
    confidence: float = Field(description="0~1")
    reason: str = Field(description="一句话理由")

structured_llm = llm.with_structured_output(Sentiment)   # 返回的就是 Sentiment 实例
result = structured_llm.invoke("这家店服务太差了，再也不来了")
print(result.label, result.confidence)
```
底层自动生成 JSON Schema 并让模型按 schema 输出，**类型错了直接抛 ValidationError**。

## 传统 OutputParser（理解即可）
```python
from langchain_core.output_parsers import JsonOutputParser
parser = JsonOutputParser(pydantic_object=Sentiment)
prompt = ChatPromptTemplate.from_template(
    "分类用户评论。\n{format_instructions}\n评论：{review}")
# format_instructions = parser.get_format_instructions()
```
1.x 时代优先用 `with_structured_output`，parser 方案作为了解。

## 三个工程要点
1. **schema 描述要写清取值范围**（description 字段是提示的一部分）；
2. **兜底**：解析失败时重试或降级为自由文本流程，别让一条脏数据打崩服务；
3. **别过度嵌套**：三层以上嵌套 Schema 的准确率明显下降，能平铺就平铺。

## 常见坑
1. Pydantic 字段名用了中文/驼峰与模型输出不一致 → 字段全空；
2. 忘记 `Field(description=...)`，模型猜字段含义；
3. 在 temperature=1.0 下追求严格 JSON → 调低 temperature 到 0~0.3。

## 自测
1. `with_structured_output` 返回的是 dict 还是 Pydantic 对象？（默认模型对象，传 method/schema 参数可变）
2. 解析失败的三种兜底方式？

## 练习
```yaml
- id: so-1
  type: code
  prompt: |
    定义 Pydantic 模型 BookInfo：title(str)、authors(list[str])、year(int，可为 None)、
    tags(list[str]，至少 1 个)。用 with_structured_output 写 extract(text) 函数，
    从一段图书介绍文本中抽取信息。
  starter: |
    from pydantic import BaseModel, Field

    class BookInfo(BaseModel):
        # TODO
        ...

    def extract(text: str) -> BookInfo:
        # TODO: llm.with_structured_output(BookInfo).invoke(...)
        ...
  hints:
    - "可选字段写 year: int | None = None"
    - "Field(description=...) 里写清楚取值约束，比如 tags 至少 1 个"
- id: so-2
  type: bugfix
  prompt: |
    找出下面代码的问题（模型偶发返回缺失 confidence 字段）：
    ```python
    class R(BaseModel):
        label: str
        confidence: float
    r = llm.with_structured_output(R).invoke(text)
    score = r.confidence * 100
    ```
  hints:
    - "两个方向：schema 侧给字段默认值/可选；代码侧 try/except ValidationError 兜底"
  solution: |
    from pydantic import BaseModel, Field, ValidationError

    class R(BaseModel):
        label: str
        confidence: float = Field(default=0.0, description="0~1，缺失时给 0")

    try:
        r = llm.with_structured_output(R).invoke(text)
        score = r.confidence * 100
    except ValidationError:
        score = 0
```
