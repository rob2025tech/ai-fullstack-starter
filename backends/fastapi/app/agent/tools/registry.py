"""Deterministic tool registry for the agent execution loop.

Design principles
-----------------
- No FastAPI, app.state, or LLMProvider imports; purely a domain module.
- Exact-name dictionary routing; no fuzzy matching or substring routing.
- Input validated via the registered Pydantic model before the callable runs.
- Tool callable exceptions are wrapped into ToolInvocationError so the loop
  can record a structured tool-error event without exposing tracebacks.
- ToolRisk labels enable approval gating in a later story without changing
  the registry interface.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Type

from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class ToolInvocationError(Exception):
    """Raised for all registry-level failures.

    Attributes
    ----------
    tool_name:
        The name of the tool that failed (may be ``None`` for lookup errors).
    reason:
        Human-readable description of the failure.
    details:
        Optional validation or contextual detail dictionary.
    """

    def __init__(
        self,
        reason: str,
        *,
        tool_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.reason = reason
        self.tool_name = tool_name
        self.details = details
        super().__init__(reason)

    def __repr__(self) -> str:
        return (
            f"ToolInvocationError(tool_name={self.tool_name!r}, reason={self.reason!r})"
        )


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------


class ToolRisk(str, enum.Enum):
    """Risk level assigned to a tool.

    read_only:
        Safe to call without human oversight; does not modify any state.
    mutating:
        Modifies local workspace state (files, config); warrants audit.
    unsafe:
        Executes code, network calls, or system commands; requires approval.
    """

    read_only = "read_only"
    mutating = "mutating"
    unsafe = "unsafe"


# ---------------------------------------------------------------------------
# Tool definition and result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolDefinition:
    """Immutable specification for a registered tool.

    Parameters
    ----------
    name:
        Unique identifier used for exact-name routing (e.g. ``repo.tree``).
    description:
        Human-readable description of what the tool does.
    input_schema:
        Pydantic BaseModel subclass that validates the raw JSON payload.
    output_schema:
        Pydantic BaseModel subclass that validates the tool's return value.
    callable:
        Async function ``async def fn(input: InputModel) -> OutputModel``.
    risk:
        Risk classification for the tool.
    """

    name: str
    description: str
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    callable: Callable[..., Awaitable[BaseModel]]
    risk: ToolRisk = ToolRisk.read_only


@dataclass
class ToolResult:
    """Structured result returned by ToolRegistry.invoke.

    Attributes
    ----------
    tool_name:
        The name of the tool that was invoked.
    risk:
        Risk classification of the invoked tool.
    output:
        Validated output model instance.
    metadata:
        Optional extra context (elapsed time, source, etc.).
    """

    tool_name: str
    risk: ToolRisk
    output: BaseModel
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Deterministic registry for agent tools.

    Usage
    -----
    ::

        registry = ToolRegistry()
        registry.register(my_tool_def)
        result = await registry.invoke("repo.tree", {"path": "."})
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition.

        Raises ``ToolInvocationError`` if the name is empty or already taken.
        """
        if not tool.name or not tool.name.strip():
            raise ToolInvocationError(
                "Tool name must be a non-empty string",
                tool_name=tool.name or "",
            )
        if tool.name in self._tools:
            raise ToolInvocationError(
                f"Tool {tool.name!r} is already registered; duplicate names are not allowed",
                tool_name=tool.name,
            )
        self._tools[tool.name] = tool

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tools in insertion order."""
        return list(self._tools.values())

    def get(self, name: str) -> ToolDefinition | None:
        """Return the ToolDefinition for *name*, or ``None`` if not registered."""
        return self._tools.get(name)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    async def invoke(self, tool_name: str, payload: dict[str, Any]) -> ToolResult:
        """Validate *payload* and invoke the named tool.

        Steps
        -----
        1. Exact-name lookup; raises ``ToolInvocationError`` for unknown tools.
        2. Input validation via the registered ``input_schema``; raises
           ``ToolInvocationError`` with Pydantic error details on failure.
        3. Callable invocation; wraps any exception into ``ToolInvocationError``.
        4. Output validation via the registered ``output_schema``; wraps
           validation errors.
        5. Returns a ``ToolResult``.

        Parameters
        ----------
        tool_name:
            Exact registered name of the tool.
        payload:
            Raw JSON-compatible dictionary that will be validated by the tool's
            ``input_schema``.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolInvocationError(
                f"Unknown tool: {tool_name!r}. Registered tools: "
                + str(list(self._tools)),
                tool_name=tool_name,
            )

        # Validate input
        try:
            validated_input = tool.input_schema.model_validate(payload)
        except ValidationError as exc:
            raise ToolInvocationError(
                f"Invalid input for tool {tool_name!r}",
                tool_name=tool_name,
                details={"validation_errors": exc.errors()},
            ) from exc

        # Invoke callable
        try:
            raw_output = await tool.callable(validated_input)
        except ToolInvocationError:
            raise
        except Exception as exc:
            raise ToolInvocationError(
                f"Tool {tool_name!r} raised an unexpected error: {exc}",
                tool_name=tool_name,
                details={"exception_type": type(exc).__name__, "message": str(exc)},
            ) from exc

        # Validate output
        try:
            validated_output = tool.output_schema.model_validate(
                raw_output.model_dump() if isinstance(raw_output, BaseModel) else raw_output
            )
        except ValidationError as exc:
            raise ToolInvocationError(
                f"Tool {tool_name!r} returned an invalid output",
                tool_name=tool_name,
                details={"validation_errors": exc.errors()},
            ) from exc

        return ToolResult(
            tool_name=tool_name,
            risk=tool.risk,
            output=validated_output,
        )
