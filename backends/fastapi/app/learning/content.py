from dataclasses import dataclass


@dataclass(frozen=True)
class LearningConcept:
    concept: str
    title: str
    meaning: str
    why_it_matters: str
    key_point: str


CONCEPTS: dict[str, LearningConcept] = {
    "additive-versioning": LearningConcept(
        concept="additive-versioning",
        title="Additive API versioning",
        meaning=(
            "A compatible API can evolve by adding optional response "
            "fields without breaking existing clients."
        ),
        why_it_matters=(
            "Web and mobile clients may be deployed at different times. "
            "Removing or changing an existing field can break an older client."
        ),
        key_point=(
            "Add optional fields when possible; reserve a new API version "
            "for breaking changes."
        ),
    ),
    "contract-first-design": LearningConcept(
        concept="contract-first-design",
        title="Contract-first API design",
        meaning=(
            "The API contract is defined explicitly before clients and "
            "server implementations depend on it."
        ),
        why_it_matters=(
            "The web client, mobile client, and backend can independently "
            "implement the same boundary without relying on each other's code."
        ),
        key_point=(
            "The contract is the shared source of truth for the API boundary."
        ),
    ),
    "sse-vs-json-mode": LearningConcept(
        concept="sse-vs-json-mode",
        title="SSE versus JSON mode",
        meaning=(
            "Different clients can use different transport modes while "
            "preserving the same logical API response."
        ),
        why_it_matters=(
            "The web client can consume streaming SSE, while the mobile "
            "client may use a normal JSON response when streaming APIs are "
            "not available or practical."
        ),
        key_point=(
            "Client capabilities should influence transport choices without "
            "forcing different application-level message contracts."
        ),
    ),
    "provider-fallback-pattern": LearningConcept(
        concept="provider-fallback-pattern",
        title="Provider fallback",
        meaning=(
            "An application can fall back to a deterministic or alternate "
            "provider behavior when an external AI provider fails."
        ),
        why_it_matters=(
            "External model providers can be unavailable, slow, rate-limited, "
            "or misconfigured. A fallback keeps the application usable instead "
            "of turning a provider failure into a complete application failure."
        ),
        key_point=(
            "Treat an external LLM as a dependency that can fail, not as the "
            "only thing standing between the user and a working application."
        ),
    ),
    "spaced-repetition-scheduling": LearningConcept(
        concept="spaced-repetition-scheduling",
        title="Spaced repetition scheduling",
        meaning=(
            "Review timing is adjusted according to estimated mastery so "
            "weaker knowledge is reviewed sooner and stronger knowledge later."
        ),
        why_it_matters=(
            "Getting an answer correct once does not prove durable retention. "
            "Scheduling another retrieval attempt creates an opportunity to "
            "verify whether the knowledge survives over time."
        ),
        key_point=(
            "Mastery should influence when the learner is tested again."
        ),
    ),
}


def get_concept(concept: str) -> LearningConcept | None:
    return CONCEPTS.get(concept)
