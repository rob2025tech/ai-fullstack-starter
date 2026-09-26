"""Unit and integration tests for governed command execution tools.

All tests use tmp_path workspaces and an injectable fake runner so no
destructive host commands are ever invoked.  asyncio_mode=auto in pyproject.toml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import pytest

from app.agent.tools.commands import (
    ALWAYS_BLOCKED,
    GIT_READ_ONLY_SUBCOMMANDS,
    CommandInput,
    CommandOutput,
    CommandPolicy,
    CommandRiskClassifier,
    CommandTool,
)
from app.agent.tools.registry import ToolInvocationError, ToolRegistry, ToolRisk
from app.agent.tools.workspace import WorkspacePolicy


# ---------------------------------------------------------------------------
# Fake runners (no subprocess calls in tests)
# ---------------------------------------------------------------------------


async def _fake_runner(
    argv: list[str],
    cwd: Path | None = None,
    timeout: float = 30.0,
) -> tuple[int, bytes, bytes]:
    return 0, b"fake stdout", b""


async def _failing_runner(
    argv: list[str],
    cwd: Path | None = None,
    timeout: float = 30.0,
) -> tuple[int, bytes, bytes]:
    return 1, b"", b"command failed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture()
def policy(workspace: Path) -> WorkspacePolicy:
    return WorkspacePolicy(root=workspace)


# ---------------------------------------------------------------------------
# CommandRiskClassifier — pure classification tests
# ---------------------------------------------------------------------------


def test_classifier_git_status_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "status"]) == ToolRisk.read_only


def test_classifier_git_diff_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "diff"]) == ToolRisk.read_only


def test_classifier_git_diff_with_args_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "diff", "--stat", "HEAD"]) == ToolRisk.read_only


def test_classifier_git_log_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "log", "--oneline", "-10"]) == ToolRisk.read_only


def test_classifier_git_show_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "show", "HEAD"]) == ToolRisk.read_only


def test_classifier_git_add_is_mutating() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "add", "."]) == ToolRisk.mutating


def test_classifier_git_commit_is_mutating() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "commit", "-m", "msg"]) == ToolRisk.mutating


def test_classifier_git_checkout_is_mutating() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["git", "checkout", "-b", "feature"]) == ToolRisk.mutating


def test_classifier_rm_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["rm", "-rf", "/"]) == ToolRisk.unsafe


def test_classifier_sudo_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["sudo", "ls"]) == ToolRisk.unsafe


def test_classifier_curl_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["curl", "https://example.com"]) == ToolRisk.unsafe


def test_classifier_pip_install_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["pip", "install", "requests"]) == ToolRisk.unsafe


def test_classifier_pip3_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["pip3", "install", "requests"]) == ToolRisk.unsafe


def test_classifier_ls_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["ls", "-la"]) == ToolRisk.read_only


def test_classifier_grep_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["grep", "-r", "foo", "."]) == ToolRisk.read_only


def test_classifier_unknown_command_is_mutating() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["make", "build"]) == ToolRisk.mutating


def test_classifier_empty_argv_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify([]) == ToolRisk.unsafe


def test_classifier_path_prefixed_rm_is_unsafe() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["/bin/rm", "-rf", "dir"]) == ToolRisk.unsafe


def test_classifier_path_prefixed_git_status_is_read_only() -> None:
    clf = CommandRiskClassifier()
    assert clf.classify(["/usr/bin/git", "status"]) == ToolRisk.read_only


def test_always_blocked_contains_required_commands() -> None:
    assert "rm" in ALWAYS_BLOCKED
    assert "sudo" in ALWAYS_BLOCKED
    assert "curl" in ALWAYS_BLOCKED
    assert "pip" in ALWAYS_BLOCKED
    assert "pip3" in ALWAYS_BLOCKED
    assert "bash" in ALWAYS_BLOCKED
    assert "sh" in ALWAYS_BLOCKED


def test_git_read_only_subcommands_contains_expected() -> None:
    assert "status" in GIT_READ_ONLY_SUBCOMMANDS
    assert "diff" in GIT_READ_ONLY_SUBCOMMANDS
    assert "log" in GIT_READ_ONLY_SUBCOMMANDS


# ---------------------------------------------------------------------------
# CommandTool — blocked commands
# ---------------------------------------------------------------------------


async def test_command_blocked_rm(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(CommandInput(command="rm -rf /"))
    assert exc_info.value.details["reason"] == "command_blocked"


async def test_command_blocked_sudo(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(CommandInput(command="sudo ls"))
    assert exc_info.value.details["reason"] == "command_blocked"


async def test_command_blocked_curl(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(CommandInput(command="curl https://example.com"))
    assert exc_info.value.details["reason"] == "command_blocked"


async def test_command_blocked_pip_install(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(CommandInput(command="pip install requests"))
    assert exc_info.value.details["reason"] == "command_blocked"


async def test_blocked_command_never_calls_runner(policy: WorkspacePolicy) -> None:
    called: list[list[str]] = []

    async def tracking_runner(
        argv: list[str], cwd: Path | None = None, timeout: float = 30.0
    ) -> tuple[int, bytes, bytes]:
        called.append(argv)
        return 0, b"", b""

    tool = CommandTool(policy, runner=tracking_runner)
    with pytest.raises(ToolInvocationError):
        await tool.callable(CommandInput(command="rm file.txt"))
    assert called == [], "Runner must never be called for blocked commands"


# ---------------------------------------------------------------------------
# CommandTool — approval gating for mutating commands
# ---------------------------------------------------------------------------


async def test_mutating_command_requires_approval(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    with pytest.raises(ToolInvocationError) as exc_info:
        await tool.callable(CommandInput(command="git add ."))
    assert exc_info.value.details["reason"] == "command_requires_approval"
    assert exc_info.value.details["risk"] == "mutating"


async def test_mutating_command_runs_when_approved(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    result: CommandOutput = await tool.callable(
        CommandInput(command="git add .", approved=True)
    )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CommandTool — read-only commands execute without approval
# ---------------------------------------------------------------------------


async def test_read_only_git_status_executes(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git status"))
    assert result.exit_code == 0
    assert result.stdout == "fake stdout"
    assert result.command == "git status"


async def test_read_only_git_diff_executes(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git diff"))
    assert result.exit_code == 0


async def test_read_only_ls_executes(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="ls -la"))
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CommandTool — output and edge cases
# ---------------------------------------------------------------------------


async def test_command_captures_non_zero_exit_code(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_failing_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git status"))
    assert result.exit_code == 1
    assert result.stderr == "command failed"
    assert result.stdout == ""


async def test_command_output_truncated_at_limit(policy: WorkspacePolicy) -> None:
    big_output = b"x" * 200

    async def big_runner(
        argv: list[str], cwd: Path | None = None, timeout: float = 30.0
    ) -> tuple[int, bytes, bytes]:
        return 0, big_output, b""

    cmd_policy = CommandPolicy(max_output_bytes=100)
    tool = CommandTool(policy, command_policy=cmd_policy, runner=big_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git status"))
    assert result.truncated_stdout is True
    assert len(result.stdout) == 100


async def test_command_stderr_truncated_at_limit(policy: WorkspacePolicy) -> None:
    async def err_runner(
        argv: list[str], cwd: Path | None = None, timeout: float = 30.0
    ) -> tuple[int, bytes, bytes]:
        return 1, b"", b"e" * 200

    cmd_policy = CommandPolicy(max_output_bytes=100)
    tool = CommandTool(policy, command_policy=cmd_policy, runner=err_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git status"))
    assert result.truncated_stderr is True
    assert len(result.stderr) == 100


async def test_command_not_truncated_within_limit(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git status"))
    assert result.truncated_stdout is False
    assert result.truncated_stderr is False


async def test_command_risk_in_output(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    result: CommandOutput = await tool.callable(CommandInput(command="git status"))
    assert result.risk == "read_only"


async def test_command_tool_risk_is_unsafe(policy: WorkspacePolicy) -> None:
    tool = CommandTool(policy, runner=_fake_runner)
    assert tool.risk == ToolRisk.unsafe


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------


async def test_registry_blocked_command_rejected_without_subprocess(
    policy: WorkspacePolicy,
) -> None:
    registry = ToolRegistry()
    registry.register(CommandTool(policy, runner=_fake_runner))
    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("command.run", {"command": "rm -rf ."})
    assert exc_info.value.details["reason"] == "command_blocked"


async def test_registry_read_only_command_executes(policy: WorkspacePolicy) -> None:
    registry = ToolRegistry()
    registry.register(CommandTool(policy, runner=_fake_runner))
    result = await registry.invoke("command.run", {"command": "git status"})
    assert isinstance(result.output, CommandOutput)
    assert result.output.exit_code == 0


async def test_registry_mutating_requires_approval(policy: WorkspacePolicy) -> None:
    registry = ToolRegistry()
    registry.register(CommandTool(policy, runner=_fake_runner))
    with pytest.raises(ToolInvocationError) as exc_info:
        await registry.invoke("command.run", {"command": "git add ."})
    assert exc_info.value.details["reason"] == "command_requires_approval"
