from app.learning.teaching import generate_teaching


def test_teaching_for_concept_explains_meaning_and_contrast():
    result = generate_teaching("虽然", None)

    assert result is not None
    assert "although / even though" in result.explanation
    assert "因为" not in result.explanation
    assert result.practice_question == "Which meaning best matches 虽然?"
    assert result.choices == ("although / even though", "because")


def test_teaching_addresses_known_misconception():
    result = generate_teaching(
        "虽然",
        "Confuses 虽然 (although / even though) with 因为 (because).",
    )

    assert result is not None
    assert "因为 means because" in result.explanation
    assert "despite" in result.explanation


def test_teaching_returns_none_for_unknown_concept():
    assert generate_teaching("未知", None) is None
