# Subordina — v1 design

*Date: 2026-04-17 · Author: brainstorming session*

> ## ⚠ PIVOT NOTICE (2026-04-17, post-Task-12)
>
> After Tasks 1-12 + Task 10b landed, the founder clarified the monetisation path: **build a CLI first, validate demand with ~10 ML researchers, then build the web SaaS if validation succeeds.**
>
> **v1 ships as a CLI (`subordina` Python entrypoint), not a web app.** The backend code built in Tasks 1-12 is a library the CLI uses directly; no HTTP routers, no SSE, no frontend in v1.
>
> The chat-dominant UI spec below (sections 4.2, 5.2, visual register) remains authoritative design material for **v2 (web SaaS)** if CLI validation succeeds. Read it as "how the web version will look when we build it," not "what v1 ships."
>
> Concretely, for v1:
> - User interaction: `subordina say "..."`, `subordina /inquiry "..."`, `subordina /convergence "..."`
> - Persistence: SQLite in `.subordina/state.db` inside the user's project folder
> - Streaming: stdout with a simple progress header; no SSE
> - Auth / monetisation: deferred to v1.1 — v1 uses the user's own `ANTHROPIC_API_KEY`
> - Plan 2 (frontend) is indefinitely deferred; do not build without an explicit green light after CLI validation
>
> Sections 4.1 (backend modules), 5.1 (data flow), 6 (data model), 7 (error handling), 8 (testing), 9 (non-functional) remain correct. Only the delivery surface changed from web UI to CLI.

## 1. Summary

Subordina is a web application that wraps a set of enforcement-driven ML research skills — originally built as a Claude Code plugin — in a researcher-facing UI. The point of the app is not to replace the plugin; it is to prove, in a standalone surface that could eventually become a company, that the **enforcement-driven agentic loop** is load-bearing, legible, and worth using.

v1 ships two of the nine eventual skills: `Inquiry` (verified Q&A, 2-iteration review loop) and `Convergence` (iterated architecture search, convergence loop with ≥3 iterations and 2 consecutive defenses). Together they exercise both enforcement patterns and validate the framework before the other seven skills are added module-by-module.

This document is the frozen design that implementation must follow. The implementation plan is a separate artifact produced by the *writing-plans* step after this spec is approved.

## 2. Scope

### In v1.0

- **Three interaction modes** in the chat: plain chat (default) plus two rigorous skills — `Inquiry` and `Convergence`.
- **Chat-dominant UI.** Chats belong to a project; each chat is bound to a folder (`chat.root_path` override, defaulting to `project.root_path`). Skills invoked via slash commands (`/inquiry`, `/convergence`); everything else is plain chat.
- **File + web tools.** All three modes (plain chat, Inquiry, Convergence) can read and write inside the chat's folder, and do web searches. No code execution, no GPU — those arrive with `Experiment` in v1.5.
- **Local web application** (FastAPI backend + Next.js frontend).
- **Single-project UI; SQLite schema is multi-project-ready** from day 1.
- **Hand-rolled agent loop** against the primary model API, with enforcement inline. `runner_raw.py` is v1; `runner_agent_sdk.py` is a documented future swap.
- **Async task per invocation, SSE for progress, DB checkpoints** after every model turn.
- **No mid-skill intervention.** Skills run uninterrupted to completion. Cancel is the only control during a running skill.
- **Scholarly visual register** with softened edges (8-10px radius, subtle shadows).

### Deferred, in order

| Module | Skill added | Why this order |
|---|---|---|
| v1.1 | `Survey` (was: `literature-review`) | Same shape as `Convergence`; no new infrastructure |
| v1.2 | `Implementation` (was: `implement`) | Code-artifact handling; no GPU yet |
| v1.3 | `Revision` (was: `write`) | Markdown section editing; textarea is enough |
| v1.4 | `Manuscript` (was: `paper`) | LaTeX cliff — Monaco + KaTeX preview + BibTeX list |
| v1.5 | `Experiment` | GPU cliff — job runner, training-curve streaming, GPU telemetry |
| v1.6 | `Analysis` (was: `results`) | Plotting + statistical tests over stored experiment data |
| v1.7 | `Extension` (was: `reexp`) | Reuses v1.5 infrastructure |
| v2.0 | UI polish pass | Animated score changes, smoother streaming, side-by-side critique diff — after the skill set has stabilised |

