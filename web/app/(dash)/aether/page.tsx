"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Send, Bot, User, Loader2, Sparkles, FileText } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useChat } from "@/hooks/useChat";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

/* ------------------------------------------------------------------ */
/*  Message bubble                                                    */
/* ------------------------------------------------------------------ */

function ChatMessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: index * 0.03, duration: 0.25, ease: "easeOut" }}
      className={cn(
        "flex items-start gap-3",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-on-primary" : "bg-secondary text-on-secondary"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-on-primary rounded-br-sm"
            : "bg-surface border border-border rounded-bl-sm"
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.tool_calls.map((tc) => (
              <Badge key={tc.tool} tone="secondary" className="text-[10px]">
                {tc.tool}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Typing indicator                                                  */
/* ------------------------------------------------------------------ */

function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-3"
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-on-secondary">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-3">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="block h-2 w-2 rounded-full bg-muted-fg"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export default function AetherPage() {
  const { messages, send, isLoading } = useChat();
  const [input, setInput] = useState("");
  const [docContext, setDocContext] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    send(text, docContext || undefined);
    setInput("");
  };

  return (
    <div className="flex flex-col h-[calc(100dvh-3.5rem)] -mx-6 -mt-6">
      {/* Ambient background */}
      <div className="absolute inset-0 pointer-events-none opacity-30">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-gradient-to-br from-primary/10 to-transparent rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-gradient-to-tl from-secondary/10 to-transparent rounded-full blur-3xl" />
      </div>

      <div className="relative flex flex-col h-full max-w-3xl mx-auto w-full px-4">
        {/* Header */}
        <PageHeader
          title="Aether"
          subtitle="Ask about any document, pipeline status, or system health."
          actions={
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-fg" />
              <Input
                placeholder="Document context (optional ID)"
                className="max-w-[12rem] font-mono text-xs h-8"
                value={docContext}
                onChange={(e) => setDocContext(e.target.value)}
              />
            </div>
          }
        />

        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-4 py-4 pr-2">
          <AnimatePresence mode="popLayout">
            {messages.map((msg, i) => (
              <ChatMessageBubble key={i} message={msg} index={i} />
            ))}
          </AnimatePresence>
          {isLoading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="pb-4 pt-2">
          <Card className="border shadow-lg">
            <div className="flex items-center gap-2 p-2">
              <Input
                placeholder="Ask Aether something..."
                className="flex-1 border-0 shadow-none focus-visible:ring-0"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                disabled={isLoading}
              />
              <Button
                size="icon"
                loading={isLoading}
                disabled={!input.trim()}
                onClick={handleSend}
                aria-label="Send"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
            {docContext && (
              <div className="px-3 pb-2 flex items-center gap-1.5">
                <Sparkles className="h-3 w-3 text-muted-fg" />
                <span className="text-[10px] text-muted-fg font-mono">
                  Context: {docContext}
                </span>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
