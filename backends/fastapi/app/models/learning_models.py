from datetime import datetime

from pydantic import BaseModel, Field


class LearningStateResponse(BaseModel):
    user_id: str
    concept: str
    mastery: float
    attempts: int
    correct_count: int
    last_misconception: str | None = None
    next_review_at: datetime | None


class LearningAnswerRequest(BaseModel):
    user_id: str | None = None
    concept: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class LearningAnswerResponse(BaseModel):
    user_id: str
    concept: str
    is_correct: bool
    misconception: str | None = None
    mastery_before: float
    mastery_after: float
    attempts: int
    correct_count: int
    next_review_at: datetime | None
    teaching: "TeachingResponse | None" = None


class TeachingResponse(BaseModel):
    explanation: str
    practice_question: str
    choices: list[str]


class LearningQuizResponse(BaseModel):
    concept: str
    question: str
    choices: list[str]
    bloom_level: str


class LearningQuizAnswerRequest(BaseModel):
    user_id: str | None = None
    concept: str = Field(min_length=1)
    selected_answer: str = Field(min_length=1)


class LearningQuizAnswerResponse(BaseModel):
    user_id: str
    concept: str
    is_correct: bool
    selected_answer: str
    correct_answer: str
    mastery_before: float
    mastery_after: float
    attempts: int
    correct_count: int
    next_review_at: datetime | None
    explanation: str | None = None
    misconception: str | None = None
    practice_question: str | None = None
    practice_choices: list[str] | None = None


class LearningPracticeAnswerRequest(BaseModel):
    user_id: str | None = None
    concept: str = Field(min_length=1)
    selected_answer: str = Field(min_length=1)


class LearningPracticeAnswerResponse(BaseModel):
    user_id: str
    concept: str
    is_correct: bool
    selected_answer: str
    correct_answer: str
    mastery_before: float
    mastery_after: float
    attempts: int
    correct_count: int
    next_review_at: datetime | None
    explanation: str | None = None


class LearningRetestResponse(BaseModel):
    concept: str
    question: str
    choices: list[str]
    bloom_level: str


class LearningRetestAnswerRequest(BaseModel):
    user_id: str | None = None
    concept: str = Field(min_length=1)
    selected_answer: str = Field(min_length=1)


class LearningRetestAnswerResponse(BaseModel):
    user_id: str
    concept: str
    is_correct: bool
    selected_answer: str
    correct_answer: str
    mastery_before: float
    mastery_after: float
    attempts: int
    correct_count: int
    next_review_at: datetime | None
    misconception: str | None = None
