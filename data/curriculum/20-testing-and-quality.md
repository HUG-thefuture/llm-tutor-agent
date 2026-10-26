---
id: testing-and-quality
title: 测试与质量工程（LLM 应用版）
level: advanced
track: quality
prereq: [fullstack-project]
est_minutes: 60
tags: [pytest, 测试, 内存泄漏, 静态检查, 复盘]
---

# 测试与质量工程

## LLM 应用的测试金字塔
| 层 | 测什么 | 怎么测 |
|---|---|---|
| 单元 | 切分/解析/工具函数 | pytest，纯逻辑无模型 |
| 集成 | 接口/DB/向量库 | TestClient + 固定 fixture |
| 模型 | 输出质量 | 评测集 + 断言（含关键词/JSON 合法/引用存在） |
| 人工 | 体验 | 10 个代表性场景走查 |

## 单元测试模板
```python
import pytest
from myapp.splitter import split_text

def test_split_keeps_overlap():
    chunks = split_text("a" * 1000, size=100, overlap=20)
    assert all(len(c) <= 100 for c in chunks)
    assert chunks[1].startswith(chunks[0][-20:])     # 重叠生效

@pytest.mark.parametrize("bad", ["", None, 123])
def test_split_rejects_bad_input(bad):
    with pytest.raises((ValueError, TypeError)):
        split_text(bad, size=100, overlap=10)
```
**正常路径 + 边界 + 非法输入**三件套，一个都不能少。

## mock 模型：让测试快而稳
```python
class FakeLLM:
    async def chat(self, messages, **kw):
        return '{"label": "positive", "confidence": 0.9}'
# 依赖注入：app.state.llm = FakeLLM()
```
原则：单测里**永不调用真实模型**（慢/贵/不稳定）；模型质量交给评测集。

## 内存与资源体检清单
1. `while True` 有退出条件？—— 死循环；
2. 文件/连接是否都 `with`/`finally close`？—— 句柄泄漏；
3. 全局 list/dict 是否无限增长？—— 缓存要配上限（LRU/TTL）；
4. 异步任务异常是否被吞？—— `asyncio.create_task` 要保存引用并加回调；
5. 大对象是否被闭包/全局持有？—— 用完置 None。

复现法：循环调用 1000 次后 `tracemalloc` 对比堆增长。

## 静态检查
```bash
py -3 -m py_compile *.py            # 语法
ruff check . && ruff format .       # 风格与常见错误（推荐）
bandit -r .                          # 安全扫描
```
本助手 backend/core/staticcheck.py 内置了 AST 级扫描
（可变默认参数/裸 except/while True/未超时 requests/硬编码密钥），可对照学习。

## 复盘机制（S6）
每次任务结束固定三问：**结果 vs 预期差在哪？根因是什么？哪条经验进清单？**
把错因沉淀为检查项，下次 review 直接查——本助手的错题本/技能矩阵就是这个机制的落地。

## 自测
1. 为什么单测里不能调真实模型？
2. 五条内存体检清单各对应什么泄漏？

## 练习
```yaml
- id: tq-1
  type: code
  prompt: |
    为本助手 backend/core/rag.py 的 tokenize() 写 4 个 pytest 用例：
    纯英文、纯中文（验证 bigram）、中英混合、空字符串。
  starter: |
    import sys; sys.path.insert(0, r"D:\llm-tutor-agent")
    from backend.core.rag import tokenize

    def test_english():
        assert "hello" in tokenize("Hello World")
    # TODO: 其余三个
  hints:
    - "中文 bigram：tokenize('知识库') 应包含 '知识' 与 '识库'"
    - "空字符串返回 []"
- id: tq-2
  type: quiz
  prompt: |
    同伴的 RAG 服务"越跑越慢"，重启就好。给出你的排查步骤（按概率排序）。
  hints:
    - "1) 全局容器无限增长（缓存/日志/历史）2) 连接未关闭累积 3) asyncio 任务堆积"
    - "4) 磁盘/索引膨胀 5) 用 tracemalloc 与 task 数量监控证实"
```
