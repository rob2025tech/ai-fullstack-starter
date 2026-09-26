"""Unit tests for ProviderPolicy.

All tests use deterministic fake providers — no network calls to
OpenAI or any real backend are made.

Fake provider fixtures
----------------------
``FakeSuccessProvider``      — always returns ``"ok"``
``FakeUnavailableProvider``  — always raises ``ProviderUnavailableError``
``FakeProviderErrorProvider``— always raises ``ProviderError``
``FakeCountingProvider``     — counts calls; raises ``ProviderUnavailableError``
                               until ``succeed_after`` attempts, then returns ``"ok"``
``FakeSlowProvider``         — sleeps indefinitely (asyncio.Event wait) to trigger timeout
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.errors import InvalidRequestError, ProviderError, ProviderUnavailableError
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig


# ---------------------------------------------------------------------------
# Deterministic fake providers (no network)
# ---------------------------------------------------------------------------


class FakeSuccessProvider(LLMProvider):
    """Always succeeds immediately."""

    async def generate(self, prompt: str) -> str:
        return "ok"


class FakeUnavailableProvider(LLMProvider):
    """Always raises ProviderUnavailableError."""

    async def generate(self, prompt: str) -> str:
        raise ProviderUnavailableError("simulated unavailability")


class FakeProviderErrorProvider(LLMProvider):
    """Always raises ProviderError (non-transient)."""

    async def generate(self, prompt: str) -> str:
        raise ProviderError("simulated non-transient provider error")


class FakeCountingProvider(LLMProvider):
    """Counts generate calls; raises ProviderUnavailableError until ``succeed_after`` calls."""

    def __init__(self, succeed_after: int = 0) -> None:
        """
        succeed_after: succeed on call number ``succeed_after + 1`` and beyond.
        succeed_after=0 means succeed on the very first call.
        succeed_after=-1 means always fail.
        """
        self.call_count = 0
        self._succeed_after = succeed_after

    async def generate(self, prompt: str) -> str:
        self.call_count += 1
        if self._succeed_after >= 0 and self.call_count > self._succeed_after:
            raise ProviderUnavailableError(f"fail on call {self.call_count}")
        return "ok"


class FakeAlwaysFailCountingProvider(LLMProvider):
    """Counts generate calls; always raises ProviderUnavailableError."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, prompt: str) -> str:
        self.call_count += 1
        raise ProviderUnavailableError(f"fail on call {self.call_count}")


class FakeSlowProvider(LLMProvider):
    """Hangs indefinitely to exercise timeout logic."""

    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(3600)  # will be cancelled by wait_for
        return "never"


class FakeUnexpectedExceptionProvider(LLMProvider):
    """Raises an arbitrary non-BackendError exception."""

    async def generate(self, prompt: str) -> str:
        raise RuntimeError("unexpected crash")


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------


def _policy(
    provider: LLMProvider,
    *,
    timeout_seconds: float = 5.0,
    max_retries: int = 0,
    max_payload_bytes: int = 256,
) -> ProviderPolicy:
    return ProviderPolicy(
        provider,
        ProviderPolicyConfig(
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_payload_bytes=max_payload_bytes,
        ),
    )


# ---------------------------------------------------------------------------
# AC-1: Timeout → ProviderUnavailableError
# ---------------------------------------------------------------------------


async def test_timeout_raises_provider_unavailable():
    """ProviderPolicy.generate raises ProviderUnavailableError when the provider hangs."""
    policy = _policy(FakeSlowProvider(), timeout_seconds=0.05, max_retries=0)
    with pytest.raises(ProviderUnavailableError, match="timed out"):
        await policy.generate("ping")


async def test_timeout_message_includes_duration():
    policy = _policy(FakeSlowProvider(), timeout_seconds=0.05, max_retries=0)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await policy.generate("hi")
    assert "0.05" in exc_info.value.message


# ---------------------------------------------------------------------------
# AC-2: Payload limit → InvalidRequestError (before provider call)
# ---------------------------------------------------------------------------


async def test_payload_limit_raises_invalid_request():
    """Oversized prompt is rejected before calling the provider."""
    provider = FakeSuccessProvider()
    policy = _policy(provider, max_payload_bytes=10)
    oversized = "a" * 11  # 11 bytes > limit of 10
    with pytest.raises(InvalidRequestError, match="11 bytes"):
        await policy.generate(oversized)


async def test_payload_limit_exact_size_is_accepted():
    """Prompt of exactly max_payload_bytes is accepted."""
    policy = _policy(FakeSuccessProvider(), max_payload_bytes=10)
    result = await policy.generate("a" * 10)
    assert result == "ok"


async def test_payload_limit_one_byte_over_is_rejected():
    """Prompt one byte over max_payload_bytes is rejected."""
    policy = _policy(FakeSuccessProvider(), max_payload_bytes=10)
    with pytest.raises(InvalidRequestError):
        await policy.generate("a" * 11)


