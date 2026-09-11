from datetime import datetime

from pydantic import BaseModel, Field


class LearningStateResponse(BaseModel):
    user_id: str
    concept: str
    mastery: float
    attempts: int
    correct_count: int
    last_misconception: str | None = None
    next_review_at: datetime | None = None


class LearningAnswerRequest(BaseModel):
    user_id: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class TeachingResponse(BaseModel):
    explanation: str
    practice_question: str
    choices: list[str]


class LearningAnswerResponse(BaseModel):
    user_id: str
    concept: str
    is_correct: bool
    misconception: str | None = None
    mastery_before: float
    mastery_after: float
    attempts: int
    correct_count: int
    next_review_at: datetime
    teaching: TeachingResponse | None = None
