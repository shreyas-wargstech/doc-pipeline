"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ChatRequest, ChatResponse, ChatMessage } from "@/lib/types";

async function postChat(body: ChatRequest): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
  return res.json();
}

const GREETING = "I'm Aether, your pipeline assistant. Ask me about any document, system health, or pipeline status.";

function makeGreeting(): ChatMessage {
  return { role: "assistant", content: GREETING, timestamp: new Date().toISOString() };
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([makeGreeting()]);

  const [recent, setRecent] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      return JSON.parse(localStorage.getItem("aether:recent") || "[]");
    } catch {
      return [];
    }
  });

  const mutation = useMutation({
    mutationFn: postChat,
    onSuccess: (data, variables) => {
      setMessages((prev) => [
        ...prev,
        {
          role: data.role,
          content: data.content,
          tool_calls: data.tool_calls,
          timestamp: new Date().toISOString(),
        },
      ]);
    },
  });

  const send = (message: string, documentId?: string) => {
    const userMsg: ChatMessage = {
      role: "user",
      content: message,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setRecent((prev) => {
      const next = [message, ...prev.filter((m) => m !== message)].slice(0, 5);
      try {
        localStorage.setItem("aether:recent", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
    mutation.mutate({ message, document_id: documentId });
  };

  const clearThread = () => setMessages([makeGreeting()]);

  const clearRecent = () => {
    setRecent([]);
    try {
      localStorage.removeItem("aether:recent");
    } catch {
      /* ignore */
    }
  };

  return { messages, send, isLoading: mutation.isPending, recent, clearThread, clearRecent };
}
