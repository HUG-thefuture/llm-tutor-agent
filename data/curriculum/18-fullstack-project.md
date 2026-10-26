---
id: fullstack-project
title: 综合实战：全栈 LLM 应用（前端 + FastAPI + RAG + Agent）
level: advanced
track: fullstack
prereq: [fastapi-backend, frontend-basics, rag-pipeline]
est_minutes: 180
tags: [全栈, 项目, 实战, 验收]
---

# 综合实战：全栈 LLM 应用

## 项目目标
把前 16 讲串成一条线：**一个带知识库问答、工具调用与流式聊天界面的完整 Web 应用**。
规格书见 `projects/fullstack-llm-app/README.md`，这里讲方法与验收。

## 架构图
```text
┌─────────────┐   fetch/SSE   ┌──────────────────┐
│  前端 chat   │ ────────────▶ │  FastAPI 后端      │
│  index.html  │ ◀──────────── │  /api/chat/stream │
└─────────────┘   SSE delta    └──────┬───────────┘
                                      │ 组合
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
              知识库检索(RAG)     工具层(function)     记忆层(history)
              FAISS/Chroma       天气/搜索/SQL        JSON/SQLite
```

## 里程碑（每个都可独立验收）
| # | 里程碑 | 验收 |
|---|---|---|
| M1 | 后端骨架 | /api/health 返回模型状态；/docs 可交互 |
| M2 | 非流式问答链 | curl POST /api/chat 得到回答 |
| M3 | 流式改造 | 前端逐字渲染，首字 < 2s |
| M4 | 接入 RAG | 问文档内问题带引用；问外的问题拒答 |
| M5 | 接入工具 | "现在几点/搜一下 xx" 触发工具并回答 |
| M6 | 会话记忆 | 多轮追问不丢上下文；重启服务记忆还在 |
| M7 | 工程收尾 | 鉴权、日志、错误处理、README |

## 开发纪律（对照本助手的开发工作流）
1. **先计划后动手**：文件清单 + 接口契约（请求/响应 JSON）先写下来；
2. **最小可行再迭代**：M2 的假 LLM（直接返回 echo）也行，链路通了再换真模型；
3. **每个里程碑跑一次测试**：pytest 打后端、curl 打接口、浏览器点一遍前端；
4. **复盘**：每个 M 完成后记下"卡点 + 解法"，这就是你的错题本。

## 前后端联调清单
- [ ] 后端 CORS 或同源部署（本助手是 StaticFiles 同源挂载）
- [ ] 流式接口前端按 `\n\n` 切帧，UTF-8 流式解码
- [ ] 401/400/500 各触发一次，前端都有提示
- [ ] 长文本、空输入、连续快发 10 次，服务不死

## 用本助手练
在「开发工作流」页输入本 README 的目标，让 Agent 走"思考→计划→审查→开发→测试"
生成项目骨架到 workspace/ 下，再手动完善——**生成的代码就是你的第一份 review 素材**。

## 自测
1. M3 之前为什么要先做假 LLM？
2. 前后端联调最常见的三类错误？

## 练习
```yaml
- id: fp-1
  type: project
  prompt: |
    完成 M1+M2：FastAPI 项目（main.py, llm.py, test_main.py），/api/chat 接收
    {"message": str} 返回 {"reply": str}，内部调用本机 Ollama；pytest 覆盖
    正常/空消息两条路径。在 workspace/fullstack-llm-app/ 下完成。
  starter: |
    # workspace/fullstack-llm-app/main.py
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI()

    class ChatReq(BaseModel):
        message: str
    # TODO: /api/health 与 /api/chat
  hints:
    - "空消息先在 Pydantic 层或 handler 里返回 400"
    - "测试用 fastapi.testclient.TestClient(app)"
- id: fp-2
  type: project
  prompt: |
    完成 M4：给 /api/chat 加检索增强——启动时加载 FAISS 索引（没有就现建），
    回答前先检索 top3 并注入 prompt，回答末尾附引用。准备 3 个测试问题：
    2 个文档内、1 个文档外，验收拒答行为。
  hints:
    - "索引不存在时启动建一次即可，别每请求重建（性能事故）"
    - "prompt 里声明'资料中没有就回答资料未涉及'"
```
