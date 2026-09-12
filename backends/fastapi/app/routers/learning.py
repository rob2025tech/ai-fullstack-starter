from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.errors import InvalidRequestError
from app.learning.quiz import evaluate_answer
from app.learning.quiz_content import get_quiz_question
from app.learning.service import LearningService
from app.models.error_models import ErrorResponse
from app.models.learning_models import (
    LearningAnswerRequest,
    LearningAnswerResponse,
    LearningQuizAnswerRequest,
    LearningQuizAnswerResponse,
    LearningQuizResponse,
    LearningStateResponse,
    TeachingResponse,
)

router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


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
    state = service.get_state(user_id, concept)

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
async def answer_learning_question(
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

    teaching = (
        TeachingResponse(
            explanation=result.teaching.explanation,
            practice_question=result.teaching.practice_question,
            choices=list(result.teaching.choices),
        )
        if result.teaching is not None
        else None
    )

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
        teaching=teaching,
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
        raise InvalidRequestError(
            f"Unknown quiz concept: {concept}",
        )

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
        raise InvalidRequestError(
            f"Unknown quiz concept: {request.concept}",
        )

    result = evaluate_answer(
        question,
        request.selected_answer,
    )

    service: LearningService = raw_request.app.state.learning_service

    state_before = service.get_state(
        request.user_id,
        request.concept,
    )

    mastery_before = state_before.mastery

    state = service.record_quiz_result(
        request.user_id,
        result,
        now=datetime.now(timezone.utc),
    )

    return LearningQuizAnswerResponse(
        user_id=state.user_id,
        concept=state.concept,
        is_correct=result.is_correct,
        mastery_before=mastery_before,
        mastery_after=state.mastery,
        attempts=state.attempts,
        correct_count=state.correct_count,
        next_review_at=state.next_review_at,
    )
