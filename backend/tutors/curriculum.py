"""课程加载与解析：data/curriculum/*.md（YAML frontmatter + 结尾练习 YAML 块）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..core.config import CURRICULUM_DIR


@dataclass
class Exercise:
    id: str
    type: str                  # code | quiz | project
    prompt: str
    starter: str = ""
    hints: list[str] = field(default_factory=list)
    solution: str = ""

    def to_dict(self, with_solution: bool = False) -> dict:
        d = {"id": self.id, "type": self.type, "prompt": self.prompt,
             "starter": self.starter, "hints": self.hints}
        if with_solution:
            d["solution"] = self.solution
        return d


@dataclass
class Lesson:
    id: str
    title: str
    level: str                 # beginner | intermediate | advanced
    track: str                 # python | llm-core | langchain | rag | fullstack | quality
    prereq: list[str]
    est_minutes: int
    tags: list[str]
    body: str                  # 去掉 frontmatter 的正文（含练习）
    exercises: list[Exercise]
    path: str

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "level": self.level, "track": self.track,
                "prereq": self.prereq, "est_minutes": self.est_minutes, "tags": self.tags,
                "exercises": [e.to_dict() for e in self.exercises], "path": self.path}


def _parse_exercises(body: str, lesson_id: str) -> list[Exercise]:
    """取『## 练习』小节里的 ```yaml 块（列表）。"""
    out: list[Exercise] = []
    if "## 练习" not in body:
        return out
    tail = body.split("## 练习", 1)[1]
    import re
    for m in re.finditer(r"```yaml\s*\n(.*?)```", tail, re.S):
        try:
            data = yaml.safe_load(m.group(1))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            out.append(Exercise(
                id=str(it.get("id") or f"{lesson_id}-ex{i+1}"),
                type=str(it.get("type") or "code"),
                prompt=str(it.get("prompt") or ""),
                starter=str(it.get("starter") or ""),
                hints=[str(h) for h in (it.get("hints") or [])],
                solution=str(it.get("solution") or ""),
            ))
    return out


def load_lessons(directory: Path = CURRICULUM_DIR) -> dict[str, Lesson]:
    lessons: dict[str, Lesson] = {}
    if not directory.exists():
        return lessons
    for f in sorted(directory.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except Exception:
                    meta = {}
                body = parts[2]
        lid = str(meta.get("id") or f.stem)
        lessons[lid] = Lesson(
            id=lid,
            title=str(meta.get("title") or f.stem),
            level=str(meta.get("level") or "beginner"),
            track=str(meta.get("track") or "llm-core"),
            prereq=[str(x) for x in (meta.get("prereq") or [])],
            est_minutes=int(meta.get("est_minutes") or 45),
            tags=[str(x) for x in (meta.get("tags") or [])],
            body=body.strip(),
            exercises=_parse_exercises(body, lid),
            path=f.name,
        )
    return lessons


def check_prereq(lesson: Lesson, lessons: dict[str, Lesson], done: set[str]) -> list[str]:
    return [p for p in lesson.prereq if p not in done]
