"""学习引导导师：生成学习路径 → 引导式授课 → 练习批改 → 进度沉淀。"""
from __future__ import annotations

import json
from pathlib import Path

from ..core import memory
from ..core.config import ROOT
from ..core.llm import LLMClient, LLMError
from ..core.rag import KnowledgeBase
from .curriculum import Lesson, check_prereq

_BUILTIN_SYSTEM = (
    "你是一位耐心、专业的大模型开发导师，正在一对一辅导学员从零掌握 LangChain/RAG/"
    "函数调用/前后端开发等技能。要求：\n"
    "1. 全程中文，循序渐进，多用类比和可运行的代码示例；\n"
    "2. 引导式教学：先讲概念，再用提问检查理解，不直接甩答案；\n"
    "3. 代码示例必须标注语言、可直接运行，并在关键行加中文注释；\n"
    "4. 指出常见坑与调试方法。"
)


def _load_system_prompt() -> str:
    f = ROOT / "prompts" / "system_prompt.md"
    if f.exists():
        text = f.read_text(encoding="utf-8")
        # 去掉 markdown 标题行，仅保留提示正文
        lines = [x for x in text.splitlines() if not x.startswith("# ")]
        return "\n".join(lines).strip() or _BUILTIN_SYSTEM
    return _BUILTIN_SYSTEM


TUTOR_SYSTEM = _load_system_prompt()


async def plan_path(llm: LLMClient, kb: KnowledgeBase, lessons: dict[str, Lesson],
                    goal: str, learner_id: str = "default") -> dict:
    """根据目标 + 已有进度，产出个性化学习路径。"""
    progress = memory.load(learner_id)
    done = {k for k, v in progress["lessons"].items() if v.get("passed_at")}
    catalog = "\n".join(
        f"- {l.id} | {l.title} | 级别:{l.level} | 方向:{l.track} | 标签:{','.join(l.tags)}"
        + (f" | 前置:{','.join(l.prereq)}" if l.prereq else "")
        for l in lessons.values())
    context, _ = await kb.context_async(goal, k=6)
    known = list(lessons.keys())
    try:
        plan = await llm.chat_json(
            [{"role": "system", "content": TUTOR_SYSTEM},
             {"role": "user", "content":
              f"学员目标：{goal}\n\n课程目录（只能从中选择 lesson_id）：\n{catalog}\n\n"
              f"学员已完成：{', '.join(sorted(done)) or '（尚无）'}\n"
              f"知识库相关资料摘录：\n{context[:3000]}\n\n"
              '请输出 JSON: {"assessment": "对该目标与学员现状的评估", '
              '"steps": [{"lesson_id": "必须是目录中的 id", "why": "为什么学它/学到什么程度", '
              '"focus": "本讲要重点练什么"}], '
              '"project": "学完后的综合实战项目建议（一句话）"}。'
              f"可用的 lesson_id 列表: {json.dumps(known, ensure_ascii=False)}。"
              "步骤要由浅入深、可执行，通常 5~10 步。"}],
            temperature=0.3)
    except LLMError:
        # 降级：按关键词匹配 course track 排课
        key_map = {"rag": "rag", "知识库": "rag", "检索": "rag",
                   "langchain": "langchain", "框架": "langchain",
                   "函数": "llm-core", "调用": "llm-core", "api": "llm-core",
                   "前端": "fullstack", "后端": "fullstack", "全栈": "fullstack",
                   "测试": "quality", "python": "python"}
        track_order = ["python", "llm-core", "langchain", "rag", "fullstack", "quality"]
        want = [t for t in track_order if any(k in goal.lower() for k, t in key_map.items())] or \
               ["python", "llm-core", "langchain", "rag", "fullstack"]
        picked = [l for l in sorted(lessons.values(), key=lambda x: x.id)
                  if l.track in want and l.id not in done]
        plan = {"assessment": "（离线降级模式：按方向自动排课）",
                "steps": [{"lesson_id": l.id, "why": f"{l.title}（{l.track} 方向）",
                           "focus": "完成本讲练习并通过自测"} for l in picked],
                "project": "综合实战：构建一个带 RAG 知识库的问答 Web 应用"}
    steps = []
    for s in plan.get("steps", []):
        lid = s.get("lesson_id")
        if lid in lessons:
            miss = check_prereq(lessons[lid], lessons, done)
            steps.append({"lesson_id": lid, "title": lessons[lid].title,
                          "why": s.get("why", ""), "focus": s.get("focus", ""),
                          "status": "done" if lid in done else ("todo" if not miss else "blocked"),
                          "missing_prereq": miss})
    memory.set_path(learner_id, goal, steps)
    plan["steps"] = steps
    plan["goal"] = goal
    return plan


