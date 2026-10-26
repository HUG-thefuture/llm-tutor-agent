"""力扣辅导导师：选题 → 渐进提示 → 本地判题 + AI 点评 → 解法精讲。"""
from __future__ import annotations

import json

from ..core import judge, memory
from ..core.llm import LLMClient, LLMError

COACH_SYSTEM = (
    "你是一位算法教练，辅导学员刷力扣题。风格：苏格拉底式引导，先问思路再给提示；"
    "讲复杂度时给出估算过程；代码示例用 Python 并带中文注释。全程中文。"
)


class ProblemBank:
    def __init__(self, data: dict):
        self.problems: dict[str, dict] = {p["id"]: p for p in data.get("problems", [])}

    def list(self) -> list[dict]:
        return [
            {"id": p["id"], "title": p["title"], "difficulty": p["difficulty"],
             "tags": p["tags"], "func": p["func"], "signature": p.get("signature", ""),
             "hint_count": len(p.get("hints", []))}
            for p in self.problems.values()
        ]

    def get(self, pid: str) -> dict | None:
        return self.problems.get(pid)

    def next_for(self, learner_id: str) -> dict | None:
        """难度阶梯选题：优先未解出的 easy，再 medium；已解出的不重复推。"""
        prog = memory.load(learner_id)["leetcode"]
        solved = set(prog["solved"])
        order = {"easy": 0, "medium": 1, "hard": 2}
        todo = sorted((p for p in self.problems.values() if p["id"] not in solved),
                      key=lambda p: (order.get(p["difficulty"], 3), p["id"]))
        return todo[0] if todo else None


def starter_code(problem: dict) -> str:
    sig = problem.get("signature") or f"def {problem['func']}(...):\n"
    return sig + "\n    # 在这里写你的解法\n    pass\n"


async def hint(llm: LLMClient, problem: dict, level: int, user_code: str = "") -> str:
    """渐进提示：level 1..n，取题库内置提示，再用 LLM 结合学员代码个性化。"""
    hints = problem.get("hints", [])
    base = hints[min(max(level, 1), len(hints)) - 1] if hints else ""
    try:
        out = await llm.chat(
            [{"role": "system", "content": COACH_SYSTEM},
             {"role": "user", "content":
              f"题目：{problem['title']}\n题意：{problem['description'][:600]}\n"
              f"学员当前代码：\n{(user_code or '（还没写）')[:3000]}\n\n"
              f"内置提示素材（第 {level} 级，不要原样照搬，融入讲解）：\n{base}\n\n"
              f"请给出第 {level} 级提示（level 越大越接近答案）。"
              "要求：3-6 句话；引导式口吻；如果学员代码有 bug 顺带点出来但不要直接给完整正确代码。"}],
            temperature=0.4)
    except LLMError:
        out = base or "（模型暂不可用）"
    return out


async def review(llm: LLMClient, problem: dict, code: str, timeout: float,
                 learner_id: str = "default") -> dict:
    """判题（客观）+ AI 点评（复杂度/风格/边界）。"""
    jr = judge.run_tests(problem, code, timeout=timeout)
    memory.record_attempt(learner_id, problem["id"], jr["verdict"])
    coach = {}
    try:
        failed = [r for r in jr.get("results", []) if not r.get("pass")]
        coach = await llm.chat_json(
            [{"role": "system", "content": COACH_SYSTEM},
             {"role": "user", "content":
              f"题目：{problem['title']}\n{problem['description'][:500]}\n\n"
              f"【学员代码】\n{code[:6000]}\n\n"
              f"【判题结果】{jr['verdict']}，通过 {jr.get('passed')}/{jr.get('total')}"
              + (f"，失败用例：{json.dumps(failed[:3], ensure_ascii=False)}" if failed else "")
              + f"，参考解法（仅供你对照，勿直接贴给学员）：\n{problem.get('reference', '')[:1500]}\n\n"
              '输出 JSON: {"complexity": {"time": "O(..) 及理由", "space": "O(..) 及理由"}, '
              '"issues": ["代码问题（无则空）"], '
              '"style_tips": ["规范性建议（无则空）"], '
              '"edge_cases": ["未考虑的边界（无则空）"], '
              '"summary": "一句话总评", "score": 0-100}'}],
            temperature=0.2)
    except LLMError:
        coach = {"complexity": {"time": "", "space": ""}, "issues": [], "style_tips": [],
                 "edge_cases": [], "summary": "（模型暂不可用，仅显示判题结果）", "score": -1}
    return {"judge": jr, "coach": coach}


async def explain_solution(llm: LLMClient, problem: dict, user_code: str = "") -> str:
    try:
        out = await llm.chat(
            [{"role": "system", "content": COACH_SYSTEM},
             {"role": "user", "content":
              f"题目：{problem['title']}\n{problem['description'][:600]}\n"
              f"学员代码：\n{(user_code or '（未提供）')[:2000]}\n\n"
              f"参考解法：\n{problem.get('reference', '')}\n\n"
              "请精讲：1) 逐步推导思路（为什么想到这个方向）2) 逐段解释参考代码 "
              "3) 复杂度分析 4) 与学员代码的差异与可改进点 5) 记忆点/同类题。"}],
            temperature=0.4)
    except LLMError:
        out = f"（模型暂不可用）参考解法：\n```python\n{problem.get('reference', '')}\n```"
    return out


def next_problem_id(learner_id: str, bank: ProblemBank) -> str | None:
    p = bank.next_for(learner_id)
    return p["id"] if p else None
