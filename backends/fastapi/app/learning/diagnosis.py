from dataclasses import dataclass

from app.learning.content import get_concept


@dataclass(frozen=True)
class Diagnosis:
    is_correct: bool
    misconception: str | None


def diagnose_answer(concept: str, answer: str) -> Diagnosis:
    learning_concept = get_concept(concept)

    if learning_concept is None:
        return Diagnosis(is_correct=False, misconception=None)

    normalized = answer.strip().lower()

    if normalized in {"although", "even though", "though"}:
        return Diagnosis(is_correct=True, misconception=None)

    for contrasted_term, contrasted_meaning in learning_concept.contrast_with.items():
        if normalized == contrasted_meaning:
            return Diagnosis(
                is_correct=False,
                misconception=(
                    f"Confuses {concept} ({learning_concept.meaning}) "
                    f"with {contrasted_term} ({contrasted_meaning})."
                ),
            )

    return Diagnosis(is_correct=False, misconception=None)