async def teach(llm: LLMClient, kb: KnowledgeBase, lesson: Lesson,
                learner_id: str = "default") -> str:
    """引导式授课：讲解 + 检查性提问 + 练习布置。"""
    history = memory.chat_history(learner_id, limit=6)
    context, _ = await kb.context_async(lesson.title, k=4)
    msgs = [{"role": "system", "content": TUTOR_SYSTEM}]
    msgs.extend({"role": h["role"], "content": h["content"]} for h in history)
    msgs.append({"role": "user", "content":
                 f"请围绕下面这讲内容给我上一节课（面向有一点编程基础但不熟悉大模型开发的学员）。\n"
                 f"【课程标题】{lesson.title}（预计 {lesson.est_minutes} 分钟）\n"
                 f"【课程讲义原文】\n{lesson.body[:9000]}\n"
                 f"【知识库补充资料】\n{context[:2500]}\n\n"
                 "授课结构要求：\n"
                 "## 本讲导读（3 句话讲清楚为什么学/学什么）\n"
                 "## 核心概念讲解（配可运行代码）\n"
                 "## 动手环节（明确告诉我现在打开编辑器做什么，一步一步）\n"
                 "## 检查理解（向我提 2 个问题，等我回答后再继续）\n"
                 "## 常见的坑\n"
                 "最后给出本讲的练习要求提醒（不要直接给答案）。"})
    out = await llm.chat(msgs, temperature=0.5)
    memory.mark_step(learner_id, lesson.id, "learning")
    return out


async def grade_submission(llm: LLMClient, lesson: Lesson, exercise_id: str,
                           submission: str, learner_id: str = "default") -> dict:
    """批改练习：评分 + 反馈 + 下一步动作。"""
    ex = next((e for e in lesson.exercises if e.id == exercise_id), None)
    ex_desc = (f"练习 id: {ex.id}\n类型: {ex.type}\n要求: {ex.prompt}\n参考要点: {ex.solution[:1200]}"
               if ex else f"练习 id: {exercise_id}（讲义练习区）")
    try:
        result = await llm.chat_json(
            [{"role": "system", "content": TUTOR_SYSTEM},
             {"role": "user", "content":
              f"课程: {lesson.title}\n{ex_desc}\n\n【学员提交】\n{submission[:8000]}\n\n"
              '按以下维度批改：正确性/完整性、代码规范、是否理解概念（从注释与写法判断）。\n'
              '输出 JSON: {"score": 0-100, "passed": true或false(>=60为true), '
              '"strengths": ["亮点..."], "problems": [{"level": "high|medium|low", "text": "问题描述"}], '
              '"suggestions": ["具体改进建议..."], "concept_gaps": ["暴露出的概念缺口，用于复习队列"], '
              '"next": "next" 或 "retry"，"coach": "给学员的鼓励与下一步指引(2-3句)"}'}],
            temperature=0.2)
    except LLMError:
        result = {"score": -1, "passed": False, "strengths": [], "problems": [],
                  "suggestions": [], "concept_gaps": [],
                  "next": "retry", "coach": "模型暂不可用，请稍后重试提交。"}
    score = int(result.get("score", 0) or 0)
    passed = bool(result.get("passed")) and score >= 60
    memory.record_lesson(learner_id, lesson.id, score, passed)
    if passed:
        memory.mark_step(learner_id, lesson.id, "done")
        memory.bump_skill(learner_id, lesson.track, lesson.id)
    else:
        for p_ in result.get("problems", []) or []:
            if isinstance(p_, dict) and p_.get("level") == "high":
                memory.add_wrong(learner_id, lesson.title, p_.get("text", ""))
    for gap in result.get("concept_gaps", []) or []:
        memory.add_review_item(learner_id, f"[{lesson.title}] {gap}")
    result["score"], result["passed"] = score, passed
    result["lesson_id"] = lesson.id
    # 评估留痕（S6 复盘素材）
    try:
        evals_dir = ROOT / "evals"
        evals_dir.mkdir(exist_ok=True)
        import time as _t
        (evals_dir / f"grade-{lesson.id}-{_t.strftime('%Y%m%d-%H%M%S')}.json").write_text(
            json.dumps({"lesson": lesson.id, "exercise": exercise_id,
                        "submission": submission[:2000], "result": result},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return result


async def answer(llm: LLMClient, kb: KnowledgeBase, question: str,
                 learner_id: str = "default", use_web: bool = False,
                 web_fn=None) -> str:
    """RAG 问答：先查知识库；资料不足且允许联网时补充网络检索结果。"""
    hits = await kb.search(question, k=5)
    context = "\n\n".join(
        f"【资料 {i+1}】来源: {c.source} · {c.heading}\n{c.text}"
        for i, (c, _s) in enumerate(hits))
    web_block = ""
    if use_web and web_fn and ((not hits) or hits[0][1] < 2.0):
        try:
            results = await web_fn(question)
            if results:
                web_block = "\n\n【网络检索结果】\n" + "\n".join(
                    f"- {r['title']} ({r['url']})：{r['snippet']}" for r in results[:4])
        except Exception:
            pass
    history = memory.chat_history(learner_id, limit=8)
    msgs = [{"role": "system", "content": TUTOR_SYSTEM +
             "\n回答时优先依据【知识库资料】与【网络检索结果】，并标注来源；"
             "资料不足时说明并给出建议的学习路径。"}]
    msgs.extend({"role": h["role"], "content": h["content"]} for h in history)
    msgs.append({"role": "user", "content":
                 f"【知识库资料】\n{context[:6000] or '（未命中）'}{web_block}\n\n"
                 f"【学员提问】{question}"})
    out = await llm.chat(msgs, temperature=0.5)
    memory.append_chat(learner_id, "user", question)
    memory.append_chat(learner_id, "assistant", out)
    return out
