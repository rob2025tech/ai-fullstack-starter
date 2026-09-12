from app.learning.quiz import QuizQuestion, evaluate_answer


def test_correct_answer_is_evaluated_as_correct():
    question = QuizQuestion(
        concept="staged git diff",
        question="Which command shows changes staged for the next commit?",
        choices=("git diff", "git diff --cached", "git status", "git log"),
        correct_answer="git diff --cached",
        bloom_level="remember",
    )

    result = evaluate_answer(question, "git diff --cached")

    assert result.is_correct is True
    assert result.selected_answer == "git diff --cached"


def test_wrong_answer_is_evaluated_as_incorrect():
    question = QuizQuestion(
        concept="staged git diff",
        question="Which command shows changes staged for the next commit?",
        choices=("git diff", "git diff --cached", "git status", "git log"),
        correct_answer="git diff --cached",
        bloom_level="remember",
    )

    result = evaluate_answer(question, "git status")

    assert result.is_correct is False
    assert result.selected_answer == "git status"


def test_answer_evaluation_ignores_surrounding_whitespace_and_case():
    question = QuizQuestion(
        concept="staged git diff",
        question="Which command shows changes staged for the next commit?",
        choices=("git diff", "git diff --cached", "git status", "git log"),
        correct_answer="git diff --cached",
        bloom_level="remember",
    )

    result = evaluate_answer(question, "  GIT DIFF --CACHED  ")

    assert result.is_correct is True


def test_quiz_question_preserves_bloom_level():
    question = QuizQuestion(
        concept="staged git diff",
        question="Why inspect staged changes before committing?",
        choices=(
            "To review exactly what will be committed",
            "To create a new branch",
            "To delete untracked files",
            "To download dependencies",
        ),
        correct_answer="To review exactly what will be committed",
        bloom_level="understand",
    )

    assert question.bloom_level == "understand"
