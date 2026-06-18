# Frontend Redesign — Crafting Alive Interfaces

> **Scope:** Discard the current MUI-based frontend. Rebuild on shadcn/ui + motion/react + MagicUI with a refined warm-alive aesthetic. Data layer (hooks, API, types) stays intact. Phase 5 UI will build on this foundation.

## 1. Philosophy

The current frontend is functional but flat — MUI components with no motion, no entrance animation, no ambient life. The new design applies the **Crafting Alive Interfaces** checklist to every surface:

1. **Entrance** — nothing appears instantly; staggered fade/blur/slide
2. **Response** — every hover/focus/press is acknowledged with motion
3. **Waiting** — content-shaped skeletons, not spinners
4. **Transition** — drawers, modals, tabs ease; never snap
5. **Theme** — token system, not inline hex; warm tones, low saturation
6. **Type** — deliberate font voice (Geist family); clear hierarchy
7. **Ambient** — subtle always-on motion (gradient pulse, shimmer)

**User constraints (from FIX-049):** Reject futuristic/gamified/spatial/3D/AR/VR. Keep it practical, warm, editorial. Cost-conscious.

## 2. Stack Changes

| Remove | Add |
|--------|-----|
| `@mui/material` + `@mui/icons-material` | `shadcn/ui` (Radix primitives) |
| `@emotion/react` + `@emotion/styled` | `motion/react` (Framer Motion v11) |
| MUI AppBar/Drawer/Menu/Dialog | `shadcn/ui` Sheet, Dialog, DropdownMenu, Sidebar |
| Custom Button/Card/Input primitives | `shadcn/ui` Button, Card, Input + themed overrides |
| `Fraunces` display font | `Geist` (variable, modern, clean) |

Keep: `lucide-react`, `react-query`, `react-zoom-pan-pinch`, `next`.

## 3. Design Tokens (New)

### Colors — Warm Alive Palette
```
background:      #F9F7F4  (warm cream, slightly cooler than current)
surface:         #FFFFFF  (cards/panels)
surface-hover:   #F5F2ED  (hover states)
surface-alt:     #EDE8E0  (subtle fills, sidebar)
foreground:      #1A1714  (rich warm black)
muted-fg:        #7A7268  (secondary text)
tertiary-fg:     #A8A094  (placeholder)
border:          #E4DFD7  (hairline)
border-strong:   #D8D2C8  (input borders)

primary:         #0D9488  (teal — keep, it's the brand)
primary-hover:   #0F766E
primary-tint:    #E8F4F2  (selection bg)
secondary:       #C49A6C  (warm amber/gold — NEW accent for depth)
secondary-hover:#B0854F
secondary-tint: #F5EDE3  (amber wash)

on-primary:      #FFFFFF
ok:              #0F766E
ok-bg:           #E8F4F2
success:         #15803D
success-bg:      #E8F2EA
warn:            #B45309
warn-bg:         #FEF3C7
danger:          #B91C1C
danger-bg:       #FDE8E8
info:            #2563EB
info-bg:         #EFF6FF
```

### Typography — Geist Family
```
Display:  Geist (variable, weight 400-700) — headings, logomark wordmark
Sans:     Geist (same family, weight 400-600) — body, UI text
Mono:     Geist Mono (weight 500) — identifiers, codes, metadata
```

### Shadows — Warm Depth
```
sm:  0 1px 2px rgba(60,45,25,0.04)
md:  0 4px 12px -4px rgba(60,45,25,0.10)
lg:  0 10px 30px -12px rgba(60,45,25,0.16)
xl:  0 24px 60px -24px rgba(60,45,25,0.28)
inner: inset 0 2px 4px rgba(60,45,25,0.04)
```

### Radius
```
base:   8px   (buttons, inputs)
panel:  12px  (cards, panels)
pill:   24px  (badges, tags)
full:   9999px (avatars, icon buttons)
```

### Spacing
8px scale. `gap-2` = 8px, `gap-3` = 12px, `gap-4` = 16px, etc.

