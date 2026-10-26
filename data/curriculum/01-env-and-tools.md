---
id: env-and-tools
title: 开发环境与工具链
level: beginner
track: python
prereq: []
est_minutes: 30
tags: [环境, venv, pip, git, api-key]
---

# 开发环境与工具链

## 为什么是第一课
大模型开发 80% 的入门障碍不是模型，而是环境：版本冲突、依赖污染、密钥泄露。本讲把地基打牢。

## 虚拟环境：项目之间互不干扰
```bash
# Windows（py 启动器）
py -3 -m venv .venv
.venv\Scripts\activate
# Linux / macOS
python3 -m venv .venv && source .venv/bin/activate

# 依赖管理
pip install -r requirements.txt
pip freeze > requirements.txt
```
原则：**一个项目一个 venv**；`requirements.txt` 进 git，`.venv` 不进。

## Git 最低限度
```bash
git init && git add . && git commit -m "init"
git checkout -b feat/rag    # 分支上实验，稳定后合回 main
```
`.gitignore` 必须包含：`.venv/`、`.env`、`__pycache__/`、数据目录。

## API Key 管理（安全红线）
```python
# .env 文件（不进 git）
DEEPSEEK_API_KEY=sk-xxxx

# 代码中读取（python-dotenv 或手写解析）
import os
key = os.environ["DEEPSEEK_API_KEY"]   # 永远不要硬编码在源码里
```
常见事故：把 key 提交到 GitHub → 几分钟内被机器人扫到盗刷。**key 只存在于 .env 或系统环境变量。**

## 编辑器与调试
- VS Code / PyCharm + Python 插件，断点调试（F5）比 print 高效十倍。
- 学会用 `python -X utf8` 解决 Windows 控制台中文乱码（本机 cmd 默认 GBK）。

## 自测
1. 为什么不能把 venv 目录提交到 git？
2. `.env` 与环境变量各适合放什么？

## 练习
```yaml
- id: env-1
  type: code
  prompt: |
    创建一个项目目录，完成：1) 建立 venv 并激活；2) 写 requirements.txt（内容为 httpx）；
    3) 写 .env 与 .gitignore；4) 写 config.py，用 os.environ 读取 MY_API_KEY，
    key 缺失时抛出带中文提示的 RuntimeError。
  hints:
    - "读环境变量用 os.environ.get('MY_API_KEY')，为空时 raise RuntimeError('请先配置 MY_API_KEY')"
  solution: |
    import os
    def get_key() -> str:
        key = os.environ.get("MY_API_KEY", "")
        if not key:
            raise RuntimeError("未配置 MY_API_KEY：请写入 .env 或系统环境变量")
        return key
```
