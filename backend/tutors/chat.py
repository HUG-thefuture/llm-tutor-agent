"""通用对话导师：自动决定是否检索知识库，携带学员进度上下文。"""
from __future__ import annotations

import asyncio

from ..core import memory
from ..core.llm import LLMClient
from ..core.rag import KnowledgeBase
from .learning import TUTOR_SYSTEM


def _progress_brief(learner_id: str) -> str:
    p = memory.load(learner_id)
    done = [k for k, v in p["lessons"].items() if v.get("passed_at")]
    lc = p["leetcode"]
    path_goal = (p.get("path") or {}).get("goal", "")
    return (f"已完成课程: {', '.join(done) if done else '（无）'}; "
            f"力扣已解出: {len(lc['solved'])} 题 {lc['solved']}; "
            f"当前学习目标: {path_goal or '（未设定）'}; "
            f"待复习: {', '.join(p['review_queue'][:5]) if p['review_queue'] else '（无）'}")


async def chat(llm: LLMClient, kb: KnowledgeBase, message: str,
               learner_id: str = "default", use_web: bool = False,
               web_fn=None) -> dict:
    hits = await kb.search(message, k=4)
    context = "\n\n".join(
        f"【资料 {i+1}】来源: {c.source} · {c.heading}\n{c.text}"
        for i, (c, _s) in enumerate(hits))
    grounded = bool(hits) and hits[0][1] > 1.0
    web_block = ""
    if use_web and web_fn:
        try:
            results = await asyncio.wait_for(web_fn(message), timeout=10)
            if results:
                web_block = "\n\n【网络检索结果】\n" + "\n".join(
                    f"- {r['title']} ({r['url']})：{r['snippet']}" for r in results[:4])
        except Exception:
            pass

    history = memory.chat_history(learner_id, limit=10)
    sys_prompt = TUTOR_SYSTEM + (
        "\n你同时是本学习助手的对话入口，可以帮助学员规划学习、答疑、审代码、聊职业发展。"
        f"\n\n【学员进度画像】{_progress_brief(learner_id)}"
        + (f"\n\n【知识库资料】\n{context[:6000]}" if grounded else "")
        + web_block
        + ("\n回答时结合以上资料并标注来源。" if (grounded or web_block)
           else "\n（本次未命中知识库与网络资料，按你的专业知识直接回答。）"))
    msgs = [{"role": "system", "content": sys_prompt}]
    msgs.extend({"role": h["role"], "content": h["content"]} for h in history)
    msgs.append({"role": "user", "content": message})
    out = await llm.chat(msgs, temperature=0.6)
    memory.append_chat(learner_id, "user", message)
    memory.append_chat(learner_id, "assistant", out)
    return {"reply": out, "grounded": grounded, "web_used": bool(web_block)}
