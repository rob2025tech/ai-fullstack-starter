"""Configuration matrix tests for fastapi/app/config/settings.py.

These tests instantiate Settings with _env_file=None so that the CI
environment and any developer shell .env file never influence the results.
All secret values used here are deterministic placeholders; no real secrets
are referenced.
"""

import pytest
from pydantic import ValidationError

from app.config.settings import Settings

# ---------------------------------------------------------------------------
# Placeholder secret used wherever a valid non-blank secret is needed.
# Length >= 32 bytes satisfies any downstream minimum-length check.
# ---------------------------------------------------------------------------
_PLACEHOLDER_SECRET = "test-session-secret-minimum-32-bytes"


# ---------------------------------------------------------------------------
# Local mode — no secret required
# ---------------------------------------------------------------------------


def test_local_mode_no_secret_is_accepted() -> None:
    s = Settings(_env_file=None, deployment_mode="local", session_secret=None)
    assert s.deployment_mode == "local"
    assert s.session_secret is None


def test_local_mode_with_secret_is_accepted() -> None:
    s = Settings(_env_file=None, deployment_mode="local", session_secret=_PLACEHOLDER_SECRET)
    assert s.session_secret == _PLACEHOLDER_SECRET


def test_local_mode_requires_session_auth_returns_false() -> None:
    s = Settings(_env_file=None, deployment_mode="local", session_secret=None)
    assert s.requires_session_auth() is False


# ---------------------------------------------------------------------------
# shared-demo mode — secret is required
# ---------------------------------------------------------------------------


def test_shared_demo_without_secret_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret=None)


def test_shared_demo_blank_secret_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret="")


def test_shared_demo_whitespace_only_secret_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret="   ")


def test_shared_demo_with_placeholder_secret_is_accepted() -> None:
    s = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret=_PLACEHOLDER_SECRET,
    )
    assert s.deployment_mode == "shared-demo"
    assert s.session_secret == _PLACEHOLDER_SECRET


def test_shared_demo_requires_session_auth_returns_true() -> None:
    s = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret=_PLACEHOLDER_SECRET,
    )
    assert s.requires_session_auth() is True


# ---------------------------------------------------------------------------
# production mode — secret is required
# ---------------------------------------------------------------------------


def test_production_without_secret_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="production", session_secret=None)


def test_production_blank_secret_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="production", session_secret="")


def test_production_whitespace_only_secret_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="production", session_secret="   ")


def test_production_with_placeholder_secret_is_accepted() -> None:
    s = Settings(
        _env_file=None,
        deployment_mode="production",
        session_secret=_PLACEHOLDER_SECRET,
    )
    assert s.deployment_mode == "production"
    assert s.session_secret == _PLACEHOLDER_SECRET


def test_production_requires_session_auth_returns_true() -> None:
    s = Settings(
        _env_file=None,
        deployment_mode="production",
        session_secret=_PLACEHOLDER_SECRET,
    )
    assert s.requires_session_auth() is True


# ---------------------------------------------------------------------------
# Unknown deployment_mode — must fail validation
# ---------------------------------------------------------------------------


def test_unknown_deployment_mode_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="staging")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# session_ttl_seconds — must be a positive integer
# ---------------------------------------------------------------------------


def test_session_ttl_zero_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="local", session_ttl_seconds=0)


def test_session_ttl_negative_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="local", session_ttl_seconds=-1)


def test_session_ttl_positive_is_accepted() -> None:
    s = Settings(_env_file=None, deployment_mode="local", session_ttl_seconds=3600)
    assert s.session_ttl_seconds == 3600


# ---------------------------------------------------------------------------
# session_issuer — default value present
# ---------------------------------------------------------------------------


def test_session_issuer_default_is_set() -> None:
    s = Settings(_env_file=None, deployment_mode="local")
    assert s.session_issuer
    assert isinstance(s.session_issuer, str)


def test_session_issuer_can_be_overridden() -> None:
    s = Settings(_env_file=None, deployment_mode="local", session_issuer="my-service")
    assert s.session_issuer == "my-service"
