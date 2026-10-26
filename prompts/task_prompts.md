# 任务提示模板参考（导师模块使用；此处为文档化版本，便于查看与定制）

## 学习路径规划
输入：学员目标、课程目录、已完成列表、知识库检索摘录。
输出 JSON：assessment / steps[{lesson_id, why, focus}] / project。
约束：lesson_id 必须来自目录；步骤 5~10 个，由浅入深。

## 授课
输入：课程讲义、知识库补充、最近对话。
输出（Markdown）：本讲导读 → 核心概念讲解（可运行代码）→ 动手环节 → 检查理解（2 个提问）→ 常见的坑 → 练习提醒。

## 批改
输入：练习要求、参考要点、学员提交。
输出 JSON：score(0-100) / passed / strengths / problems[{level,text}] /
suggestions / concept_gaps / next("next"|"retry") / coach。
不通过时进入错题本（wrong_book）并扣技能矩阵经验值。

## 力扣提示（渐进）
level 1：只给方向；level 2：给关键数据结构/算法；level 3：给伪代码或骨架。
结合学员当前代码个性化，不直接给完整正确代码。

## 力扣点评
输出 JSON：complexity{time,space} / issues / style_tips / edge_cases / summary / score。

## 复盘（S6）
输入：一次任务/一讲/一道题的目标、过程、问题、验证结果。
输出：目标回顾 / 做法 / 问题与修复 / 验证结果 / 知识点沉淀 / 下一步。