## 4. Motion Tokens

```
hover:     150ms  ease-out
press:     100ms  ease-out
entrance:  300ms  cubic-bezier(0.16, 1, 0.3, 1)
exit:      200ms  ease-in
drawer:    400ms  cubic-bezier(0.16, 1, 0.3, 1)
stagger:   60ms   between siblings
ambient:   6000ms linear loop
```

## 5. Component Architecture

### shadcn/ui Components to Install
```bash
npx shadcn@latest init --yes --base-color stone
npx shadcn@latest add button card input dialog dropdown-menu sheet skeleton badge avatar separator scroll-area tooltip
```

### MagicUI Components (copy-paste from catalog)
- `blur-fade` — entrance animation for all content surfaces
- `bento-grid` — dashboard metrics layout
- `number-ticker` — metric counts animate on mount
- `dock` — macOS-style icon toolbar (optional for nav)
- `ripple` — ambient background behind hero/thread
- `shimmer` — skeleton shimmer for loading states

### Custom Components (replace MUI)
| Old (MUI) | New (shadcn/motion) |
|-----------|---------------------|
| AppBar | `header` with `sticky` + `backdrop-blur` |
| Drawer (sidebar) | `shadcn/ui` Sidebar or custom Sheet |
| List/ListItem | Custom nav list with motion hover |
| Menu | `shadcn/ui` DropdownMenu |
| Dialog | `shadcn/ui` Dialog + motion scale |
| IconButton | `shadcn/ui` Button variant="ghost" size="icon" |
| Typography | Tailwind typography classes |
| Box | `div` with Tailwind |

## 6. Shell Design (AppShell)

### Layout
- **Header**: `sticky top-0 z-50`, `backdrop-blur-md bg-background/80 border-b`, height 56px
- **Logo**: teal dot (8px) + "Docintel" wordmark in Geist 600
- **Sidebar**: Collapsible rail, 64px collapsed / 240px expanded, warm surface-alt bg, border-r
- **Nav items**: Icon + label, hover lifts with subtle shadow, active state = primary-tint bg + primary text
- **Main**: `min-h-[calc(100dvh-56px)]` with `p-6` padding (up from `p-2`)
- **Action bar**: Below header, sticky, `border-b bg-surface/80 backdrop-blur`

### Motion
- Sidebar collapse: `motion` width transition, 300ms easeInOut
- Nav items: hover `translateX(2px)` + shadow lift, 150ms
- Header scroll: subtle shadow appears on scroll (via `useScroll` or CSS `scroll-shadow`)
- Page transitions: `AnimatePresence` with cross-fade on route change

## 7. Page Design Notes

### Login
- Two-panel: left = brand (ambient `ripple` background + large logomark), right = form
- Form fields: `shadcn/ui` Input with focus ring animation
- Demo cards: stagger entrance with `blur-fade`

### Documents List (`/`)
- Table → keep structure but add:
  - Skeleton rows matching table row shape while loading
  - Row hover: `bg-surface-hover` + subtle translateX
  - Badge colors from token palette
  - Stagger entrance on filter/sort change

### Document Detail (`/documents/[id]`)
- Page header: `blur-fade` in, bookmark star with scale press
- Metadata cards: `bento-grid` style with hover-reveal
- Page grid: staggered entrance, hover lifts card

### Page Viewer (`/documents/[id]/pages/[n]`)
- Image viewer: `lens` zoom on hover (MagicUI)
- Data panel: `AnimatePresence` slide-in from right
- Zoom controls: `dock` style toolbar

### Pipelines, Eval, Retrieval, Observability, Admin, Audit, Bookmarks, Metrics
- All get the same treatment: shadcn components, motion entrance, skeleton loading, hover states
- Admin tables: keep functionality, add row hover + stagger
- Eval laber: `blur-fade` on page advance
- Retrieval: search bar gets focus animation, results stagger

## 8. Accessibility (keep existing)

