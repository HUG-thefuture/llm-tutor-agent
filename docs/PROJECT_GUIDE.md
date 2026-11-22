# PROJECT_GUIDE — 项目全景导读

> 面向"快速掌握这个项目"的一页导读：它是什么、怎么运转、代码在哪、怎么改、怎么测。

## 一句话定位

**一个教学与工程同构的 LLM 应用开发学习平台**：20+ 门中文课程 + 力扣题库 + 开发工作流 Agent，
后端本身就是一份"可运行的 RAG / Agent / 判题教材"（手写实现，不藏黑盒）。

## 三层结构（读代码的推荐顺序）

```
1. 装配层   backend/main.py          —— 30 行看懂依赖注入：config → KB → 课程 → 题库 → 路由 → 前端
2. 端点层   backend/api/routes.py    —— 22 个端点，每个 10 行左右，LLMError 统一映射 503
3. 能力层   backend/core/            —— 真正的"教材"在这里：
   ├── rag.py         手写 BM25（中文 bigram）+ Ollama 向量 → 0.5/0.5 归一化融合；无向量自动退化
   ├── llm.py         多 provider 降级链（ollama/openai/demo 三类 kind）+ 流式（NDJSON/SSE 双协议）
   │                  + ThinkStripper（跨 chunk 剥 <think>）+ extract_json（三级容错解析）
   ├── judge.py       判题三道防线：AST 黑名单 → 子进程 -I 隔离+超时 → 逐用例 HARNESS 比对
   ├── agent.py       开发工作流：THINK→PLAN↔REVIEW→DEVELOP→TEST→复盘，带升级模型与全留痕
   ├── memory.py      学员档案 JSON 原子写（tmp + os.replace），单进程锁
   └── tutors/        chat（流式共用 prepare）/ learning / coding / curriculum 四位导师
```

前端 `frontend/app.js`（约 480 行零依赖）：SSE 打字机、手写 mdLite 渲染、学员切换、令牌重试。

## 数据流

- 课程：`data/curriculum/*.md`（frontmatter + 练习 yaml）→ `curriculum.py` 解析 → RAG 索引 + 授课
- 知识块：启动时 `load_existing()` 读缓存 `data/kb_index/`（246 chunks）；缺失则现场 `build()`
- 向量：后台任务补建（lifespan），有 Ollama embedding 才有混合检索，否则纯 BM25
- 进度：`data/progress/<learner_id>.json`，按学员隔离
- 题库：`data/leetcode/problems.json`，每题自带 tests/hints/reference，判题零外部依赖

## 关键设计决策（为什么这样写）

| 决策 | 原因 |
|---|---|
| 手写 BM25 而非依赖 rank_bm25 | 教学同构：代码即教材；且中文 bigram 分词自定义更顺手 |
| provider kind 三类（ollama/openai/demo） | demo 让公网部署零 Key 可用，且永远排在降级链末位、json 任务拒绝（诚实降级） |
| 流式中断不换源重放 | 已流给用户的内容无法撤回，换源会造成重复输出 |
| MCP 零依赖实现 | 协议子集小（5 个方法），引入 SDK 反而增加教学噪音；stdio 纯 ASCII 输出规避 Windows 编码坑 |
| 令牌默认关闭 | 本地单机使用零配置；公网部署一行环境变量开启 |

## 测试地图（59 项，`py -3 -m pytest -q` 约 8 秒）

| 文件 | 覆盖 |
|---|---|
| test_agent.py (4) | 开发工作流回炉循环 / `_safe_join` 路径穿越 |
| test_curriculum.py (6) | 课程完整性 / 题库自洽引用 |
| test_judge.py (6) | 全题库参考解 accepted / blocked / timeout |
| test_llm.py (7) | strip_think / extract_json 三级解析 |
| test_rag.py (4) | 分词 / 切块 / BM25 排序 / KB 构建 |
| test_retrieval_eval.py (1) | **检索质量 CI 回归门**（hit@3≥0.60 / MRR≥0.50） |
| test_stream.py (9) | ThinkStripper 状态机 / demo provider / SSE 端到端 |
| test_mcp.py (13) | JSON-RPC 调度 / 判题工具 / **stdio 子进程全握手** |
| test_auth.py (5) | 令牌三通道 / 默认开放 / 题库多学员隔离 |

## 扩展指引

- **加课程**：`data/curriculum/NN-title.md`（frontmatter 对齐现有格式）→ `POST /api/kb/reindex`
- **加题目**：`data/leetcode/problems.json` 追加（tests + reference 必填，test_judge 会全量自洽校验）
- **加 provider**：`config.yaml` providers 追加一行；新协议类型在 `llm.py` 加分支
- **加 MCP 工具**：`backend/mcp_server.py` 的 TOOLS 注册 + call_tool 分支，两处必须同步

## 已知边界（诚实清单）

- 判题沙箱是黑名单 AST + 超时兜底，面向教学场景；不建议直接用于对抗性公网判题
- memory 为单进程文件锁，多 uvicorn worker 会竞态（单 worker 部署无碍）
- 检索为纯 Python O(N·d)，知识块上千后查询会变慢（可迁移 numpy/FAISS，课程 07 有对照实现）
- 无数据库；`data/kb_index`、`data/progress` 不入库，克隆后首启自动重建
