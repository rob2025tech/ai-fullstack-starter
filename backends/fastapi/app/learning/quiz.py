from dataclasses import dataclass
from typing import Literal


BloomLevel = Literal[
    "remember",
    "understand",
    "apply",
    "analyze",
    "evaluate",
    "create",
]


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


@dataclass(frozen=True)
class PracticeQuestion:
    concept: str
    question: str
    choices: tuple[str, ...]
    correct_answer: str


@dataclass(frozen=True)
class PracticeResult:
    question: PracticeQuestion
    selected_answer: str
    is_correct: bool


def evaluate_answer(
    question: QuizQuestion,
    selected_answer: str,
) -> QuizResult:
    """Evaluate a retention-quiz answer deterministically."""
    return QuizResult(
        question=question,
        selected_answer=selected_answer,
        is_correct=(
            selected_answer.strip().lower()
            == question.correct_answer.strip().lower()
        ),
    )


def evaluate_practice_answer(
    question: PracticeQuestion,
    selected_answer: str,
) -> PracticeResult:
    """Evaluate a targeted practice answer deterministically."""
    return PracticeResult(
        question=question,
        selected_answer=selected_answer,
        is_correct=(
            selected_answer.strip().lower()
            == question.correct_answer.strip().lower()
        ),
    )
