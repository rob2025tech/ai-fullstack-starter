import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.core.errors import BackendError
from app.models.error_models import Error, ErrorResponse
from app.models.request_models import ChatRequest
from app.models.response_models import ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def create_chat(request: ChatRequest, raw_request: Request) -> Response:
    service: ChatService = raw_request.app.state.chat_service
    if not request.stream:
        return await service.complete(request)
    return StreamingResponse(_event_stream(service, request), media_type="text/event-stream")


async def _event_stream(service: ChatService, request: ChatRequest) -> AsyncIterator[bytes]:
    try:
        async for name, payload in service.stream_events(request):
            yield f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode()
    except BackendError as exc:
        yield _error_event(exc.code, exc.message)
    except Exception:  # noqa: BLE001 — contract requires a terminal event even on unexpected failures
        yield _error_event("internal_error", "unexpected server error")


def _error_event(code: str, message: str) -> bytes:
    body = ErrorResponse(error=Error(code=code, message=message))
    return f"event: error\ndata: {body.model_dump_json()}\n\n".encode()
