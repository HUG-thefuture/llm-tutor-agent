---
id: agents-and-tools
title: Agent 与工具调用（Tool Calling / ReAct）
level: advanced
track: agent
prereq: [langchain-structured-output]
est_minutes: 90
tags: [agent, tool-calling, react, 多agent]
---

# Agent 与工具调用

## Agent 的本质
模型不只会说话，还能**决定调用哪个函数**。循环：模型输出"要调用的工具+参数" →
代码执行 → 结果回传 → 模型继续，直到它认为任务完成。这就是 Tool Calling Agent。

## 定义工具：docstring 就是说明书
```python
# pip install -U langchain  (1.x)
from langchain_core.tools import tool

@tool
def search_web(query: str) -> str:
    """联网搜索最新信息。当问题涉及时效性内容（价格/版本/新闻）时使用。"""
    # 真实实现接 DuckDuckGo/Bing API
    return f"（演示）{query} 的搜索结果"

@tool
def sql_query(sql: str) -> str:
    """只读查询订单库。只允许 SELECT 语句。"""
    if not sql.strip().lower().startswith("select"):
        return "错误：仅允许 SELECT"        # 工具内部要做权限校验！
    ...

tools = [search_web, sql_query]
```
**参数 schema、函数描述、错误处理**是工具三要素；描述写得越清楚，模型选得越准。

## 创建并运行 Agent（langchain 1.x）
```python
from langchain.agents import create_agent

agent = create_agent(
    model,                      # ChatOpenAI / ChatOllama
    tools=[search_web, sql_query],
    system_prompt="你是订单助手。查询类问题必须用 sql_query，时效问题用 search_web。",
)
result = agent.invoke({"messages": [{"role": "user", "content": "查一下今天卖出多少单"}]})
for m in result["messages"]:
    m.pretty_print()
```
（0.3 版本对应 `langgraph.prebuilt.create_react_agent`；本质都是 ReAct 循环。）

## 手写迷你 Agent 循环（理解原理，30 行）
```python
import json
tools_spec = [...]            # OpenAI tools 格式的 JSON Schema
messages = [{"role": "user", "content": "北京现在多少度？"}]
while True:
    resp = client.chat.completions.create(model=..., messages=messages, tools=tools_spec)
    msg = resp.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break                                     # 模型给出最终回答
    for tc in msg.tool_calls:                     # 执行所有工具调用
        result = dispatch(tc.function.name, json.loads(tc.function.arguments))
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
```

## 失败回退与安全
1. 工具内 try/except，把**错误信息作为结果**返回给模型让它自行调整参数重试；
2. 单次任务限制最大工具调用轮数（防死循环烧 token）；
3. 写操作工具（删库/发邮件/支付）必须有人工确认或白名单；
4. 工具参数用 Pydantic 校验，别信模型的字符串。

## 多 Agent 协作（概念）
把"规划者/执行者/审查者"拆成多个 Agent 互相喂消息（AutoGen/CrewAI 的核心玩法）。
收益是职责单一、上下文干净；代价是 token 成本与延迟翻倍。**能单 Agent 解决就别上多 Agent。**

## 自测
1. 模型怎么知道有哪些工具、怎么传参？（tools spec + 消息里的结果回传）
2. 工具报错为什么不该直接抛异常终止？

## 练习
```yaml
- id: at-1
  type: code
  prompt: |
    用 @tool 定义两个工具：read_file(path)（只允许读当前目录下 .md 文件，
    否则返回错误字符串）与 calc(expression)（用 ast 安全求值四则运算）。
    并写出 tools_spec 之外的 dispatch(name, args) 分发函数。
  starter: |
    from langchain_core.tools import tool

    @tool
    def read_file(path: str) -> str:
        """读取当前目录下的 markdown 文件内容"""
        ...

    @tool
    def calc(expression: str) -> str:
        """计算四则运算表达式"""
        ...
  hints:
    - "read_file 校验 path.endswith('.md') 且不含 '..' 与绝对路径"
    - "calc 用 ast.parse(expr, mode='eval') 遍历 BinOp/Num，拒绝其他节点"
- id: at-2
  type: quiz
  prompt: |
    Agent 在第 5 轮工具调用后又请求同一个工具、同样参数，循环了 3 次。你会怎么处理？
  hints:
    - "1) 设 max_iterations 上限强制终止 2) 检测重复调用直接终止并告知用户"
    - "3) 给模型的工具结果里加提示'该工具已连续返回同样结果，请改变策略'"
```
