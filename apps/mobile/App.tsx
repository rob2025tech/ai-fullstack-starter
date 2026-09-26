import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  type AgentEventResponse,
  ContractError,
  createAgentSession,
  getAgentEvents,
  sendChat,
  submitAgentApproval,
  submitAgentTask,
} from "./lib/api";

// ---------------------------------------------------------------------------
// Chat types (existing)
// ---------------------------------------------------------------------------

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

let nextId = 0;
function makeMessage(role: Message["role"], content: string): Message {
  nextId += 1;
  return { id: `${role}-${nextId}`, role, content };
}

// ---------------------------------------------------------------------------
// Agent types
// ---------------------------------------------------------------------------

type PendingApproval = {
  approvalId: string;
  toolName: string;
  risk: string;
  submitting: boolean;
  decisionError: string | null;
};

type FinalResult =
  | { kind: "success"; content: string }
  | { kind: "error"; code: string; message: string };

// Extract pending approval from an event payload (null if not applicable)
export function extractMobileApproval(
  event: AgentEventResponse,
): PendingApproval | null {
  if (event.event_type !== "approval_requested") return null;
  const p = event.payload ?? {};
  const approvalId =
    typeof p["approval_id"] === "string" ? p["approval_id"] : "";
  if (!approvalId) return null;
  return {
    approvalId,
    toolName: typeof p["tool_name"] === "string" ? p["tool_name"] : "unknown",
    risk: typeof p["risk"] === "string" ? p["risk"] : "mutating",
    submitting: false,
    decisionError: null,
  };
}

// De-duplicate events by event_id, sorted ascending by sequence
export function mergeEvents(
  existing: AgentEventResponse[],
  incoming: AgentEventResponse[],
): AgentEventResponse[] {
  const seen = new Set(existing.map((e) => e.event_id));
  const next = [...existing];
  for (const e of incoming) {
    if (!seen.has(e.event_id)) {
      next.push(e);
      seen.add(e.event_id);
    }
  }
  return next.sort((a, b) => a.sequence - b.sequence);
}

// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

type AppMode = "chat" | "agent";