async def test_payload_limit_check_is_utf8_byte_count():
    """Byte count is based on UTF-8 encoding, not character count."""
    policy = _policy(FakeSuccessProvider(), max_payload_bytes=3)
    # "é" is 2 UTF-8 bytes; 2 chars × 2 bytes = 4 bytes > 3-byte limit
    with pytest.raises(InvalidRequestError):
        await policy.generate("éé")


# ---------------------------------------------------------------------------
# AC-3: Retry behaviour
# ---------------------------------------------------------------------------


async def test_unavailable_retried_exactly_max_retries_times():
    """ProviderUnavailableError causes exactly max_retries additional attempts."""
    max_retries = 2
    provider = FakeAlwaysFailCountingProvider()
    policy = _policy(provider, max_retries=max_retries)
    with pytest.raises(ProviderUnavailableError):
        await policy.generate("hi")
    # 1 initial attempt + max_retries retries = max_retries + 1 total
    assert provider.call_count == max_retries + 1


async def test_provider_error_not_retried():
    """ProviderError (non-transient) is raised immediately without retry."""
    provider = FakeCountingProvider(succeed_after=-1)

    class _NonTransientProvider(LLMProvider):
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, prompt: str) -> str:
            self.calls += 1
            raise ProviderError("non-transient")

    p = _NonTransientProvider()
    policy = _policy(p, max_retries=3)
    with pytest.raises(ProviderError):
        await policy.generate("hi")
    # Must have been called exactly once — no retries for ProviderError
    assert p.calls == 1


async def test_zero_retries_means_single_attempt():
    """max_retries=0 means exactly one attempt total."""
    provider = FakeAlwaysFailCountingProvider()
    policy = _policy(provider, max_retries=0)
    with pytest.raises(ProviderUnavailableError):
        await policy.generate("hi")
    assert provider.call_count == 1


async def test_successful_after_first_retry():
    """Success on the second attempt is returned after one retry."""

    class _FailOnceThenSucceed(LLMProvider):
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise ProviderUnavailableError("first fail")
            return "recovered"

    provider = _FailOnceThenSucceed()
    policy = _policy(provider, max_retries=2)
    result = await policy.generate("hi")
    assert result == "recovered"
    assert provider.calls == 2


async def test_invalid_request_not_retried():
    """InvalidRequestError (payload limit) is never retried."""

    class _RaisesInvalidRequest(LLMProvider):
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, prompt: str) -> str:
            self.calls += 1
            raise InvalidRequestError("caller error")

    p = _RaisesInvalidRequest()
    policy = _policy(p, max_retries=3)
    with pytest.raises(InvalidRequestError):
        await policy.generate("hi")
    assert p.calls == 1


# ---------------------------------------------------------------------------
# Successful path
# ---------------------------------------------------------------------------


async def test_successful_generate_returns_content():
    policy = _policy(FakeSuccessProvider())
    result = await policy.generate("hello")
    assert result == "ok"


async def test_mock_provider_passes_through_policy():
    """The real MockLLMProvider works end-to-end through ProviderPolicy."""
    policy = ProviderPolicy(
        MockLLMProvider(),
        ProviderPolicyConfig(timeout_seconds=5.0, max_retries=0, max_payload_bytes=65536),
    )
    result = await policy.generate("ping")
    assert result == "echo: ping"


# ---------------------------------------------------------------------------
# Unexpected exception wrapping
# ---------------------------------------------------------------------------


async def test_unexpected_exception_wrapped_as_provider_error():
    """Arbitrary non-BackendError exceptions are wrapped as ProviderError."""
    policy = _policy(FakeUnexpectedExceptionProvider())
    with pytest.raises(ProviderError, match="RuntimeError"):
        await policy.generate("hi")


# ---------------------------------------------------------------------------
# ProviderPolicyConfig validation
# ---------------------------------------------------------------------------


def test_config_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="timeout_seconds"):
        ProviderPolicyConfig(timeout_seconds=0)


def test_config_rejects_negative_timeout():
    with pytest.raises(ValueError, match="timeout_seconds"):
        ProviderPolicyConfig(timeout_seconds=-1.0)


def test_config_rejects_negative_retries():
    with pytest.raises(ValueError, match="max_retries"):
        ProviderPolicyConfig(max_retries=-1)


def test_config_rejects_non_positive_payload_bytes():
    with pytest.raises(ValueError, match="max_payload_bytes"):
        ProviderPolicyConfig(max_payload_bytes=0)


def test_config_valid_defaults():
    config = ProviderPolicyConfig()
    assert config.timeout_seconds > 0
    assert config.max_retries >= 0
    assert config.max_payload_bytes > 0


# ---------------------------------------------------------------------------
# ProviderPolicy.provider accessor
# ---------------------------------------------------------------------------


def test_policy_exposes_underlying_provider():
    provider = FakeSuccessProvider()
    policy = _policy(provider)
    assert policy.provider is provider