### Out of scope (for v1.0 and beyond, unless stated)

- Authentication, sharing, collaboration, multi-user — schema is ready but no UI
- Multi-model abstraction layer — deferred until a second model is actually introduced
- Provenance as a public feature — internal tracing stays, no "provenance moat" marketing
- Integrations (GitHub, W&B, Overleaf, Slack) — slot exists in backend, no integrations ship in v1
- Public cost display — internal cost tracking is mandatory; surfacing money to the user is out
- Any vendor names in user-facing copy — the UI never mentions the model vendor

## 3. Architecture

### 3.1 Top-level layout

```
subordina-app/
├── backend/                       # Python 3.11+, FastAPI
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── skills.py              # POST /api/skills/{name}/start
│   │   ├── invocations.py         # CRUD + cancel
│   │   └── events.py              # SSE stream
│   ├── agent/
│   │   ├── runner.py              # AgentRunner abstract base (swap point)
│   │   ├── runner_raw.py          # v1 hand-rolled implementation
│   │   └── tools.py               # Tool definitions + handlers
│   ├── enforcement/               # Copied from plugin, raises instead of sys.exit
│   │   ├── review_loop.py
│   │   ├── research_loop.py
│   │   └── critique_quality.py
│   ├── skills/
│   │   ├── base.py                # Skill dataclass
│   │   ├── query.py               # "Inquiry" backend
│   │   └── deep_research.py       # "Convergence" backend
│   ├── db/
│   │   ├── models.py              # SQLAlchemy
│   │   └── session.py
│   ├── integrations/              # Empty slot for v2+
│   └── pyproject.toml
├── frontend/                      # Next.js 14 App Router, TypeScript
│   ├── app/
│   ├── components/
│   ├── lib/
│   │   ├── api.ts
│   │   ├── events.ts              # SSE hook
│   │   └── vocabulary.ts          # slug → UI name mapping (one file)
│   └── package.json
├── docs/
│   └── superpowers/specs/         # This file lives here
├── package.json                   # Root: npm run dev orchestrates both
├── .env.example
└── CLAUDE.md
```

### 3.2 Three explicit swap points

Designed so future changes are one file, not a rewrite.

1. **`agent/runner.py`.** `AgentRunner` is an abstract class. `runner_raw.py` is the v1 implementation. If we ever decide the Agent SDK is worth the boilerplate reduction, `runner_agent_sdk.py` drops in as a peer.
2. **`enforcement/` copied from the plugin.** v1 copies the three modules verbatim and adapts them to raise exceptions rather than `sys.exit`. Later, both the plugin and the app should consume a shared `subordina-core` package — but that's a refactor that waits until the API surface has stabilised.
3. **`db/models.py`.** Every entity has `id`, `created_at`, `updated_at`, and `user_id` from day 1. For v1, `user_id` is a single hardcoded value. When authentication becomes real, the schema is already there.

### 3.3 Process model

- **Development.** Root `package.json` script uses `concurrently` to run backend (`uvicorn --reload`) and frontend (`next dev`) together. Two ports, logs interleaved. Frontend reads `NEXT_PUBLIC_API_URL`.
- **Production (you running it daily).** `npm run build` produces a static Next.js bundle; FastAPI mounts it at `/` and routes `/api/*` to the backend. One process, one port, one command.

## 4. Components

### 4.1 Backend modules