- `prefers-reduced-motion`: collapse all motion to instant
- High-contrast mode: keep existing CSS class toggle
- Large-text mode: keep existing CSS class toggle
- Focus-visible: `ring-2 ring-primary ring-offset-2`
- All shadcn components are accessible by default (Radix primitives)

## 9. Phase 5 Foundation

Phase 5 UI will need:
- A clean, extensible component system (shadcn gives us this)
- Motion primitives already in place (motion/react)
- Token system ready for new surfaces (just add tokens)
- Sidebar/nav system that can accommodate new routes
- This redesign is the substrate — Phase 5 adds features, not rewrites foundations

## 10. Migration Strategy

1. **Tooling swap** — remove MUI/Emotion, install shadcn/ui + motion, init shadcn
2. **Tokens + CSS** — rewrite `tokens.ts`, `globals.css`, `tailwind.config.ts`, layout fonts
3. **Shell** — rewrite AppShell without MUI (biggest surface)
4. **Primitives** — replace custom Button/Card/Input/Dialog/Drawer with shadcn + theme overrides
5. **Pages** — restyle each page route (top-to-bottom, keeping JSX structure)
6. **Motion** — add entrance animations, transitions, ambient to all surfaces
7. **Tests** — fix broken imports, update snapshots, keep green
8. **Build** — verify `tsc --noEmit` + `next build` clean

## 11. Files to Touch (comprehensive list)

```
web/package.json                          # remove MUI/Emotion, add motion
web/app/layout.tsx                       # new fonts, new CSS vars
web/app/globals.css                      # new tokens, new utility classes
web/app/(dash)/layout.tsx                # keep structure
web/app/login/page.tsx                   # restyle form
web/app/(dash)/page.tsx                  # restyle documents list
web/app/(dash)/documents/[id]/page.tsx   # restyle detail
web/app/(dash)/documents/[id]/pages/[n]/page.tsx  # restyle viewer
web/app/(dash)/pipelines/page.tsx        # restyle
web/app/(dash)/eval/page.tsx             # restyle
web/app/(dash)/eval/[id]/page.tsx        # restyle
web/app/(dash)/retrieval/page.tsx        # restyle
web/app/(dash)/observability/page.tsx    # restyle
web/app/(dash)/admin/page.tsx            # restyle
web/app/(dash)/audit/page.tsx            # restyle
web/app/(dash)/bookmarks/page.tsx        # restyle
web/app/(dash)/metrics/page.tsx          # restyle
web/components/AppShell.tsx              # rewrite (no MUI)
web/components/ui/*                      # replace with shadcn or theme overrides
web/components/AccessibilityToolbar.tsx  # keep, restyle
web/components/Breadcrumbs.tsx           # keep, restyle
web/components/ActionButtons.tsx         # keep, restyle
web/components/DocumentsTable.tsx        # keep, restyle
web/components/BookmarkStar.tsx          # keep, restyle
web/components/LoginBrandPanel.tsx       # restyle
web/components/JsonViewer.tsx            # keep, restyle
web/components/KpiCard.tsx               # keep, restyle
web/components/MetricBar.tsx             # keep, restyle
web/components/ComingSoon.tsx            # keep, restyle
web/components/EvalLabeler.tsx           # keep, restyle
web/components/EvalScorePanel.tsx        # keep, restyle
web/components/EvalQueueTable.tsx        # keep, restyle
web/components/EvalCorrectionForm.tsx    # keep, restyle
web/components/Filters.tsx               # keep, restyle
web/components/PageRail.tsx              # keep, restyle
web/components/retrieval/*              # keep, restyle
web/components/pipelines/*              # keep, restyle
web/components/admin/*                  # keep, restyle
web/lib/tokens.ts                        # rewrite
web/lib/mui-theme.ts                   # DELETE (no MUI)
web/lib/mui-theme.test.ts               # DELETE
web/app/EmotionRegistry.tsx              # DELETE (no Emotion)
web/app/providers.tsx                    # remove MUI/Emotion providers
web/tailwind.config.ts                   # update
```
