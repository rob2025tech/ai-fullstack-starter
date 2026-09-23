from typing import Annotated, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DeploymentMode = Literal["local", "shared-demo", "production"]

_PROTECTED_MODES: frozenset[str] = frozenset({"shared-demo", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    contract_version: str = "1.0.0"

    deployment_mode: DeploymentMode = "local"
    session_secret: str | None = None
    session_issuer: str = "ai-fullstack-starter"
    session_ttl_seconds: Annotated[int, Field(gt=0)] = 8 * 60 * 60

    @model_validator(mode="after")
    def _require_secret_in_protected_modes(self) -> "Settings":
        if self.deployment_mode in _PROTECTED_MODES:
            if not self.session_secret or not self.session_secret.strip():
                raise ValueError(
                    f"session_secret must be set and non-blank when "
                    f"deployment_mode is '{self.deployment_mode}'"
                )
        return self

    def requires_session_auth(self) -> bool:
        """Return True when the deployment mode requires session authentication."""
        return self.deployment_mode in _PROTECTED_MODES


settings = Settings()