| Module | Purpose |
|---|---|
| `main.py` | FastAPI app instance, router mounts, static-file serving in prod |
| `config.py` | Reads API key, model name, DB path, project root |
| `routers/projects.py` | Projects CRUD: `POST /api/projects`, `GET /api/projects` |
| `routers/chats.py` | Chats CRUD: `POST /api/chats` (accepts optional `root_path` override), `GET /api/chats?project_id=`, `PATCH /api/chats/{id}` (rename) |
| `routers/skills.py` | `GET /api/skills` (list skills), `POST /api/skills/{slug}/start` — accepts `chat_id` |
| `routers/invocations.py` | `GET /api/invocations`, `GET /api/invocations/{id}`, `POST /api/invocations/{id}/cancel` |
| `routers/events.py` | `GET /api/invocations/{id}/events` — Server-Sent Events |
| `agent/runner.py` | Abstract base: `run(invocation) -> None`, `cancel()` |
| `agent/runner_raw.py` | Drives the loop using the raw LLM API; inline enforcement; checkpoints per turn; for `loop_type="plain"` runs exactly one turn and terminates on `end_turn` |
| `agent/tools.py` | Tool schema definitions and Python handlers: `web_search`, `read_file`, `write_file`, `submit_draft`, `submit_review`, `submit_revision`, `record_candidate`, `challenge_leader`, `record_final`, `finalize` |
| `skills/base.py` | `Skill` dataclass: `slug`, `display_name`, `system_prompt`, `tools`, `max_iterations`, `loop_type` (review \| convergence \| plain) |
| `skills/chat.py` | `Skill(slug="chat", display_name="chat", loop_type="plain", ...)` — plain Q&A with file + web tools, no enforcement |
| `skills/query.py` | `Skill(slug="query", display_name="Inquiry", ...)` — system prompt, checklist, 2-iteration review loop |
| `skills/deep_research.py` | `Skill(slug="deep-research", display_name="Convergence", ...)` — system prompt, 5-axis scoring, convergence loop |
| `enforcement/review_loop.py` | Ported from plugin; enforces ≥50-char critique, finalization gate |
| `enforcement/research_loop.py` | Ported; enforces ≥3 iterations, 2-streak before `record_final` |
| `enforcement/critique_quality.py` | Mechanical checks: length, rubber-stamp patterns, substance |
| `db/models.py` | `Project`, `Chat`, `Invocation`, `Checkpoint`, `Message`, `ReviewLoopState`, `Candidate` |
| `db/session.py` | SQLAlchemy 2.0 async engine, session factory |

### 4.2 Frontend modules

| Module | Purpose |
|---|---|
| `app/page.tsx` | Project selector / new-chat landing |
| `app/chats/[id]/page.tsx` | Chat thread — the primary surface |
| `components/Sidebar.tsx` | Chats in the current project; nine methods greyed/active per version |
| `components/Chat.tsx` | Chat thread container; renders messages in order |
| `components/Composer.tsx` | Input with `+` (attach, v2), send/cancel, slash-command hint |
| `components/PlainBubble.tsx` | Dashed-border assistant bubble for plain chat turns |
| `components/InquiryBubble.tsx` | Solid-border assistant bubble for Inquiry; in-progress and verified states |
| `components/ConvergenceBubble.tsx` | Solid-border bubble for Convergence; inline candidates expansion |
| `components/ReasoningTrace.tsx` | Streaming text pane with `[role]` line markers, rendered inside a bubble |
| `components/ReviewHistoryDrawer.tsx` | Expansion: reviewer critiques on a single timeline |
| `components/EvidenceTrail.tsx` | Expansion: which source supports which claim |
| `components/CandidatesTable.tsx` | 5-axis scored candidates with disposition |
| `components/ConvergenceTrace.tsx` | Tufte-style line of numerals showing leader score by iteration |
| `lib/api.ts` | Typed REST client; Zod-validated responses |
| `lib/events.ts` | `useInvocationEvents(id)` hook wrapping EventSource |
| `lib/slash.ts` | Parses a user message to detect `/inquiry` / `/convergence` — routes to the right skill |
| `lib/vocabulary.ts` | One file mapping `slug → display name` and internal status terms to UI terms |

### 4.3 Vocabulary (slug → UI name)

The backend never uses these display strings. `lib/vocabulary.ts` is the single translation point.

| Backend slug / term | UI display |
|---|---|
| `query` | Inquiry |
| `deep-research` | Convergence |
| `literature-review` | Survey |
| `implement` | Implementation |
| `write` | Revision |
| `paper` | Manuscript |
| `experiment` | Experiment |
| `results` | Analysis |
| `reexp` | Extension |
| `leader` | preferred candidate (★) |
| `streak`, `survived n` | *n defenses* / *defended* |
| `challenger` | critique (in trace) / *adversarial review* (in prose) |
| `defeated` | *superseded* |
| `active` | *under consideration* |
| `iter` | *iteration* (spelled out) |
| `finalized` | *verified* |
| `escalated` | *deferred to author* |
| `running` | *in progress* |
| `Score` (column) | Σ |
| `Status` (column) | Disposition |

