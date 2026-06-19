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

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "I'm Aether, your pipeline assistant. Ask me about any document, system health, or pipeline status.",
      timestamp: new Date().toISOString(),
    },
  ]);

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
    mutation.mutate({ message, document_id: documentId });
  };

  return { messages, send, isLoading: mutation.isPending };
}
