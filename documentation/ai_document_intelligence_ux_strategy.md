# AI Document Intelligence Platform — UX Architecture & Design Strategy

## Executive Summary

This product is not a single feature; it is a platform with several tightly coupled enterprise workflows:

- document ingestion and processing
- document viewer and navigation
- evaluation and human correction
- retrieval and query exploration
- observability and system monitoring
- authentication and RBAC

The main UX risk is trying to design all of these at once. That creates a visually polished but structurally weak product. The right approach is to design the platform shell first, then the highest-frequency workflow, then the dependent workflows in order of reuse and risk.

The recommended sequence is:

1. Document viewer & navigation revamp
2. Evaluation section revamp
3. Pipeline trigger UI
4. Query & retrieval workspace
5. Observability layer
6. Authentication & RBAC overhaul

This order is sensible because the viewer becomes the shared context surface for evaluation, retrieval, and correction. If the viewer shell is wrong, everything that sits beside it will be reworked later.

The move from Tailwind to MUI should be treated as a design-system migration, not a styling swap. MUI should become the canonical component layer for layout, forms, tables, dialogs, navigation, and feedback states, while domain-specific behaviors remain in feature modules.

---

## Product Framing

### What the platform is

An enterprise AI document intelligence platform is a workbench for inspecting, understanding, validating, and operationalizing document data. Users are not browsing for entertainment; they are trying to complete high-trust tasks quickly and repeatedly.

### Core user jobs

- find the right document fast
- understand what the document contains
- inspect extracted data against source evidence
- correct errors safely
- run or rerun pipelines when needed
- investigate retrieval results
- monitor the health and cost of AI workflows
- work within permissions and audit boundaries

### Primary design objective

Reduce the mental burden of moving between document context, extracted output, validation, and system status.

### Secondary objective

Make the product feel calm, precise, and enterprise-grade rather than experimental or visually noisy.

---

## Why the prompt is strong

The prompt already makes several good architectural decisions:

- it acknowledges that the request spans multiple subsystems
- it explicitly requests decomposition before UI design
- it provides a recommended order
- it identifies an existing codebase and avoids greenfield assumptions
- it adds a Tailwind to MUI migration requirement

That is the right shape of input for a design assistant because it constrains the space enough to produce useful output instead of generic dashboard ideas.

What the prompt still needs is more specificity around:

- the boundaries between shared platform shell and feature modules
- the canonical navigation model
- the principles for migration from utility classes to component-driven UI
- the trust model for AI outputs and corrections
- the relationship between data density and cognitive load

---

## Dependency Analysis

### 1. Document viewer & navigation is foundational

This should come first because it is the common context surface for the rest of the platform.

Everything else depends on it:

- evaluation needs to reference source pages in context
- retrieval needs to show chunks and citations inside the document frame
- pipeline and rerun controls often sit in or near the document workspace
- permissions and access patterns are easiest to understand when attached to document scope

If the viewer is designed after the other modules, each module will invent its own patterns for breadcrumbs, context panels, and page selection.

### 2. Evaluation depends on viewer interaction quality

Evaluation is not a separate activity in this product. It is a review-and-correction layer attached to the source document.

That means the reviewer needs:

- fast page switching
- visible source context
- clear diff between source and extraction
- low-friction corrections
- safe save/submit behavior

Without a strong viewer, the evaluation UI will feel disconnected and error-prone.

### 3. Pipeline triggers are operational, but not isolated

Pipeline execution is simpler than the viewer and evaluation layers, but it still depends on the product shell.

Users need to know:

- which document set they are running against
- whether the pipeline is fresh or stale
- what happens when a rerun is triggered
- whether the action is safe under the current credit or quota situation

The trigger UI should not feel like a random admin button.

### 4. Retrieval workspace depends on navigation and evidence framing

A retrieval UI is only trustworthy if the user can inspect the evidence behind the answer.

That means retrieval must inherit:

- document context
- citation linking
- chunk inspection
- relevance explanation
- result filtering and comparison

The retrieval workspace should feel like a search-and-evidence desk, not a chatbot page.

### 5. Observability is a separate subsystem but shares identity and filtering patterns

Observability may be built later, but it should reuse shared patterns for:

- time ranges
- status chips
- event cards
- drill-down panels
- table sorting and filters

It should also remain consistent with document- and pipeline-scoped views.

### 6. Auth/RBAC should be designed after page hierarchy is stable

Security boundaries are easier to model once the major screens and actions are known.

If RBAC is designed too early, it becomes abstract and over-engineered. If it is designed too late, it creates permission holes and awkward page redesigns.

The right time is after the information architecture has stabilized, but before feature implementation hardens.

---

## Recommended Product Architecture

### Platform shell

The app should have a stable shell that remains consistent across all modules.

Recommended shell elements:

