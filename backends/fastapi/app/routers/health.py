from fastapi import APIRouter

from app.config.settings import settings
from app.models.response_models import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.contract_version)
