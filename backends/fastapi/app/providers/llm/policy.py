"""Provider call policy wrapper.

``ProviderPolicy`` is the observable reliability boundary around every
``LLMProvider.generate`` call.  It enforces:

1. **Payload limit** — reject oversized prompts before the network is used.
2. **Async timeout** — wrap the provider call with ``asyncio.wait_for`` so
   hung upstream connections are terminated deterministically.
3. **Bounded retries** — retry ``ProviderUnavailableError`` (transient) up to
   ``max_retries`` times; never retry ``ProviderError`` (non-transient) or
   ``InvalidRequestError`` (caller error).
4. **Exception normalisation** — unexpected exceptions from any provider
   implementation are wrapped as ``ProviderError`` so the error-envelope
   contract is preserved.

The streaming path (``LLMProvider.stream``) is intentionally excluded from
this story; ``ProviderPolicy.provider`` exposes the wrapped provider for
callers that need direct stream access.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.core.errors import BackendError, InvalidRequestError, ProviderError, ProviderUnavailableError
from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderPolicyConfig:
    """Configuration values for ``ProviderPolicy``.

    Attributes
    ----------
    timeout_seconds:
        Maximum wall-clock seconds to wait for a single ``generate`` attempt.
        Must be strictly positive.
    max_retries:
        Number of *additional* attempts after the first failure for
        ``ProviderUnavailableError`` and timeouts.  ``0`` means one attempt
        only (no retries).
    max_payload_bytes:
        Maximum UTF-8 encoded byte length of the prompt accepted before
        calling the provider.  Prompts at exactly this size are accepted;
        one byte over is rejected with ``InvalidRequestError``.
    """

    timeout_seconds: float = 30.0
    max_retries: int = 2
    max_payload_bytes: int = 65_536  # 64 KiB

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError(
                f"ProviderPolicyConfig.timeout_seconds must be positive, got {self.timeout_seconds}"
            )
        if self.max_retries < 0:
            raise ValueError(
                f"ProviderPolicyConfig.max_retries must be >= 0, got {self.max_retries}"
            )
        if self.max_payload_bytes <= 0:
            raise ValueError(
                f"ProviderPolicyConfig.max_payload_bytes must be positive, got {self.max_payload_bytes}"
            )


class ProviderPolicy:
    """Reliability boundary around a single ``LLMProvider`` for generate operations.

    Parameters
    ----------
    provider:
        The underlying ``LLMProvider`` implementation.
    config:
        Policy configuration; defaults to ``ProviderPolicyConfig()`` when omitted.

    Usage
    -----
    .. code-block:: python

        policy = ProviderPolicy(
            provider,
            ProviderPolicyConfig(timeout_seconds=15, max_retries=1, max_payload_bytes=32768),
        )
        response_text = await policy.generate(prompt)

        # Streaming bypasses the policy; access the raw provider directly:
        async for chunk in policy.provider.stream(prompt):
            ...
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: ProviderPolicyConfig | None = None,
    ) -> None:
        self._provider = provider
        self._config = config if config is not None else ProviderPolicyConfig()

    @property
    def provider(self) -> LLMProvider:
        """The wrapped provider (e.g. for streaming calls that bypass policy)."""
        return self._provider

    @property
    def config(self) -> ProviderPolicyConfig:
        """The active policy configuration."""
        return self._config

    async def generate(self, prompt: str) -> str:
        """Generate a response for *prompt* subject to the configured policy.

        Steps
        -----
        1. Reject oversized prompts before any provider call.
        2. Call the provider inside ``asyncio.wait_for`` with ``timeout_seconds``.
        3. On timeout or ``ProviderUnavailableError``, retry up to ``max_retries``
           additional times; raise ``ProviderUnavailableError`` after all attempts.
        4. ``ProviderError`` and other ``BackendError`` subclasses propagate without
           retry so the error-envelope code is preserved.
        5. Unexpected bare exceptions are wrapped as ``ProviderError``.

        Raises
        ------
        InvalidRequestError
            Prompt exceeds ``max_payload_bytes``.
        ProviderUnavailableError
            All attempts timed out or raised ``ProviderUnavailableError``.
        ProviderError
            Provider returned a non-transient error (never retried).
        """
        # --- 1. Payload limit check (before any network I/O) ---
        prompt_bytes = len(prompt.encode("utf-8"))
        if prompt_bytes > self._config.max_payload_bytes:
            raise InvalidRequestError(
                f"Prompt too large: {prompt_bytes} bytes exceeds the "
                f"{self._config.max_payload_bytes}-byte limit."
            )

        # --- 2-5. Attempt + bounded retry loop ---
        total_attempts = self._config.max_retries + 1
        last_unavailable: ProviderUnavailableError | None = None

        for attempt in range(total_attempts):
            if attempt > 0:
                logger.debug(
                    "ProviderPolicy retry %d/%d after transient failure",
                    attempt,
                    self._config.max_retries,
                )
            try:
                return await asyncio.wait_for(
                    self._provider.generate(prompt),
                    timeout=self._config.timeout_seconds,
                )

            except asyncio.TimeoutError:
                last_unavailable = ProviderUnavailableError(
                    f"Provider timed out after {self._config.timeout_seconds}s."
                )
                logger.warning(
                    "ProviderPolicy: attempt %d timed out after %.1fs",
                    attempt + 1,
                    self._config.timeout_seconds,
                )
                # Retry if budget remains
                if attempt < total_attempts - 1:
                    continue
                raise last_unavailable

            except ProviderUnavailableError as exc:
                last_unavailable = exc
                logger.warning(
                    "ProviderPolicy: attempt %d got ProviderUnavailableError: %s",
                    attempt + 1,
                    exc.message,
                )
                if attempt < total_attempts - 1:
                    continue
                raise

            except ProviderError:
                # Non-transient; do not retry.
                raise

            except BackendError:
                # Any other typed backend error (e.g. InvalidRequestError from provider) —
                # do not retry, preserve the original type and code.
                raise

            except Exception as exc:
                # Unexpected: wrap to keep the contract error codes stable.
                raise ProviderError(
                    f"Unexpected provider failure: {type(exc).__name__}: {exc}"
                ) from exc

        # Unreachable; the loop always returns or raises.
        assert last_unavailable is not None  # nosec
        raise last_unavailable
