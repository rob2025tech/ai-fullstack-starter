from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.errors import InvalidRequestError

from app.learning.quiz import (
    PracticeQuestion,
    evaluate_answer,
    evaluate_practice_answer,
)
from app.learning.quiz_content import (
    get_quiz_question,
    get_retest_question,
)
from app.learning.service import LearningService
from app.models.error_models import ErrorResponse
from app.models.learning_models import (
    LearningAnswerRequest,
    LearningAnswerResponse,
    LearningPracticeAnswerRequest,
    LearningPracticeAnswerResponse,
    LearningQuizAnswerRequest,
    LearningQuizAnswerResponse,
    LearningQuizResponse,
    LearningRetestAnswerRequest,
    LearningRetestAnswerResponse,
    LearningRetestResponse,
    LearningStateResponse,
)


router = APIRouter(
    prefix="/api/v1/learning",
    tags=["learning"],
)


def _unknown_concept_error(concept: str) -> InvalidRequestError:
    return InvalidRequestError(f"Unknown quiz concept: {concept}")


@router.get(
    "/state",
    response_model=LearningStateResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_learning_state(
    user_id: str,
    concept: str,
    raw_request: Request,
) -> LearningStateResponse:
    service: LearningService = raw_request.app.state.learning_service

    state = service.get_state(
        user_id,
        concept,
    )

    return LearningStateResponse(
        user_id=state.user_id,
        concept=state.concept,
        mastery=state.mastery,
        attempts=state.attempts,
        correct_count=state.correct_count,
        last_misconception=state.last_misconception,
        next_review_at=state.next_review_at,
    )


@router.post(
    "/answer",
    response_model=LearningAnswerResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def answer_learning(
    request: LearningAnswerRequest,
    raw_request: Request,
) -> LearningAnswerResponse:
    service: LearningService = raw_request.app.state.learning_service

    result = await service.answer(
        request.user_id,
        request.concept,
        request.answer,
        now=datetime.now(timezone.utc),
    )

    teaching = result.teaching

    return LearningAnswerResponse(
        user_id=result.state.user_id,
        concept=result.state.concept,
        is_correct=result.is_correct,
        misconception=result.misconception,
        mastery_before=result.mastery_before,
        mastery_after=result.mastery_after,
        attempts=result.state.attempts,
        correct_count=result.state.correct_count,
        next_review_at=result.state.next_review_at,
        teaching=(
            None
            if teaching is None
            else {
                "explanation": teaching.explanation,
                "practice_question": teaching.practice_question,
                "choices": list(teaching.choices),
            }
        ),
    )


@router.get(
    "/quiz",
    response_model=LearningQuizResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_learning_quiz(
    concept: str,
) -> LearningQuizResponse:
    question = get_quiz_question(concept)

    if question is None:
        raise _unknown_concept_error(concept)

    return LearningQuizResponse(
        concept=question.concept,
        question=question.question,
        choices=list(question.choices),
        bloom_level=question.bloom_level,
    )


@router.post(
    "/quiz/answer",
    response_model=LearningQuizAnswerResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def answer_learning_quiz(
    request: LearningQuizAnswerRequest,
    raw_request: Request,
) -> LearningQuizAnswerResponse:
    question = get_quiz_question(request.concept)

    if question is None:
        raise _unknown_concept_error(request.concept)

    result = evaluate_answer(
        question,
        request.selected_answer,
    )

    service: LearningService = raw_request.app.state.learning_service

    adaptive_result = await service.answer_quiz(
        request.user_id,
        result,
        now=datetime.now(timezone.utc),
    )

    practice_question = adaptive_result.practice_question

    return LearningQuizAnswerResponse(
        user_id=adaptive_result.state.user_id,
        concept=adaptive_result.state.concept,
        is_correct=adaptive_result.is_correct,
        selected_answer=adaptive_result.selected_answer,
        correct_answer=adaptive_result.correct_answer,
        mastery_before=adaptive_result.mastery_before,
        mastery_after=adaptive_result.mastery_after,
        attempts=adaptive_result.state.attempts,
        correct_count=adaptive_result.state.correct_count,
        next_review_at=adaptive_result.state.next_review_at,
        explanation=adaptive_result.explanation,
        misconception=adaptive_result.misconception,
        practice_question=(
            None
            if practice_question is None
            else practice_question.question
        ),
        practice_choices=(
            None
            if practice_question is None
            else list(practice_question.choices)
        ),
    )


@router.post(
    "/quiz/practice",
    response_model=LearningPracticeAnswerResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def answer_learning_practice(
    request: LearningPracticeAnswerRequest,
    raw_request: Request,
) -> LearningPracticeAnswerResponse:
    service: LearningService = raw_request.app.state.learning_service

    teaching = await service.teaching_service.generate(
        request.concept,
        None,
    )

    if teaching is None:
        raise _unknown_concept_error(request.concept)

    practice_question = PracticeQuestion(
        concept=request.concept,
        question=teaching.practice_question,
        choices=teaching.choices,
        correct_answer=teaching.practice_correct_answer,
    )

    result = evaluate_practice_answer(
        practice_question,
        request.selected_answer,
    )

    adaptive_result = await service.answer_practice(
        request.user_id,
        result,
        now=datetime.now(timezone.utc),
    )

    return LearningPracticeAnswerResponse(
        user_id=adaptive_result.state.user_id,
        concept=adaptive_result.state.concept,
        is_correct=adaptive_result.is_correct,
        selected_answer=adaptive_result.selected_answer,
        correct_answer=adaptive_result.correct_answer,
        mastery_before=adaptive_result.mastery_before,
        mastery_after=adaptive_result.mastery_after,
        attempts=adaptive_result.state.attempts,
        correct_count=adaptive_result.state.correct_count,
        next_review_at=adaptive_result.state.next_review_at,
        explanation=adaptive_result.explanation,
    )


@router.get(
    "/quiz/retest",
    response_model=LearningRetestResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_learning_retest(
    concept: str,
    raw_request: Request,
) -> LearningRetestResponse:
    service: LearningService = raw_request.app.state.learning_service

    question = service.get_retest_question(concept)

    if question is None:
        raise _unknown_concept_error(concept)

    return LearningRetestResponse(
        concept=question.concept,
        question=question.question,
        choices=list(question.choices),
        bloom_level=question.bloom_level,
    )


@router.post(
    "/quiz/retest",
    response_model=LearningRetestAnswerResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def answer_learning_retest(
    request: LearningRetestAnswerRequest,
    raw_request: Request,
) -> LearningRetestAnswerResponse:
    service: LearningService = raw_request.app.state.learning_service

    question = service.get_retest_question(request.concept)

    if question is None:
        raise _unknown_concept_error(request.concept)

    result = evaluate_answer(
        question,
        request.selected_answer,
    )

    adaptive_result = await service.answer_retest(
        request.user_id,
        result,
        now=datetime.now(timezone.utc),
    )

    return LearningRetestAnswerResponse(
        user_id=adaptive_result.state.user_id,
        concept=adaptive_result.state.concept,
        is_correct=adaptive_result.is_correct,
        selected_answer=adaptive_result.selected_answer,
        correct_answer=adaptive_result.correct_answer,
        mastery_before=adaptive_result.mastery_before,
        mastery_after=adaptive_result.mastery_after,
        attempts=adaptive_result.state.attempts,
        correct_count=adaptive_result.state.correct_count,
        next_review_at=adaptive_result.state.next_review_at,
        misconception=adaptive_result.state.last_misconception,
    )
