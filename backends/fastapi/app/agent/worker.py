"""Local agent worker for in-process task execution.

Provides:
  LocalAgentWorker — claims runnable tasks from the AgentRepository, invokes
                     AgentLoop.run, and persists terminal task state.

Design
------
- The worker is callable from tests as a single-run method (run_once) and
  does not require a production message broker or external queue.
- AgentRepository.find_next_runnable_task provides the claim primitive;
  terminal status is always set by AgentLoop.run itself.
- Unhandled exceptions from AgentLoop.run are caught at the worker boundary,
  persisted as a failed status, and returned as a failed AgentLoopResult so
  the calling test can inspect the outcome without the exception propagating.
"""

from __future__ import annotations

import uuid

from app.agent.loop import AgentLoop, AgentLoopResult
from app.agent.repository import AgentRepository

__all__ = ["LocalAgentWorker"]


class LocalAgentWorker:
    """Single-worker in-process task executor.

    Parameters
    ----------
    loop:
        The ``AgentLoop`` instance used to execute tasks.
    repo:
        The ``AgentRepository`` used to discover and claim runnable tasks.
    """

    def __init__(self, loop: AgentLoop, repo: AgentRepository) -> None:
        self._loop = loop
        self._repo = repo

    async def run_once(self) -> AgentLoopResult | None:
        """Claim the next pending task and execute it.

        Returns the ``AgentLoopResult`` on success or failure, or ``None``
        if no runnable task is available.
        """
        task = self._repo.find_next_runnable_task()
        if task is None:
            return None
        return await self._execute(task.session_id, task.task_id)

    async def run_task(self, session_id: str, task_id: str) -> AgentLoopResult:
        """Execute a specific task by session and task identifier.

        Useful in integration tests where the caller already knows the task.
        """
        return await self._execute(session_id, task_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute(self, session_id: str, task_id: str) -> AgentLoopResult:
        try:
            return await self._loop.run(session_id, task_id)
        except Exception as exc:
            # Safety net: AgentLoop.run should never raise, but we protect the
            # worker from any unexpected exception escaping the loop boundary.
            error_msg = f"{type(exc).__name__}: {exc}"
            self._repo.append_event(
                event_id=str(uuid.uuid4()),
                session_id=session_id,
                task_id=task_id,
                event_type="error",
                payload={"error_type": "worker_error", "message": error_msg},
            )
            try:
                self._repo.update_task_status(task_id, "failed", result="worker_error")
            except Exception:
                pass
            return AgentLoopResult(
                status="failed",
                task_id=task_id,
                error="worker_error",
            )
