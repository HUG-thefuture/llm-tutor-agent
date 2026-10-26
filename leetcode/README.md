# 力扣算法训练

## 题库位置
机器可读题库（含测试用例/渐进提示/参考解法）：`data/leetcode/problems.json`
当前内置 12 道经典题（8 easy / 4 medium），覆盖：数组、哈希、栈、双指针、
滑动窗口、链表、二叉树、BFS、动态规划、贪心（Boyer-Moore）。

## 使用方式
浏览器打开本助手 → 「LeetCode」页：选题 → 写代码 → 运行评测（本地判题，
带沙箱防护与超时拦截）→ 逐级提示（3 级渐进）→ AI 点评复杂度与边界 → 解法精讲。

## 判题约定
- 返回值用 list/int/str/bool；链表/二叉树题由判题器自动做 数组↔结构 转换；
- 比对模式：exact（精确）/ sorted（无序结果）/ any（多解任一）。

## 扩充题库
往 problems.json 添加新题即可，字段：
id / title / difficulty / tags / description / func / signature / match /
tests[{args,expected}] / hints[] / reference / followup / 可选 setup+arg_builders+result_serializer。

## 每题标准流程（训练纪律）
审题 → 例子走查 → 思路（说清数据结构选择理由）→ 暴力解 → 优化解 →
编码 → 本地判题 → 复杂度分析 → 同类题 → 复盘（错因进错题本）。

## 目标
easy 30 题 / medium 30 题 / 部分 hard。内置 12 题作为起步，
更多题目可让对话导师按同格式生成（AI 生成后务必人工核对测试用例）。
