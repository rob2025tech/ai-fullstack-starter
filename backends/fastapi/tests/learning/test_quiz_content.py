from app.learning.quiz import evaluate_answer
from app.learning.quiz_content import QUIZ_QUESTIONS, get_quiz_question


def test_every_question_correct_answer_is_one_of_its_own_choices():
    for concept, question in QUIZ_QUESTIONS.items():
        assert question.correct_answer in question.choices, concept
        assert question.concept == concept


def test_questions_span_at_least_four_distinct_bloom_levels():
    levels = {question.bloom_level for question in QUIZ_QUESTIONS.values()}

    # "Bloom's taxonomy in practice" means real range, not five copies of
    # the same recall-level question with different words.
    assert len(levels) >= 4


def test_get_quiz_question_returns_none_for_unknown_concept():
    assert get_quiz_question("not-a-real-concept") is None


def test_get_quiz_question_returns_the_matching_question():
    question = get_quiz_question("spaced-repetition-scheduling")

    assert question is not None
    assert question.bloom_level == "evaluate"


def test_selecting_the_correct_choice_evaluates_as_correct():
    question = get_quiz_question("additive-versioning")
    assert question is not None

    result = evaluate_answer(question, question.correct_answer)

    assert result.is_correct is True


def test_selecting_a_distractor_evaluates_as_incorrect():
    question = get_quiz_question("additive-versioning")
    assert question is not None

    distractor = next(
        choice for choice in question.choices if choice != question.correct_answer
    )
    result = evaluate_answer(question, distractor)

    assert result.is_correct is False
