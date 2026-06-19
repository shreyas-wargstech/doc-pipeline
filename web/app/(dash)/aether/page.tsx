"use client";
import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { PageHeader } from "@/components/ui/PageHeader";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "@/components/aether/MessageBubble";
import { TypingIndicator } from "@/components/aether/TypingIndicator";
import { Composer } from "@/components/aether/Composer";
import { CommandPalette } from "@/components/aether/CommandPalette";
import { WelcomeHero } from "@/components/aether/WelcomeHero";

const CHIPS = [
  { label: "Summarize a document", query: "Summarize doc " },
  { label: "Why did it fail?", query: "Why did doc " },
  { label: "System health", query: "System health" },
  { label: "Ask anything…", query: "", accent: true },
];

export default function AetherPage() {
  const { messages, send, isLoading, recent } = useChat();
  const [input, setInput] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
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

  return (
    <div className="flex flex-col h-[calc(100dvh-3.5rem)] -mx-6 -mt-6">
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

      <div className="relative mx-auto flex h-full w-full max-w-3xl flex-col px-4">
        {!isEmpty && <PageHeader title="Aether" subtitle="Ask about any document, pipeline status, or system health." />}

        <div className="flex-1 overflow-y-auto py-4 pr-2">
          <AnimatePresence mode="wait">
            {isEmpty ? (
              <motion.div key="hero" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <WelcomeHero recent={recent} onPick={pick} />
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
    </div>
  );
}
