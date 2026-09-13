from dataclasses import dataclass


from app.learning.content import get_concept


@dataclass(frozen=True)
class TeachingResponse:
    explanation: str
    practice_question: str
    choices: tuple[str, ...]
    practice_correct_answer: str


TEACHING_CONTENT: dict[str, TeachingResponse] = {
    "additive-versioning": TeachingResponse(
        explanation=(
            "Additive API versioning means evolving an existing API by adding "
            "backward-compatible fields or capabilities instead of changing "
            "the meaning of fields that existing clients already use. "
            "For example, adding a new optional response field can ship in v1 "
            "because an older client can simply ignore it. Removing a field, "
            "renaming an endpoint, or changing the meaning of an existing "
            "response would be a breaking change and may require a new version."
        ),
        practice_question=(
            "Your v1 API already returns user_id and mastery. You need to add "
            "next_review_at for newer clients. What is the safest change?"
        ),
        choices=(
            "Add next_review_at as a new optional response field",
            "Remove mastery and replace it with next_review_at",
            "Rename /api/v1/learning/state to /api/v2/learning/state immediately",
            "Change the meaning of mastery so it contains the review date",
        ),
        practice_correct_answer=(
            "Add next_review_at as a new optional response field"
        ),
    ),
    "contract-first-design": TeachingResponse(
        explanation=(
            "Contract-first design makes the API boundary explicit before "
            "individual clients depend on implementation details. In this "
            "project, openapi.yaml describes the shared request and response "
            "shapes. The web client, mobile client, and FastAPI backend can "
            "then implement and validate against the same contract. This "
            "reduces accidental differences between clients and makes API "
            "changes visible before they become integration bugs."
        ),
        practice_question=(
            "The web client and mobile client are implemented by different "
            "developers. What is the strongest reason to define the OpenAPI "
            "contract first?"
        ),
        choices=(
            "Both clients can implement the same explicit API boundary",
            "The backend no longer needs tests",
            "OpenAPI makes network requests execute faster",
            "The clients can avoid having any TypeScript or Python types",
        ),
        practice_correct_answer=(
            "Both clients can implement the same explicit API boundary"
        ),
    ),
    "sse-vs-json-mode": TeachingResponse(
        explanation=(
            "SSE and normal JSON responses can represent the same logical "
            "application result while using different transports. The web "
            "client benefits from streaming because it can display model "
            "output incrementally. The mobile client in this project uses "
            "JSON mode because its runtime does not provide the same browser "
            "streaming primitives without additional compatibility work. "
            "The important design principle is to adapt the transport to the "
            "client while keeping the application-level contract coherent."
        ),
        practice_question=(
            "The web client needs incremental chat output, but the mobile "
            "client uses JSON mode. Which design best preserves the API "
            "architecture?"
        ),
        choices=(
            "Keep the logical response contract consistent while allowing different transports",
            "Create an unrelated response schema for every client",
            "Force mobile to emulate browser EventSource before it can use the API",
            "Remove streaming from the web client so every client behaves identically",
        ),
        practice_correct_answer=(
            "Keep the logical response contract consistent while allowing different transports"
        ),
    ),
    "provider-fallback-pattern": TeachingResponse(
        explanation=(
            "An external LLM provider is a dependency that can fail. A "
            "provider-fallback pattern prevents that failure from taking down "
            "the entire learning experience. If a provider is unavailable, "
            "misconfigured, rate-limited, or temporarily failing, the "
            "application can fall back to deterministic content or another "
            "provider. This is especially useful in a live demo because the "
            "core learning loop remains usable even when an external service "
            "has a problem."
        ),
        practice_question=(
            "Your AI provider becomes unavailable during a live hackathon "
            "demo. What behavior best protects the learning experience?"
        ),
        choices=(
            "Fall back to a deterministic explanation instead of crashing",
            "Show a blank screen until the provider returns",
            "Delete the learner's current mastery state",
            "Require the learner to restart the application",
        ),
        practice_correct_answer=(
            "Fall back to a deterministic explanation instead of crashing"
        ),
    ),
    "spaced-repetition-scheduling": TeachingResponse(
        explanation=(
            "Spaced repetition uses repeated retrieval over time rather than "
            "assuming that one correct answer proves durable learning. In this "
            "project, estimated mastery determines the next review interval. "
            "Lower mastery produces a sooner review, while stronger mastery "
            "allows a longer interval. The scheduler therefore turns a quiz "
            "result into a future learning action instead of ending the "
            "learning process when the question is answered."
        ),
        practice_question=(
            "A learner's mastery is still below the durable threshold after "
            "a quiz. What should the scheduler generally do?"
        ),
        choices=(
            "Schedule another review sooner",
            "Never test the concept again",
            "Assume one correct answer proves permanent mastery",
            "Increase the review interval regardless of mastery",
        ),
        practice_correct_answer=(
            "Schedule another review sooner"
        ),
    ),
}


def generate_teaching(
    concept: str,
    misconception: str | None,
) -> TeachingResponse | None:
    """Generate deterministic adaptive teaching for a known concept.

    The misconception is accepted as part of the teaching boundary so an
    LLM-backed implementation can later personalize the explanation around
    the learner's specific error.
    """
    learning_concept = get_concept(concept)

    if learning_concept is None:
        return None

    teaching = TEACHING_CONTENT.get(concept)

    if teaching is None:
        return None

    if misconception:
        explanation = (
            f"{teaching.explanation} "
            f"Your previous answer suggests a possible misconception: "
            f"{misconception}"
        )

        return TeachingResponse(
            explanation=explanation,
            practice_question=teaching.practice_question,
            choices=teaching.choices,
            practice_correct_answer=teaching.practice_correct_answer,
        )

    return teaching
