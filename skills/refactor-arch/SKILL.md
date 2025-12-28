---
name: refactor-arch
description: Architecture/code-pattern refactor audit. Reads repo docs and key code, finds evolution blockers and maintenance issues, and outputs a prioritized refactor task list for human decision (no code changes unless explicitly requested).
---

# Refactor-Arch（架构与代码模式重构审计）

## Scope

Use this skill when the user asks for:
- architecture refactor planning
- finding misalignment with future requirements
- identifying coupling/redundancy/god-files
- producing a prioritized refactor backlog for decision-making

Default behavior: **diagnose + document + task-list only**. Do not change code unless the user explicitly asks to start refactoring.

## Inputs to Read (minimal but sufficient)

1) Project constraints / decision sources
- `AGENTS.md`
- `docs/design/overview.md`
- `docs/design/decisions.md`
- `docs/spec/prompt-contract.md`
- `docs/spec/runtime-feedback-repair.md`
- `docs/spec/model-routing.md`
- `docs/self-test.md`
- `docs/collaboration/todo.md`
- `docs/collaboration/decision-log.md`

2) Key implementation hotspots (sample, expand only if needed)
- `App.tsx`
- `server/index.mjs`
- `server/tools.js`
- `types.ts`
- `components/*`
- `prompts/*`

## Workflow

### Step 1: Extract “Future Requirements” (non-negotiables)

Summarize:
- stability priorities (rollback-first, observability, regression avoidance)
- tool-first / canvas-awareness strategy
- concurrency stance (not now, but don’t lock it out)
- default UX principles (child-first; LLM-first; deterministic code only as safety net)

Prefer concrete bullets. Cite the source files (by path) in the report.

### Step 2: Map the current architecture (“as-is”)

Produce a small architecture map:
- entry points (client/server)
- main flow (chat → model → commands → execution → feedback/repair)
- tool flow (tool_request → tool runner → TOOL_RESULT → final)
- key contracts (schema/types/docs)

### Step 3: Identify blockers

Split findings into two categories:

1) **Evolution blockers** (architecture mismatches vs future needs)
- examples: global mutable state, duplicated protocols, implicit/unstable contracts, split APIs, unbounded retries, unclear ownership boundaries

2) **Maintenance blockers** (code structure issues)
- examples: god files, low cohesion/high coupling, duplicated parsing/validation, scattered constants, ad-hoc fallbacks, unclear layering

Each finding must include:
- Evidence (file/symbol/behavior)
- Risk (why it matters for the stated future requirements)
- Recommended direction (what to change, not how to micro-implement)

### Step 4: Output a prioritized refactor list (decision-ready)

Create a table ordered by priority (P0/P1/P2):
- ID (next free task IDs from `docs/collaboration/todo.md`)
- Title
- Problem
- Recommendation
- Effort (S/M/L)
- Risk (L/M/H)
- DependsOn
- Validation (“自测” checklist items + `npm run build`)

### Step 5: Write artifacts + update todo board

1) Write/update report:
- `docs/design/refactor-arch-report-YYYY-MM-DD.md`

2) Update tasks:
- Add/update items in `docs/collaboration/todo.md` (single source of truth)
- Keep titles short, and include DependsOn + validation notes.

### Step 6: Ask for decisions (before touching code)

Before any refactor implementation, ask the user to choose:
- which P0 items to do first
- whether to deprecate/remove legacy surfaces
- any compatibility constraints (no breaking changes vs acceptable migration)

## Guardrails (stability-first)

- Do not introduce concurrency mechanisms unless requested.
- Prefer contract/versioning/typing work before file-splitting refactors.
- Avoid adding special-case if/else for specific scenarios; prefer prompts/tools/contracts.
- After any implementation work (only when requested): run “自主测试” + `npm run build`, then commit.

