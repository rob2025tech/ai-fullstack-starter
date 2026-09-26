"""Unit tests for the deterministic tool registry.

All tests use committed fake Pydantic models and async callables;
no filesystem mutation, external service, or LLM provider required.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.agent.tools.registry import (
    ToolDefinition,
    ToolInvocationError,
    ToolRegistry,
    ToolResult,
    ToolRisk,
)


# ---------------------------------------------------------------------------
# Fake tool models and callables (deterministic fixtures)
# ---------------------------------------------------------------------------


class TreeInput(BaseModel):
    path: str
    max_depth: int = 3


class TreeOutput(BaseModel):
    entries: list[str]
    total: int


class WriteInput(BaseModel):
    path: str
    content: str


class WriteOutput(BaseModel):
    bytes_written: int
    path: str


class BrokenOutput(BaseModel):
    required_field: str  # tool callable won't return this


async def _fake_tree(input: TreeInput) -> TreeOutput:
    return TreeOutput(entries=[f"{input.path}/file.py"], total=1)


async def _fake_write(input: WriteInput) -> WriteOutput:
    return WriteOutput(bytes_written=len(input.content), path=input.path)


async def _fake_always_raises(input: TreeInput) -> TreeOutput:
    raise RuntimeError("simulated tool crash")


async def _fake_broken_output(input: TreeInput) -> BrokenOutput:
    # Returns dict missing required_field — will fail output validation
    return BrokenOutput(required_field="ok")  # this is fine; separate fake below


async def _fake_bad_output_type(input: TreeInput) -> dict:  # type: ignore[return]
    return {"not_a_base_model": True}


TREE_TOOL = ToolDefinition(
    name="repo.tree",
    description="List repository entries at a given path",
    input_schema=TreeInput,
    output_schema=TreeOutput,
    callable=_fake_tree,
    risk=ToolRisk.read_only,
)

WRITE_TOOL = ToolDefinition(
    name="fs.write",
    description="Write content to a file path",
    input_schema=WriteInput,
    output_schema=WriteOutput,
    callable=_fake_write,
    risk=ToolRisk.mutating,
)

CRASHING_TOOL = ToolDefinition(
    name="tool.crash",
    description="Always raises an exception",
    input_schema=TreeInput,
    output_schema=TreeOutput,
    callable=_fake_always_raises,
    risk=ToolRisk.unsafe,
)


# ---------------------------------------------------------------------------
# Registration tests (AC-2)
# ---------------------------------------------------------------------------


def test_register_single_tool() -> None:
    registry = ToolRegistry()
    registry.register(TREE_TOOL)
    assert registry.get("repo.tree") is TREE_TOOL


def test_register_multiple_tools() -> None:
    registry = ToolRegistry()
    registry.register(TREE_TOOL)
    registry.register(WRITE_TOOL)
    assert len(registry.list_tools()) == 2


def test_duplicate_name_raises_before_replacing(monkeypatch) -> None:
    """AC-2: Duplicate registration raises ToolInvocationError without replacing."""
    registry = ToolRegistry()
    registry.register(TREE_TOOL)

    duplicate = ToolDefinition(
        name="repo.tree",  # same name, different description
        description="A different tree tool",
        input_schema=TreeInput,
        output_schema=TreeOutput,
        callable=_fake_tree,
        risk=ToolRisk.read_only,
    )
    with pytest.raises(ToolInvocationError) as exc_info:
        registry.register(duplicate)

    assert exc_info.value.tool_name == "repo.tree"
    # Original remains unchanged
    assert registry.get("repo.tree") is TREE_TOOL


def test_empty_name_raises() -> None:
    registry = ToolRegistry()
    empty_tool = ToolDefinition(
        name="",
        description="bad",
        input_schema=TreeInput,
        output_schema=TreeOutput,
        callable=_fake_tree,
        risk=ToolRisk.read_only,
    )
    with pytest.raises(ToolInvocationError):
        registry.register(empty_tool)


def test_whitespace_name_raises() -> None:
    registry = ToolRegistry()
    ws_tool = ToolDefinition(
        name="   ",
        description="bad",
        input_schema=TreeInput,
        output_schema=TreeOutput,
        callable=_fake_tree,
        risk=ToolRisk.read_only,
    )
    with pytest.raises(ToolInvocationError):
        registry.register(ws_tool)


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


def test_list_tools_empty_registry() -> None:
    assert ToolRegistry().list_tools() == []


def test_list_tools_preserves_insertion_order() -> None:
    registry = ToolRegistry()
    registry.register(TREE_TOOL)
    registry.register(WRITE_TOOL)
    names = [t.name for t in registry.list_tools()]
    assert names == ["repo.tree", "fs.write"]


def test_get_unknown_returns_none() -> None:
    registry = ToolRegistry()
    assert registry.get("no.such.tool") is None


# ---------------------------------------------------------------------------
# Invocation — success paths (AC-3)
# ---------------------------------------------------------------------------


async def test_invoke_routes_to_registered_tool() -> None:
    """AC-3: invoke('repo.tree', {...}) routes to the fake tool and returns ToolResult."""
    registry = ToolRegistry()
    registry.register(TREE_TOOL)

    result = await registry.invoke("repo.tree", {"path": "."})

    assert isinstance(result, ToolResult)
    assert result.tool_name == "repo.tree"
    assert result.risk == ToolRisk.read_only
    assert isinstance(result.output, TreeOutput)
    assert result.output.entries == ["./file.py"]
    assert result.output.total == 1


async def test_invoke_mutating_tool_returns_correct_risk() -> None:
    registry = ToolRegistry()
    registry.register(WRITE_TOOL)

    result = await registry.invoke("fs.write", {"path": "/tmp/x.py", "content": "hello"})

    assert result.risk == ToolRisk.mutating
    assert isinstance(result.output, WriteOutput)
    assert result.output.bytes_written == 5


async def test_invoke_passes_optional_fields_to_tool() -> None:
    registry = ToolRegistry()
    registry.register(TREE_TOOL)

    result = await registry.invoke("repo.tree", {"path": "src", "max_depth": 5})
    assert result.output.entries == ["src/file.py"]


# ---------------------------------------------------------------------------
# Invocation — unknown tool (AC-4)
# ---------------------------------------------------------------------------


async def test_invoke_unknown_tool_raises_with_name() -> None:
    """AC-4: Unknown tool raises ToolInvocationError containing the tool name."""
    registry = ToolRegistry()
    registry.register(TREE_TOOL)

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("no.such.tool", {"path": "."})

    err = exc_info.value
    assert err.tool_name == "no.such.tool"
    assert "no.such.tool" in err.reason


async def test_invoke_unknown_tool_does_not_call_registered_tools(monkeypatch) -> None:
    """AC-4: Registered tool callable is never invoked for an unknown name."""
    called = []

    async def _recording_tree(inp: TreeInput) -> TreeOutput:
        called.append(inp)
        return TreeOutput(entries=[], total=0)

    registry = ToolRegistry()
    recording = ToolDefinition(
        name="repo.tree",
        description="recording",
        input_schema=TreeInput,
        output_schema=TreeOutput,
        callable=_recording_tree,
        risk=ToolRisk.read_only,
    )
    registry.register(recording)

    with pytest.raises(ToolInvocationError):
        await registry.invoke("other.tool", {"path": "."})

    assert called == [], "Registered tool was called despite unknown name"


# ---------------------------------------------------------------------------
# Invocation — invalid input (AC-5)
# ---------------------------------------------------------------------------


async def test_invoke_missing_required_input_raises_before_callable() -> None:
    """AC-5: Missing required field raises ToolInvocationError before the callable runs."""
    called = []

    async def _spy(inp: TreeInput) -> TreeOutput:
        called.append(inp)
        return TreeOutput(entries=[], total=0)

    registry = ToolRegistry()
    spy = ToolDefinition(
        name="repo.tree",
        description="spy",
        input_schema=TreeInput,
        output_schema=TreeOutput,
        callable=_spy,
        risk=ToolRisk.read_only,
    )
    registry.register(spy)

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("repo.tree", {})  # missing required 'path'

    assert called == [], "Callable was invoked despite invalid input"
    err = exc_info.value
    assert err.tool_name == "repo.tree"
    assert err.details is not None
    assert "validation_errors" in err.details


async def test_invoke_wrong_type_input_raises() -> None:
    registry = ToolRegistry()
    registry.register(TREE_TOOL)

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("repo.tree", {"path": 123})  # int where str expected

    assert exc_info.value.tool_name == "repo.tree"


# ---------------------------------------------------------------------------
# Invocation — callable exception wrapping
# ---------------------------------------------------------------------------


async def test_invoke_wraps_callable_exception() -> None:
    registry = ToolRegistry()
    registry.register(CRASHING_TOOL)

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("tool.crash", {"path": "."})

    err = exc_info.value
    assert err.tool_name == "tool.crash"
    assert "simulated tool crash" in err.reason
    assert err.details is not None
    assert err.details["exception_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# ToolRisk values
# ---------------------------------------------------------------------------


def test_tool_risk_values_exist() -> None:
    assert ToolRisk.read_only == "read_only"
    assert ToolRisk.mutating == "mutating"
    assert ToolRisk.unsafe == "unsafe"


# ---------------------------------------------------------------------------
# ToolDefinition immutability
# ---------------------------------------------------------------------------


def test_tool_definition_is_frozen() -> None:
    with pytest.raises((TypeError, AttributeError)):
        TREE_TOOL.name = "modified"  # type: ignore[misc]
