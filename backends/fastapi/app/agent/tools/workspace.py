"""Read-only workspace inspection tools.

Provides two ToolDefinition-compatible tools:
  - repo.tree  — list entries under a workspace path as relative POSIX paths
  - file.read  — read a file's contents within the workspace root

Security boundary
-----------------
All path inputs are resolved via WorkspacePolicy.resolve_safe which uses
pathlib.Path.resolve (following symlinks) and verifies the result is inside
the configured workspace root. Paths that escape through traversal or symlinks
raise ToolInvocationError with structured reason codes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from app.agent.tools.registry import ToolDefinition, ToolInvocationError, ToolRisk


# ---------------------------------------------------------------------------
# Workspace policy
# ---------------------------------------------------------------------------


@dataclass
class WorkspacePolicy:
    """Configuration and path-safety boundary for workspace tools.

    Attributes
    ----------
    root:
        Absolute, resolved workspace root directory.
    max_tree_entries:
        Maximum number of entries returned by repo.tree before truncation.
    max_read_bytes:
        Maximum file size (bytes) allowed by file.read.
    """

    root: Path
    max_tree_entries: int = 1000
    max_read_bytes: int = 1_048_576  # 1 MiB

    def __post_init__(self) -> None:
        self.root = self.root.resolve()

    def resolve_safe(self, path_str: str) -> Path:
        """Return the resolved path for *path_str* if it is within the workspace root.

        Raises ``ToolInvocationError`` with:
        - ``reason: path_outside_workspace`` — traversal or absolute path outside root
        - ``reason: symlink_escape`` — symlink whose target resolves outside root
        """
        if not path_str or path_str.strip() in ("", "."):
            return self.root

        p = Path(path_str)
        if p.is_absolute():
            normalized = Path(os.path.normpath(p))
        else:
            normalized = Path(os.path.normpath(self.root / p))

        try:
            normalized.relative_to(self.root)
        except ValueError:
            raise ToolInvocationError(
                "Path escapes workspace root",
                details={"reason": "path_outside_workspace", "requested": path_str},
            )

        # Follow symlinks and re-check the resolved target
        resolved = normalized.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            raise ToolInvocationError(
                "Path resolves outside workspace root through symlink",
                details={"reason": "symlink_escape", "requested": path_str},
            )

        return resolved


# ---------------------------------------------------------------------------
# I/O models
# ---------------------------------------------------------------------------


class RepositoryTreeInput(BaseModel):
    path: str = "."


class RepositoryTreeOutput(BaseModel):
    root: str
    entries: list[str]
    truncated: bool


class FileReadInput(BaseModel):
    path: str = Field(min_length=1)


class FileReadOutput(BaseModel):
    path: str
    content: str
    size_bytes: int
    encoding: str


# ---------------------------------------------------------------------------
# Tool factories
# ---------------------------------------------------------------------------


def RepositoryTreeTool(policy: WorkspacePolicy) -> ToolDefinition:  # noqa: N802
    """Return a ToolDefinition for 'repo.tree' bound to *policy*."""

    async def _invoke(inp: RepositoryTreeInput) -> RepositoryTreeOutput:
        target = policy.resolve_safe(inp.path)

        if not target.is_dir():
            raise ToolInvocationError(
                f"Path {inp.path!r} is not a directory",
                details={"reason": "not_a_directory", "requested": inp.path},
            )

        all_items: list[Path] = sorted(target.rglob("*"))
        truncated = len(all_items) > policy.max_tree_entries
        entries: list[str] = []
        for item in all_items[: policy.max_tree_entries]:
            entries.append(item.relative_to(policy.root).as_posix())

        root_rel = (
            target.relative_to(policy.root).as_posix()
            if target != policy.root
            else "."
        )
        return RepositoryTreeOutput(root=root_rel, entries=entries, truncated=truncated)

    return ToolDefinition(
        name="repo.tree",
        description=(
            "List all files and directories under a workspace path as relative POSIX paths."
        ),
        input_schema=RepositoryTreeInput,
        output_schema=RepositoryTreeOutput,
        callable=_invoke,
        risk=ToolRisk.read_only,
    )


def FileReadTool(policy: WorkspacePolicy) -> ToolDefinition:  # noqa: N802
    """Return a ToolDefinition for 'file.read' bound to *policy*."""

    async def _invoke(inp: FileReadInput) -> FileReadOutput:
        target = policy.resolve_safe(inp.path)

        if target.is_dir():
            raise ToolInvocationError(
                f"Path {inp.path!r} is a directory, not a file",
                details={"reason": "not_a_file", "requested": inp.path},
            )

        if not target.exists():
            raise ToolInvocationError(
                f"Path {inp.path!r} does not exist",
                details={"reason": "not_found", "requested": inp.path},
            )

        size_bytes = target.stat().st_size
        if size_bytes > policy.max_read_bytes:
            raise ToolInvocationError(
                "File exceeds max_read_bytes limit",
                details={
                    "reason": "file_too_large",
                    "requested": inp.path,
                    "size_bytes": size_bytes,
                    "max_read_bytes": policy.max_read_bytes,
                },
            )

        raw = target.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ToolInvocationError(
                f"File {inp.path!r} is not valid UTF-8",
                details={"reason": "not_utf8", "requested": inp.path},
            )

        return FileReadOutput(
            path=target.relative_to(policy.root).as_posix(),
            content=content,
            size_bytes=size_bytes,
            encoding="utf-8",
        )

    return ToolDefinition(
        name="file.read",
        description="Read the UTF-8 content of a file inside the workspace root.",
        input_schema=FileReadInput,
        output_schema=FileReadOutput,
        callable=_invoke,
        risk=ToolRisk.read_only,
    )
