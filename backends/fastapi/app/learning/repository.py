from dataclasses import dataclass
from datetime import datetime


@dataclass
class LearningState:
    user_id: str
    concept: str
    mastery: float = 0.32
    attempts: int = 0
    correct_count: int = 0
    last_misconception: str | None = None
    next_review_at: datetime | None = None


class InMemoryLearningRepository:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], LearningState] = {}

    def get_or_create(self, user_id: str, concept: str) -> LearningState:
        key = (user_id, concept)

        if key not in self._states:
            self._states[key] = LearningState(
                user_id=user_id,
                concept=concept,
            )

        return self._states[key]

    def save(self, state: LearningState) -> None:
        self._states[(state.user_id, state.concept)] = state
