"""Quiz content drawn from this repo's own architecture decisions.

Rather than quizzing an external subject, these questions test whether
the builder actually retained *why* this codebase is shaped the way it
is - contract-first design, additive versioning, the SSE/JSON split,
the provider fallback pattern, and the spaced-repetition scheduler
itself. Each concept is pinned to the Bloom's-taxonomy level it's
actually testing, spanning remember through evaluate.

Note: true Bloom's "create" needs a free-response answer (design
something new), which a multiple-choice evaluator can't grade. That's
left as a follow-up (a free-text reflection prompt) rather than faked
here with a multiple-choice question dressed up as "create".
"""

from app.learning.quiz import QuizQuestion

QUIZ_QUESTIONS: dict[str, QuizQuestion] = {
    "additive-versioning": QuizQuestion(
        concept="additive-versioning",
        question="Per ADR-002, which change can ship inside v1 without a new /api/v2?",
        choices=(
            "Adding a new optional field to a response",
            "Removing a field a client currently depends on",
            "Renaming an existing endpoint",
            "Changing what a 200 status code means",
        ),
        correct_answer="Adding a new optional field to a response",
        bloom_level="remember",
    ),
    "contract-first-design": QuizQuestion(
        concept="contract-first-design",
        question="Why is openapi.yaml hand-written instead of generated from the FastAPI code?",
        choices=(
            ("So every client language implements the exact same boundary "
             "without ever reading each other's code"),
            "Because YAML parses faster than Python at runtime",
            "Because FastAPI is incapable of generating an OpenAPI spec",
            "To avoid writing any Pydantic models",
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
            "Why does the mobile client call /api/v1/chat with stream:false "
            "instead of using SSE like the web client?"
        ),
        choices=(
            ("React Native has no EventSource and no streaming fetch body, "
             "so JSON mode returns the same message shape without a polyfill"),
            "The backend only supports SSE for browsers, not mobile devices",
            "JSON mode is a completely different, incompatible contract",
            "Mobile apps are not allowed to call the /chat endpoint",
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
            "Why does TeachingService catch ProviderError/ProviderUnavailableError "
            "instead of letting them raise?"
        ),
        choices=(
            ("So a flaky LLM provider degrades to a deterministic explanation "
             "instead of crashing a live demo"),
            ("Because the deterministic fallback text is more pedagogically "
             "accurate than a real model"),
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
            "Mastery jumps from 0.32 to 0.62 right after a wrong answer gets "
            "corrected. Why does review_interval() still schedule a short "
            "3-day review instead of a long one?"
        ),
        choices=(
            ("Mastery is still below the durable threshold, so the gain is "
             "fragile and needs re-testing soon"),
            "The scheduler always assigns 3 days regardless of mastery",
            ("A big mastery jump means the concept is now fully learned and "
             "needs no further review"),
            "3 days is simply the maximum interval the scheduler supports",
        ),
        correct_answer=(
            "Mastery is still below the durable threshold, so the gain is "
            "fragile and needs re-testing soon"
        ),
        bloom_level="evaluate",
    ),
}


def get_quiz_question(concept: str) -> QuizQuestion | None:
    return QUIZ_QUESTIONS.get(concept)
