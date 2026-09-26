"""Governed command execution tools.

Provides:
  ALWAYS_BLOCKED          — commands never executed regardless of approval
  GIT_READ_ONLY_SUBCOMMANDS — git subcommands classified read_only
  CommandRiskClassifier   — pure classification, no I/O
  CommandPolicy           — output byte limits and timeout
  CommandInput / CommandOutput — Pydantic I/O models
  CommandTool(policy, *, ...) — ToolDefinition factory with injectable runner

Security boundary
-----------------
- shell=False always; shlex.split is used only to convert a command string
  to an argv list before handing it to asyncio.create_subprocess_exec.
- ALWAYS_BLOCKED commands are rejected before any subprocess call.
- Mutating and unsafe commands require approved=True from the caller;
  they are not executed by default.
- No public API endpoint exposes this tool.
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from app.agent.tools.registry import ToolDefinition, ToolInvocationError, ToolRisk
from app.agent.tools.workspace import WorkspacePolicy


# ---------------------------------------------------------------------------
# Command classification constants
# ---------------------------------------------------------------------------

# Commands that are never executed, regardless of approval flag.
ALWAYS_BLOCKED: frozenset[str] = frozenset(
    {
        "rm",
        "sudo",
        "curl",
        "wget",
        "pip",
        "pip3",
        "ssh",
        "scp",
        "sftp",
        "nc",
        "netcat",
        "bash",
        "sh",
        "zsh",
        "fish",
        "dash",
        "eval",
        "exec",
        "kill",
        "pkill",
        "killall",
        "chmod",
        "chown",
        "chgrp",
        "dd",
        "mkfs",
        "fdisk",
        "parted",
        "mount",
        "umount",
        "apt",
        "apt-get",
        "yum",
        "dnf",
        "brew",
        "npm",
        "yarn",
        "npx",
        "node",
        "docker",
        "kubectl",
        "terraform",
    }
)

# Non-git commands treated as read_only by default.
_BASE_READ_ONLY: frozenset[str] = frozenset(
    {
        "ls",
        "find",
        "cat",
        "head",
        "tail",
        "wc",
        "echo",
        "pwd",
        "env",
        "which",
        "type",
        "file",
        "stat",
        "grep",
        "rg",
        "ag",
        "diff",
        "sort",
        "uniq",
        "cut",
        "true",
        "false",
    }
)

# git subcommands that do not modify repository state.
GIT_READ_ONLY_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "diff",
        "log",
        "show",
        "blame",
        "branch",
        "remote",
        "fetch",
        "describe",
        "rev-parse",
        "ls-files",
        "shortlog",
        "--version",
        "--help",
        "stash",
        "tag",
        "reflog",
        "for-each-ref",
        "config",
    }
)


# ---------------------------------------------------------------------------
# Risk classifier
# ---------------------------------------------------------------------------


@dataclass
class CommandRiskClassifier:
    """Classify a parsed argv list as ToolRisk.read_only, .mutating, or .unsafe.

    Rules (applied in order):
    1. Empty argv → unsafe.
    2. Base executable name in ALWAYS_BLOCKED → unsafe.
    3. Base executable name is 'git' and subcommand in GIT_READ_ONLY_SUBCOMMANDS → read_only.
    4. Base executable name in _BASE_READ_ONLY → read_only.
    5. Everything else → mutating.
    """

    def classify(self, argv: list[str]) -> ToolRisk:
        if not argv:
            return ToolRisk.unsafe

        base = _base_name(argv[0])

        if base in ALWAYS_BLOCKED:
            return ToolRisk.unsafe

        if base == "git":
            sub = argv[1] if len(argv) > 1 else ""
            if sub in GIT_READ_ONLY_SUBCOMMANDS:
                return ToolRisk.read_only
            return ToolRisk.mutating

        if base in _BASE_READ_ONLY:
            return ToolRisk.read_only

        return ToolRisk.mutating

    def is_blocked(self, argv: list[str]) -> bool:
        """Return True if the command must never execute."""
        if not argv:
            return True
        return _base_name(argv[0]) in ALWAYS_BLOCKED


def _base_name(executable: str) -> str:
    """Strip directory prefix: /usr/bin/git → git."""
    return executable.split("/")[-1]


# ---------------------------------------------------------------------------
# Command policy and runner type
# ---------------------------------------------------------------------------


@dataclass
class CommandPolicy:
    max_output_bytes: int = 65_536  # 64 KiB per stream
    timeout_seconds: float = 30.0


# Injectable runner: (argv, cwd, timeout) → (exit_code, stdout_bytes, stderr_bytes)
CommandRunner = Callable[..., Awaitable[tuple[int, bytes, bytes]]]


async def _default_runner(
    argv: list[str],
    cwd: Path | None = None,
    timeout: float = 30.0,
) -> tuple[int, bytes, bytes]:
    """Execute *argv* with shell=False."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise ToolInvocationError(
            "Command timed out",
            details={
                "reason": "command_timeout",
                "timeout_seconds": timeout,
            },
        )
    return proc.returncode or 0, stdout, stderr


