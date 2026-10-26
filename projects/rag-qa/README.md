# 项目 1：rag-qa —— 本地 PDF 知识库问答

## 目标
对本地文档目录构建 RAG 知识库，提供带引用溯源的问答 API 与命令行入口。

## 功能
1. `python ingest.py ./docs` —— 加载 PDF/MD/TXT，切分、向量化、入库（支持增量）；
2. `python ask.py "问题"` —— 检索 top4 + 生成回答，末尾附引用来源；
3. 文档外问题明确回答"资料未涉及"。

## 技术栈
langchain-community(loader/splitter) + FAISS/Chroma + OllamaEmbeddings + ChatOllama

## 里程碑
- M1 ingest 跑通，索引落盘
- M2 检索命中正确章节（5 个测试问题）
- M3 带引用回答 + 拒答
- M4 增量更新（文档哈希去重）

## 验收标准
- [ ] 5 个文档内问题回答正确且引用可查
- [ ] 3 个文档外问题全部拒答
- [ ] 二次 ingest 不重复入库
