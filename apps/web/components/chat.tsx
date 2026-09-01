"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { streamChat } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || isStreaming) return;
    setInput("");
    setError(null);
    setIsStreaming(true);
    setMessages((previous) => [
      ...previous,
      { role: "user", content: prompt },
      { role: "assistant", content: "" },
    ]);

    await streamChat(
      { prompt, user_id: "web" },
      {
        onDelta: (content) => {
          setMessages((previous) => {
            const next = [...previous];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + content };
            return next;
          });
        },
        onMessage: (response) => {
          setMessages((previous) => {
            const next = [...previous];
            next[next.length - 1] = { role: "assistant", content: response.message.content };
            return next;
          });
          setIsStreaming(false);
        },
        onError: (contractError) => {
          setMessages((previous) => {
            const next = [...previous];
            if (next.length > 0 && next[next.length - 1].content === "") {
              next.pop();
            }
            return next;
          });
          setError(`${contractError.code}: ${contractError.message}`);
          setIsStreaming(false);
        },
      },
    );
    setIsStreaming(false);
  }

  return (
    <div className="flex w-full max-w-2xl flex-1 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-gray-300 p-4 dark:border-gray-700">
        {messages.length === 0 && (
          <p className="text-sm opacity-60">Send a prompt to chat with the backend.</p>
        )}
        {messages.map((message, index) => (
          <div
            key={index}
            className={
              message.role === "user"
                ? "ml-auto max-w-[80%] rounded-lg bg-blue-600 px-3 py-2 text-white"
                : "mr-auto max-w-[80%] whitespace-pre-wrap rounded-lg bg-gray-200 px-3 py-2 dark:bg-gray-800"
            }
          >
            {message.content || (isStreaming && index === messages.length - 1 ? "…" : "")}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type a prompt…"
          aria-label="Prompt"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-900"
        />
        <button
          type="submit"
          disabled={isStreaming || !input.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {isStreaming ? "Streaming…" : "Send"}
        </button>
      </form>
    </div>
  );
}
