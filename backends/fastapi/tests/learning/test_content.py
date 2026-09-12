from app.learning.content import get_concept


def test_although_concept_has_because_as_contrast():
    result = get_concept("虽然")

    assert result is not None
    assert result.meaning == "although / even though"
    assert result.contrast_with == {"因为": "because"}


def test_because_concept_has_although_as_contrast():
    result = get_concept("因为")

    assert result is not None
    assert result.meaning == "because"
    assert result.contrast_with == {"虽然": "although / even though"}


def test_but_concept_has_therefore_as_contrast():
    result = get_concept("但是")

    assert result is not None
    assert result.meaning == "but / however"
    assert result.contrast_with == {"所以": "therefore / so"}


def test_therefore_concept_has_but_as_contrast():
    result = get_concept("所以")

    assert result is not None
    assert result.meaning == "therefore / so"
    assert result.contrast_with == {"但是": "but / however"}


def test_unknown_concept_returns_none():
    assert get_concept("未知") is None
