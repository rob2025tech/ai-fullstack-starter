from app.learning.content import get_concept


def test_additive_versioning_concept_exists():
    result = get_concept("additive-versioning")

    assert result is not None
    assert result.title == "Additive API versioning"
    assert "adding optional response fields" in result.meaning
    assert "break" in result.why_it_matters.lower()
    assert "Add optional fields" in result.key_point


def test_contract_first_design_concept_exists():
    result = get_concept("contract-first-design")

    assert result is not None
    assert result.title == "Contract-first API design"
    assert "API contract" in result.meaning
    assert "shared source of truth" in result.key_point


def test_provider_fallback_concept_exists():
    result = get_concept("provider-fallback-pattern")

    assert result is not None
    assert result.title == "Provider fallback"
    assert "fall back" in result.meaning
    assert "external LLM" in result.key_point


def test_spaced_repetition_concept_exists():
    result = get_concept("spaced-repetition-scheduling")

    assert result is not None
    assert result.title == "Spaced repetition scheduling"
    assert "mastery" in result.meaning
    assert "tested again" in result.key_point


def test_unknown_concept_returns_none():
    assert get_concept("unknown-concept") is None
