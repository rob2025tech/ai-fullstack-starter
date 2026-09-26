"""Unit and integration tests for workspace mutation tools (file.write).

All tests use tmp_path fixtures; no network or external processes required.
asyncio_mode=auto (pyproject.toml) lets async tests run without explicit marks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.tools.mutation import FileWriteInput, FileWriteOutput, FileWriteTool
from app.agent.tools.registry import ToolInvocationError, ToolRegistry, ToolRisk
from app.agent.tools.workspace import WorkspacePolicy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "existing.txt").write_text("original content")
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text("print('hello')\n")
    return ws


@pytest.fixture()
def policy(workspace: Path) -> WorkspacePolicy:
    return WorkspacePolicy(root=workspace)


# ---------------------------------------------------------------------------
# Successful create
# ---------------------------------------------------------------------------


async def test_file_write_creates_new_file(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    result: FileWriteOutput = await tool.callable(
        FileWriteInput(path="new_file.txt", content="hello world")
    )
    assert result.action == "created"
    assert result.path == "new_file.txt"
    assert result.size_bytes == len("hello world".encode("utf-8"))
    assert (workspace / "new_file.txt").read_text() == "hello world"


async def test_file_write_nested_path_with_existing_parent(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    result: FileWriteOutput = await tool.callable(
        FileWriteInput(path="src/utils.py", content="# utils")
    )
    assert result.action == "created"
    assert result.path == "src/utils.py"
    assert (workspace / "src" / "utils.py").read_text() == "# utils"


async def test_file_write_creates_parents_when_flag_set(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    result: FileWriteOutput = await tool.callable(
        FileWriteInput(path="deep/nested/dir/file.py", content="# code", create_parents=True)
    )
    assert result.action == "created"
    assert (workspace / "deep" / "nested" / "dir" / "file.py").exists()


# ---------------------------------------------------------------------------
# Overwrite protection
# ---------------------------------------------------------------------------


async def test_file_write_refuses_overwrite_by_default(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileWriteInput(path="existing.txt", content="new content"))
    assert exc_info.value.details["reason"] == "overwrite_refused"
    # Original content must be intact
    assert (workspace / "existing.txt").read_text() == "original content"


async def test_file_write_overwrite_succeeds_when_flag_set(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    result: FileWriteOutput = await tool.callable(
        FileWriteInput(path="existing.txt", content="updated content", overwrite=True)
    )
    assert result.action == "overwritten"
    assert (workspace / "existing.txt").read_text() == "updated content"


# ---------------------------------------------------------------------------
# Missing parent
# ---------------------------------------------------------------------------


async def test_file_write_missing_parent_rejected_by_default(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(
            FileWriteInput(path="nonexistent_dir/file.txt", content="x")
        )
    assert exc_info.value.details["reason"] == "missing_parent"


# ---------------------------------------------------------------------------
# Path security
# ---------------------------------------------------------------------------


async def test_file_write_traversal_rejected(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileWriteInput(path="../outside.txt", content="x"))
    assert exc_info.value.details["reason"] == "path_outside_workspace"
    assert exc_info.value.details["requested"] == "../outside.txt"


async def test_file_write_absolute_outside_rejected(
    workspace: Path, tmp_path: Path
) -> None:
    outside = str(tmp_path / "outside.txt")
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileWriteInput(path=outside, content="x"))
    assert exc_info.value.details["reason"] == "path_outside_workspace"


async def test_file_write_symlink_escape_rejected(
    workspace: Path, tmp_path: Path
) -> None:
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    link = workspace / "link_to_outside"
    link.symlink_to(outside_dir)

    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileWriteInput(path="link_to_outside/evil.txt", content="x"))
    assert exc_info.value.details["reason"] in ("symlink_escape", "path_outside_workspace")


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------


def test_file_write_tool_is_mutating(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileWriteTool(policy)
    assert tool.risk == ToolRisk.mutating


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------


async def test_registry_file_write_creates_file(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(FileWriteTool(policy))

    result = await registry.invoke("file.write", {"path": "registry_test.txt", "content": "ok"})
    assert result.tool_name == "file.write"
    assert result.risk == ToolRisk.mutating
    assert isinstance(result.output, FileWriteOutput)
    assert (workspace / "registry_test.txt").read_text() == "ok"


async def test_registry_file_write_overwrite_refused(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(FileWriteTool(policy))

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke(
            "file.write", {"path": "existing.txt", "content": "new"}
        )
    assert exc_info.value.details["reason"] == "overwrite_refused"


async def test_registry_file_write_traversal_rejected(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(FileWriteTool(policy))

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke(
            "file.write", {"path": "../outside.txt", "content": "x"}
        )
    assert exc_info.value.details["reason"] == "path_outside_workspace"
