from dataclasses import dataclass
from typing import Literal


BloomLevel = Literal["remember", "understand", "apply"]


@dataclass(frozen=True)
class QuizQuestion:
    concept: str
    question: str
    choices: tuple[str, ...]
    correct_answer: str
    bloom_level: BloomLevel


@dataclass(frozen=True)
class QuizResult:
    question: QuizQuestion
    selected_answer: str
    is_correct: bool


def evaluate_answer(
    question: QuizQuestion,
    selected_answer: str,
) -> QuizResult:
    return QuizResult(
        question=question,
        selected_answer=selected_answer,
        is_correct=selected_answer.strip().lower()
        == question.correct_answer.strip().lower(),
    )
