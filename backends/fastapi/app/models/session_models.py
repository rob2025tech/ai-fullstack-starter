from typing import Literal

from pydantic import BaseModel


class SessionBootstrapRequest(BaseModel):
    transport: Literal["cookie", "bearer"] = "cookie"


class SessionBootstrapResponse(BaseModel):
    user_id: str
    expires_at: str
    token_type: Literal["cookie", "bearer"]
    access_token: str | None = None
