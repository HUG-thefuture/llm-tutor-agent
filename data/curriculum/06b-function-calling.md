---
id: function-calling
title: 函数调用（Function Calling）：LLM 的双手
level: intermediate
track: llm-core
prereq: [llm-api-basics, prompt-engineering]
est_minutes: 60
tags: [function-calling, tool-use, json-schema]
---

# 函数调用（Function Calling）

## 是什么
把函数的**名字、用途、参数 JSON Schema** 告诉模型；模型在对话中返回
"我要调 tool_x，参数是 {...}"；**你的代码**执行后把结果回传。模型从不直接执行任何东西。

## OpenAI 兼容协议三步走
```python
tools_spec = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询城市当前天气。用户问到天气/气温/降雨时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "city":   {"type": "string", "description": "城市名，如 '北京'"},
                "unit":   {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"},
            },
            "required": ["city"],
        },
    },
}]

# 1) 带着tools发消息
r = client.chat.completions.create(model=..., messages=msgs, tools=tools_spec)
msg = r.choices[0].message

# 2) 模型要工具 → 执行
if msg.tool_calls:
    msgs.append(msg)
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)          # 永远要 try/except！
        result = DISPATCH[tc.function.name](**args)
        msgs.append({"role": "tool", "tool_call_id": tc.id,
                     "content": json.dumps(result, ensure_ascii=False)})

# 3) 带着工具结果再请求 → 模型生成最终回答
```

## 参数设计经验
1. **description 决定选择准确率**：写清"什么时候用、什么时候不用"；
2. 参数越少越好，枚举值用 `enum` 限制；必填项用 `required`；
3. 返回值是给模型看的：出错时返回 `"错误：城市不存在，请确认拼写"` 而非抛异常，
   让模型有机会纠正后重试。

## 与 Agent 的关系
单次工具调用 = function calling；**循环"调用→观察→再决策"直到完成目标** = Agent（下一课展开）。
LangChain 的 `@tool` 装饰器 + `create_agent` 是这套协议的工程化封装。

## 安全红线
1. 工具是权限边界：`sql_query` 内部校验只允许 SELECT；
2. 参数白名单：路径拼接前检查 `..` 与绝对路径；
3. 记录每次工具调用审计日志（谁、何时、调了什么、参数）。

## 自测
1. 模型能自己执行函数吗？谁执行的？
2. 工具执行出错为什么要"返回错误字符串"而不是抛异常？

## 练习
```yaml
- id: fc-1
  type: code
  prompt: |
    为"图书管理助手"设计两个工具的 tools_spec（只写 JSON，不用实现）：
    search_books(keyword, max_results≤20) 与 borrow_book(book_id)。
    要求：description 说清用途与限制；borrow_book 是写操作，参数里加 confirmed: bool。
  hints:
    - "search_books 的 max_results 写 type=integer, default=10, maximum=20"
    - "写操作加 confirmed 是人工确认的简化形态，description 注明'必须为 true 才执行'"
- id: fc-2
  type: bugfix
  prompt: |
    下面的工具循环哪里危险？
    ```python
    while True:
        msg = ask_model(messages, tools)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                messages.append({"role": "tool", "content": str(DISPATCH[tc.function.name](**args))})
        else:
            break
    ```
  hints:
    - "三个问题：无轮数上限；json.loads 无异常处理；丢 tool_call_id 模型无法对账"
  solution: |
    for i in range(MAX_ITERATIONS):          # 1) 上限
        msg = ask_model(messages, tools)
        if not msg.tool_calls:
            break
        messages.append(msg)
        for tc in msg.tool_calls:
            try:                              # 2) 参数解析兜底
                args = json.loads(tc.function.arguments)
                result = str(DISPATCH[tc.function.name](**args))
            except Exception as e:
                result = f"工具执行失败: {e}"   # 3) 错误回传而非崩溃
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": result})
```
