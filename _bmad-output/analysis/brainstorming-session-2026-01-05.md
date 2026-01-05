---
stepsCompleted: [1, 2]
inputDocuments: []
session_topic: "Prompt/LangGraph orchestration for hard-geometry solving with GeoGebra-verified iteration"
session_goals: "Enhancement plan for stable reasoning, tool-grounded trial-and-error, and UI-visible progress (without relying on hidden chain-of-thought)"
selected_approach: "AI-Recommended Techniques"
techniques_used: ["Constraint Mapping", "Morphological Analysis", "Decision Tree Mapping"]
ideas_generated: []
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Lord
**Date:** 2026-01-05

## Session Overview

**Topic:** Prompt/LangGraph orchestration for hard-geometry solving with GeoGebra-verified iteration
**Goals:** Produce an enhancement plan to improve stability on hard geometry problems, enforce tool-based verification/repair loops, and display progress in the UI even when models do not reveal chain-of-thought.

### Context Guidance

_No external context file provided for this session._

### Session Setup

- Focus on prompt contract + LangGraph node design that drives measurable, tool-grounded iteration.
- Treat “verification via GeoGebra tools” as the default for non-trivial geometry steps.
- For UI visibility, prefer structured progress events (plan items, checkpoints, hypothesis/test/result) over revealing private chain-of-thought.

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** hard-geometry prompt + LangGraph orchestration, tool-based verification loops, and UI-visible progress (without relying on hidden chain-of-thought).

**Recommended Techniques:**

- **Constraint Mapping** — make constraints explicit: what must be hidden vs shown, what the UI can render, what the model can/can’t provide, and what “stability” means operationally.
- **Morphological Analysis** — systematically explore combinations across prompt/graph/tool/UI dimensions to avoid ad-hoc fixes.
- **Decision Tree Mapping** — map run-time branching: when to call tools, when to ask clarifying questions, when to attempt repair, when to stop.

**AI Rationale:** This sequence is optimized for complex systems design (prompt + orchestration + UI), where hidden constraints and branching behavior drive reliability.

## Technique Execution Results

**Constraint Mapping:**

- **Hard constraints (top priority):**
  - **Observability & reproducibility:** we must know why the AI performs poorly and be able to reproduce/evaluate failures (logs, deterministic traces, replayable inputs).
  - **UX split by difficulty:** hard problems should follow a staged loop (phase → hypothesis → verification → revision); simple imperative requests should stay direct (draw/answer).

- **UI minimum viable process signals (hard problems only):**
  - **Phase/Stage** (e.g., understand → plan → test → refine → finalize)
  - **Hypothesis** (what we think will work next)
  - **Verification** (which GeoGebra/tool check we are running)
  - **Result** (pass/fail + what changed)
  - **Next step** (what we will try next)

- **Intentionally unconstrained areas (for now):** model/provider choices, policy constraints, and tool list details unless they impact observability or the hard-vs-simple UX split.

**Morphological Analysis:**

- **Morphological box (dimensions → options):**
  - **A) Difficulty routing:** (A1 heuristics) / **(A2 small-model difficulty classifier)** / (A3 uncertainty or failure escalation)
  - **B) Graph shape:** (B1 direct) / (B2 plan→act→finalize) / **(B3 plan→act→verify→revise loop)**
  - **C) Verification cadence:** (C1 on-demand) / (C2 every key step) / **(C3 layered verify: light→heavy→rollback)**
  - **D) UI process signals:** (D1 final only) / (D2 existing SSE events) / **(D3 structured phase/hypothesis/verify/result/next events)**
  - **E) Repro & eval:** (E1 logs) / **(E2 event-level trace + replay)** / (E3 automated eval suite)

- **Chosen mainline (MVP-A):** **A2 (small-model difficulty classifier, upfront) + B3 + C3 + D2→D3 + E2**
  - Trigger hard-mode up-front from problem features via a small-model classifier; if the classifier is unavailable, fail fast with an explicit error (no fallback).
  - Make verification a first-class loop in the graph, not ad-hoc prompt text.
  - Start by surfacing existing SSE (`plan_update`, `node_*`, `tool_*`) as the UI-visible “thinking process”, then add structured phase events that are safe to show.
  - Persist event streams + tool IO so we can reproduce “why it performed badly” and evaluate changes.
- **Hard-mode trigger decision (user):** Prefer **up-front difficulty routing based on problem features** via a **small-model classifier** (A2), not only runtime failure escalation.
  - Implication: hard-mode is a first-class branch in the graph; classification must emit user-visible reasons for observability.
- **Concrete MVP-A design notes (implementation-facing):**
  - **Difficulty router (hard-mode upfront):** add a small-model classifier that tags requests as `simple|hard` and emits safe, user-visible reasons. **No fallback:** if classifier is unavailable, fail fast with explicit error.
  - **Graph loop (verify-first-class):** `ingest → (difficulty_router) → plan → act → verify → revise (repeat) → finalize`.
  - **Layered verification:** prefer cheap checks first (`get_canvas_state`, `eval_numeric`); escalate to `exec_geogebra_commands`; use `delete_objects` for rollback when a branch fails.
  - **UI visibility without CoT:** treat `plan_update` + `node_start/end` + `tool_start/end` as baseline “thinking trace”; add explicit safe events/fields for `phase/hypothesis/verification/result/next` (summaries, not hidden reasoning).
  - **Repro & evaluation:** keep per-run JSONL traces (already supported by `apps/api/app/debug_trace.py` when `ui_debug=true`); add lightweight run summaries/metrics so failures can be replayed and compared across prompt/graph changes.
**Decision Tree Mapping:**

- **Runtime decision tree (high level):**
  1) **Ingest user request**
     - If request is empty/invalid → return user-friendly error
  2) **Difficulty classify (small model, required)**
     - If classifier fails/unavailable → **fail fast** with explicit error + trace
     - If `simple` → route to **direct act** (minimal UI trace)
     - If `hard` → route to **staged loop** (UI shows phase/hypothesis/verify/result/next)
  3) **Hard-mode staged loop (repeat until done or stop condition):**
     - **Phase: Understand** → extract givens/targets; if ambiguous → ask clarifying question
     - **Phase: Plan** → emit `plan_update` (high-level, safe) + phase summary
     - **Phase: Act** → propose next construction step(s)
     - **Phase: Verify (layered)**
       - Light checks: `get_canvas_state`, `eval_numeric` / `eval_expression`
       - If insufficient → execute: `exec_geogebra_commands`
       - If branch fails → rollback via `delete_objects` (and record rollback)
     - **Phase: Revise**
       - If verify failed → update hypothesis, adjust plan, loop
       - If verify passed → advance to next step or finalize
     - **Stop conditions:**
       - Success criteria met → finalize
       - Too many failed attempts / no progress → ask user for missing info or return “unable” with trace-friendly summary
  4) **Finalize**
     - Provide child-first explanation (concept + steps)
     - Provide minimal, structured debug trail for developers (events already captured)

- **UI mapping:**
  - **Baseline (D2):** show `plan_update`, `node_start/end`, `tool_start/end`, `interrupt`/`resume` timeline
  - **Enhanced (D3):** add explicit `phase_update` events with fields: `phase`, `hypothesis`, `verification`, `result`, `next`

- **Observability hooks:**
  - Persist per-run JSONL trace (input + classification + SSE events + tool IO + errors)
  - Ensure classification reasons and phase updates are included in trace for reproducibility
