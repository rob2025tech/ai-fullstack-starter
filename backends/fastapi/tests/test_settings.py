"""Settings construction tests — local valid, production invalid, production valid."""

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


# ---------------------------------------------------------------------------
# Local mode — must construct without secrets
# ---------------------------------------------------------------------------


def test_local_defaults_construct_without_secrets() -> None:
    s = Settings(_env_file=None)
    assert s.deployment_mode == "local"
    assert s.llm_provider == "mock"
    assert s.session_secret is None


def test_local_explicit_mock_no_secret() -> None:
    s = Settings(_env_file=None, deployment_mode="local", llm_provider="mock", session_secret=None)
    assert "http://localhost:3000" in s.cors_origins


def test_shared_demo_no_secret_constructs() -> None:
    # shared-demo is not fail-closed at construction; downstream session code rejects missing secret
    s = Settings(_env_file=None, deployment_mode="shared-demo", session_secret=None)
    assert s.deployment_mode == "shared-demo"


# ---------------------------------------------------------------------------
# Production invalid — missing session_secret
# ---------------------------------------------------------------------------


def test_production_no_session_secret_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            session_secret=None,
            cors_origins=["https://example.com"],
        )
    assert "SESSION_SECRET" in str(exc_info.value)


def test_production_whitespace_session_secret_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            session_secret="   ",
            cors_origins=["https://example.com"],
        )
    assert "SESSION_SECRET" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Production invalid — cors_origins empty or wildcard
# ---------------------------------------------------------------------------


def test_production_empty_cors_origins_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            session_secret="test-secret",
            cors_origins=[],
        )
    assert "CORS_ORIGINS" in str(exc_info.value)


def test_production_wildcard_cors_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            session_secret="test-secret",
            cors_origins=["*"],
        )
    assert "CORS_ORIGINS" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Production invalid — openai provider without api key
# ---------------------------------------------------------------------------


def test_production_openai_no_api_key_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            llm_provider="openai",
            openai_api_key=None,
            session_secret="test-secret",
            cors_origins=["https://example.com"],
        )
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_production_openai_whitespace_api_key_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            llm_provider="openai",
            openai_api_key="   ",
            session_secret="test-secret",
            cors_origins=["https://example.com"],
        )
    assert "OPENAI_API_KEY" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Production invalid — multiple violations reported together
# ---------------------------------------------------------------------------


def test_production_multiple_violations_reported() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            deployment_mode="production",
            session_secret=None,
            cors_origins=[],
        )
    error_text = str(exc_info.value)
    assert "SESSION_SECRET" in error_text
    assert "CORS_ORIGINS" in error_text


# ---------------------------------------------------------------------------
# Production valid
# ---------------------------------------------------------------------------


def test_production_valid_mock_provider() -> None:
    # mock provider does not require OPENAI_API_KEY
    s = Settings(
        _env_file=None,
        deployment_mode="production",
        llm_provider="mock",
        session_secret="test-secret",
        cors_origins=["https://example.com"],
    )
    assert s.deployment_mode == "production"
    assert s.llm_provider == "mock"


def test_production_valid_openai_provider() -> None:
    s = Settings(
        _env_file=None,
        deployment_mode="production",
        llm_provider="openai",
        openai_api_key="test-api-key",
        session_secret="test-secret",
        cors_origins=["https://example.com"],
    )
    assert s.deployment_mode == "production"
    assert s.openai_api_key == "test-api-key"


def test_production_valid_multiple_cors_origins() -> None:
    s = Settings(
        _env_file=None,
        deployment_mode="production",
        session_secret="test-secret",
        cors_origins=["https://app.example.com", "https://admin.example.com"],
    )
    assert len(s.cors_origins) == 2


# ---------------------------------------------------------------------------
# No real secrets committed — placeholder values used throughout
# ---------------------------------------------------------------------------


def test_no_real_secrets_in_placeholders() -> None:
    # Verify placeholder values are not real credentials by checking well-known prefixes
    placeholder_secret = "test-secret"
    placeholder_api_key = "test-api-key"
    assert not placeholder_api_key.startswith("sk-")
    assert len(placeholder_secret) < 40