export default function App() {
  const [mode, setMode] = useState<AppMode>("chat");

  return (
    <SafeAreaView style={styles.safeArea}>
      {/* Mode switcher */}
      <View style={styles.modeSwitcher}>
        <Pressable
          style={[styles.modeTab, mode === "chat" && styles.modeTabActive]}
          onPress={() => setMode("chat")}
        >
          <Text
            style={[
              styles.modeTabText,
              mode === "chat" && styles.modeTabTextActive,
            ]}
          >
            Chat
          </Text>
        </Pressable>
        <Pressable
          style={[styles.modeTab, mode === "agent" && styles.modeTabActive]}
          onPress={() => setMode("agent")}
        >
          <Text
            style={[
              styles.modeTabText,
              mode === "agent" && styles.modeTabTextActive,
            ]}
          >
            Agent
          </Text>
        </Pressable>
      </View>

      {mode === "chat" ? <ChatScreen /> : <AgentScreen />}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// ChatScreen — preserved from day-1 implementation
// ---------------------------------------------------------------------------

function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<Message>>(null);

  const handleSubmit = useCallback(async () => {
    const trimmed = prompt.trim();
    if (!trimmed || pending) return;
    setPrompt("");
    setError(null);
    setPending(true);
    const placeholder = makeMessage("assistant", "");
    setMessages((prev) => [...prev, makeMessage("user", trimmed), placeholder]);
    try {
      const response = await sendChat({ prompt: trimmed });
      setMessages((prev) =>
        prev.map((message) =>
          message.id === placeholder.id
            ? { ...message, content: response.message.content }
            : message,
        ),
      );
    } catch (caught) {
      const contract =
        caught instanceof ContractError
          ? `${caught.code}: ${caught.message}`
          : "internal_error: unexpected failure";
      setMessages((prev) =>
        prev.filter((message) => message.id !== placeholder.id),
      );
      setError(contract);
    } finally {
      setPending(false);
    }
  }, [prompt, pending]);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <Text style={styles.title}>AI Fullstack Starter</Text>
        <Text style={styles.subtitle}>/api/v1 · JSON mode</Text>
      </View>
      <FlatList
        ref={listRef}
        style={styles.flex}
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() =>
          listRef.current?.scrollToEnd({ animated: true })
        }
        renderItem={({ item }) => (
          <View
            style={[
              styles.bubble,
              item.role === "user"
                ? styles.userBubble
                : styles.assistantBubble,
            ]}
          >
            <Text
              style={
                item.role === "user" ? styles.userText : styles.assistantText
              }
            >
              {item.content === "" ? "…" : item.content}
            </Text>
          </View>
        )}
        ListEmptyComponent={
          <Text style={styles.empty}>
            Send a prompt — the mock backend echoes it back.
          </Text>
        }
      />
      {error !== null && <Text style={styles.error}>{error}</Text>}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={prompt}
          onChangeText={setPrompt}
          placeholder="Type a prompt"
          editable={!pending}
          multiline
          onSubmitEditing={handleSubmit}
        />
        <Pressable
          style={[
            styles.send,
            (pending || prompt.trim() === "") && styles.sendDisabled,
          ]}
          onPress={handleSubmit}
          disabled={pending || prompt.trim() === ""}
        >
          <Text style={styles.sendText}>{pending ? "…" : "Send"}</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// AgentScreen — JSON-replay agent workspace (no SSE)
// ---------------------------------------------------------------------------

function AgentScreen() {
  // Session / task state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [resumeInput, setResumeInput] = useState("");
  const [taskPrompt, setTaskPrompt] = useState("");

  // Timeline state
  const [events, setEvents] = useState<AgentEventResponse[]>([]);
  const [approvals, setApprovals] = useState<Map<string, PendingApproval>>(
    new Map(),
  );
  const [finalResult, setFinalResult] = useState<FinalResult | null>(null);

  // UI flags
  const [loadingSession, setLoadingSession] = useState(false);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // Event ingestion helper
  // -------------------------------------------------------------------------

  function ingestEvents(incoming: AgentEventResponse[]) {
    setEvents((prev) => {
      const merged = mergeEvents(prev, incoming);
      return merged;
    });

    // Update pending approvals
    for (const event of incoming) {
      const appr = extractMobileApproval(event);
      if (appr) {
        setApprovals((prev) => {
          if (prev.has(appr.approvalId)) return prev;
          const next = new Map(prev);
          next.set(appr.approvalId, appr);
          return next;
        });
      }
      // Resolve terminal states
      if (event.event_type === "completed") {
        const p = event.payload ?? {};
        setFinalResult({
          kind: "success",
          content:
            typeof p["content"] === "string"
              ? p["content"]
              : "Task completed.",
        });
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
      }
    }
  }

  // -------------------------------------------------------------------------
  // Refresh timeline from replay endpoint
  // -------------------------------------------------------------------------

  async function refreshTimeline(sid: string, tid: string) {
    setLoadingEvents(true);
    setAgentError(null);
    try {
      const result = await getAgentEvents(sid, tid);
      ingestEvents(result.events);
    } catch (err) {
      setAgentError(
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Failed to load events.",
      );
    } finally {
      setLoadingEvents(false);
    }
  }

  // -------------------------------------------------------------------------
  // Session management
  // -------------------------------------------------------------------------

  async function handleCreateSession() {
    setLoadingSession(true);
    setAgentError(null);
    try {
      const session = await createAgentSession();
      setSessionId(session.session_id);
      setTaskId(null);
      setEvents([]);
      setApprovals(new Map());
      setFinalResult(null);
    } catch (err) {
      setAgentError(
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Session creation failed.",
      );
    } finally {
      setLoadingSession(false);
    }
  }

  function handleResumeSession() {
    const id = resumeInput.trim();
    if (!id) return;
    setSessionId(id);
    setTaskId(null);
    setEvents([]);
    setApprovals(new Map());
    setFinalResult(null);
    setAgentError(null);
    setResumeInput("");
  }

  // -------------------------------------------------------------------------
  // Task submission
  // -------------------------------------------------------------------------

  async function handleSubmitTask() {
    if (!sessionId || !taskPrompt.trim() || loadingTask) return;
    setLoadingTask(true);
    setAgentError(null);
    setEvents([]);
    setApprovals(new Map());
    setFinalResult(null);

    try {
      const task = await submitAgentTask(sessionId, {
        prompt: taskPrompt.trim(),
      });
      setTaskId(task.task_id);
      setTaskPrompt("");
      // Immediately fetch the initial replay
      await refreshTimeline(sessionId, task.task_id);
    } catch (err) {
      setAgentError(
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Task submission failed.",
      );
    } finally {
      setLoadingTask(false);
    }
  }

  // -------------------------------------------------------------------------
  // Approval decisions
  // -------------------------------------------------------------------------

  async function handleApprovalDecision(
    approvalId: string,
    decision: "approved" | "rejected",
  ) {
    if (!sessionId || !taskId) return;

    setApprovals((prev) => {
      const next = new Map(prev);
      const entry = next.get(approvalId);
      if (entry)
        next.set(approvalId, {
          ...entry,
          submitting: true,
          decisionError: null,
        });
      return next;
    });

    try {
      await submitAgentApproval(sessionId, approvalId, { decision });
      // Remove from pending and refresh timeline
      setApprovals((prev) => {
        const next = new Map(prev);
        next.delete(approvalId);
        return next;
      });
      await refreshTimeline(sessionId, taskId);
    } catch (err) {
      const message =
        err instanceof ContractError
          ? `${err.code}: ${err.message}`
          : "Approval decision failed.";
      setApprovals((prev) => {
        const next = new Map(prev);
        const entry = next.get(approvalId);
        if (entry)
          next.set(approvalId, {
            ...entry,
            submitting: false,
            decisionError: message,
          });
        return next;
      });
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (!sessionId) {
    return (
      <ScrollView
        style={styles.flex}
        contentContainerStyle={styles.agentContainer}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>Agent Workspace</Text>
        <Text style={styles.subtitle}>JSON replay · no streaming</Text>

        <Pressable
          style={[styles.send, loadingSession && styles.sendDisabled]}
          onPress={handleCreateSession}
          disabled={loadingSession}
        >
          <Text style={styles.sendText}>
            {loadingSession ? "Creating…" : "New Session"}
          </Text>
        </Pressable>

        <Text style={styles.orDivider}>— or resume —</Text>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={resumeInput}
            onChangeText={setResumeInput}
            placeholder="Session ID…"
            accessibilityLabel="Session ID"
            autoCapitalize="none"
          />
          <Pressable
            style={[styles.send, !resumeInput.trim() && styles.sendDisabled]}
            onPress={handleResumeSession}
            disabled={!resumeInput.trim()}
          >
            <Text style={styles.sendText}>Resume</Text>
          </Pressable>
        </View>

        {agentError && <Text style={styles.error}>{agentError}</Text>}
      </ScrollView>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        style={styles.flex}
        contentContainerStyle={styles.agentContainer}
        keyboardShouldPersistTaps="handled"
      >
        {/* Session info */}
        <View style={styles.sessionBar}>
          <Text style={styles.sessionLabel} numberOfLines={1}>
            Session: {sessionId}
          </Text>
          <Pressable
            onPress={() => {
              setSessionId(null);
              setTaskId(null);
              setEvents([]);
              setApprovals(new Map());
              setFinalResult(null);
            }}
          >
            <Text style={styles.changeLink}>Change</Text>
          </Pressable>
        </View>

        {agentError && <Text style={styles.error}>{agentError}</Text>}

        {/* Task submission — only shown when no active task */}
        {!taskId && (
          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              value={taskPrompt}
              onChangeText={setTaskPrompt}
              placeholder="Describe the coding task…"
              accessibilityLabel="Task prompt"
              editable={!loadingTask}
              multiline
            />
            <Pressable
              style={[
                styles.send,
                (loadingTask || !taskPrompt.trim()) && styles.sendDisabled,
              ]}
              onPress={handleSubmitTask}
              disabled={loadingTask || !taskPrompt.trim()}
            >
              <Text style={styles.sendText}>
                {loadingTask ? "…" : "Submit"}
              </Text>
            </Pressable>
          </View>
        )}

        {/* Active task + refresh */}
        {taskId && (
          <View style={styles.taskBar}>
            <Text style={styles.sessionLabel} numberOfLines={1}>
              Task: {taskId}
            </Text>
            <Pressable
              style={[styles.refreshBtn, loadingEvents && styles.sendDisabled]}
              onPress={() => refreshTimeline(sessionId, taskId)}
              disabled={loadingEvents}
              accessibilityLabel="Refresh timeline"
            >
              <Text style={styles.refreshText}>
                {loadingEvents ? "…" : "Refresh"}
              </Text>
            </Pressable>
          </View>
        )}

        {/* Pending approval cards */}
        {approvals.size > 0 &&
          [...approvals.values()].map((appr) => (
            <View key={appr.approvalId} style={styles.approvalCard}>
              <Text style={styles.approvalTitle}>Approval required</Text>
              <Text style={styles.approvalDetail}>
                Tool:{" "}
                <Text style={styles.mono}>{appr.toolName}</Text>
                {"  "}
                <Text style={styles.riskBadge}>[{appr.risk}]</Text>
              </Text>
              <Text style={styles.approvalDetail}>ID: {appr.approvalId}</Text>
              {appr.decisionError && (
                <Text style={styles.error}>{appr.decisionError}</Text>
              )}
              <View style={styles.approvalButtons}>
                <Pressable
                  style={[
                    styles.approveBtn,
                    appr.submitting && styles.sendDisabled,
                  ]}
                  onPress={() =>
                    handleApprovalDecision(appr.approvalId, "approved")
                  }
                  disabled={appr.submitting}
                  accessibilityLabel={`Approve ${appr.approvalId}`}
                >
                  <Text style={styles.sendText}>Approve</Text>
                </Pressable>
                <Pressable
                  style={[
                    styles.rejectBtn,
                    appr.submitting && styles.sendDisabled,
                  ]}
                  onPress={() =>
                    handleApprovalDecision(appr.approvalId, "rejected")
                  }
                  disabled={appr.submitting}
                  accessibilityLabel={`Reject ${appr.approvalId}`}
                >
                  <Text style={styles.sendText}>Reject</Text>
                </Pressable>
              </View>
            </View>
          ))}

        {/* Event timeline */}
        {events.length > 0 ? (
          <View style={styles.timeline}>
            <Text style={styles.timelineHeader}>
              Timeline ({events.length} events)
            </Text>
            {events.map((event) => (
              <View
                key={`${event.task_id}-${event.sequence}`}
                style={styles.eventRow}
                accessibilityLabel={`event sequence ${event.sequence}`}
              >
                <Text style={styles.seqNum}>{event.sequence}</Text>
                <View style={styles.eventBody}>
                  <Text
                    style={[
                      styles.eventType,
                      eventTypeStyle(event.event_type),
                    ]}
                  >
                    {event.event_type}
                  </Text>
                  <Text style={styles.eventSummary} numberOfLines={2}>
                    {summariseEventPayload(event)}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        ) : taskId && !loadingEvents ? (
          <Text style={styles.empty}>No events yet — tap Refresh.</Text>
        ) : null}

        {loadingEvents && (
          <ActivityIndicator
            style={styles.spinner}
            accessibilityLabel="Loading events"
          />
        )}

        {/* Final result */}
        {finalResult && (
          <View
            style={[
              styles.resultCard,
              finalResult.kind === "success"
                ? styles.resultSuccess
                : styles.resultError,
            ]}
          >
            <Text style={styles.resultTitle}>
              {finalResult.kind === "success"
                ? "Task completed"
                : `Task failed — ${finalResult.code}`}
            </Text>
            <Text style={styles.resultBody}>
              {finalResult.kind === "success"
                ? finalResult.content
                : finalResult.message}
            </Text>
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

function eventTypeStyle(eventType: string): object {
  switch (eventType) {
    case "completed":
      return styles.eventCompleted;
    case "error":
      return styles.eventError;
    case "approval_requested":
      return styles.eventApproval;
    case "tool_call":
    case "tool_result":
      return styles.eventTool;
    default:
      return styles.eventDefault;
  }
}

function summariseEventPayload(event: AgentEventResponse): string {
  const p = event.payload;
  if (!p) return "";
  switch (event.event_type) {
    case "assistant_output":
      return typeof p["content"] === "string"
        ? (p["content"] as string).slice(0, 100)
        : "";
    case "tool_call":
    case "tool_result":
      return typeof p["tool_name"] === "string" ? String(p["tool_name"]) : "";
    case "approval_requested":
      return typeof p["tool_name"] === "string"
        ? `${String(p["tool_name"])} [${String(p["risk"] ?? "mutating")}]`
        : "";
    case "error":
      return typeof p["message"] === "string"
        ? (p["message"] as string).slice(0, 100)
        : "";
    case "completed":
      return typeof p["content"] === "string"
        ? (p["content"] as string).slice(0, 100)
        : "";
    default:
      return "";
  }
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f8fafc" },
  flex: { flex: 1 },

  // Mode switcher
  modeSwitcher: {
    flexDirection: "row",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#e2e8f0",
  },
  modeTab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: "center",
  },
  modeTabActive: {
    borderBottomWidth: 2,
    borderBottomColor: "#2563eb",
  },
  modeTabText: { fontSize: 14, color: "#64748b" },
  modeTabTextActive: { color: "#2563eb", fontWeight: "600" },

  // Shared
  header: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#e2e8f0",
  },
  title: { fontSize: 18, fontWeight: "600", color: "#0f172a" },
  subtitle: { fontSize: 12, color: "#64748b", marginTop: 2 },
  list: { paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  bubble: { maxWidth: "80%", padding: 12, borderRadius: 12 },
  userBubble: { alignSelf: "flex-end", backgroundColor: "#2563eb" },
  assistantBubble: { alignSelf: "flex-start", backgroundColor: "#e2e8f0" },
  userText: { color: "#ffffff", fontSize: 15 },
  assistantText: { color: "#0f172a", fontSize: 15 },
  empty: {
    color: "#64748b",
    textAlign: "center",
    marginTop: 32,
    fontSize: 14,
  },
  error: {
    color: "#b91c1c",
    paddingHorizontal: 16,
    paddingBottom: 8,
    fontSize: 13,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 8,
    padding: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#e2e8f0",
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    backgroundColor: "#ffffff",
    color: "#0f172a",
    fontSize: 15,
  },
  send: {
    height: 40,
    paddingHorizontal: 16,
    borderRadius: 12,
    backgroundColor: "#2563eb",
    alignItems: "center",
    justifyContent: "center",
  },
  sendDisabled: { backgroundColor: "#94a3b8" },
  sendText: { color: "#ffffff", fontWeight: "600", fontSize: 15 },

  // Agent-specific
  agentContainer: {
    padding: 16,
    gap: 12,
  },
  orDivider: {
    textAlign: "center",
    color: "#64748b",
    fontSize: 13,
    marginVertical: 4,
  },
  sessionBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#e2e8f0",
  },
  taskBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 6,
  },
  sessionLabel: { fontSize: 11, color: "#64748b", flex: 1 },
  changeLink: { fontSize: 13, color: "#2563eb", marginLeft: 8 },
  refreshBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: "#0f172a",
  },
  refreshText: { color: "#fff", fontSize: 13, fontWeight: "600" },

  // Approval card
  approvalCard: {
    backgroundColor: "#fffbeb",
    borderWidth: 1,
    borderColor: "#fcd34d",
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  approvalTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: "#92400e",
  },
  approvalDetail: { fontSize: 13, color: "#78350f" },
  mono: { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  riskBadge: { color: "#b45309" },
  approvalButtons: { flexDirection: "row", gap: 8, marginTop: 4 },
  approveBtn: {
    height: 36,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: "#16a34a",
    alignItems: "center",
    justifyContent: "center",
  },
  rejectBtn: {
    height: 36,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: "#dc2626",
    alignItems: "center",
    justifyContent: "center",
  },

  // Timeline
  timeline: { gap: 4 },
  timelineHeader: {
    fontSize: 13,
    fontWeight: "600",
    color: "#475569",
    marginBottom: 4,
  },
  eventRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    paddingVertical: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#f1f5f9",
  },
  seqNum: {
    width: 24,
    fontSize: 11,
    color: "#94a3b8",
    textAlign: "right",
    paddingTop: 2,
  },
  eventBody: { flex: 1 },
  eventType: {
    fontSize: 11,
    fontWeight: "600",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    alignSelf: "flex-start",
    overflow: "hidden",
    marginBottom: 2,
  },
  eventSummary: { fontSize: 12, color: "#475569" },
  eventDefault: { backgroundColor: "#f1f5f9", color: "#475569" },
  eventCompleted: { backgroundColor: "#dcfce7", color: "#166534" },
  eventError: { backgroundColor: "#fee2e2", color: "#991b1b" },
  eventApproval: { backgroundColor: "#fef3c7", color: "#92400e" },
  eventTool: { backgroundColor: "#dbeafe", color: "#1e40af" },

  spinner: { marginVertical: 16 },

  // Result card
  resultCard: {
    borderRadius: 12,
    padding: 14,
    gap: 6,
    borderWidth: 1,
  },
  resultSuccess: { backgroundColor: "#f0fdf4", borderColor: "#86efac" },
  resultError: { backgroundColor: "#fef2f2", borderColor: "#fca5a5" },
  resultTitle: { fontSize: 15, fontWeight: "600", color: "#0f172a" },
  resultBody: { fontSize: 14, color: "#334155" },
});
