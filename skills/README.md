# 技能矩阵说明

本目录维护“学员能力模型”，`skills/matrix.yaml` 定义：

- **tracks（技能方向）**：python / llm-core / langchain / rag / agent / fullstack / quality
- **L1—L6 能力分级**：
  - L1 基础：Python、环境、第一次大模型调用
  - L2 框架入门：LangChain 核心链路、提示工程、函数调用
  - L3 RAG 构建：向量库、完整检索增强流水线
  - L4 Agent 与工具：工具调用、记忆、多 Agent、RAG 进阶
  - L5 前后端与部署：FastAPI、前端、全栈项目
  - L6 算法与工程化：部署运维、测试质量、自主进阶

学员每通过一讲的练习，`backend/core/memory.py` 会更新其
`data/progress/<learner>.json` 中的 `skill_matrix`（经验值累计），
并把失分点写入 `wrong_book`（错题本）、概念缺口写入复习队列。

学习路径规划（`POST /api/learn/path`）优先让大模型定制排课；
模型不可用时按本目录 matrix.yaml 的顺序兜底。
