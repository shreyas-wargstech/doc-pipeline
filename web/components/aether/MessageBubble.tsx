"use client";
import { motion } from "motion/react";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";
import { ToolResultCard } from "@/components/aether/ToolResultCard";

export function MessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  const isUser = message.role === "user";
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25, ease: "easeOut" }}
      className={cn("flex items-start gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
        isUser ? "bg-primary text-on-primary" : "bg-secondary text-on-secondary")}>
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className={cn("min-w-0", isUser ? "max-w-[80%]" : "flex-1")}>
        {message.content && (
          <div className={cn("rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser ? "bg-primary text-on-primary rounded-br-sm" : "bg-surface border border-border rounded-bl-sm")}>
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
        )}
        {!isUser && message.tool_calls?.length ? (
          <div className="mt-2 space-y-2">
            {message.tool_calls.map((tc, i) => <ToolResultCard key={i} result={tc.result} />)}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
