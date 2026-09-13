from dataclasses import dataclass

from app.learning.quiz_content import get_quiz_question


@dataclass(frozen=True)
class Diagnosis:
    is_correct: bool
    misconception: str | None


def diagnose_answer(concept: str, answer: str) -> Diagnosis:
    """Diagnose a quiz answer using the concept's canonical quiz content."""
    question = get_quiz_question(concept)

    if question is None:
        return Diagnosis(is_correct=False, misconception=None)

    normalized = answer.strip().lower()
    correct = question.correct_answer.strip().lower()

    if normalized == correct:
        return Diagnosis(is_correct=True, misconception=None)

    for choice in question.choices:
        if choice.strip().lower() == normalized:
            return Diagnosis(
                is_correct=False,
                misconception=(
                    f'Confuses the correct approach '
                    f'("{question.correct_answer}") with '
                    f'the distractor "{choice}".'
                ),
            )

    return Diagnosis(is_correct=False, misconception=None)
