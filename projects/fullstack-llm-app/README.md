# 项目 4：fullstack-llm-app —— 综合全栈 LLM 应用（毕业项目）

## 目标
整合全部能力：前端聊天 + FastAPI + RAG 知识库 + 工具调用 + 会话记忆 + 部署。

## 架构
前端(index.html) ←SSE→ FastAPI(/api/chat/stream) → 检索(RAG) + 工具(function calling) + 记忆(history/SQLite)

## 功能
1. 流式聊天，回答基于知识库并附引用；
2. 时效类问题自动触发联网工具；
3. 多轮会话记忆（滑动窗口 + 摘要）；
4. 简单限流与 token 消耗统计；
5. Dockerfile 一键部署。

## 里程碑（详见课程 18 全栈项目讲）
M1 后端骨架 → M2 问答链 → M3 流式 → M4 RAG → M5 工具 → M6 记忆 → M7 工程收尾

## 验收标准
- [ ] 本地演示全流程流畅
- [ ] pytest 覆盖核心接口；无内存泄漏（循环压测验证）
- [ ] 无硬编码密钥；错误处理完备
- [ ] README 完整可复现
