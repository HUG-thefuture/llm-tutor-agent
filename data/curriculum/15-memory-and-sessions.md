---
id: memory-and-sessions
title: 记忆系统：短期、长期与向量记忆
level: advanced
track: agent
prereq: [agents-and-tools]
est_minutes: 45
tags: [memory, 会话, 摘要, 向量记忆]
---

# 记忆系统

## 模型没有记忆，应用才有
每次请求都是独立的；"记忆"是应用层把历史**塞回 context** 的策略。三种层次：

## 一、短期记忆：滑动窗口
```python
def trim_history(history: list[dict], max_rounds: int = 10) -> list[dict]:
    """保留最近 max_rounds 轮 + 永远保留 system"""
    sys = [m for m in history if m["role"] == "system"]
    rest = [m for m in history if m["role"] != "system"][-max_rounds * 2:]
    return sys + rest
```
简单有效，但丢了早期信息。

## 二、摘要记忆：越聊越浓缩
超过阈值时，让模型把旧历史压缩成一段摘要，替换原文：
```text
请把以下对话压缩为要点摘要（保留：用户目标/关键决定/未决问题）：
{历史}
```
适合长会话客服；**摘要本身要防止累计失真**（定期用原文重建）。

## 三、长期记忆：向量库检索
跨会话记忆 → 存向量库，按当前问题检索相关记忆片段注入：
```python
def remember(state, text: str):
    state.vs.add_texts([text], metadata={"ts": time.time(), "user": uid})

def recall(state, query: str, k: int = 3) -> str:
    return "\n".join(d.page_content for d in state.vs.similarity_search(query, k=k))
```
写什么进长期记忆是关键：**用户偏好、明确事实、重要决定**；琐碎寒暄不入库。

## 工程要点
1. **Token 预算**：context 是稀缺资源，给 system/历史/检索资料分配固定预算；
2. **会话隔离**：多用户系统记忆必须按 user_id 隔离（metadata 过滤）；
3. **可遗忘**：提供删除接口（合规要求 + 空间管理）；
4. 本助手把学员进度、错题本、技能矩阵持久化在 data/progress/*.json，
   就是一种"结构化长期记忆"——记忆不一定要用向量库。

## 自测
1. 滑动窗口 vs 摘要记忆各自丢什么信息？
2. 什么信息值得进长期记忆？

## 练习
```yaml
- id: ms-1
  type: code
  prompt: |
    实现 summarize_if_long(history: list[dict], max_tokens_est: int = 2000, summarize_fn) -> list[dict]：
    用每条消息 len(content) 估算 token；超限时把除最近 4 条外的历史经 summarize_fn 压缩为
    一条 role=system 的摘要消息。
  starter: |
    def summarize_if_long(history, max_tokens_est=2000, summarize_fn=None):
        # TODO: 估算总长 → 超限则拆分 → summarize_fn(旧消息) → 拼回
        ...
  hints:
    - "recent = history[-4:]；old = history[:-4]；summary = summarize_fn(old)"
    - "返回 [{'role':'system','content':'历史摘要：'+summary}] + recent"
- id: ms-2
  type: quiz
  prompt: |
    记忆注入的"多用户隔离"为什么必须做？给出一个不做隔离的事故场景。
  hints:
    - "A 用户的隐私记忆被检索进 B 用户的回答 → 数据泄露事故；所有记忆读写必须带 user_id 过滤"
```