## 5. Data flow

### 5.1 Skill invocation lifecycle

1. **User starts a skill.** UI posts to `/api/skills/{slug}/start` with `{ project_id, input, context }`. Backend inserts an `Invocation` row, spawns an `asyncio.create_task` running the agent loop, returns `202` with the `invocation_id`.
2. **UI subscribes to events.** `GET /api/invocations/{id}/events` opens an SSE stream. Typed events:
   - `token_chunk` — partial tokens for the reasoning trace
   - `tool_call` — a tool was invoked (name + args)
   - `tool_result` — a tool returned (name + result)
   - `state_change` — an enforcement gate fired (pass/fail + which)
   - `user_intervention` — echoed back so the trace in the UI stays consistent
   - `checkpoint` — a DB checkpoint was written (revision number)
   - `finalized` — invocation completed successfully
   - `escalated` — invocation exited in an unrecoverable state
   - `error` — unrecoverable backend error
3. **The loop.** Per turn:
   - Call the model API with the current conversation + tool definitions, streaming responses
   - Forward token chunks to SSE
   - On a `tool_use` block: dispatch to the matching handler in `agent/tools.py`
     - Handlers that mutate state run their enforcement gate inline and raise a typed error on failure
     - Enforcement errors are returned to the model as an error block; the model self-corrects in the next turn
   - Append `tool_result` to the message history
   - Write a `Checkpoint` row with the full message state, iteration number, and running cost
   - Check the cancellation flag; if set, terminate cleanly
   - Check the cost cap; if exceeded, terminate with status `cost-capped`
   - Loop until the skill's `finalize` tool succeeds, or the skill-specific iteration limit is hit
4. **Folder resolution.** When a skill starts, the runner resolves the working folder as `chat.root_path ?? project.root_path`. The `ToolExecutor` is constructed with this resolved path; every `read_file` / `write_file` call is sandboxed to it by `_safe_join`, which rejects any path that escapes the resolved root.
5. **Plain chat turns.** The `chat` skill (`loop_type="plain"`) runs exactly one model turn and terminates on `end_turn`. No review loop, no convergence loop, no enforcement — just a streamed response with the same file and web tools available. Plain-chat invocations end with status `replied` instead of `verified`.
6. **Cancellation.** `POST /api/invocations/{id}/cancel` flips a flag. The loop checks between turns only; no mid-tool kill. Partial state is preserved.
7. **Finalization.** When a skill's `finalize` tool succeeds (which itself runs the enforcement finalisation check), backend marks the invocation `verified`, emits a final SSE event, and the UI fetches the artifact. `Convergence` terminates on successful `record_final` with the same status.
8. **No mid-skill intervention.** While a skill invocation is running, the UI composer is locked to *Cancel* only. The loop runs to completion uninterrupted. If the user wants to change direction, they cancel and re-invoke. This simplification was chosen deliberately; reinstating mid-run intervention is a future consideration, not v1.
9. **Reload-resilience.** SSE is best-effort. On reload, the frontend re-subscribes and also fetches the latest `Checkpoint` to render current state. The DB is the source of truth.

### 5.2 Interaction model (amended — chat with punctual skills)

