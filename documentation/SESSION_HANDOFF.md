# SESSION HANDOFF (brainstorm→plan done; ready to implement)

> Temp file. Delete once implementation is complete. Switching to Sonnet 4.6 medium for execution.

## Where we are

**Task:** Document viewer redesign (warm-editorial foundation, direction B).
**Phase:** Brainstorm + plan COMPLETE and committed. Zero implementation code written yet.

## Resume instructions (Sonnet 4.6 session)

1. Session ritual: read `session_log.md` (newest entry = this task) + `error_fixes.md`.
2. Read the plan: `docs/superpowers/plans/2026-06-14-document-viewer-redesign.md` — 8 TDD tasks, self-contained, exact code per step.
3. Spec (context): `docs/superpowers/specs/2026-06-14-document-viewer-redesign-design.md`.
4. Execute with **superpowers:subagent-driven-development** (recommended) or **superpowers:executing-plans**.
5. All web commands run from `web/`; package manager = npm. Tests: `npx vitest run <file>`; `npx tsc --noEmit`; `npm run build`.

## Key locked decisions (don't relitigate)

- Direction B (refined split), all 3 surfaces, restyle + rich UX.
- Rail = flat icon+title list, collapses to icon strip. Data panel + main sidebar also collapsible. State persisted via `useCollapsible` (Task 1).
- Image zoom/pan = `react-zoom-pan-pinch` (approved). bbox overlays EXCLUDED (no data).
- Bookmarks = server-side per-user, but SPLIT INTO ITS OWN SPEC (Spec 2, not yet brainstormed). Viewer only reserves a disabled bookmark-star slot.

## After implementation

- Verify (Task 8: full `npm test`, tsc, build). Note known pre-existing `action-bar.test.tsx` tinypool crash is unrelated.
- Then: finishing-a-development-branch, and brainstorm **Spec 2 (document bookmarks)**.
- Delete this file.
