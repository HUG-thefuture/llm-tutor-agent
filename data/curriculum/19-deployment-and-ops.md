---
id: deployment-and-ops
title: 部署与运维：Docker、模型路由与成本控制
level: advanced
track: fullstack
prereq: [fullstack-project]
est_minutes: 75
tags: [docker, 部署, 路由, 成本, 缓存, 限流]
---

# 部署与运维

## Docker 最小镜像
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY frontend/ frontend/
COPY data/ data/
EXPOSE 8787
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8787"]
```
```bash
docker build -t tutor-agent .
docker run -d -p 8787:8787 --env-file .env tutor-agent
```
要点：`.env` 走 `--env-file` 不进镜像；数据目录挂 volume：`-v ./data:/app/data`。

## 模型路由：按任务分配模型
```python
ROUTING = {
    "plan":    "deepseek-chat",      # 计划/审查 → 强模型
    "review":  "deepseek-chat",
    "chat":    "local-qwen3:8b",     # 日常对话 → 本地
    "embed":   "nomic-embed-text",
}
def route(task: str):
    return get_provider(ROUTING[task])   # 本地优先/外部增强，配置化切换
```
原则：**隐私与高频走本地，复杂推理与最新知识走外部**；失败自动互为备份。

## 成本控制四板斧
1. **缓存**：相同问题（归一化后）直接命中缓存；embedding 结果永不重复计算；
2. **限流**：每用户每分钟 N 次（令牌桶），防刷也防账单爆炸；
3. **预算**：记录每次外部调用的 token 消耗，超日预算自动降级到本地模型；
4. **压缩**：历史消息摘要化（见记忆一讲），prompt 瘦身 30-60%。

## 可观测性
```python
# 结构化日志：时间/用户/路由到的模型/耗时/token/是否命中缓存
log.info(json.dumps({"t": ts, "uid": uid, "model": model,
                     "ms": elapsed_ms, "tokens": n, "cache": hit}))
```
三个必看指标：**P95 延迟、每千次调用成本、缓存命中率**。

## 反向代理与 HTTPS
```nginx
server {
    listen 443 ssl;
    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_buffering off;          # SSE 必须关缓冲，否则流式变一次性吐
    }
}
```

## 自测
1. SSE 经过 nginx 变成"一次性吐完"，最可能的原因？
2. 降级到本地模型的触发条件有哪些？

## 练习
```yaml
- id: dp-1
  type: code
  prompt: |
    实现令牌桶限流器 TokenBucket(rate_per_min: int)：
    allow(uid) -> bool；桶容量 = rate_per_min，每分钟补充；同 uid 连续调用超限返回 False。
    不用外部库，用时间戳与计数实现。
  starter: |
    import time, collections

    class TokenBucket:
        def __init__(self, rate_per_min: int):
            ...
        def allow(self, uid: str) -> bool:
            ...
  hints:
    - "记录每个 uid 的 {tokens, last_ts}；按流逝时间补充 tokens = min(cap, tokens + elapsed/60*rate)"
    - "allow 时 tokens >= 1 则扣 1 返回 True，否则 False"
- id: dp-2
  type: quiz
  prompt: |
    为什么 embedding 结果值得永久缓存，而 chat 回答要设短 TTL？
  hints:
    - "embedding 由(模型,文本)唯一决定、可复现；chat 有随机性且可能随知识更新过期"
```
