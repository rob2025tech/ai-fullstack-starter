from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.models.error_models import ErrorResponse
from app.models.learning_models import (
    LearningAnswerRequest,
    LearningAnswerResponse,
    LearningStateResponse,
)
from app.learning.service import LearningService

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

    result = service.answer(
        request.user_id,
        request.concept,
        request.answer,
        now=datetime.now(timezone.utc),
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
    )
