# scorecard.md — Kimi Execution Scorecard

> Claude (Architect) reviews Kimi's (Executor) completed work and scores it here.
> **Kimi:** read **Current Standing** at the start of every job and apply the improvement asks.
> **Claude:** after reviewing a Kimi execution, overwrite **Current Standing** and append a dated entry to **Review Log**.

## Rubric (0–10 each)

| Dimension | What it measures |
|---|---|
| **Correctness** | Does the code do what the plan/spec required? Tests + `make test` green? No regressions? |
| **TDD / Test discipline** | Test-first, meaningful assertions, failing-then-passing cycle, coverage of the deliverable. |
| **Scope adherence** | Built exactly what the task asked — no unrequested scope, no skipped requirements. |
| **Code cleanliness** | Follows existing patterns, DRY, focused files, clear naming, no dead code. |

**Overall** = holistic 0–10 (not a strict average). Verdict = one line.

---

## Current Standing

**Latest overall:** 9/10 — dark-mode plan (2026-06-20), faithful TDD execution, all green.

**Improvement asks for next job:**
1. When execution exposes a plan-level smell, flag it in the handoff. Here: the `[theme]` effect writes `localStorage('docintel:theme','system')` on every fresh mount even when the user never touched the toggle — harmless but noisy. Plan-derived, but worth a one-line note.
2. Keep doing what you did with `app-shell.test.tsx`: when a change breaks an out-of-scope existing test, fixing it with a minimal mock is correct — just call it out in the handoff so the reviewer isn't surprised by a file outside the plan's list.

---

## Review Log

<!-- Newest entry appended at the BOTTOM. Template:

### YYYY-MM-DD — <task / plan reviewed> — Overall N/10
- Correctness: N/10 — note
- TDD/Test discipline: N/10 — note
- Scope adherence: N/10 — note
- Code cleanliness: N/10 — note
- **Verdict:** one line.
- **Do next time:** the 1–3 asks copied into Current Standing.
-->

### 2026-06-20 — dark-mode plan (`docs/superpowers/plans/2026-06-20-dark-mode.md`, 3 tasks) — Overall 9/10
- Correctness: 10/10 — `tsc --noEmit` clean; 20/20 new tests pass (tokens 6, theme 6, toolbar 8); full web suite green; high-contrast specificity (`html.high-contrast` 0,1,1 > bare `.dark` 0,1,0) verified in `globals.css`; no regressions.
- TDD/Test discipline: 9/10 — test files committed per-task with the impl; assertions are meaningful (key-alignment, triplet validity, cycle order, live OS subscription, persistence, no-FOUC class). Can't retro-prove red→green per commit, but structure follows the plan exactly.
- Scope adherence: 10/10 — built exactly the 3 tasks, nothing extra. The one file outside the plan's list (`web/__tests__/app-shell.test.tsx`) was a necessary `@/lib/theme` mock to keep an existing test green — correct diligence, not creep.
- Code cleanliness: 10/10 — DRY `block()` helper for CSS emission; SSR-safe `try/catch` around every `window`/`localStorage`/`matchMedia` matching `accessibility.tsx`; shadow moved to `--color-shadow` var cleanly across tokens + tailwind; icon-cycle (Monitor/Sun/Moon) reads naturally.
- **Verdict:** Textbook execution of an already-strong plan — green, in-scope, idiomatic. Lost half a point only for not flagging the mount-time localStorage write smell.
- **Do next time:** (1) flag plan-level smells you notice mid-execution (e.g. the mount-time `setItem('system')` write); (2) keep calling out necessary out-of-plan test fixes in the handoff.
