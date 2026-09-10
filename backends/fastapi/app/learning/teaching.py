from dataclasses import dataclass

from app.learning.content import get_concept


@dataclass(frozen=True)
class TeachingResponse:
    explanation: str
    practice_question: str
    choices: tuple[str, ...]


def generate_teaching(
    concept: str,
    misconception: str | None,
) -> TeachingResponse | None:
    learning_concept = get_concept(concept)
    if learning_concept is None:
        return None

    if misconception:
        explanation = (
            f"{concept} means {learning_concept.meaning}. "
            "It is used when one idea is true despite another condition. "
            "By contrast, 因为 means because and gives the reason for something."
        )
    else:
        explanation = (
            f"{concept} means {learning_concept.meaning}. "
            "It introduces a contrast: something is true despite another condition."
        )

    return TeachingResponse(
        explanation=explanation,
        practice_question=f"Which meaning best matches {concept}?",
        choices=("although / even though", "because"),
    )
