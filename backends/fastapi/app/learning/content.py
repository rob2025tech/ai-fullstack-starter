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
        contrast_with={"因为": "because"},
    ),
    "因为": LearningConcept(
        concept="因为",
        meaning="because",
        contrast_with={"虽然": "although / even though"},
    ),
    "但是": LearningConcept(
        concept="但是",
        meaning="but / however",
        contrast_with={"所以": "therefore / so"},
    ),
    "所以": LearningConcept(
        concept="所以",
        meaning="therefore / so",
        contrast_with={"但是": "but / however"},
    ),
}


def get_concept(concept: str) -> LearningConcept | None:
    return CONCEPTS.get(concept)
