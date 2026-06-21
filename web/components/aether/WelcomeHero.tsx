"use client";
import { motion } from "motion/react";
import { Sparkles, Stethoscope, Users, ShieldCheck, Activity } from "lucide-react";
import { TEMPLATES } from "@/components/aether/templates";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  stethoscope: Stethoscope, users: Users, shield: ShieldCheck, activity: Activity,
};

const FEATURED = ["autopsy", "search", "identity", "health"];

export function WelcomeHero({ onPick }: { onPick: (query: string) => void }) {
  const cards = FEATURED.map((id) => TEMPLATES.find((t) => t.id === id)!).filter(Boolean);
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="flex flex-col items-center text-center py-8">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-on-primary shadow-lg animate-pulse">
        <Sparkles className="h-6 w-6" />
      </div>
      <h1 className="font-display text-2xl font-medium tracking-tight">What can I find for you?</h1>
      <p className="mt-1.5 max-w-sm text-sm text-muted-fg">
        Ask about any document, practitioner, or the pipeline itself. I read your data directly.
      </p>

      <div className="mt-6 grid w-full max-w-lg grid-cols-1 gap-2.5 sm:grid-cols-2">
        {cards.map((t, i) => {
          const Icon = ICONS[t.icon] ?? Sparkles;
          return (
            <motion.button key={t.id} type="button" onClick={() => onPick(t.query)}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.05 }}
              className="group flex items-start gap-3 rounded-xl border border-border bg-surface p-3 text-left transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md hover:border-primary/20">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-tint text-primary transition-transform duration-200 group-hover:scale-105">
                <Icon className="h-4 w-4" />
              </span>
              <span>
                <span className="block text-[13px] font-medium">{t.label}</span>
                <span className="block text-[11px] text-muted-fg">{t.hint}</span>
              </span>
            </motion.button>
          );
        })}
      </div>
    </motion.div>
  );
}
