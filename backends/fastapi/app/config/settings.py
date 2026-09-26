from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DeploymentMode = Literal["local", "shared-demo", "production"]


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
    session_ttl_seconds: int = 8 * 60 * 60

    # Provider call policy — conservative local defaults
    provider_timeout_seconds: float = 30.0
    provider_max_retries: int = 2
    provider_max_payload_bytes: int = 65_536  # 64 KiB

    @model_validator(mode="after")
    def _validate_production_config(self) -> "Settings":
        """Fail closed at construction time for production deployments."""
        if self.deployment_mode != "production":
            return self

        errors: list[str] = []

        if not (self.session_secret and self.session_secret.strip()):
            errors.append(
                "SESSION_SECRET must be set to a non-empty value for production deployment"
            )

        has_wildcard = not self.cors_origins or any(
            origin.strip() in ("*", "") or "://*" in origin
            for origin in self.cors_origins
        )
        if has_wildcard:
            errors.append(
                "CORS_ORIGINS must be set to one or more explicit non-wildcard origins"
                " for production deployment"
            )

        if self.llm_provider == "openai" and not (
            self.openai_api_key and self.openai_api_key.strip()
        ):
            errors.append(
                "OPENAI_API_KEY must be set when LLM_PROVIDER=openai in production deployment"
            )

        if errors:
            raise ValueError("; ".join(errors))

        return self


settings = Settings()
