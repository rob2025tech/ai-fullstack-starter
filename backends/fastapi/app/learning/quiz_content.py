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


QUIZ_QUESTIONS: dict[str, QuizQuestion] = {
    "additive-versioning": QuizQuestion(
        concept="additive-versioning",
        question=(
            "Which change is backward-compatible with existing clients?"
        ),
        choices=(
            "Adding a new optional field to a response",
            "Removing an existing response field",
            "Renaming an existing endpoint",
            "Changing the meaning of an existing field",
        ),
        correct_answer="Adding a new optional field to a response",
        bloom_level="remember",
    ),
    "contract-first-design": QuizQuestion(
        concept="contract-first-design",
        question=(
            "Why define an OpenAPI contract before independently implementing "
            "the web client, mobile client, and backend?"
        ),
        choices=(
            "So every client language implements the exact same boundary "
            "without ever reading each other's code",
            "So the backend no longer needs integration tests",
            "So network requests execute faster",
            "So clients no longer need their own types",
        ),
        correct_answer=(
            "So every client language implements the exact same boundary "
            "without ever reading each other's code"
        ),
        bloom_level="understand",
    ),
    "sse-vs-json-mode": QuizQuestion(
        concept="sse-vs-json-mode",
        question=(
            "Why can this project use streaming for the web client but JSON "
            "mode for React Native while keeping the same application-level "
            "response contract?"
        ),
        choices=(
            "React Native has no EventSource and no streaming fetch body, "
            "so JSON mode returns the same message shape without a polyfill",
            "React Native cannot make HTTP requests",
            "SSE and JSON represent completely different application results",
            "The web client cannot consume JSON responses",
        ),
        correct_answer=(
            "React Native has no EventSource and no streaming fetch body, "
            "so JSON mode returns the same message shape without a polyfill"
        ),
        bloom_level="apply",
    ),
    "provider-fallback-pattern": QuizQuestion(
        concept="provider-fallback-pattern",
        question=(
            "Why does TeachingService catch ProviderError/"
            "ProviderUnavailableError instead of letting them raise?"
        ),
        choices=(
            "So a flaky LLM provider degrades to a deterministic explanation "
            "instead of crashing a live demo",
            "Because the deterministic fallback text is more pedagogically "
            "accurate than a real model",
            "To hide provider bugs so they never show up in tests",
            "Because FastAPI requires every exception to be caught inside services",
        ),
        correct_answer=(
            "So a flaky LLM provider degrades to a deterministic explanation "
            "instead of crashing a live demo"
        ),
        bloom_level="analyze",
    ),
    "spaced-repetition-scheduling": QuizQuestion(
        concept="spaced-repetition-scheduling",
        question=(
            "A learner's mastery is still below the durable threshold. "
            "What should the scheduler generally do?"
        ),
        choices=(
            "Schedule another review sooner",
            "Never test the concept again",
            "Assume one correct answer proves permanent mastery",
            "Increase the review interval regardless of mastery",
        ),
        correct_answer="Schedule another review sooner",
        bloom_level="evaluate",
    ),
}


RETEST_QUESTIONS: dict[str, QuizQuestion] = {
    "additive-versioning": QuizQuestion(
        concept="additive-versioning",
        question=(
            "A new mobile client needs a new optional field while older "
            "clients still use the existing API. Which approach best avoids "
            "a breaking change?"
        ),
        choices=(
            "Add the new field without removing or changing existing fields",
            "Replace the existing fields with the new field",
            "Rename the existing endpoint for every client",
            "Change the meaning of an existing field",
        ),
        correct_answer=(
            "Add the new field without removing or changing existing fields"
        ),
        bloom_level="apply",
    ),
    "contract-first-design": QuizQuestion(
        concept="contract-first-design",
        question=(
            "The web and mobile teams are implementing clients independently. "
            "What artifact should they use to agree on request and response "
            "shapes before integration?"
        ),
        choices=(
            "The shared OpenAPI contract",
            "The backend's private implementation details",
            "A screenshot of the web application",
            "A database query copied from the backend",
        ),
        correct_answer="The shared OpenAPI contract",
        bloom_level="apply",
    ),
    "sse-vs-json-mode": QuizQuestion(
        concept="sse-vs-json-mode",
        question=(
            "A browser client needs incremental output, while a mobile "
            "runtime uses ordinary JSON. What should remain consistent "
            "between the two implementations?"
        ),
        choices=(
            "The logical application-level response contract",
            "The exact browser streaming primitive",
            "The mobile runtime's networking implementation",
            "The internal component tree of each client",
        ),
        correct_answer="The logical application-level response contract",
        bloom_level="analyze",
    ),
    "provider-fallback-pattern": QuizQuestion(
        concept="provider-fallback-pattern",
        question=(
            "During a live demo, the external model provider becomes "
            "unavailable while a learner is being taught. Which behavior "
            "best preserves the learning experience?"
        ),
        choices=(
            "Use deterministic teaching content as a fallback",
            "Discard the learner's current learning state",
            "Block the application until the provider recovers",
            "Restart the learner's session",
        ),
        correct_answer="Use deterministic teaching content as a fallback",
        bloom_level="evaluate",
    ),
    "spaced-repetition-scheduling": QuizQuestion(
        concept="spaced-repetition-scheduling",
        question=(
            "A learner demonstrates weak mastery of a concept after "
            "retrieval practice. Which scheduling decision is most "
            "consistent with the retention goal?"
        ),
        choices=(
            "Give the concept a shorter review interval",
            "Give the concept the longest possible review interval",
            "Remove the concept from future reviews",
            "Treat the weak result as proof of durable mastery",
        ),
        correct_answer="Give the concept a shorter review interval",
        bloom_level="evaluate",
    ),
}


def get_quiz_question(concept: str) -> QuizQuestion | None:
    return QUIZ_QUESTIONS.get(concept)


def get_retest_question(concept: str) -> QuizQuestion | None:
    return RETEST_QUESTIONS.get(concept)
