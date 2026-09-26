"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  type AgentEventResponse,
  ContractError,
  createAgentSession,
  getAgentEvents,
  streamAgentEvents,
  submitAgentApproval,
  submitAgentTask,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PendingApproval = {
  approval_id: string;
  tool_name: string;
  risk: string;
  fingerprint: string;
  submitting: boolean;
  error: string | null;
};

type FinalResult =
  | { kind: "success"; content: string }
  | { kind: "error"; code: string; message: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Human-readable label for each event_type discriminant. */
export function formatEventType(eventType: string): string {
  return eventType
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Extract pending approval metadata from an approval_requested payload. */
export function extractApproval(event: AgentEventResponse): PendingApproval | null {
  if (event.event_type !== "approval_requested") return null;
  const p = event.payload ?? {};
  const approval_id = typeof p["approval_id"] === "string" ? p["approval_id"] : "";
  if (!approval_id) return null;
  return {
    approval_id,
    tool_name: typeof p["tool_name"] === "string" ? p["tool_name"] : "unknown",
    risk: typeof p["risk"] === "string" ? p["risk"] : "mutating",
    fingerprint: typeof p["fingerprint"] === "string" ? p["fingerprint"] : "",
    submitting: false,
    error: null,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AgentWorkspace() {
  // Session / task state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [resumeInput, setResumeInput] = useState("");

  // Timeline state
  const [events, setEvents] = useState<AgentEventResponse[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<
    Map<string, PendingApproval>
  >(new Map());
  const [finalResult, setFinalResult] = useState<FinalResult | null>(null);

  // UI flags
  const [creatingSession, setCreatingSession] = useState(false);
  const [submittingTask, setSubmittingTask] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latestSequenceRef = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll timeline on new events
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  // ---------------------------------------------------------------------------
  // Event ingestion
  // ---------------------------------------------------------------------------

  const ingestEvent = useCallback((event: AgentEventResponse) => {
    setEvents((prev) => {
      if (prev.some((e) => e.event_id === event.event_id)) return prev;
      return [...prev].concat(event).sort((a, b) => a.sequence - b.sequence);
    });

    latestSequenceRef.current = Math.max(
      latestSequenceRef.current,
      event.sequence,
    );

    // Track pending approvals (deduplicated by approval_id)
    const approval = extractApproval(event);
    if (approval) {
      setPendingApprovals((prev) => {
        if (prev.has(approval.approval_id)) return prev;
        const next = new Map(prev);
        next.set(approval.approval_id, approval);
        return next;
      });
    }

    // Terminal events
    if (event.event_type === "completed") {
      const p = event.payload ?? {};
      setFinalResult({
        kind: "success",
        content:
          typeof p["content"] === "string" ? p["content"] : "Task completed.",
      });
      setStreaming(false);
    }
    if (event.event_type === "error") {
      const p = event.payload ?? {};
      setFinalResult({
        kind: "error",
        code:
          typeof p["error_type"] === "string" ? p["error_type"] : "error",
        message:
          typeof p["message"] === "string" ? p["message"] : "Task failed.",
      });
      setStreaming(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Session management
  // ---------------------------------------------------------------------------

  async function handleCreateSession(event: FormEvent) {
    event.preventDefault();
    setCreatingSession(true);
    setError(null);
    try {
      const session = await createAgentSession();
      setSessionId(session.session_id);
    } catch (err) {
      setError(
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Session creation failed.",
      );
    } finally {
      setCreatingSession(false);
    }
  }

  function handleResumeSession(event: FormEvent) {
    event.preventDefault();
    const id = resumeInput.trim();
    if (!id) return;
    setSessionId(id);
    setError(null);
  }

  // ---------------------------------------------------------------------------
  // Task submission + streaming
  // ---------------------------------------------------------------------------

  async function handleSubmitTask(event: FormEvent) {
    event.preventDefault();
    if (!sessionId || !prompt.trim() || submittingTask) return;

    setSubmittingTask(true);
    setError(null);
    setEvents([]);
    setPendingApprovals(new Map());
    setFinalResult(null);
    latestSequenceRef.current = 0;

    let tid: string;
    try {
      const task = await submitAgentTask(sessionId, { prompt: prompt.trim() });
      tid = task.task_id;
      setTaskId(tid);
      setPrompt("");
    } catch (err) {
      setError(
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Task submission failed.",
      );
      setSubmittingTask(false);
      return;
    }

    // Replay prior events, then stream live ones
    setSubmittingTask(false);
    setStreaming(true);

    try {
      const replay = await getAgentEvents(sessionId, tid, 0);
      replay.events.forEach(ingestEvent);
    } catch {
      // non-fatal — proceed to live stream
    }

    await streamAgentEvents(
      sessionId,
      tid,
      latestSequenceRef.current,
      {
        onEvent: ingestEvent,
        onError: (err) => {
          setError(`${err.code}: ${err.message}`);
          setStreaming(false);
        },
      },
    );

    setStreaming(false);
  }

  // ---------------------------------------------------------------------------
  // Approval decisions
  // ---------------------------------------------------------------------------

  async function handleApprovalDecision(
    approvalId: string,
    decision: "approved" | "rejected",
  ) {
    if (!sessionId) return;

    setPendingApprovals((prev) => {
      const next = new Map(prev);
      const entry = next.get(approvalId);
      if (entry) next.set(approvalId, { ...entry, submitting: true, error: null });
      return next;
    });

    try {
      await submitAgentApproval(sessionId, approvalId, { decision });
      // Remove from pending once decision is recorded
      setPendingApprovals((prev) => {
        const next = new Map(prev);
        next.delete(approvalId);
        return next;
      });
    } catch (err) {
      const message =
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Approval decision failed.";
      setPendingApprovals((prev) => {
        const next = new Map(prev);
        const entry = next.get(approvalId);
        if (entry)
          next.set(approvalId, { ...entry, submitting: false, error: message });
        return next;
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!sessionId) {
    return (
      <div className="w-full max-w-2xl space-y-6">
        <h2 className="text-lg font-semibold">Agent Workspace</h2>

        <form onSubmit={handleCreateSession} className="flex gap-2">
          <button
            type="submit"
            disabled={creatingSession}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {creatingSession ? "Creating…" : "New Session"}
          </button>
        </form>

        <form onSubmit={handleResumeSession} className="flex gap-2">
          <input
            value={resumeInput}
            onChange={(e) => setResumeInput(e.target.value)}
            placeholder="Resume session ID…"
            aria-label="Session ID"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-900"
          />
          <button
            type="submit"
            disabled={!resumeInput.trim()}
            className="rounded-lg bg-gray-600 px-4 py-2 text-white disabled:opacity-50"
          >
            Resume
          </button>
        </form>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="w-full max-w-2xl space-y-6">
      <h2 className="text-lg font-semibold">Agent Workspace</h2>

      <p className="text-xs text-black/50 dark:text-white/50">
        Session: <span className="font-mono">{sessionId}</span>
      </p>

      {/* Task submission form */}
      <form onSubmit={handleSubmitTask} className="flex gap-2">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the coding task…"
          aria-label="Task prompt"
          disabled={submittingTask || streaming}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-indigo-500 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900"
        />
        <button
          type="submit"
          disabled={submittingTask || streaming || !prompt.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {submittingTask ? "Submitting…" : streaming ? "Running…" : "Submit"}
        </button>
      </form>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {/* Pending approval cards */}
      {pendingApprovals.size > 0 && (
        <section aria-label="Pending approvals" className="space-y-3">
          <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-400">
            Pending Approvals
          </h3>
          {[...pendingApprovals.values()].map((appr) => (
            <div
              key={appr.approval_id}
              className="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-950"
            >
              <p className="text-sm font-medium">
                Tool: <span className="font-mono">{appr.tool_name}</span>{" "}
                <span className="ml-2 text-xs text-amber-600">
                  [{appr.risk}]
                </span>
              </p>
              <p className="mt-1 text-xs text-black/50 dark:text-white/50">
                ID: {appr.approval_id}
              </p>
              {appr.error && (
                <p className="mt-1 text-xs text-red-600">{appr.error}</p>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() =>
                    handleApprovalDecision(appr.approval_id, "approved")
                  }
                  disabled={appr.submitting}
                  className="rounded bg-green-600 px-3 py-1 text-xs text-white disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() =>
                    handleApprovalDecision(appr.approval_id, "rejected")
                  }
                  disabled={appr.submitting}
                  className="rounded bg-red-600 px-3 py-1 text-xs text-white disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Event timeline */}
      {(events.length > 0 || streaming) && (
        <section aria-label="Event timeline">
          <h3 className="mb-2 text-sm font-semibold">
            Timeline
            {taskId && (
              <span className="ml-2 text-xs font-normal text-black/50 dark:text-white/50">
                task: {taskId}
              </span>
            )}
          </h3>
          <div className="max-h-80 space-y-2 overflow-y-auto rounded-lg border border-gray-200 p-3 dark:border-gray-700">
            {events.map((event) => (
              <div
                key={`${event.task_id}-${event.sequence}`}
                data-sequence={event.sequence}
                className="flex items-start gap-2 text-xs"
              >
                <span className="w-6 shrink-0 text-right text-black/30 dark:text-white/30">
                  {event.sequence}
                </span>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 font-mono font-medium ${eventTypeClass(event.event_type)}`}
                >
                  {event.event_type}
                </span>
                <span className="truncate text-black/70 dark:text-white/70">
                  {summarisePayload(event)}
                </span>
              </div>
            ))}
            {streaming && events.length === 0 && (
              <p className="text-xs text-black/40 dark:text-white/40">
                Waiting for events…
              </p>
            )}
            <div ref={bottomRef} />
          </div>
        </section>
      )}

      {/* Final result */}
      {finalResult && (
        <section aria-label="Final result">
          {finalResult.kind === "success" ? (
            <div className="rounded-lg border border-green-300 bg-green-50 p-4 dark:border-green-700 dark:bg-green-950">
              <h3 className="text-sm font-semibold text-green-700 dark:text-green-400">
                Task completed
              </h3>
              <p className="mt-1 whitespace-pre-wrap text-sm">
                {finalResult.content}
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-700 dark:bg-red-950">
              <h3 className="text-sm font-semibold text-red-700 dark:text-red-400">
                Task failed — {finalResult.code}
              </h3>
              <p className="mt-1 text-sm">{finalResult.message}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

function eventTypeClass(eventType: string): string {
  switch (eventType) {
    case "completed":
      return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
    case "error":
      return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    case "approval_requested":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200";
    case "tool_call":
    case "tool_result":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    default:
      return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
  }
}

function summarisePayload(event: AgentEventResponse): string {
  const p = event.payload;
  if (!p) return "";
  switch (event.event_type) {
    case "assistant_output":
      return typeof p["content"] === "string"
        ? (p["content"] as string).slice(0, 80)
        : "";
    case "tool_call":
    case "tool_result":
      return typeof p["tool_name"] === "string"
        ? String(p["tool_name"])
        : "";
    case "approval_requested":
      return typeof p["tool_name"] === "string"
        ? `${String(p["tool_name"])} [${String(p["risk"] ?? "mutating")}]`
        : "";
    case "error":
      return typeof p["message"] === "string"
        ? (p["message"] as string).slice(0, 80)
        : "";
    case "completed":
      return typeof p["content"] === "string"
        ? (p["content"] as string).slice(0, 80)
        : "";
    default:
      return "";
  }
}
