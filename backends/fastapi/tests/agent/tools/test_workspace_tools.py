"""Unit and integration tests for workspace inspection tools.

Fixtures build isolated workspaces under pytest's tmp_path; no host filesystem
paths escape into assertions.  All tests use asyncio_mode=auto (configured in
pyproject.toml) so async tests run without explicit marks.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from app.agent.tools.registry import ToolInvocationError, ToolRegistry, ToolRisk
from app.agent.tools.workspace import (
    FileReadInput,
    FileReadOutput,
    FileReadTool,
    RepositoryTreeInput,
    RepositoryTreeOutput,
    RepositoryTreeTool,
    WorkspacePolicy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Workspace with nested directories, a Python file, JSON, and a README."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "README.md").write_text("# Hello\n")
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text("print('hello')\n")
    (ws / "src" / "utils.py").write_text("def helper(): pass\n")
    (ws / "data").mkdir()
    (ws / "data" / "sample.json").write_text('{"key": "value"}\n')
    return ws


@pytest.fixture()
def policy(workspace: Path) -> WorkspacePolicy:
    return WorkspacePolicy(root=workspace)


@pytest.fixture()
def tree_tool(policy: WorkspacePolicy) -> object:
    return RepositoryTreeTool(policy)


@pytest.fixture()
def read_tool(policy: WorkspacePolicy) -> object:
    return FileReadTool(policy)


# ---------------------------------------------------------------------------
# WorkspacePolicy.resolve_safe
# ---------------------------------------------------------------------------


def test_resolve_safe_dot_returns_root(policy: WorkspacePolicy) -> None:
    assert policy.resolve_safe(".") == policy.root


def test_resolve_safe_empty_returns_root(policy: WorkspacePolicy) -> None:
    assert policy.resolve_safe("") == policy.root


def test_resolve_safe_relative_inside(policy: WorkspacePolicy, workspace: Path) -> None:
    result = policy.resolve_safe("src/main.py")
    assert result == (workspace / "src" / "main.py").resolve()


def test_resolve_safe_absolute_inside(policy: WorkspacePolicy, workspace: Path) -> None:
    abs_path = str((workspace / "README.md").resolve())
    result = policy.resolve_safe(abs_path)
    assert result == (workspace / "README.md").resolve()


def test_resolve_safe_traversal_rejected(policy: WorkspacePolicy) -> None:
    with pytest.raises(ToolInvocationError) as exc_info:
        policy.resolve_safe("../outside.txt")
    assert exc_info.value.details["reason"] == "path_outside_workspace"
    assert exc_info.value.details["requested"] == "../outside.txt"


def test_resolve_safe_absolute_outside_rejected(
    policy: WorkspacePolicy, tmp_path: Path
) -> None:
    outside = str(tmp_path / "outside.txt")
    with pytest.raises(ToolInvocationError) as exc_info:
        policy.resolve_safe(outside)
    assert exc_info.value.details["reason"] == "path_outside_workspace"


def test_resolve_safe_symlink_escape_rejected(
    policy: WorkspacePolicy, workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret content")
    link = workspace / "evil_link"
    link.symlink_to(outside)

    with pytest.raises(ToolInvocationError) as exc_info:
        policy.resolve_safe("evil_link")
    assert exc_info.value.details["reason"] == "symlink_escape"


# ---------------------------------------------------------------------------
# RepositoryTreeTool — direct invocation
# ---------------------------------------------------------------------------


async def test_tree_returns_relative_paths(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = RepositoryTreeTool(policy)
    result: RepositoryTreeOutput = await tool.callable(RepositoryTreeInput(path="."))

    assert result.truncated is False
    # All entries must be relative POSIX paths (no leading slash)
    for entry in result.entries:
        assert not entry.startswith("/"), f"absolute path leaked: {entry}"

    # Expected files present
    assert "README.md" in result.entries
    assert "src/main.py" in result.entries
    assert "src/utils.py" in result.entries
    assert "data/sample.json" in result.entries


async def test_tree_nested_dirs_included(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = RepositoryTreeTool(policy)
    result: RepositoryTreeOutput = await tool.callable(RepositoryTreeInput(path="."))

    # Directory entries themselves appear
    assert "src" in result.entries
    assert "data" in result.entries


async def test_tree_root_relative_for_subdirectory(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = RepositoryTreeTool(policy)
    result: RepositoryTreeOutput = await tool.callable(RepositoryTreeInput(path="src"))

    assert result.root == "src"
    # Entries under src are relative to the workspace root, not to src
    assert "src/main.py" in result.entries
    assert "src/utils.py" in result.entries


async def test_tree_root_dot_for_workspace_root(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = RepositoryTreeTool(policy)
    result: RepositoryTreeOutput = await tool.callable(RepositoryTreeInput(path="."))
    assert result.root == "."


async def test_tree_truncates_at_max_entries(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    for i in range(5):
        (ws / f"file_{i}.txt").write_text("x")

    policy = WorkspacePolicy(root=ws, max_tree_entries=3)
    tool = RepositoryTreeTool(policy)
    result: RepositoryTreeOutput = await tool.callable(RepositoryTreeInput(path="."))

    assert result.truncated is True
    assert len(result.entries) == 3


async def test_tree_not_truncated_when_within_limit(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace, max_tree_entries=1000)
    tool = RepositoryTreeTool(policy)
    result: RepositoryTreeOutput = await tool.callable(RepositoryTreeInput(path="."))
    assert result.truncated is False


async def test_tree_path_traversal_rejected(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = RepositoryTreeTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(RepositoryTreeInput(path="../outside"))
    assert exc_info.value.details["reason"] == "path_outside_workspace"


# ---------------------------------------------------------------------------
# FileReadTool — direct invocation
# ---------------------------------------------------------------------------


async def test_file_read_returns_content(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileReadTool(policy)
    result: FileReadOutput = await tool.callable(FileReadInput(path="README.md"))

    assert result.content == "# Hello\n"
    assert result.size_bytes > 0
    assert result.encoding == "utf-8"
    assert result.path == "README.md"
    # Returned path must not be absolute
    assert not result.path.startswith("/")


async def test_file_read_nested_path(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileReadTool(policy)
    result: FileReadOutput = await tool.callable(FileReadInput(path="src/main.py"))
    assert "print" in result.content
    assert result.path == "src/main.py"


async def test_file_read_traversal_rejected(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileReadTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileReadInput(path="../outside.txt"))
    assert exc_info.value.details["reason"] == "path_outside_workspace"
    assert exc_info.value.details["requested"] == "../outside.txt"


async def test_file_read_absolute_outside_rejected(
    workspace: Path, tmp_path: Path
) -> None:
    outside = str(tmp_path / "outside.txt")
    policy = WorkspacePolicy(root=workspace)
    tool = FileReadTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileReadInput(path=outside))
    assert exc_info.value.details["reason"] == "path_outside_workspace"


async def test_file_read_symlink_escape_rejected(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret content")
    link = workspace / "evil_link"
    link.symlink_to(outside)

    policy = WorkspacePolicy(root=workspace)
    tool = FileReadTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileReadInput(path="evil_link"))
    assert exc_info.value.details["reason"] == "symlink_escape"


async def test_file_read_oversized_rejected(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    limit = 512
    big_file = ws / "big.bin"
    big_file.write_bytes(b"x" * (limit + 1))

    policy = WorkspacePolicy(root=ws, max_read_bytes=limit)
    tool = FileReadTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileReadInput(path="big.bin"))

    details = exc_info.value.details
    assert details["reason"] == "file_too_large"
    assert details["max_read_bytes"] == limit
    assert details["size_bytes"] > limit


async def test_file_read_directory_rejected(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    tool = FileReadTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileReadInput(path="src"))
    assert exc_info.value.details["reason"] == "not_a_file"


async def test_file_read_non_utf8_rejected(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    binary_file = ws / "image.bin"
    # Write bytes that are not valid UTF-8
    binary_file.write_bytes(bytes([0xFF, 0xFE, 0x00, 0xD8, 0x01]))

    policy = WorkspacePolicy(root=ws)
    tool = FileReadTool(policy)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(FileReadInput(path="image.bin"))
    assert exc_info.value.details["reason"] == "not_utf8"


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------


async def test_registry_tree_tool_routes_by_exact_name(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(RepositoryTreeTool(policy))

    result = await registry.invoke("repo.tree", {"path": "."})
    assert result.tool_name == "repo.tree"
    assert result.risk == ToolRisk.read_only
    assert isinstance(result.output, RepositoryTreeOutput)
    assert "README.md" in result.output.entries


async def test_registry_file_read_tool_routes_by_exact_name(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(FileReadTool(policy))

    result = await registry.invoke("file.read", {"path": "README.md"})
    assert result.tool_name == "file.read"
    assert result.risk == ToolRisk.read_only
    assert isinstance(result.output, FileReadOutput)
    assert result.output.content == "# Hello\n"


async def test_registry_rejects_unknown_tool_name(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(RepositoryTreeTool(policy))
    registry.register(FileReadTool(policy))

    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("repo.TREE", {"path": "."})
    # Exact-name routing: 'repo.TREE' != 'repo.tree'
    assert "repo.TREE" in exc_info.value.reason


async def test_registry_both_tools_registered(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(RepositoryTreeTool(policy))
    registry.register(FileReadTool(policy))

    names = {t.name for t in registry.list_tools()}
    assert names == {"repo.tree", "file.read"}


async def test_registry_tree_invalid_input_raises(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(RepositoryTreeTool(policy))

    # Missing required fields is fine since path has a default, but extra
    # validation errors should surface cleanly via registry.
    # Pass a type-wrong value to trigger validation error:
    with pytest.raises(ToolInvocationError):
        await registry.invoke("repo.tree", {"path": 12345})


async def test_registry_file_read_traversal_via_registry(workspace: Path) -> None:
    policy = WorkspacePolicy(root=workspace)
    registry = ToolRegistry()
    registry.register(FileReadTool(policy))

    with pytest.raises(ToolInvocationError):
        await registry.invoke("file.read", {"path": "../outside.txt"})
