"""学员进度存储：data/progress/<learner_id>.json，原子写入。"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable

from .config import PROGRESS_DIR

_LOCK = threading.Lock()

_MAX_HISTORY = 60


def _default() -> dict:
    return {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chat_history": [],
        "path": {},                 # 最近一次学习计划 {"goal":..., "steps":[{lesson_id, why, focus, status}]}
        "lessons": {},              # {lesson_id: {"score":0-100, "attempts":n, "passed_at":ts|""}}
        "leetcode": {
            "solved": [],           # 题目 id
            "attempts": [],         # [{id, ts, verdict}]
        },
        "review_queue": [],         # 需要复习的知识点
        "skill_matrix": {},         # {track: {"level": 1-6, "passed": n, "evidence": [lesson_id...]}}
        "wrong_book": [],           # 错题本 [{ts, lesson, text}]
        "common_funcs": [],         # 常用函数/API 速查（学员收藏）
    }


def _file(learner_id: str) -> Path:
    safe = "".join(c for c in learner_id if c.isalnum() or c in "-_") or "default"
    return PROGRESS_DIR / f"{safe}.json"


def load(learner_id: str = "default") -> dict:
    f = _file(learner_id)
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            base = _default()
            base.update(data)
            base.setdefault("leetcode", {"solved": [], "attempts": []})
            return base
        except Exception:
            pass
    return _default()


def save(learner_id: str, data: dict) -> None:
    with _LOCK:
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        f = _file(learner_id)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, f)


def update(learner_id: str, fn: Callable[[dict], None]) -> dict:
    data = load(learner_id)
    fn(data)
    save(learner_id, data)
    return data


# ---------- 高层操作 ----------
def append_chat(learner_id: str, role: str, content: str) -> None:
    def fn(d):
        d["chat_history"].append({"role": role, "content": content[:6000], "ts": time.time()})
        d["chat_history"] = d["chat_history"][-_MAX_HISTORY:]
    update(learner_id, fn)


def chat_history(learner_id: str, limit: int = 12) -> list[dict]:
    return load(learner_id)["chat_history"][-limit:]


def record_lesson(learner_id: str, lesson_id: str, score: int, passed: bool) -> None:
    def fn(d):
        rec = d["lessons"].setdefault(lesson_id, {"score": 0, "attempts": 0, "passed_at": ""})
        rec["attempts"] += 1
        rec["score"] = max(rec.get("score", 0), score)
        if passed and not rec["passed_at"]:
            rec["passed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    update(learner_id, fn)


def set_path(learner_id: str, goal: str, steps: list[dict]) -> None:
    def fn(d):
        d["path"] = {"goal": goal, "steps": steps}
    update(learner_id, fn)


def mark_step(learner_id: str, lesson_id: str, status: str = "done") -> None:
    def fn(d):
        for s in d.get("path", {}).get("steps", []):
            if s.get("lesson_id") == lesson_id:
                s["status"] = status
    update(learner_id, fn)


def record_attempt(learner_id: str, problem_id: str, verdict: str) -> dict:
    solved = verdict == "accepted"

    def fn(d):
        lc = d["leetcode"]
        lc["attempts"].append({"id": problem_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "verdict": verdict})
        lc["attempts"] = lc["attempts"][-200:]
        if solved and problem_id not in lc["solved"]:
            lc["solved"].append(problem_id)
    update(learner_id, fn)
    return {"solved": solved}


def add_review_item(learner_id: str, item: str) -> None:
    def fn(d):
        if item and item not in d["review_queue"]:
            d["review_queue"].append(item)
            d["review_queue"] = d["review_queue"][-50:]
    update(learner_id, fn)


def add_wrong(learner_id: str, lesson_title: str, text: str) -> None:
    """错题本：练习未通过时记录失分点。"""
    def fn(d):
        d["wrong_book"].append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "lesson": lesson_title, "text": text[:300]})
        d["wrong_book"] = d["wrong_book"][-100:]
    update(learner_id, fn)


def bump_skill(learner_id: str, track: str, lesson_id: str, step: int = 1) -> None:
    """技能矩阵：通过一讲，对应方向经验 +1；每 3 讲升一级（上限 L6）。"""
    def fn(d):
        rec = d["skill_matrix"].setdefault(track, {"level": 1, "passed": 0, "evidence": []})
        if lesson_id not in rec["evidence"]:
            rec["evidence"].append(lesson_id)
            rec["passed"] += 1
            rec["level"] = min(6, 1 + rec["passed"] // 3)
    update(learner_id, fn)


def add_common_func(learner_id: str, sig: str) -> None:
    def fn(d):
        if sig and sig not in d["common_funcs"]:
            d["common_funcs"].append(sig[:200])
            d["common_funcs"] = d["common_funcs"][-80:]
    update(learner_id, fn)
