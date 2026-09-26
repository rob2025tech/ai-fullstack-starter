"""Governed filesystem mutation tools.

Provides one ToolDefinition-compatible tool:
  - file.write — create or overwrite a UTF-8 file inside the workspace root

All mutations are classified ToolRisk.mutating so approval-gating services
can require explicit human authorisation before execution.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agent.tools.registry import ToolDefinition, ToolInvocationError, ToolRisk
from app.agent.tools.workspace import WorkspacePolicy


# ---------------------------------------------------------------------------
# I/O models
# ---------------------------------------------------------------------------


class FileWriteInput(BaseModel):
    path: str = Field(min_length=1)
    content: str
    overwrite: bool = False
    create_parents: bool = False


class FileWriteOutput(BaseModel):
    path: str
    size_bytes: int
    action: Literal["created", "overwritten"]


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------


def FileWriteTool(policy: WorkspacePolicy) -> ToolDefinition:  # noqa: N802
    """Return a ToolDefinition for 'file.write' bound to *policy*."""

    async def _invoke(inp: FileWriteInput) -> FileWriteOutput:
        target = policy.resolve_safe(inp.path)

        if target.is_dir():
            raise ToolInvocationError(
                f"Path {inp.path!r} is a directory",
                details={"reason": "is_a_directory", "requested": inp.path},
            )

        if not target.parent.exists():
            if not inp.create_parents:
                raise ToolInvocationError(
                    f"Parent directory does not exist for {inp.path!r}",
                    details={"reason": "missing_parent", "requested": inp.path},
                )
            target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not inp.overwrite:
            raise ToolInvocationError(
                f"File {inp.path!r} already exists; set overwrite=true to replace it",
                details={"reason": "overwrite_refused", "requested": inp.path},
            )

        action: Literal["created", "overwritten"] = (
            "overwritten" if target.exists() else "created"
        )
        raw = inp.content.encode("utf-8")
        target.write_bytes(raw)

        return FileWriteOutput(
            path=target.relative_to(policy.root).as_posix(),
            size_bytes=len(raw),
            action=action,
        )

    return ToolDefinition(
        name="file.write",
        description="Create or overwrite a UTF-8 file inside the workspace root.",
        input_schema=FileWriteInput,
        output_schema=FileWriteOutput,
        callable=_invoke,
        risk=ToolRisk.mutating,
    )