# ---------------------------------------------------------------------------
# I/O models
# ---------------------------------------------------------------------------


class CommandInput(BaseModel):
    command: str = Field(min_length=1)
    approved: bool = False


class CommandOutput(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    truncated_stdout: bool
    truncated_stderr: bool
    risk: str  # ToolRisk value for the invoked command


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------


def CommandTool(  # noqa: N802
    policy: WorkspacePolicy | None = None,
    *,
    command_policy: CommandPolicy | None = None,
    runner: CommandRunner | None = None,
    classifier: CommandRiskClassifier | None = None,
) -> ToolDefinition:
    """Return a ToolDefinition for 'command.run'.

    Parameters
    ----------
    policy:
        WorkspacePolicy used to set the working directory for subprocess calls.
        When *None*, the subprocess inherits the process cwd.
    command_policy:
        Output size and timeout limits. Defaults to CommandPolicy().
    runner:
        Injectable async callable for subprocess execution.  Defaults to the
        real asyncio runner; tests supply a fake to avoid host side-effects.
    classifier:
        Risk classifier. Defaults to CommandRiskClassifier().
    """
    _cmd_policy = command_policy or CommandPolicy()
    _runner: CommandRunner = runner or _default_runner
    _classifier = classifier or CommandRiskClassifier()

    async def _invoke(inp: CommandInput) -> CommandOutput:
        try:
            argv = shlex.split(inp.command)
        except ValueError as exc:
            raise ToolInvocationError(
                f"Failed to parse command: {exc}",
                details={"reason": "parse_error", "command": inp.command},
            )

        if not argv:
            raise ToolInvocationError(
                "Empty command after parsing",
                details={"reason": "empty_command", "command": inp.command},
            )

        if _classifier.is_blocked(argv):
            raise ToolInvocationError(
                f"Command {argv[0]!r} is blocked by policy",
                details={"reason": "command_blocked", "command": inp.command},
            )

        risk = _classifier.classify(argv)

        if risk != ToolRisk.read_only and not inp.approved:
            raise ToolInvocationError(
                f"Command requires approval (risk={risk.value})",
                details={
                    "reason": "command_requires_approval",
                    "command": inp.command,
                    "risk": risk.value,
                },
            )

        cwd = policy.root if policy is not None else None

        exit_code, stdout_bytes, stderr_bytes = await _runner(
            argv,
            cwd=cwd,
            timeout=_cmd_policy.timeout_seconds,
        )

        truncated_stdout = len(stdout_bytes) > _cmd_policy.max_output_bytes
        truncated_stderr = len(stderr_bytes) > _cmd_policy.max_output_bytes
        stdout_str = stdout_bytes[: _cmd_policy.max_output_bytes].decode(
            "utf-8", errors="replace"
        )
        stderr_str = stderr_bytes[: _cmd_policy.max_output_bytes].decode(
            "utf-8", errors="replace"
        )

        return CommandOutput(
            command=inp.command,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            truncated_stdout=truncated_stdout,
            truncated_stderr=truncated_stderr,
            risk=risk.value,
        )

    return ToolDefinition(
        name="command.run",
        description=(
            "Execute a command with shell=False.  Blocked commands are always rejected. "
            "Mutating or unsafe commands require approved=True."
        ),
        input_schema=CommandInput,
        output_schema=CommandOutput,
        callable=_invoke,
        risk=ToolRisk.unsafe,
    )
