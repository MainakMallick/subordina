# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context

Full plugin architecture, all 6 app options, adversarial review methods, and honest limitations are documented at:

- `C:\Users\mmallick7\subordinate\docs\software_handoff.md`

Read that file FIRST before any work. It contains everything: the 9 skills, enforcement scripts (`research_loop.py`, `review_loop.py`, hooks), the 5-axis weighted scoring system, convergence/review loop mechanics, candidate architectures (Options A–F), UI components to build, backend API design, and the intended `frontend/` + `backend/` file layout.

Plugin source (reference implementation to port from): `C:\Users\mmallick7\subordinate`

## Repository state

This repo is **pre-scaffold** — no code, package manifests, or build tooling yet. Once `frontend/` and `backend/` are initialized per the handoff doc, re-run `/init` so this file can be filled in with real build/test/lint commands and concrete architecture.

## Hard constraints (non-negotiable)

- **Claude API model:** always `claude-opus-4-7` — never Sonnet or Haiku. This applies to every API call and every subagent dispatch.
- **Enforcement is Python, not prompts:** every quality gate must be a Python function that returns a bool or raises. Markdown instructions are suggestions Claude ignores once context grows; only script-level enforcement survives. Do not "enforce" via prompt text.
- **File-first pattern:** write assessments/drafts/scores to file or DB before presenting them to the user. This is the primary anti-sycophancy mechanism.
- **Anti-sycophancy is mechanical:** critique quality (length ≥ 50 chars, no rubber-stamp patterns, no "looks good") is checked by code, not judged by the model.
- **deep-research convergence ≠ review loop:** deep-research requires ≥ 3 iterations AND leader survives 2 consecutive challenges. All other skills use a 2-iteration review loop (paper gets 4).
- **Port, don't rewrite:** `research_loop.py`, `review_loop.py`, and the hooks in the plugin repo are the source of truth. Refactor them into backend modules — do not reinvent the logic.

## Environment

- Windows 11, Git Bash (not cmd/PowerShell) — use Unix shell syntax and forward slashes.
- Dual NVIDIA A4000 16GB GPUs available locally for experiment execution; factor this into any architecture decision involving GPU access (see Options A vs B/E in the handoff doc).
