"use client";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

const WORDS = ["understood", "searchable", "verified", "connected"];

export function LoginBrandPanel() {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return;
    const t = setInterval(() => setI((n) => (n + 1) % WORDS.length), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="relative hidden flex-col overflow-hidden p-10 text-[#EAF6F3] md:flex" style={{ background: "radial-gradient(120% 120% at 0% 0%, #0F766E 0%, #0C5F58 55%, #0A4D47 100%)" }}>
      <div className="flex items-center gap-2.5">
        <span aria-hidden className="h-8 w-8 rounded-[9px]" style={{ background: "linear-gradient(135deg,#5EEAD4,#2DD4BF)", boxShadow: "0 4px 14px rgba(45,212,191,.5)" }} />
        <span className="font-display text-lg font-semibold">Docintel</span>
      </div>

      <div className="mt-auto">
        <div className="font-mono text-[10.5px] uppercase tracking-[1.5px] text-[#7FE0D2]">Maharashtra Council of Homoeopathy</div>
        <h1 className="mt-3.5 font-display text-4xl font-semibold leading-[1.08] tracking-tight text-white">
          Every document,<br />
          <span className="italic text-[#5EEAD4]">{WORDS[i]}</span>.
        </h1>
        <p className="mt-4 max-w-sm text-sm leading-relaxed text-[#C6E9E3]">
          The intelligence layer for practitioner registration archives. Scanned bundles in English, Marathi and Hindi
          flow through OCR, extraction and cross-referencing — then become searchable, verifiable, and linked to the registry.
        </p>

        <div className="mt-6 flex flex-col gap-3">
          {[
            ["Read anything", "Mixed-language scans, handwriting, official record books."],
            ["Linked & verified", "Auto-matched against 92K practitioner records by registration no."],
            ["Retrieve by meaning", "Find the right bundle by owner, type, or semantic search."],
          ].map(([title, body], index) => (
            <motion.div
              key={title}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + index * 0.1, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="flex gap-3"
            >
              <span aria-hidden className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[9px] border border-white/20 bg-white/10 text-xs">●</span>
              <div>
                <div className="text-[13px] font-semibold text-white">{title}</div>
                <div className="text-xs text-[#A9D8D0]">{body}</div>
              </div>
            </motion.div>
          ))}
        </div>

        <div className="mt-7 flex gap-7 border-t border-white/15 pt-5">
          {[["92,431", "Registry rows"], ["6", "Pipeline stages"], ["4", "Linked datastores"]].map(([n, l], index) => (
            <motion.div
              key={l}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 + index * 0.08, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="font-display text-xl font-semibold text-white">{n}</div>
              <div className="text-[10.5px] uppercase tracking-wide text-[#8FCEC4]">{l}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