- left navigation rail or sidebar
- top app bar with workspace context
- global search or command palette
- user/account menu
- notification center
- contextual action bar
- persistent right-side details panel where useful

### Feature modules

Each major subsystem should own its own route group and internal layout:

- documents
- evaluation
- pipelines
- retrieval
- observability
- administration

### Shared UI primitives

Use MUI as the foundation for the reusable layer:

- AppBar
- Drawer
- Tabs
- Breadcrumbs
- DataGrid
- Table
- Dialog
- Menu
- Tooltip
- Alert
- Snackbar
- Chip
- Stepper
- Accordion
- Skeleton
- Card
- List
- Divider

Then build domain-specific composites on top of these.

---

## Information Architecture

### Top-level navigation

The IA should be organized by user intent, not by backend systems.

Recommended primary groups:

- Documents
- Evaluation
- Pipelines
- Retrieval
- Observability
- Admin

This gives users a direct way to locate task-oriented areas instead of forcing them through internal product jargon.

### Secondary navigation inside Documents

The document area should support:

- document list
- folder or collection view
- document detail
- page viewer
- document summary
- page summary
- metadata
- source references
- related documents

### Secondary navigation inside Evaluation

The evaluation area should support:

- review queue
- issue list
- record detail
- source evidence
- correction form
- approval or submission state
- history / audit trail

### Secondary navigation inside Retrieval

The retrieval area should support:

- query input
- filters
- answer panel
- source chunks
- relevance explanation
- comparison view
- debug / trace view

### Secondary navigation inside Observability

The observability area should support:

- overview metrics
- event logs
- request traces
- webhook status
- latency and failure analysis
- cost and token usage

### Secondary navigation inside Admin

The admin area should support:

- users
- roles
- permissions
- access groups
- audit logs
- configuration

---

## Navigation Model Recommendation

### Best fit: hybrid persistent sidebar + context header

For this platform, a hybrid model is the strongest fit.

Use:

- a persistent sidebar for major areas
- a top header for page context, breadcrumbs, and actions
- a right detail panel for evidence, metadata, or system context

This reduces cognitive load because users always know:

- where they are
- what they are working on
- what actions apply to the current scope

### Why not a purely top-navigation model

Top navigation becomes cramped once you have many enterprise modules and deep sub-pages.

### Why not a purely drawer-driven model

A drawer-heavy model hides important system structure and makes the app feel unstable.

The hybrid model offers clarity without wasting horizontal space.

---

## UX Principles

### 1. Progressive disclosure

Show only what is needed for the current task. Reveal advanced controls only when the user is in a relevant workflow.

### 2. Recognition over recall

Avoid making users remember page numbers, pipeline names, or filter combinations. Keep context visible.

### 3. Evidence-first interaction

For every AI-generated or extracted result, the source should be one click away.

### 4. Stable layout

The shell should not jump or change structure between modules.

### 5. Safe destructive actions

Reruns, deletes, permission changes, and corrections should be confirmation-backed and auditable.

### 6. Dense but readable

Enterprise software often needs density. Density should come from layout efficiency, not clutter.

---

## Migration Strategy: Tailwind to MUI

### Principle

Do not replace Tailwind classes screen by screen in a visual-only way. Replace the UI architecture underneath the app.

### Phase 1: Establish design tokens

Create a single source of truth for:

- color
- typography
- spacing
- radius
- elevation
- shadows
- status colors
- density modes

These tokens should map cleanly to MUI theme values.

### Phase 2: Build the MUI theme

Define:

- palette
- typography scale
- shape
- shadows
- breakpoints
- component overrides

### Phase 3: Introduce shared MUI primitives

Replace common UI patterns first:

- buttons
- inputs
- dialogs
- menus
- tables
- tabs
- cards
- chips
- alerts

### Phase 4: Migrate shell before features

Move the app shell to MUI first:

- navigation
- header
- layout containers
- side panels

### Phase 5: Migrate the highest-value workflow next

The document viewer should be the first feature module migrated in full.

### Phase 6: Convert feature-by-feature

Migrate evaluation, retrieval, pipeline, observability, and admin sections incrementally.

### What not to do

- Do not mix Tailwind and MUI randomly in the same component without a migration rule.
- Do not duplicate spacing and color logic in both systems.
- Do not preserve broken layout patterns just because they are already implemented.

---

## Document Viewer & Navigation Revamp

### UX goal

Make the document workspace feel like the center of the product.

### Core layout

Recommended three-panel structure:

- left: navigation / document list / collection tree
- center: document viewer
- right: context / metadata / summary / evidence panel

### Why this works

The user can scan documents, inspect the current page, and validate extracted context without leaving the workspace.

### Key features

- page thumbnails or page rail
- page jump controls
- document summary
- page summary
- annotations or highlights
- metadata panel
- related items panel
- keyboard navigation
- deep links to pages and page ranges

### Navigation behavior

