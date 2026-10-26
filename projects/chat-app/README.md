# 项目 2：chat-app —— 流式聊天 Web 应用

## 目标
FastAPI 后端 + 原生前端聊天界面，支持 SSE 流式输出与多轮会话。

## 功能
1. POST /api/chat/stream —— SSE 流式回答；
2. 前端聊天界面：气泡、Markdown 代码块渲染、loading、错误提示；
3. 会话历史保存（SQLite 或 JSON），刷新不丢。

## 技术栈
FastAPI + StreamingResponse + 原生 JS(fetch + ReadableStream) + SQLite

## 里程碑
- M1 非流式问答接口
- M2 流式接口 + 前端逐字渲染
- M3 会话持久化（按 session_id）
- M4 鉴权（X-API-Key）+ 请求日志

## 验收标准
- [ ] 首字延迟 < 2s（本机模型）
- [ ] 中文流式不乱码（UTF-8 流式解码正确）
- [ ] 401/400/500 前端均有提示
- [ ] 连续快发 10 次服务不崩
