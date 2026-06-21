"use client";
import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { History } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "@/components/aether/MessageBubble";
import { TypingIndicator } from "@/components/aether/TypingIndicator";
import { Composer } from "@/components/aether/Composer";
import { CommandPalette } from "@/components/aether/CommandPalette";
import { WelcomeHero } from "@/components/aether/WelcomeHero";
import { RecentDrawer } from "@/components/aether/RecentDrawer";

const CHIPS = [
  { label: "Summarize a document", query: "Summarize doc " },
  { label: "Why did it fail?", query: "Why did doc " },
  { label: "System health", query: "System health" },
  { label: "Ask anything…", query: "", accent: true },
];

export default function AetherPage() {
  const { messages, send, isLoading, recent, clearRecent } = useChat();
  const [input, setInput] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const isEmpty = messages.length <= 1;

  useEffect(() => { bottomRef.current?.scrollIntoView?.({ behavior: "smooth" }); }, [messages, isLoading]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    send(text);
    setInput("");
  };
  const pick = (query: string) => {
    if (query && !query.endsWith(" ") && !query.includes("<id>")) { send(query); setInput(""); }
    else setInput(query);
  };

  const historyTrigger = (
    <button
      type="button"
      onClick={() => setHistoryOpen(true)}
      aria-label="Open recent searches"
      className="relative flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12px] font-medium text-muted-fg transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:text-foreground"
    >
      <History className="h-3.5 w-3.5" />
      Recent
      {recent.length > 0 && (
        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-on-primary tnum">
          {recent.length}
        </span>
      )}
    </button>
  );

  return (
    <div className="relative flex h-[calc(100dvh-3.5rem)] flex-col -mx-6 -mt-6 -mb-6 overflow-hidden">
      <div className="absolute inset-0 pointer-events-none opacity-30">
        <motion.div
          animate={{ opacity: [0.3, 0.5, 0.3] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-0 left-1/4 h-96 w-96 rounded-full bg-gradient-to-br from-primary/10 to-transparent blur-3xl"
        />
        <motion.div
          animate={{ opacity: [0.3, 0.5, 0.3] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut", delay: 1 }}
          className="absolute bottom-0 right-1/4 h-96 w-96 rounded-full bg-gradient-to-tl from-secondary/10 to-transparent blur-3xl"
        />
      </div>

      <div className="relative mx-auto flex h-full min-h-0 w-full max-w-4xl flex-1 flex-col px-4 sm:px-6">
        {!isEmpty ? (
          <div className="pt-6">
            <PageHeader title="Aether" subtitle="Ask about any document, pipeline status, or system health." actions={historyTrigger} />
          </div>
        ) : (
          <div className="flex justify-end pt-6">{historyTrigger}</div>
        )}

        <div className="flex-1 min-h-0 overflow-y-auto py-4 pr-2 no-scrollbar">
          <AnimatePresence mode="wait">
            {isEmpty ? (
              <motion.div key="hero" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <WelcomeHero onPick={pick} />
              </motion.div>
            ) : (
              <motion.div key="chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <div className="space-y-4">
                  <AnimatePresence mode="popLayout">
                    {messages.map((msg, i) => <MessageBubble key={i} message={msg} index={i} />)}
                  </AnimatePresence>
                  {isLoading && <TypingIndicator />}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={bottomRef} />
        </div>

        <div className="pb-4">
          <Composer value={input} onChange={setInput} onSubmit={handleSend}
            onSlash={() => { setInput(""); setPaletteOpen(true); }}
            disabled={isLoading} chips={isEmpty ? [] : CHIPS} />
        </div>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onSelect={pick} />
      <RecentDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} recent={recent} onPick={pick} onClear={clearRecent} />
    </div>
  );
}