The viewer should support:

- next / previous page
- jump to page
- open page summary
- copy page link
- open related context
- preserve scroll state when navigating between items

### MUI mapping

- Drawer for collection tree
- Tabs for document sub-sections
- List for page list or document list
- Card for summary blocks
- Chip for status tags
- Breadcrumbs for location context
- IconButton for compact actions

---

## Evaluation Section Revamp

### UX goal

Make review and correction feel like a structured validation workflow rather than a secondary page.

### Recommended pattern

Use a review workspace with:

- source on one side
- extracted data or model output on the other
- correction actions inline
- audit trail below or in a side panel

### Why this matters

Users should not have to switch between separate screens to compare source and result.

### Important behaviors

- highlight mismatches
- show confidence or extraction certainty carefully
- keep corrections reversible
- preserve reviewer notes
- provide submit/approve actions with clear state changes

---

## Pipeline Trigger UI

### UX goal

Turn pipeline execution into a clear operational control surface.

### Design requirements

- show current pipeline state
- show last run
- show queue or pending jobs
- explain the impact of rerun actions
- prevent accidental repeated triggers

### Good interaction patterns

- primary run button
- secondary rerun / refresh actions
- status banner
- job progress timeline
- confirmation dialog for destructive or expensive runs

---

## Query & Retrieval Workspace

### UX goal

Help users trust and inspect the retrieval process.

### Important views

- query input
- answer panel
- source citations
- chunk list
- filter sidebar
- debugging trace
- similarity or ranking explanation

### Key rule

Never present retrieval output as a black box.

### Recommended pattern

Users should be able to move from:

query -> answer -> source evidence -> document context -> query refinement

without losing the thread.

---

## Observability Layer

### UX goal

Help operators understand what the system is doing, what failed, and what is costing money or time.

### Core metrics

- success rate
- latency
- token usage
- credit consumption
- error rate
- webhook delivery status
- retry count

### UX principle

Observability should be diagnostic, not decorative.

### Recommended views

- overview dashboard
- request log table
- event detail drawer
- pipeline health timeline
- webhook status panel

---

## Auth / RBAC Overhaul

### UX goal

Make access control understandable and safe.

### Recommended model

Use role-based access as the primary mental model, with permission detail available on demand.

### Key screens

- users
- roles
- permissions matrix
- workspace access
- document access
- audit log

### UX risk to avoid

Do not expose a complex permission matrix to non-admin users by default.

Use progressive disclosure and grouped permissions.

---

## Cognitive Load Risks

### High-risk areas

- too many competing side panels
- duplicate navigation paths
- overuse of dense tables without hierarchy
- unclear action ownership between document, pipeline, and evaluation screens
- mixing operational controls and review workflows
- exposing advanced AI diagnostics too early

### Recommended mitigation

- keep one dominant action per screen
- use consistent panel placement
- group related metadata visually
- hide advanced controls behind contextual actions
- default to sane states and expose details only when needed

---

## Design System Guidance for MUI

### Visual direction

Apple-inspired does not mean overly minimal. In enterprise software, it means:

- restrained color usage
- clear spacing
- soft surfaces
- careful elevation
- precise typography
- calm motion

### Theme recommendations

- use a neutral base palette
- reserve accent color for primary actions and highlights
- use semantic colors sparingly and consistently
- prefer soft dividers over heavy borders
- use readable font sizes for dense information

### Component behavior guidelines

- buttons should be visually differentiated by priority
- tables should support density modes
- drawers should retain context and not feel like page replacements
- dialogs should be used only for actions that truly interrupt flow

---

## Recommended Delivery Plan

### Phase 1

Define the platform shell, navigation, tokens, and MUI theme.

### Phase 2

Redesign document viewer and navigation.

### Phase 3

Redesign evaluation inside the new document context.

### Phase 4

Introduce pipeline control UI.

### Phase 5

Build retrieval workspace and evidence inspection.

### Phase 6

Add observability dashboards and logs.

### Phase 7

Finalize auth and RBAC.

---

## Risks

### 1. Overdesigning all screens at once

This causes shallow design and inconsistent patterns.

### 2. Migrating styling without system migration

This creates a mixed UI that feels incoherent.

### 3. Designing AI features without evidence visibility

This reduces trust.

### 4. Designing RBAC before the product structure stabilizes

This causes permission mismatch and redundant complexity.

### 5. Replacing Tailwind with MUI too aggressively

This can disrupt productivity if the migration is not incremental.

---

## Final Recommendation

The strongest framing is:

> This is an enterprise document intelligence platform with a shared shell, a central document workspace, and several dependent operational modules.

Design it in that order.

Start with the shell and the document viewer.
Then layer evaluation, retrieval, pipeline, observability, and RBAC on top of a stable architecture.

If the platform is designed this way, MUI becomes an enabler of consistency rather than a cosmetic swap.
