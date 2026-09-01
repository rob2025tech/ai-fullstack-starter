import { useCallback, useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ContractError, sendChat } from "./lib/api";

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

export default function App() {
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
      setMessages((prev) => prev.filter((message) => message.id !== placeholder.id));
      setError(contract);
    } finally {
      setPending(false);
    }
  }, [prompt, pending]);

  return (
    <SafeAreaView style={styles.safeArea}>
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
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          renderItem={({ item }) => (
            <View
              style={[
                styles.bubble,
                item.role === "user" ? styles.userBubble : styles.assistantBubble,
              ]}
            >
              <Text style={item.role === "user" ? styles.userText : styles.assistantText}>
                {item.content === "" ? "…" : item.content}
              </Text>
            </View>
          )}
          ListEmptyComponent={
            <Text style={styles.empty}>Send a prompt — the mock backend echoes it back.</Text>
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
            style={[styles.send, (pending || prompt.trim() === "") && styles.sendDisabled]}
            onPress={handleSubmit}
            disabled={pending || prompt.trim() === ""}
          >
            <Text style={styles.sendText}>{pending ? "…" : "Send"}</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f8fafc" },
  flex: { flex: 1 },
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
  empty: { color: "#64748b", textAlign: "center", marginTop: 32, fontSize: 14 },
  error: { color: "#b91c1c", paddingHorizontal: 16, paddingBottom: 8, fontSize: 13 },
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
});