The primary user-facing surface is a **chat thread**. Chats belong to a project; each chat is bound to a folder (the project's `root_path` by default, optionally overridden on creation). Default interaction is plain chat — normal Claude conversation against the chat's folder. Rigorous skills are invoked punctually.

- **Plain chat is the default.** A message without a slash command runs as a plain-chat turn. No review loop, no verification, no confidence badge. Just a streamed response from the model, with `read_file` / `write_file` / `web_search` available. Plain chat bubbles are visually distinct (dashed border, header *Subordina · chat*).
- **Skills are invoked on demand.** A message beginning with `/inquiry` or `/convergence` starts that skill. The rigorous loop runs to completion. While it runs, the composer is locked to *Cancel only*. On completion, the verified artifact arrives as the next assistant bubble (solid border) with expansion affordances for review history, evidence trail, and reasoning trace.
- **After a skill completes, the conversation returns to plain chat.** The next message without a slash is plain chat, not a fresh skill invocation.
- **Chat is bound to a folder.** Every chat has an effective `root_path`. Tools operate on that folder only; path-traversal is blocked.
- **No mid-skill intervention in v1.** The loop runs uninterrupted. Cancel + re-invoke is the escape hatch; mid-run annotation/flag/steer is deferred.
- **Follow-ups are natural.** A follow-up is simply the next message in the same chat thread. Prior messages are included as context automatically.
- **Every turn — plain chat or skill — is an `Invocation` in the backend.** The chat skill has `loop_type="plain"`; Inquiry has `loop_type="review"`; Convergence has `loop_type="convergence"`. The runner treats all three, terminating each appropriately.

## 6. Data model

### 6.1 Entity sketch

```
Project
  id, name, root_path, created_at, updated_at, user_id
  // root_path is required; the default folder for chats in this project

Chat
  id, project_id, title, root_path, created_at, updated_at, user_id
  // root_path is optional (nullable); null = inherit from project
  // title is a short human label (first user message truncated is fine)

Invocation
  id, chat_id, skill_slug, input, status,
  created_at, updated_at, user_id,
  total_cost_cents (internal), max_cost_cents (internal)
  // status ∈ {running, verified, replied, deferred, cost-capped, cancelled, error}
  // - verified: review-loop or convergence-loop skill completed successfully
  // - replied: plain-chat skill completed (single turn, end_turn)

Checkpoint
  id, invocation_id, iteration, conversation_json,
  running_cost_cents (internal), created_at
  // one row per model turn

Message
  id, invocation_id, role, content, created_at
  // role ∈ {system, user-prompt, agent, tool}
  // - agent: every model turn regardless of sub-role (researcher/reviewer/challenger)

ReviewLoopState
  id, invocation_id, skill_slug, iteration, status,
  max_iterations, drafts_json, reviews_json
  // status ∈ {reviewing, revising, passed, failed, escalated}

Candidate      // Convergence only
  id, invocation_id, name, evidence_json,
  score_theoretical, score_empirical, score_feasibility,
  score_complexity, score_novelty, composite_score,
  disposition
  // disposition ∈ {preferred, under-consideration, superseded}
```

### 6.2 Cost tracking is internal

Every `Checkpoint` writes the running cost in cents. The `Invocation` has a `max_cost_cents` cap. Both are surfaced through `/api/admin/cost-report` for operator use but never rendered in the researcher UI. This is deliberate — the user should not be scared to click buttons, and the interface should not talk about money.

## 7. Error handling

| Failure | Response |
|---|---|
| Model API transient error (rate limit, 5xx) | Exponential backoff, up to 3 retries; then fail invocation with status `error`, log full context |
| Model API auth error | Fail immediately; do not retry |
| Tool handler exception (Python error) | Return error block to the model; the model may retry or escalate |
| Enforcement gate fails | Return the gate's error to the model; model self-corrects on next turn. If the same gate fails on two consecutive turns on the same subject, escalate |
| Loop hangs (no progress, no tool calls) | Each skill has a `max_turns`; hitting it escalates with the last state intact |
| Cost cap exceeded | Terminate the invocation with status `cost-capped`; keep all checkpoints; UI shows the last state (no money mentioned in the user copy — phrasing is "resource limit reached for this invocation") |
| Cancellation race with in-flight tool | Cancellation flag is only checked between turns; in-flight tool completes. No mid-tool kill |
| SSE client disconnection | Server keeps running; on reconnect the client reads checkpoint state to catch up; event buffer holds last N events per invocation for resumption |
| DB write failure | Log, fail the invocation with status `error`; state prior to the failure is preserved via WAL |
| Skill finalization called before loop passed | Enforcement module raises; the agent sees the raise and keeps working |
| Unknown skill slug on `/skills/{slug}/start` | Return `404`; no invocation created |
| Invalid `chat_id` on `/skills/.../start` | Return `404`; no invocation created |
| Folder doesn't exist when resolved at skill start | Return `400`; invocation not created; UI prompts to set `chat.root_path` |

### Failure modes that are not handled in v1

- Multi-user concurrency (single-user app)
- Offline mode (the API is a hard dependency)
- Long-term archival (all state lives in one SQLite file; backup is the user's responsibility)

## 8. Testing strategy

- **Unit tests for enforcement modules.** Port the plugin's existing tests for `review_loop`, `research_loop`, `critique_quality`. These are the load-bearing pieces; break them and the whole thesis breaks.
- **Unit tests for skill modules.** System prompt content, tool list presence, checklist structure — snapshot-style tests catch accidental drift.
- **Agent-runner integration tests with a mocked LLM.** The test injects a `MockLLMClient` that returns pre-scripted responses (token chunks, tool calls, stop reasons). The test asserts the runner drives the loop correctly, checkpoints at the right moments, and raises on enforcement failures.
- **End-to-end test.** Using the mocked LLM, start an invocation via the HTTP API, subscribe to SSE, simulate the full loop, verify the final DB state and the artifact content.
- **No live-API tests in CI.** Too expensive, too flaky, slow. Fixtures are recorded via a small helper that captures a real session and replays it.
- **Frontend.** Component tests for each major surface using recorded SSE streams as fixtures. No live backend required. End-to-end happy-path test with Playwright, mocked API.

### What we are explicitly not testing in v1

- Performance under load (single-user)
- Multi-browser compatibility (Firefox + Chrome on dev's machine)
- Accessibility (will come with the v2.0 polish pass)

## 9. Non-functional requirements / migration paths

These aren't features; they're properties the architecture must keep true.

1. **Enforcement is never a prompt.** Every gate is a Python function that raises or returns. If any future change puts a gate in the system prompt, it violates this.
2. **The model vendor is not mentioned to the user.** No strings in the frontend reference the vendor's name. All such references live in `backend/config.py` and `backend/agent/runner_raw.py` only.
3. **Money is never displayed to the user.** Cost is tracked, capped, surfaced to operator routes. Not in the UI.
4. **Agent-loop swap is one file.** The day we want to try the Agent SDK, `runner_agent_sdk.py` drops in as an `AgentRunner` implementation. No other file changes.
5. **Vocabulary is one file.** `lib/vocabulary.ts`. Rename the user-facing vocabulary freely; backend doesn't care.
6. **Skill addition is additive.** Adding `Survey` in v1.1 must not require changes to `Inquiry` or `Convergence` code paths. The framework becomes the abstraction only once the duplication makes it obvious what the abstraction should be.
7. **Every entity has `user_id` from day 1.** Even though v1 has one hardcoded user, the column exists. Multi-user arrives by populating that column correctly, not by migrating a schema.

## 10. Visual register

- Background `#f5f1e8` (warm cream)
- Body text `#1a1a1a` serif (Iowan Old Style / Charter / Georgia fallback)
- Numerals and code in monospace (Latin Modern Mono / Iosevka / Menlo)
- Hairline rules (0.5px `#999`) for table borders; 1px `#1a1a1a` for section dividers
- Status as italic prose, not coloured badges
- Roman numerals for iteration counts and sidebar ordering
- No chart fills; convergence shown as a line of numerals with thin underlines
- Polish (animations, shadcn/ui component uplift, side-by-side diff, radar charts) is v2.0 — explicitly not in v1

## 11. Open questions (to be resolved during implementation)

- Which exact web-search tool to use for `Inquiry` and `Convergence`. The API's built-in web search is one option; a dedicated search provider is another. This is a runner-level decision; the skill code shouldn't care.
- Exact SSE event schema — field names and envelope shape. Drafted here, finalised in the implementation plan.
- Whether the frontend exposes a per-chat folder picker at creation time, or defers folder override to a chat-settings panel. Frontend plan decision.
- Whether plain-chat turns should also be visible in the `/api/invocations` list, or filtered out by default since they are trivial. Backend plan decision.

## 12. What this spec does not include

- Business model, pricing, distribution
- Adversarial-review "wedge" positioning (per the verification session, this requires customer interviews before commitment)
- Multi-model adversarial review (deferred; requires multi-model abstraction first)
- Provenance as a product surface (internal tracing stays; public claim deferred)
- Public launch readiness (v1 is a learning vehicle, not a product)

---

*End of spec. Next step: writing-plans turns this into an ordered implementation plan with review checkpoints.*
