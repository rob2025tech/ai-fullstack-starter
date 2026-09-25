from typing import Literal

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


settings = Settings()
