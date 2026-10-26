"""请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatReq(BaseModel):
    message: str
    learner_id: str = "default"
    use_web: bool = False


class PathReq(BaseModel):
    goal: str
    learner_id: str = "default"


class TeachReq(BaseModel):
    lesson_id: str
    learner_id: str = "default"


class SubmitReq(BaseModel):
    lesson_id: str
    exercise_id: str = ""
    code: str = ""
    notes: str = ""
    learner_id: str = "default"


class AnswerReq(BaseModel):
    question: str
    learner_id: str = "default"
    use_web: bool = False


class RunReq(BaseModel):
    problem_id: str
    code: str
    learner_id: str = "default"


class HintReq(BaseModel):
    problem_id: str
    level: int = Field(default=1, ge=1, le=5)
    code: str = ""
    learner_id: str = "default"


class ExplainReq(BaseModel):
    problem_id: str
    code: str = ""
    learner_id: str = "default"


class DevRunReq(BaseModel):
    goal: str
    project: str = ""


class KBUploadReq(BaseModel):
    title: str
    text: str


class LLMTestReq(BaseModel):
    provider: str = ""
