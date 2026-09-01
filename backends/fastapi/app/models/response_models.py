from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    id: str
    role: Literal["assistant"]
    content: str
    finish_reason: Literal["stop", "length"]


class Usage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class ChatResponse(BaseModel):
    message: ChatMessage
    usage: Usage | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str | None = None
