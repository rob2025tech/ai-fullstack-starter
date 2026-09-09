from dataclasses import dataclass


@dataclass(frozen=True)
class LearningConcept:
    concept: str
    meaning: str
    contrast_with: dict[str, str]


CONCEPTS: dict[str, LearningConcept] = {
    "虽然": LearningConcept(
        concept="虽然",
        meaning="although / even though",
        contrast_with={
            "因为": "because",
        },
    ),
}


def get_concept(concept: str) -> LearningConcept | None:
    return CONCEPTS.get(concept)
