# QUICKSTART — 5 分钟上手

## 0. 你需要什么

| 场景 | 需要准备 |
|---|---|
| 纯体验（最快） | 什么都不用装模型——`DEMO_MODE=1` 即可（回答为知识库摘录） |
| 完整对话 | 本机 [Ollama](https://ollama.com)（`ollama pull qwen3:8b`），或任一外部 API Key |
| 混合检索（可选） | `ollama pull nomic-embed-text` |

## 1. 启动

```bash
pip install -r requirements.txt

# 方式 A：Windows 双击 start.bat
# 方式 B：命令行
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8787

# 方式 C：无模型演示模式（零 Key 体验全部功能）
DEMO_MODE=1 python -m uvicorn backend.main:app --host 127.0.0.1 --port 8787
```

打开 http://127.0.0.1:8787 —— 五个页签：对话（流式）/ 学习路径 / LeetCode / 开发工作流 / 设置。

## 2. 三分钟走完主流程

1. **对话**：输入"RAG 的切分策略怎么选？"——回答逐字流出，底部显示知识库来源
2. **学习路径**：写目标 → 生成计划 → 点任意课程开课 → 提交练习拿评分
3. **LeetCode**：选题 → 写代码 → ▶ 运行评测（本地沙箱，毫秒级判题）→ 💡 渐进提示
4. **右上角切换学员 ID**：进度 / 错题本 / 力扣战绩按学员隔离（存于 `data/progress/<id>.json`）

## 3. 接入 MCP 客户端（Claude Desktop / ZCode 等）

项目内置零依赖 MCP 服务器（stdio JSON-RPC 2.0），在客户端配置中加：

```json
{
  "mcpServers": {
    "llm-tutor": {
      "command": "py",
      "args": ["-3", "-m", "backend.mcp_server"],
      "cwd": "D:/llm-tutor-agent"
    }
  }
}
```

之后在客户端里即可直接调用 7 个工具：

| 工具 | 说明 |
|---|---|
| `search_knowledge` | 知识库混合检索（BM25+向量），返回来源与得分 |
| `list_courses` / `get_course` | 课程目录 / 完整讲义 |
| `list_problems` | 力扣题库清单 |
| `judge_code` | 本地沙箱判题（AST 防护 + 用例比对），不依赖在线判题 |
| `get_progress` | 学员进度画像 |
| `chat` | 带知识库与进度画像的完整对话（需模型可用） |

冒烟验证（命令行手测协议）：

```bash
echo {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}} | py -3 -m backend.mcp_server
```

## 4. 公网部署（含安全底线）

```bash
# 1) 演示模式 + 访问令牌（推荐组合）
DEMO_MODE=1 LLM_TUTOR_TOKEN=你的令牌 \
  python -m uvicorn backend.main:app --host 0.0.0.0 --port 8787
```

- `LLM_TUTOR_TOKEN`（或 `config.yaml → app.access_token`）非空时，所有 `/api/*` 需要
  `X-Access-Token` 头 / `Authorization: Bearer` / `?token=` 之一；前端会自动弹出输入框
- 演示模式下 LLM 回答为**知识库摘录**并明确标注，配置真实 Key 后自动切回完整模型链
- Docker 部署模板待补（本仓库暂未提供，课程 19 讲有教学版）

## 5. 常用运维

```bash
python -m pytest -q            # 59 项测试（含 MCP 子进程、鉴权、流式回归）
python evals/eval_retrieval.py --save   # 检索质量评估（hit@k / MRR）
```

- 知识库更新：把 Markdown 放进 `data/userdocs/`（或前端"设置"页上传）→ 点"重建索引"
- Provider 探活：`GET /api/health`；逐个连通性测试：前端设置页按钮
- 日志与产物：`logs/runs.log`、`workspace/<项目>/.agent_run.json`

## 6. 配置速查（config.yaml）

| 配置 | 默认 | 说明 |
|---|---|---|
| `llm.strategy` | local_first | local_first / external_first / only |
| `llm.providers[].enabled` | auto | true/false/auto（auto=配了 Key 才启用） |
| `app.access_token` | ""（开放） | 非空开启 API 鉴权；也可用环境变量 `LLM_TUTOR_TOKEN` |
| `app.demo_mode` | false | 演示模式；也可用环境变量 `DEMO_MODE=1` |
| `rag.use_ollama_embeddings` | true | 无 embedding 模型时自动退化为纯 BM25 |
| `dev_agent.max_total_cycles` | 6 | 开发工作流整循环硬上限 |
