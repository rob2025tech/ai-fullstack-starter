from typing import Literal

from pydantic import BaseModel

ErrorCode = Literal[
    "invalid_request",
    "unauthorized",
    "rate_limited",
    "internal_error",
    "provider_error",
    "provider_unavailable",
]


class Error(BaseModel):
    code: ErrorCode
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: Error
