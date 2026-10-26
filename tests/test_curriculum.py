# -*- coding: utf-8 -*-
"""课程体系与题库完整性测试：规范自检（S7 退出判断的数据基础）。"""
import json

from backend.core.config import LEETCODE_FILE
from backend.core.config import ROOT as PROJECT_ROOT
from backend.tutors.curriculum import load_lessons

KNOWN_TRACKS = {"python", "llm-core", "langchain", "rag", "agent", "fullstack", "quality"}


def test_lessons_loaded_and_unique():
    lessons = load_lessons()
    assert len(lessons) >= 20, f"课程数量不足: {len(lessons)}"
    assert len(lessons) == len(set(lessons.keys())), "课程 id 重复"


def test_every_lesson_has_exercise():
    for lid, l in load_lessons().items():
        assert l.exercises, f"课程 {lid} 没有练习"


def test_lesson_tracks_valid():
    for lid, l in load_lessons().items():
        assert l.track in KNOWN_TRACKS, f"课程 {lid} 的 track 非法: {l.track}"
        assert l.level in {"beginner", "intermediate", "advanced"}, f"课程 {lid} 级别非法"


def test_matrix_lesson_ids_exist():
    import yaml
    matrix = yaml.safe_load((PROJECT_ROOT / "skills" / "matrix.yaml").read_text(encoding="utf-8"))
    lessons = load_lessons()
    for track, levels in matrix["tracks"].items():
        for lvl, ids in levels.items():
            for lid in ids:
                assert lid in lessons, f"matrix 引用了不存在的课程: {lid}"


def test_prereq_ids_exist():
    lessons = load_lessons()
    for lid, l in lessons.items():
        for p in l.prereq:
            assert p in lessons, f"课程 {lid} 的前置 {p} 不存在"


def test_problems_bank_valid():
    data = json.loads(LEETCODE_FILE.read_text(encoding="utf-8"))
    ids = [p["id"] for p in data["problems"]]
    assert len(ids) >= 12 and len(ids) == len(set(ids))
    for p in data["problems"]:
        assert p["tests"] and p["hints"] and p["reference"], f"{p['id']} 缺少测试/提示/参考解法"
