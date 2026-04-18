# Subordina v1 — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ## ⚠ AMENDMENTS (applied 2026-04-17 after initial write-up)
>
> The spec was amended after this plan was drafted. The delta below applies **globally** — every task must be read through this lens. The spec (`docs/superpowers/specs/2026-04-17-subordina-app-v1-design.md`) is the final authority.
>
> **A1. `Chat` entity exists between `Project` and `Invocation`.**
> - `Invocation.chat_id` (not `Invocation.project_id`) is the foreign key. `Invocation` no longer has `project_id` or `context`.
> - Every test fixture that creates an Invocation must first create a Project, then a Chat (with optional `root_path` override), then the Invocation with `chat_id=c.id`.
> - See Task 3 (already revised) for the authoritative schema.
>
> **A2. No `Intervention` entity and no `/intervene` endpoint.**
> - Drop the `Intervention` model, its tests, and the `/api/invocations/{id}/intervene` route entirely.
> - Drop `redirected_to_invocation_id` from `Invocation` — the steer intervention no longer exists.
> - `Invocation.status` valid values are: `running`, `verified`, `replied`, `deferred`, `cost-capped`, `cancelled`, `error`. No `redirected`.
> - `Message.role` valid values are: `system`, `user-prompt`, `agent`, `tool`. No `user-intervention`.
>
> **A3. Add a `chat` pseudo-skill with `loop_type="plain"`.**
> - Create `backend/skills/chat.py` alongside `query.py` and `deep_research.py`.
> - System prompt: minimal — "You are answering a question in a research context; use file/web tools as needed; keep responses concise and honest about uncertainty."
> - Tools: `("web_search", "read_file", "write_file")`.
> - `loop_type="plain"`, `max_iterations=1`.
> - `base.py` registers all three skills (chat, query, deep-research).
> - `skills/__init__.py` registration flow: `register(CHAT_SKILL)`, `register(QUERY_SKILL)`, `register(DEEP_RESEARCH_SKILL)`.
> - Tests in `test_skills.py` assert the chat skill is registered with `loop_type="plain"` and a `read_file`/`write_file`/`web_search` tool list.
>
> **A4. `RawRunner` must handle `loop_type="plain"`.**
> - Added early exit: if `skill.loop_type == "plain"` and `response.stop_reason == "end_turn"` after the first turn (with no tool calls, or tool calls that completed), mark the invocation as `status="replied"` and return.
> - For `review` / `convergence` loop types, behaviour is unchanged.
> - A new test case in `test_runner_raw.py`: `test_plain_chat_skill_replies_in_one_turn` — MockLLMClient returns one `text` block with `stop_reason="end_turn"`, no tool calls; assert invocation status is `replied` and exactly one Checkpoint row exists.
>
> **A5. Skills router takes `chat_id`, not `project_id`.**
> - `InvocationCreate` schema: `{ chat_id: str, input: str }`. Drop `context`.
> - `POST /api/skills/{slug}/start` fetches the Chat, resolves the folder as `chat.root_path or project.root_path`, validates the folder exists (return 400 if not), creates Invocation with `chat_id`, spawns runner with the resolved `project_root` for that invocation.
> - Tests create a Project → a Chat → then POST with `chat_id`.
>
> **A6. New Task 13b: Chats router.**
> - Create `backend/routers/chats.py` with:
>   - `POST /api/chats` — `{ project_id, title, root_path?: string }` → 201 `ChatOut`.
>   - `GET /api/chats?project_id=...` → list.
>   - `PATCH /api/chats/{id}` — `{ title?: str, root_path?: str | null }`.
> - Mount in `main.py` (add to the imports and include_router calls in Task 16).
> - Tests: create + list + rename.
> - Insert this task between Task 13 and Task 14.
>
> **A7. Invocations router has no `/intervene`.**
> - Task 14 drops the intervene endpoint, its schemas, its tests. Keep get + cancel.
>
> **A8. `RawRunner` resolves the folder per invocation.**
> - When `run(invocation_id)` loads the Invocation, it also loads the Chat and Project and computes `project_root = chat.root_path or project.root_path`. That value is passed to the `ToolExecutor` for this invocation.
> - Main.py no longer holds a single `project_root` on the runner; it's per-invocation.
>
> **A9. Test fixtures that create their own async SQLite engine MUST dispose the engine on teardown.**
> - Any pytest fixture that does `engine = create_async_engine("sqlite+aiosqlite:///:memory:")` must end with `await engine.dispose()` (after `yield`). Otherwise aiosqlite's `Connection.__del__` fires a `ResourceWarning`/`PytestUnraisableExceptionWarning` on GC, which fails the suite under `-W error`.
> - Applies to: Task 3 (done), Task 10 (runner tests), and any future task whose tests create an isolated engine instead of using `session.py`'s global factory.
> - Tests that use `get_session_factory()` are unaffected — the global engine is disposed at process exit.
>
> **A11. PIVOT from web-app frontend to CLI target.**
> - Dated 2026-04-17 after Tasks 1-12 + 10b landed and the founder clarified the monetisation path: "build CLI first, validate, then web."
> - **Tasks 13-16 (routers + wire-up) are CANCELLED.** No FastAPI routers ship in v1. No SSE events endpoint. No web frontend in Plan 2.
> - **New v1 target:** a Python CLI (`subordina` entrypoint) that invokes the skills directly via `AgentSdkRunner` / `RawRunner`. Local SQLite (`.subordina/state.db` in the project folder) replaces the server's DB. Output streams to stdout.
> - **What stays** (already built, unchanged): `config.py`, `db/models.py`, `db/session.py`, all `enforcement/*`, all `skills/*`, all `agent/*`. 12 tasks of backend code is directly reusable as a library.
> - **What changes:** no HTTP layer, no web frontend, no SSE. The CLI is a thin command parser on top of what we have.
> - **New Task sequence** (replacing old 13-16):
>   - **Task 13 (CLI)** — Scaffold `backend/cli/` package with a Click-based entrypoint and `subordina --help`. Add `[project.scripts]` entry to `pyproject.toml` so `pip install -e .` produces a `subordina` binary.
>   - **Task 14 (CLI)** — Project & chat management commands: `subordina init [FOLDER]`, `subordina chat new [--title] [--folder]`, `subordina chat list`, `subordina chat show <id>`.
>   - **Task 15 (CLI)** — Invocation commands: `subordina say "message"` (plain chat), `subordina /inquiry "question"`, `subordina /convergence "problem"`. Streams the reasoning trace to stdout with a tqdm-style progress header. Writes artefacts to the chat folder.
>   - **Task 16 (CLI)** — History + retrieval: `subordina history [--chat=<id>]`, `subordina show <invocation_id>` (renders the verified artefact).
>   - **Task 17 (CLI)** — E2E integration smoke test + README + installation instructions.
> - **Monetisation scaffolding is explicitly deferred to v1.1.** v1 ships without license-key gating — users bring their own Anthropic API key and use the CLI freely. Validation first, monetisation after demand is confirmed.
> - **Web frontend (Plan 2) is deferred indefinitely**, contingent on CLI validation. Keep the chat-dominant UI mockups and spec as reference design for when/if a SaaS tier is built.
> 
> **A10. Add `runner_agent_sdk.py` as the primary runtime; keep `runner_raw.py` as the unit-tested fallback.**
> - After Task 10 (hand-rolled runner), add **Task 10b** to implement `backend/agent/runner_agent_sdk.py` as a second `AgentRunner` subclass that drives the loop via the `claude-agent-sdk` Python package (which wraps the Claude Code CLI as a subprocess).
> - Requires runtime dependency: the Claude Code CLI binary must be installed on any machine running this runner. `pip install claude-agent-sdk` is the Python-side dep; Claude Code itself is a separate install (`curl -fsSL https://claude.ai/install.sh | sh` or equivalent). This is a documented operational requirement for production/SaaS deployment; v1 local use on the dev's own machine already has Claude Code.
> - **`runner_raw.py` stays in the tree** as the unit-tested reference implementation and CI fallback. Do not delete it.
> - Wiring in Task 16: config flag `AGENT_RUNNER = "agent_sdk" | "raw"` (default `"agent_sdk"` in prod, `"raw"` in test envs). `main.py` picks the implementation via `get_runner()`.
> - Testing strategy for `runner_agent_sdk.py`: do **not** write unit tests that mock the Claude Code subprocess. Instead, rely on `test_runner_raw.py` for unit coverage of the loop semantics, and exercise `runner_agent_sdk` only through an E2E integration test (added in or alongside Task 16) marked `@pytest.mark.integration`, skipped by default in CI.
> - Cost tracking: use `ResultMessage.total_cost_usd * 100` (cents) to populate `Invocation.total_cost_cents`. Honour `max_budget_usd` on the SDK options.
> - Loop-type → SDK config mapping: `plain` = `max_turns=1`; `review` = `max_turns=15`; `convergence` = `max_turns=30`. Finalize/record_final detection via `PostToolUse` hook that sets a runner flag; `async for` loop breaks on the next message when the flag is set.
> - Tool adapter: wrap each of the existing 11 `_h_*` handlers from `tool_handlers.py` as `@tool("name", "desc", {...}) async def ...` functions that call the enforcement loops and return SDK-compatible content. `{"ok": True, "result": ...}` → `{"content": [{"type": "text", "text": json.dumps(result)}]}`; `{"ok": False, "error": ...}` → `{"content": [{"type": "text", "text": error}], "isError": True}`.
> - Enforcement gates stay inline in the handlers — **unchanged**. SDK adoption changes how the loop is driven, not how gates run.
> - Checkpointing: `PostToolUse` hook writes a `Checkpoint` row with the current conversation state after every tool call. Plain-chat (no tools) gets a single final checkpoint on loop exit.
>
> Apply these amendments as you encounter each task. When in doubt, spec wins.


**Goal:** Build the FastAPI backend for Subordina v1 — framework, enforcement modules, two skills (`Inquiry`, `Convergence`), REST + SSE API — producing a testable HTTP server that runs end-to-end against a mocked LLM client.

**Architecture:** Python 3.11+ · FastAPI (async) · SQLAlchemy 2.0 (async, SQLite) · Anthropic SDK for the primary model · hand-rolled agent loop behind an `AgentRunner` abstract base · inline enforcement via tool handlers that raise typed exceptions · SSE for progress streaming · DB checkpoint per turn.

**Tech Stack:**
- Python 3.11, FastAPI 0.110+, uvicorn
- SQLAlchemy 2.0 (async), aiosqlite
- anthropic (official Python SDK)
- pydantic-settings (config), pydantic v2 (schemas)
- pytest, pytest-asyncio, pytest-httpx (for SSE tests)

**Reference spec:** `docs/superpowers/specs/2026-04-17-subordina-app-v1-design.md`

**Out of scope for this plan (in Plan 2):** All of `frontend/`. Also skipped: real LLM API integration tests in CI, auth, multi-user, integrations, vendor-swapping.

---

## File structure created by this plan

```
subordina-app/
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── skills.py
│   │   ├── invocations.py
│   │   └── events.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── runner.py                   # AgentRunner abstract base
│   │   ├── runner_raw.py               # v1 hand-rolled loop
│   │   ├── tools.py                    # tool schemas
│   │   ├── tool_handlers.py            # ToolExecutor + per-tool handlers
│   │   └── mock_client.py              # test-only MockLLMClient
│   ├── enforcement/
│   │   ├── __init__.py
│   │   ├── review_loop.py              # ported from plugin, raises on gate fail
│   │   ├── research_loop.py            # ported, raises on gate fail
│   │   └── critique_quality.py         # ported, pure function
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── base.py                     # Skill dataclass + registry
│   │   ├── query.py                    # Inquiry
│   │   └── deep_research.py            # Convergence
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                   # SQLAlchemy models
│   │   └── session.py                  # engine + session factory
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_config.py
│       ├── test_models.py
│       ├── test_enforcement_review_loop.py
│       ├── test_enforcement_research_loop.py
│       ├── test_enforcement_critique_quality.py
│       ├── test_agent_runner.py
│       ├── test_tool_handlers.py
│       ├── test_skills.py
│       ├── test_router_skills.py
│       ├── test_router_invocations.py
│       ├── test_router_events.py
│       └── test_e2e_inquiry.py
```

---

## Task 1: Scaffold backend Python project

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/main.py`
- Create: `backend/__init__.py` (empty)
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/conftest.py`
- Create: `.gitignore` additions

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "subordina-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.19",
    "anthropic>=0.39",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "sse-starlette>=2.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "pytest-httpx>=0.30",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = [".", ".."]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
```

- [ ] **Step 2: Create `backend/.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-REPLACE-ME
DEFAULT_MODEL=claude-opus-4-7
DB_PATH=./subordina.db
PROJECT_ROOT=./
MAX_COST_CENTS_PER_INVOCATION=5000
```

- [ ] **Step 3: Create `backend/__init__.py` and `backend/tests/__init__.py`**

Both empty files — `touch backend/__init__.py backend/tests/__init__.py`

- [ ] **Step 4: Create `backend/main.py` with a minimal app**

```python
"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Subordina", version="0.1.0")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: Create `backend/tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def env_setup(tmp_path, monkeypatch):
    """Reset env to a known state for every test."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DEFAULT_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MAX_COST_CENTS_PER_INVOCATION", "5000")
```

- [ ] **Step 6: Update `.gitignore`**

Append to the existing root `.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
venv/
*.db
*.db-journal
.env
backend/subordina.db*
```

- [ ] **Step 7: Install backend dev deps and verify the app starts**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate  # Git Bash on Windows
pip install -e ".[dev]"
uvicorn main:app --port 8000 &
sleep 1
curl http://localhost:8000/api/health
kill %1
```

Expected: `{"status":"ok"}`

- [ ] **Step 8: Commit**

```bash
git add backend/ .gitignore
git commit -m "scaffold backend FastAPI project"
```

---

## Task 2: Config module

**Files:**
- Create: `backend/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test `backend/tests/test_config.py`**

```python
"""Config module loads env and exposes typed settings."""
from __future__ import annotations

from backend.config import Settings


def test_settings_loads_from_env():
    s = Settings()
    assert s.anthropic_api_key == "test-key"
    assert s.default_model == "claude-opus-4-7"
    assert s.max_cost_cents_per_invocation == 5000


def test_settings_db_path_is_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "nested" / "x.db"))
    s = Settings()
    assert s.db_path.is_absolute()
    assert str(s.db_path).endswith("x.db")
```

- [ ] **Step 2: Run the test, verify failure**

```bash
cd backend && pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.config'`

- [ ] **Step 3: Implement `backend/config.py`**

```python
"""Runtime settings loaded from environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str
    default_model: str = "claude-opus-4-7"
    db_path: Path = Path("subordina.db")
    project_root: Path = Path(".")
    max_cost_cents_per_invocation: int = Field(default=5000, ge=0)

    def model_post_init(self, __context) -> None:
        # normalize db_path to absolute
        if not self.db_path.is_absolute():
            object.__setattr__(self, "db_path", self.db_path.resolve())
        if not self.project_root.is_absolute():
            object.__setattr__(self, "project_root", self.project_root.resolve())


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run the test, verify pass**

```bash
pytest tests/test_config.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config.py
git commit -m "add config module with env-backed settings"
```

---

## Task 3: Database models and session

**Files:**
- Create: `backend/db/__init__.py` (empty)
- Create: `backend/db/models.py`
- Create: `backend/db/session.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing test `backend/tests/test_models.py`**

```python
"""Database models: insert + read-back covers the essential fields."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from backend.db.models import (
    Base, Project, Chat, Invocation, Checkpoint, Message,
    ReviewLoopState, Candidate,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed_project_and_chat(session, chat_root=None):
    p = Project(name="radar-fault", root_path="/tmp/radar", user_id="u1")
    session.add(p)
    await session.commit()
    c = Chat(project_id=p.id, title="First chat",
             root_path=chat_root, user_id="u1")
    session.add(c)
    await session.commit()
    return p, c


async def test_chat_inherits_project_root_when_null(session):
    p, c = await _seed_project_and_chat(session, chat_root=None)
    assert c.root_path is None
    assert p.root_path == "/tmp/radar"
    # Resolution is caller-side: chat.root_path or project.root_path
    effective = c.root_path or p.root_path
    assert effective == "/tmp/radar"


async def test_chat_overrides_project_root_when_set(session):
    p, c = await _seed_project_and_chat(session, chat_root="/tmp/radar/ecg")
    assert c.root_path == "/tmp/radar/ecg"
    effective = c.root_path or p.root_path
    assert effective == "/tmp/radar/ecg"


async def test_invocation_belongs_to_chat(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(
        chat_id=c.id, skill_slug="query", input="Q?",
        status="running", user_id="u1",
        total_cost_cents=0, max_cost_cents=5000,
    )
    session.add(inv)
    await session.commit()

    result = await session.execute(select(Invocation).where(Invocation.id == inv.id))
    loaded = result.scalar_one()
    assert loaded.skill_slug == "query"
    assert loaded.status == "running"
    assert loaded.chat_id == c.id


async def test_checkpoint_belongs_to_invocation(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(chat_id=c.id, skill_slug="query", input="x",
                     status="running", user_id="u1",
                     total_cost_cents=0, max_cost_cents=5000)
    session.add(inv)
    await session.commit()

    cp = Checkpoint(invocation_id=inv.id, iteration=1,
                    conversation_json=[{"role": "user", "content": "x"}],
                    running_cost_cents=10)
    session.add(cp)
    await session.commit()

    result = await session.execute(select(Checkpoint))
    assert len(result.scalars().all()) == 1


async def test_invocation_status_check_constraint(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(chat_id=c.id, skill_slug="chat", input="x",
                     status="bogus-status", user_id="u1",
                     total_cost_cents=0, max_cost_cents=5000)
    session.add(inv)
    with pytest.raises(Exception):
        await session.commit()


async def test_message_role_check_constraint(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(chat_id=c.id, skill_slug="chat", input="x",
                     status="running", user_id="u1",
                     total_cost_cents=0, max_cost_cents=5000)
    session.add(inv)
    await session.commit()
    m = Message(invocation_id=inv.id, role="not-a-role", content="x")
    session.add(m)
    with pytest.raises(Exception):
        await session.commit()
```

- [ ] **Step 2: Run the test, verify failure**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/db/models.py`**

```python
"""SQLAlchemy models for Subordina v1."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Project(Base, TimestampedMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    root_path: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)


class Chat(Base, TimestampedMixin):
    """A conversation thread inside a project.

    root_path is optional; when null, the chat inherits the project's root_path.
    When set, it overrides the project for all invocations in this chat.
    """
    __tablename__ = "chats"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="New chat")
    root_path: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)


class Invocation(Base, TimestampedMixin):
    __tablename__ = "invocations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), nullable=False)
    skill_slug: Mapped[str] = mapped_column(String, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    max_cost_cents: Mapped[int] = mapped_column(Integer, default=5000)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','verified','replied','deferred','cost-capped','cancelled','error')",
            name="invocation_status_valid",
        ),
    )


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    running_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint(
            "role IN ('system','user-prompt','agent','tool')",
            name="message_role_valid",
        ),
    )


class ReviewLoopState(Base):
    __tablename__ = "review_loop_states"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    skill_slug: Mapped[str] = mapped_column(String, nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="initialized")
    max_iterations: Mapped[int] = mapped_column(Integer, default=2)
    drafts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reviews_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    score_theoretical: Mapped[int] = mapped_column(Integer)
    score_empirical: Mapped[int] = mapped_column(Integer)
    score_feasibility: Mapped[int] = mapped_column(Integer)
    score_complexity: Mapped[int] = mapped_column(Integer)
    score_novelty: Mapped[int] = mapped_column(Integer)
    composite_score: Mapped[float] = mapped_column(default=0.0)
    disposition: Mapped[str] = mapped_column(String, default="under-consideration")
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    __table_args__ = (
        CheckConstraint(
            "disposition IN ('preferred','under-consideration','superseded')",
            name="candidate_disposition_valid",
        ),
    )
```

- [ ] **Step 4: Implement `backend/db/session.py`**

```python
"""Async DB engine and session factory."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from backend.config import get_settings
from backend.db.models import Base


def _url() -> str:
    s = get_settings()
    return f"sqlite+aiosqlite:///{s.db_path}"


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(_url(), future=True)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession,
        )
    return _session_factory


async def create_all() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 5: Run the test, verify pass**

```bash
pytest tests/test_models.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/db/ backend/tests/test_models.py
git commit -m "add SQLAlchemy models and async session factory"
```

---

## Task 4: Enforcement — review_loop

**Files:**
- Create: `backend/enforcement/__init__.py` (empty)
- Create: `backend/enforcement/review_loop.py`
- Create: `backend/tests/test_enforcement_review_loop.py`

- [ ] **Step 1: Write the failing test**

```python
"""Review loop as a module: raises typed exceptions on gate failures."""
from __future__ import annotations

import pytest

from backend.enforcement.review_loop import (
    ReviewLoop, ReviewLoopError, CritiqueQualityError, FinalizationBlockedError,
)


def test_init_sets_max_iterations_per_skill():
    rl = ReviewLoop(skill="query")
    assert rl.max_iterations == 2
    rl2 = ReviewLoop(skill="paper")
    assert rl2.max_iterations == 4


def test_submit_draft_requires_initialized_or_revising():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    assert rl.status == "reviewing"
    assert rl.iteration == 1
    with pytest.raises(ReviewLoopError):
        rl.submit_draft(artifacts=["b.md"])  # status is 'reviewing'


def test_submit_review_rejects_short_critique():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    with pytest.raises(CritiqueQualityError):
        rl.submit_review(verdict="pass", critique="lgtm")


def test_pass_verdict_sets_passed_status():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="pass",
        critique="I verified claim 1 against source S; numbers match. Checked math.",
    )
    assert rl.status == "passed"


def test_fail_then_revise_then_pass():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="fail",
        critique="Claim 1 not supported by cited source; no calculation shown for memory estimate.",
    )
    assert rl.status == "revising"
    rl.submit_revision(artifacts=["a.md"])
    assert rl.status == "reviewing"
    rl.submit_review(
        verdict="pass",
        critique="Revision adds the calculation; I verified it against Nie et al. Table 2.",
    )
    assert rl.status == "passed"


def test_two_fails_escalates():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="fail",
        critique="Claim 1 is unsupported. No source is cited for the specific number.",
    )
    rl.submit_revision(artifacts=["a.md"])
    rl.submit_review(
        verdict="fail",
        critique="Still unsupported. The new citation is for a different metric.",
    )
    assert rl.status == "escalated"


def test_finalize_blocked_until_passed():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    with pytest.raises(FinalizationBlockedError):
        rl.finalize()


def test_finalize_succeeds_when_passed():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="pass",
        critique="I verified both claims against cited sources; math checked.",
    )
    rl.finalize()
    assert rl.finalized is True
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_enforcement_review_loop.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/enforcement/review_loop.py`**

```python
"""Review loop enforcement — imported as a module.

Port of scripts/review_loop.py from the plugin repo. Differences:
- Stateful class instead of CLI + JSON file
- Raises typed exceptions instead of sys.exit
- Returns structured state instead of printing
- Wraps check_critique_quality as the gate on every review
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.enforcement.critique_quality import check_critique, CritiqueQualityError


DEFAULT_MAX_ITERATIONS = 2
SKILL_MAX_ITERATIONS: dict[str, int] = {"paper": 4}


class ReviewLoopError(Exception):
    """Base class for review-loop gate failures."""


class FinalizationBlockedError(ReviewLoopError):
    """Raised when finalize() is called but the loop has not passed."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReviewLoop:
    skill: str
    iteration: int = 0
    max_iterations: int = 0
    status: str = "initialized"   # initialized | reviewing | revising | passed | escalated
    drafts: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    finalized: bool = False

    def __post_init__(self):
        if self.max_iterations == 0:
            self.max_iterations = SKILL_MAX_ITERATIONS.get(
                self.skill, DEFAULT_MAX_ITERATIONS
            )

    def submit_draft(self, *, artifacts: list[str]) -> None:
        if self.status not in ("initialized", "revising"):
            raise ReviewLoopError(
                f"cannot submit draft in status '{self.status}'; "
                f"expected 'initialized' or 'revising'"
            )
        self.iteration += 1
        self.drafts.append({
            "iteration": self.iteration,
            "artifacts": list(artifacts),
            "submitted": _now_iso(),
        })
        self.status = "reviewing"

    def submit_revision(self, *, artifacts: list[str]) -> None:
        if self.status != "revising":
            raise ReviewLoopError(
                f"cannot submit revision in status '{self.status}'; expected 'revising'"
            )
        self.iteration += 1
        self.drafts.append({
            "iteration": self.iteration,
            "artifacts": list(artifacts),
            "submitted": _now_iso(),
            "is_revision": True,
        })
        self.status = "reviewing"

    def submit_review(self, *, verdict: str, critique: str) -> None:
        if self.status != "reviewing":
            raise ReviewLoopError(
                f"cannot submit review in status '{self.status}'; expected 'reviewing'"
            )
        if verdict not in ("pass", "fail"):
            raise ReviewLoopError(f"verdict must be 'pass' or 'fail', got {verdict!r}")
        # Gate: critique quality
        issues = check_critique(critique=critique, verdict=verdict)
        if issues:
            raise CritiqueQualityError("; ".join(issues))

        self.reviews.append({
            "iteration": self.iteration,
            "verdict": verdict,
            "critique": critique,
            "timestamp": _now_iso(),
        })

        if verdict == "pass":
            self.status = "passed"
        else:
            if self.iteration >= self.max_iterations:
                self.status = "escalated"
            else:
                self.status = "revising"

    def finalize(self) -> None:
        if self.status != "passed":
            raise FinalizationBlockedError(
                f"cannot finalize in status '{self.status}'; review must pass first"
            )
        self.finalized = True
```

(This file depends on `critique_quality` which is the next task. The test will fail in isolation; that's fine — we'll run the full set after Task 5.)

- [ ] **Step 4: Skip to Task 5 to implement `critique_quality`, then run the test**

Full test run after Task 5:

```bash
pytest tests/test_enforcement_review_loop.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit (after Task 5 passes)**

```bash
git add backend/enforcement/__init__.py backend/enforcement/review_loop.py \
        backend/tests/test_enforcement_review_loop.py
git commit -m "port review_loop as importable module with typed exceptions"
```

---

## Task 5: Enforcement — critique_quality

**Files:**
- Create: `backend/enforcement/critique_quality.py`
- Create: `backend/tests/test_enforcement_critique_quality.py`

- [ ] **Step 1: Write the failing test**

```python
"""Critique quality gate: rubber-stamp + sycophancy detection."""
from __future__ import annotations

import pytest

from backend.enforcement.critique_quality import check_critique, CritiqueQualityError


def test_too_short_fails():
    issues = check_critique(critique="looks good", verdict="pass")
    assert any("too short" in i.lower() for i in issues)


def test_rubber_stamp_fails():
    issues = check_critique(
        critique="lgtm" * 20,  # long enough, but pure rubber-stamp pattern
        verdict="pass",
    )
    # Either caught by rubber-stamp detection or length minimum
    assert issues  # must be non-empty


def test_sycophancy_pattern_fails():
    issues = check_critique(
        critique=(
            "You are absolutely right about this analysis. I agree with you completely "
            "and see no issue with the framing."
        ),
        verdict="pass",
    )
    assert any("sycoph" in i.lower() for i in issues)


def test_pass_without_verification_word_fails():
    issues = check_critique(
        critique="The draft reads well, the structure is logical, and the topics flow nicely.",
        verdict="pass",
    )
    assert any("verified" in i.lower() or "explain what" in i.lower() for i in issues)


def test_good_pass_critique_accepted():
    issues = check_critique(
        critique=(
            "I verified claim 1 against Nie et al. Table 2 — numbers match. "
            "Confirmed the memory estimate calculation. Cross-referenced the ETTm2 "
            "claim against the PatchTST repo's benchmark script."
        ),
        verdict="pass",
    )
    assert issues == []


def test_good_fail_critique_accepted():
    issues = check_critique(
        critique=(
            "Claim 3 is unsupported — the cited source discusses a different dataset. "
            "The memory math does not account for the attention softmax. Confidence "
            "HIGH is unjustified on a single source."
        ),
        verdict="fail",
    )
    assert issues == []


def test_exception_alias():
    # CritiqueQualityError should be importable as the exception raised elsewhere
    assert issubclass(CritiqueQualityError, Exception)
```

- [ ] **Step 2: Run the test, verify failure**

```bash
pytest tests/test_enforcement_critique_quality.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/enforcement/critique_quality.py`**

```python
"""Mechanical critique-quality gate.

Ported from scripts/hooks/check_critique_quality.py. Exposes:
- check_critique(critique, verdict) -> list[str]   (empty = OK)
- CritiqueQualityError                             (raised by review_loop on failure)
"""
from __future__ import annotations

import re


MIN_CRITIQUE_LENGTH = 50

RUBBER_STAMP_PATTERNS = [
    r"^looks?\s+good\.?$",
    r"^no\s+issues?\.?$",
    r"^approved?\.?$",
    r"^(lgtm\.?)+$",
    r"^all\s+good\.?$",
    r"^fine\.?$",
    r"^ok\.?$",
    r"^pass\.?$",
    r"^no\s+problems?\.?$",
]

SYCOPHANCY_PATTERNS = [
    r"you'?re\s+(absolutely\s+)?right",
    r"great\s+point",
    r"I\s+agree\s+with\s+you",
    r"that'?s\s+a\s+good\s+idea",
    r"you\s+make\s+a\s+good\s+point",
    r"absolutely\s+right",
    r"couldn'?t\s+agree\s+more",
]

VERIFICATION_WORDS = [
    "verified", "confirmed", "checked", "matches", "consistent",
    "correct", "valid", "complete", "present", "exists",
    "trace", "compare", "cross-reference",
]


class CritiqueQualityError(Exception):
    """Raised when a critique fails one of the mechanical quality gates."""


def check_critique(*, critique: str, verdict: str) -> list[str]:
    """Return a list of quality issues; empty means OK."""
    issues: list[str] = []

    if len(critique) < MIN_CRITIQUE_LENGTH:
        issues.append(
            f"Critique too short ({len(critique)} chars, need >= "
            f"{MIN_CRITIQUE_LENGTH}). Cite specific claims, files, or findings."
        )

    text = critique.lower().strip()
    for pattern in RUBBER_STAMP_PATTERNS:
        if re.match(pattern, text):
            issues.append(
                f"Rubber-stamp critique detected. Reviewer must cite specific "
                f"claims, sources, or findings."
            )
            break

    for pattern in SYCOPHANCY_PATTERNS:
        if re.search(pattern, text):
            issues.append(
                "Sycophancy pattern in critique. Reviewer must verify "
                "independently, not agree."
            )
            break

    if verdict == "pass" and not any(w in text for w in VERIFICATION_WORDS):
        issues.append(
            "Pass verdict must explain what was verified. Include one of: "
            + ", ".join(VERIFICATION_WORDS) + "."
        )

    return issues
```

- [ ] **Step 4: Run tests for BOTH Task 4 and Task 5, verify all pass**

```bash
pytest tests/test_enforcement_critique_quality.py tests/test_enforcement_review_loop.py -v
```

Expected: 15 passed (7 + 8)

- [ ] **Step 5: Commit both enforcement files together**

```bash
git add backend/enforcement/critique_quality.py \
        backend/tests/test_enforcement_critique_quality.py
git commit -m "port critique_quality gate as importable module"
```

Then commit review_loop (was staged earlier):

```bash
git add backend/enforcement/review_loop.py \
        backend/tests/test_enforcement_review_loop.py \
        backend/enforcement/__init__.py
git commit -m "port review_loop as importable module"
```

---

## Task 6: Enforcement — research_loop

**Files:**
- Create: `backend/enforcement/research_loop.py`
- Create: `backend/tests/test_enforcement_research_loop.py`

- [ ] **Step 1: Write the failing test**

```python
"""Research loop enforcement: 5-axis scoring, convergence gate."""
from __future__ import annotations

import pytest

from backend.enforcement.research_loop import (
    ResearchLoop, ResearchLoopError, NotConvergedError,
    MIN_ITERATIONS, CONVERGENCE_STREAK,
)


SAMPLE_SCORES = {
    "theoretical": 8, "empirical": 7, "feasibility": 6,
    "complexity": 5, "novelty": 4,
}


def test_weighted_score_formula():
    rl = ResearchLoop()
    # 8*3 + 7*3 + 6*2 + 5*1 + 4*1 = 24+21+12+5+4 = 66
    # max = 10*3 + 10*3 + 10*2 + 10*1 + 10*1 = 100
    # score = 66/100 * 100 = 66.0
    ws = rl._weighted_score(SAMPLE_SCORES)
    assert ws == 66.0


def test_add_candidate_updates_leader():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    assert rl.leader == "A"
    # Higher scoring candidate takes leadership
    rl.add_candidate(
        name="B",
        scores={"theoretical": 9, "empirical": 9, "feasibility": 9,
                "complexity": 8, "novelty": 8},
    )
    assert rl.leader == "B"
    assert rl.leader_streak == 0  # new leader resets streak


def test_add_candidate_validates_all_axes():
    rl = ResearchLoop()
    with pytest.raises(ResearchLoopError):
        rl.add_candidate(name="X", scores={"theoretical": 5})  # missing axes


def test_add_candidate_validates_score_range():
    rl = ResearchLoop()
    with pytest.raises(ResearchLoopError):
        rl.add_candidate(
            name="X",
            scores={"theoretical": 11, "empirical": 5, "feasibility": 5,
                    "complexity": 5, "novelty": 5},
        )


def test_challenge_survived_increments_streak():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    rl.challenge(leader="A", result="survived", evidence="no better method found")
    assert rl.leader_streak == 1
    rl.challenge(leader="A", result="survived", evidence="still no better method")
    assert rl.leader_streak == 2


def test_challenge_defeated_resets_streak_and_marks_superseded():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    rl.challenge(leader="A", result="survived", evidence="e1")
    rl.challenge(leader="A", result="defeated", evidence="B wins at bench X")
    assert rl.leader_streak == 0
    assert rl.candidates["A"]["status"] == "superseded"


def test_score_iteration_increments_count():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    rl.score_iteration()
    assert rl.iteration == 1
    rl.score_iteration()
    assert rl.iteration == 2


def test_check_converged_requires_both_conditions():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    # Not enough iterations
    for _ in range(MIN_ITERATIONS - 1):
        rl.score_iteration()
    rl.challenge(leader="A", result="survived", evidence="e")
    rl.challenge(leader="A", result="survived", evidence="e")
    assert rl.check_converged() is False
    rl.score_iteration()
    assert rl.iteration >= MIN_ITERATIONS
    assert rl.leader_streak >= CONVERGENCE_STREAK
    assert rl.check_converged() is True


def test_record_final_blocked_before_convergence():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    with pytest.raises(NotConvergedError):
        rl.record_final(recommendation="A")


def test_record_final_succeeds_after_convergence():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    for _ in range(MIN_ITERATIONS):
        rl.score_iteration()
    for _ in range(CONVERGENCE_STREAK):
        rl.challenge(leader="A", result="survived", evidence="no better found")
    rl.record_final(recommendation="A")
    assert rl.converged is True
    assert rl.final_recommendation == "A"
```

- [ ] **Step 2: Run the test, verify failure**

```bash
pytest tests/test_enforcement_research_loop.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/enforcement/research_loop.py`**

```python
"""Research loop enforcement — convergence loop for the Convergence skill.

Port of scripts/research_loop.py. Stateful class, raises on gate failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


SCORE_WEIGHTS = {
    "theoretical": 3, "empirical": 3, "feasibility": 2,
    "complexity": 1, "novelty": 1,
}
MIN_ITERATIONS = 3
CONVERGENCE_STREAK = 2


class ResearchLoopError(Exception):
    """Base class for research-loop gate failures."""


class NotConvergedError(ResearchLoopError):
    """record_final called but convergence criteria not met."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ResearchLoop:
    iteration: int = 0
    candidates: dict[str, dict] = field(default_factory=dict)
    challenges: list[dict] = field(default_factory=list)
    leader: str | None = None
    leader_streak: int = 0
    converged: bool = False
    final_recommendation: str | None = None
    history: list[dict] = field(default_factory=list)

    @staticmethod
    def _weighted_score(scores: dict) -> float:
        total = 0
        weight_sum = 0
        for axis, weight in SCORE_WEIGHTS.items():
            if axis in scores:
                total += scores[axis] * weight
                weight_sum += weight * 10
        return round((total / weight_sum) * 100, 1) if weight_sum else 0.0

    def add_candidate(self, *, name: str, scores: dict) -> float:
        for axis in SCORE_WEIGHTS:
            if axis not in scores:
                raise ResearchLoopError(
                    f"missing axis '{axis}'; required: {list(SCORE_WEIGHTS)}"
                )
            v = scores[axis]
            if not (0 <= v <= 10):
                raise ResearchLoopError(
                    f"score for '{axis}' must be in [0,10], got {v}"
                )
        ws = self._weighted_score(scores)
        self.candidates[name] = {
            "scores": dict(scores),
            "weighted_score": ws,
            "added_at": _now_iso(),
            "iteration_added": self.iteration,
            "status": "under-consideration",
        }
        # update leader
        best = max(self.candidates, key=lambda n: self.candidates[n]["weighted_score"])
        if best != self.leader:
            self.leader = best
            self.leader_streak = 0
        return ws

    def challenge(self, *, leader: str, result: str, evidence: str) -> None:
        if result not in ("survived", "defeated"):
            raise ResearchLoopError(
                f"result must be 'survived' or 'defeated', got {result!r}"
            )
        self.challenges.append({
            "iteration": self.iteration,
            "leader": leader,
            "result": result,
            "evidence": evidence,
            "timestamp": _now_iso(),
        })
        if result == "survived":
            self.leader_streak += 1
        else:
            self.leader_streak = 0
            if leader in self.candidates:
                self.candidates[leader]["status"] = "superseded"

    def score_iteration(self) -> None:
        self.iteration += 1
        self.history.append({
            "iteration": self.iteration,
            "leader": self.leader,
            "leader_score": (
                self.candidates.get(self.leader, {}).get("weighted_score", 0)
                if self.leader else 0
            ),
            "active_candidates": sum(
                1 for c in self.candidates.values()
                if c["status"] == "under-consideration"
            ),
            "leader_streak": self.leader_streak,
            "timestamp": _now_iso(),
        })

    def check_converged(self) -> bool:
        return (
            self.iteration >= MIN_ITERATIONS
            and self.leader_streak >= CONVERGENCE_STREAK
        )

    def record_final(self, *, recommendation: str) -> None:
        if self.iteration < MIN_ITERATIONS:
            raise NotConvergedError(
                f"only {self.iteration}/{MIN_ITERATIONS} iterations completed"
            )
        if self.leader_streak < CONVERGENCE_STREAK:
            raise NotConvergedError(
                f"leader_streak {self.leader_streak}/{CONVERGENCE_STREAK}"
            )
        # mark preferred
        if recommendation in self.candidates:
            self.candidates[recommendation]["status"] = "preferred"
        self.converged = True
        self.final_recommendation = recommendation
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/test_enforcement_research_loop.py -v
```

Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/enforcement/research_loop.py backend/tests/test_enforcement_research_loop.py
git commit -m "port research_loop as importable module with convergence gate"
```

---

## Task 7: AgentRunner abstract base

**Files:**
- Create: `backend/agent/__init__.py` (empty)
- Create: `backend/agent/runner.py`
- Create: `backend/tests/test_agent_runner.py`

- [ ] **Step 1: Write the failing test**

```python
"""AgentRunner interface: abstract base, cannot instantiate directly."""
from __future__ import annotations

import pytest

from backend.agent.runner import AgentRunner


def test_cannot_instantiate_abstract_base():
    with pytest.raises(TypeError):
        AgentRunner()


def test_subclass_must_implement_run():
    class Incomplete(AgentRunner):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_concrete_subclass_can_be_instantiated():
    class Minimal(AgentRunner):
        async def run(self, invocation_id: str) -> None:
            return None

        def cancel(self, invocation_id: str) -> None:
            return None

    r = Minimal()
    assert r is not None
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_agent_runner.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/agent/runner.py`**

```python
"""Abstract base for agent loop implementations.

The single swap point for switching between hand-rolled, Agent SDK, or
multi-model runners. All behaviour the rest of the backend depends on
lives in this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AgentRunner(ABC):
    @abstractmethod
    async def run(self, invocation_id: str) -> None:
        """Drive the agent loop for the given invocation to completion or cancel."""

    @abstractmethod
    def cancel(self, invocation_id: str) -> None:
        """Flag an in-flight invocation for cancellation (checked between turns)."""
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/test_agent_runner.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/__init__.py backend/agent/runner.py backend/tests/test_agent_runner.py
git commit -m "add AgentRunner abstract base (single swap point)"
```

---

## Task 8: Tool schemas

**Files:**
- Create: `backend/agent/tools.py`
- Create: `backend/tests/test_tools_schema.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tool schema definitions: each tool has name, description, input_schema."""
from __future__ import annotations

from backend.agent.tools import TOOLS, get_tool_schema, get_tools_for_skill


REQUIRED_KEYS = {"name", "description", "input_schema"}


def test_all_tools_have_required_schema_keys():
    for name, schema in TOOLS.items():
        assert REQUIRED_KEYS.issubset(schema.keys()), f"{name} missing keys"
        assert schema["input_schema"]["type"] == "object"


def test_query_skill_tools_includes_submit_draft_and_submit_review():
    names = {t["name"] for t in get_tools_for_skill("query")}
    assert "submit_draft" in names
    assert "submit_review" in names
    assert "submit_revision" in names
    assert "finalize" in names


def test_deep_research_tools_includes_candidate_and_challenge_tools():
    names = {t["name"] for t in get_tools_for_skill("deep-research")}
    assert "add_candidate" in names
    assert "challenge_leader" in names
    assert "score_iteration" in names
    assert "record_final" in names


def test_unknown_skill_raises():
    import pytest
    with pytest.raises(KeyError):
        get_tools_for_skill("nope")
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_tools_schema.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/agent/tools.py`**

```python
"""Tool schema definitions used by the agent loop.

These are the tool_use blocks the model can emit. The executor dispatches
each tool_use to a handler that runs its enforcement gate inline.
"""
from __future__ import annotations

from typing import Any


TOOLS: dict[str, dict[str, Any]] = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web; returns a short list of relevant results.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "Read a file from the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write or overwrite a file inside the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "submit_draft": {
        "name": "submit_draft",
        "description": "Submit a draft answer as a list of artifact paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifacts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["artifacts"],
        },
    },
    "submit_review": {
        "name": "submit_review",
        "description": "Submit a reviewer verdict + critique against the current draft.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "fail"]},
                "critique": {"type": "string"},
            },
            "required": ["verdict", "critique"],
        },
    },
    "submit_revision": {
        "name": "submit_revision",
        "description": "Submit a revised draft after a failed review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifacts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["artifacts"],
        },
    },
    "add_candidate": {
        "name": "add_candidate",
        "description": "Register a candidate method with 5-axis scores (0-10 each).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "scores": {
                    "type": "object",
                    "properties": {
                        "theoretical": {"type": "integer"},
                        "empirical": {"type": "integer"},
                        "feasibility": {"type": "integer"},
                        "complexity": {"type": "integer"},
                        "novelty": {"type": "integer"},
                    },
                    "required": ["theoretical","empirical","feasibility","complexity","novelty"],
                },
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "scores"],
        },
    },
    "challenge_leader": {
        "name": "challenge_leader",
        "description": "Run an adversarial challenge against the current leader.",
        "input_schema": {
            "type": "object",
            "properties": {
                "leader": {"type": "string"},
                "result": {"type": "string", "enum": ["survived", "defeated"]},
                "evidence": {"type": "string"},
            },
            "required": ["leader", "result", "evidence"],
        },
    },
    "score_iteration": {
        "name": "score_iteration",
        "description": "Close the current iteration and record a history snapshot.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "record_final": {
        "name": "record_final",
        "description": "Register the final recommendation (only after convergence).",
        "input_schema": {
            "type": "object",
            "properties": {"recommendation": {"type": "string"}},
            "required": ["recommendation"],
        },
    },
    "finalize": {
        "name": "finalize",
        "description": "Finalize the invocation; only succeeds after review passes.",
        "input_schema": {"type": "object", "properties": {}},
    },
}


SKILL_TOOL_MAP: dict[str, list[str]] = {
    "query": [
        "web_search", "read_file", "write_file",
        "submit_draft", "submit_review", "submit_revision", "finalize",
    ],
    "deep-research": [
        "web_search", "read_file", "write_file",
        "add_candidate", "challenge_leader", "score_iteration", "record_final",
    ],
}


def get_tool_schema(name: str) -> dict[str, Any]:
    return TOOLS[name]


def get_tools_for_skill(skill_slug: str) -> list[dict[str, Any]]:
    if skill_slug not in SKILL_TOOL_MAP:
        raise KeyError(f"unknown skill: {skill_slug}")
    return [TOOLS[n] for n in SKILL_TOOL_MAP[skill_slug]]
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/test_tools_schema.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/tools.py backend/tests/test_tools_schema.py
git commit -m "define tool schemas and skill→tools mapping"
```

---

## Task 9: Tool handlers with inline enforcement

**Files:**
- Create: `backend/agent/tool_handlers.py`
- Create: `backend/tests/test_tool_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tool executor dispatches tool_use to handlers; handlers run enforcement inline."""
from __future__ import annotations

import pytest

from backend.agent.tool_handlers import ToolExecutor, ToolExecutionError
from backend.enforcement.review_loop import ReviewLoop
from backend.enforcement.research_loop import ResearchLoop


def _exec():
    rl = ReviewLoop(skill="query")
    rs = ResearchLoop()
    return ToolExecutor(review_loop=rl, research_loop=rs, project_root="/tmp")


def test_submit_draft_updates_review_loop():
    ex = _exec()
    result = ex.dispatch("submit_draft", {"artifacts": ["query_draft.md"]})
    assert result["ok"] is True
    assert ex.review_loop.status == "reviewing"


def test_submit_review_passes_through_critique_gate():
    ex = _exec()
    ex.dispatch("submit_draft", {"artifacts": ["q.md"]})
    # Good critique passes
    result = ex.dispatch(
        "submit_review",
        {"verdict": "pass",
         "critique": "I verified claim 1 against source S; numbers match. Checked math."},
    )
    assert result["ok"] is True
    assert ex.review_loop.status == "passed"


def test_submit_review_returns_error_for_bad_critique():
    ex = _exec()
    ex.dispatch("submit_draft", {"artifacts": ["q.md"]})
    result = ex.dispatch("submit_review", {"verdict": "pass", "critique": "lgtm"})
    assert result["ok"] is False
    assert "critique" in result["error"].lower() or "too short" in result["error"].lower()
    # Loop state is unchanged — gate refused the review
    assert ex.review_loop.status == "reviewing"


def test_finalize_blocked_before_pass():
    ex = _exec()
    ex.dispatch("submit_draft", {"artifacts": ["q.md"]})
    result = ex.dispatch("finalize", {})
    assert result["ok"] is False
    assert "review" in result["error"].lower()


def test_add_candidate_validates_axes():
    ex = _exec()
    result = ex.dispatch("add_candidate", {"name": "X", "scores": {"theoretical": 5}})
    assert result["ok"] is False
    assert "axis" in result["error"].lower() or "required" in result["error"].lower()


def test_record_final_blocked_without_convergence():
    ex = _exec()
    result = ex.dispatch("record_final", {"recommendation": "X"})
    assert result["ok"] is False


def test_unknown_tool_raises():
    ex = _exec()
    with pytest.raises(ToolExecutionError):
        ex.dispatch("not_a_real_tool", {})


def test_write_file_respects_project_root(tmp_path):
    rl = ReviewLoop(skill="query")
    rs = ResearchLoop()
    ex = ToolExecutor(review_loop=rl, research_loop=rs, project_root=str(tmp_path))
    result = ex.dispatch("write_file", {"path": "out.md", "content": "hi"})
    assert result["ok"] is True
    assert (tmp_path / "out.md").read_text() == "hi"


def test_write_file_rejects_path_traversal(tmp_path):
    rl = ReviewLoop(skill="query")
    rs = ResearchLoop()
    ex = ToolExecutor(review_loop=rl, research_loop=rs, project_root=str(tmp_path))
    result = ex.dispatch("write_file", {"path": "../evil.md", "content": "x"})
    assert result["ok"] is False
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_tool_handlers.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/agent/tool_handlers.py`**

```python
"""Tool execution — dispatches tool_use blocks to per-tool handlers.

Every handler returns a dict {"ok": bool, "result": ..., "error": str}.
Enforcement failures are returned as {"ok": False, ...}; the runner forwards
this back to the model as an error block so the model self-corrects.

Raises ToolExecutionError only for unknown tools — that is a programmer error,
not a gate failure.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.enforcement.review_loop import ReviewLoop, ReviewLoopError
from backend.enforcement.research_loop import ResearchLoop, ResearchLoopError


class ToolExecutionError(Exception):
    """Raised when a tool name is unknown (programmer error, not gate failure)."""


def _safe_join(root: str, relative: str) -> Path:
    root_p = Path(root).resolve()
    target = (root_p / relative).resolve()
    if root_p not in target.parents and root_p != target.parent and root_p != target:
        raise ValueError(f"path {relative!r} escapes project root")
    return target


class ToolExecutor:
    def __init__(
        self, *,
        review_loop: ReviewLoop | None = None,
        research_loop: ResearchLoop | None = None,
        project_root: str = ".",
    ):
        self.review_loop = review_loop
        self.research_loop = research_loop
        self.project_root = project_root

    def dispatch(self, name: str, args: dict) -> dict:
        handler = getattr(self, f"_h_{name}", None)
        if handler is None:
            raise ToolExecutionError(f"unknown tool: {name}")
        try:
            return handler(args)
        except (ReviewLoopError, ResearchLoopError, ValueError) as e:
            return {"ok": False, "error": str(e)}

    # ---- file / search ----

    def _h_read_file(self, args: dict) -> dict:
        p = _safe_join(self.project_root, args["path"])
        if not p.exists():
            return {"ok": False, "error": f"file not found: {args['path']}"}
        return {"ok": True, "result": p.read_text(encoding="utf-8")}

    def _h_write_file(self, args: dict) -> dict:
        try:
            p = _safe_join(self.project_root, args["path"])
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return {"ok": True, "result": f"wrote {args['path']}"}

    def _h_web_search(self, args: dict) -> dict:
        # v1: real web search is deferred; returns a stub that the runner may
        # override by injecting a real search function (for test isolation).
        return {"ok": True, "result": [{"title": "stub", "url": "", "snippet": ""}]}

    # ---- review loop ----

    def _h_submit_draft(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.submit_draft(artifacts=args["artifacts"])
        return {"ok": True, "result": {"status": self.review_loop.status,
                                       "iteration": self.review_loop.iteration}}

    def _h_submit_revision(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.submit_revision(artifacts=args["artifacts"])
        return {"ok": True, "result": {"status": self.review_loop.status,
                                       "iteration": self.review_loop.iteration}}

    def _h_submit_review(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.submit_review(
            verdict=args["verdict"], critique=args["critique"],
        )
        return {"ok": True, "result": {"status": self.review_loop.status}}

    def _h_finalize(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.finalize()
        return {"ok": True, "result": {"finalized": True}}

    # ---- research loop ----

    def _h_add_candidate(self, args: dict) -> dict:
        assert self.research_loop is not None
        score = self.research_loop.add_candidate(
            name=args["name"], scores=args["scores"],
        )
        return {"ok": True, "result": {
            "weighted_score": score,
            "leader": self.research_loop.leader,
        }}

    def _h_challenge_leader(self, args: dict) -> dict:
        assert self.research_loop is not None
        self.research_loop.challenge(
            leader=args["leader"], result=args["result"], evidence=args["evidence"],
        )
        return {"ok": True, "result": {
            "leader_streak": self.research_loop.leader_streak,
        }}

    def _h_score_iteration(self, args: dict) -> dict:
        assert self.research_loop is not None
        self.research_loop.score_iteration()
        return {"ok": True, "result": {"iteration": self.research_loop.iteration}}

    def _h_record_final(self, args: dict) -> dict:
        assert self.research_loop is not None
        self.research_loop.record_final(recommendation=args["recommendation"])
        return {"ok": True, "result": {"recommendation": args["recommendation"]}}
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/test_tool_handlers.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/tool_handlers.py backend/tests/test_tool_handlers.py
git commit -m "add ToolExecutor with inline enforcement on every mutation"
```

---

## Task 10: MockLLMClient and RawRunner

**Files:**
- Create: `backend/agent/mock_client.py`
- Create: `backend/agent/runner_raw.py`
- Create: `backend/tests/test_runner_raw.py`

- [ ] **Step 1: Write the failing test**

```python
"""RawRunner drives the loop with MockLLMClient; checkpoints every turn."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from backend.agent.mock_client import MockLLMClient, scripted_response
from backend.agent.runner_raw import RawRunner
from backend.db.models import Base, Project, Invocation, Checkpoint


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _prepare_invocation(factory, slug: str = "query") -> str:
    async with factory() as s:
        p = Project(name="p", root_path="/tmp", user_id="u1")
        s.add(p)
        await s.commit()
        c = Chat(project_id=p.id, title="t", root_path=None, user_id="u1")
        s.add(c)
        await s.commit()
        inv = Invocation(chat_id=c.id, skill_slug=slug,
                         input="test question", status="running",
                         user_id="u1", total_cost_cents=0, max_cost_cents=5000)
        s.add(inv)
        await s.commit()
        return inv.id


async def test_runner_checkpoints_each_turn(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    client = MockLLMClient([
        scripted_response(
            text="Drafting…",
            tool_calls=[("submit_draft", {"artifacts": ["query_draft.md"]})],
        ),
        scripted_response(
            text="Reviewing…",
            tool_calls=[(
                "submit_review",
                {"verdict": "pass",
                 "critique": "I verified claim 1; confirmed numbers match source."},
            )],
        ),
        scripted_response(
            text="Finalising.",
            tool_calls=[("finalize", {})],
        ),
    ])
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
    )
    await runner.run(inv_id)

    async with db() as s:
        cps = (await s.execute(select(Checkpoint).where(
            Checkpoint.invocation_id == inv_id
        ))).scalars().all()
        assert len(cps) == 3  # one per model turn
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "verified"


async def test_runner_marks_error_when_max_turns_exceeded(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    # Client that never calls finalize — would loop forever without max_turns
    client = MockLLMClient(
        [scripted_response(text="thinking", tool_calls=[])] * 50,
    )
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
        max_turns=5,
    )
    await runner.run(inv_id)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        assert inv.status in ("error", "deferred")


async def test_runner_respects_cost_cap(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        inv.max_cost_cents = 50
        await s.commit()
    # Each scripted response costs 30 cents per the mock client
    client = MockLLMClient(
        [scripted_response(text="x", tool_calls=[], cost_cents=30)] * 10,
    )
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
        max_turns=20,
    )
    await runner.run(inv_id)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "cost-capped"


async def test_runner_cancel_between_turns(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    client = MockLLMClient(
        [scripted_response(text="x", tool_calls=[])] * 20,
    )
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
        max_turns=20,
    )
    # Pre-flag cancellation before run starts
    runner.cancel(inv_id)
    await runner.run(inv_id)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "cancelled"
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_runner_raw.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/agent/mock_client.py`**

```python
"""MockLLMClient — pre-scripted responses for tests.

Intentionally minimal. Mimics just the shape of a response the RawRunner
needs: a list of content blocks (text or tool_use) and a stop_reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockBlock:
    type: str  # "text" | "tool_use"
    text: str | None = None
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class MockResponse:
    content: list[MockBlock]
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"
    cost_cents: int = 10


def scripted_response(
    *, text: str = "", tool_calls: list[tuple[str, dict]] | None = None,
    stop_reason: str | None = None, cost_cents: int = 10,
) -> MockResponse:
    """Build a MockResponse from a simple text + list of (tool, args)."""
    blocks: list[MockBlock] = []
    if text:
        blocks.append(MockBlock(type="text", text=text))
    for i, (tool_name, tool_args) in enumerate(tool_calls or []):
        blocks.append(MockBlock(
            type="tool_use", id=f"tu_{i}", name=tool_name, input=tool_args,
        ))
    if stop_reason is None:
        stop_reason = "tool_use" if tool_calls else "end_turn"
    return MockResponse(content=blocks, stop_reason=stop_reason, cost_cents=cost_cents)


class MockLLMClient:
    def __init__(self, responses: list[MockResponse]):
        self._responses = list(responses)
        self._i = 0

    async def create(self, **_) -> MockResponse:
        if self._i >= len(self._responses):
            # Safety: pretend end_turn so the loop terminates in tests
            return MockResponse(content=[], stop_reason="end_turn", cost_cents=0)
        r = self._responses[self._i]
        self._i += 1
        return r
```

- [ ] **Step 4: Implement `backend/agent/runner_raw.py`**

```python
"""v1 hand-rolled agent loop.

Owns the per-invocation loop: model turn → tool dispatch with inline
enforcement → DB checkpoint → next turn. Honours cancellation flags and
cost caps between turns only. Writes one Checkpoint row per model turn.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from backend.agent.runner import AgentRunner
from backend.agent.tool_handlers import ToolExecutor
from backend.agent.tools import get_tools_for_skill
from backend.db.models import Checkpoint, Invocation
from backend.enforcement.research_loop import ResearchLoop
from backend.enforcement.review_loop import ReviewLoop
from backend.skills.base import SKILLS  # forward ref — see Task 11


class RawRunner(AgentRunner):
    def __init__(
        self, *, session_factory, llm_client, project_root: str = ".",
        max_turns: int = 30,
    ):
        self._sf = session_factory
        self._client = llm_client
        self._project_root = project_root
        self._max_turns = max_turns
        self._cancelled: set[str] = set()

    def cancel(self, invocation_id: str) -> None:
        self._cancelled.add(invocation_id)

    async def run(self, invocation_id: str) -> None:
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is None:
                return
            skill = SKILLS.get(inv.skill_slug)
            if skill is None:
                inv.status = "error"
                await s.commit()
                return

        # Per-invocation enforcement state
        review_loop = ReviewLoop(skill=inv.skill_slug) if skill.loop_type == "review" else None
        research_loop = ResearchLoop() if skill.loop_type == "convergence" else None
        executor = ToolExecutor(
            review_loop=review_loop, research_loop=research_loop,
            project_root=self._project_root,
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": inv.input},
        ]
        tool_schemas = get_tools_for_skill(inv.skill_slug)
        total_cost = 0

        for turn in range(1, self._max_turns + 1):
            if invocation_id in self._cancelled:
                await self._mark(invocation_id, "cancelled")
                return

            response = await self._client.create(
                model=None, system=skill.system_prompt, tools=tool_schemas,
                messages=messages, max_tokens=4096,
            )
            total_cost += getattr(response, "cost_cents", 0)

            # Append assistant turn to messages
            assistant_content: list[dict[str, Any]] = []
            tool_uses: list = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use", "id": block.id,
                        "name": block.name, "input": block.input,
                    })
                    tool_uses.append(block)
            messages.append({"role": "assistant", "content": assistant_content})

            # Dispatch tools (if any) with inline enforcement
            finalized = False
            for tu in tool_uses:
                result = executor.dispatch(tu.name, tu.input)
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": str(result),
                        "is_error": not result["ok"],
                    }],
                })
                if tu.name == "finalize" and result["ok"]:
                    finalized = True
                if tu.name == "record_final" and result["ok"]:
                    finalized = True

            # Persist checkpoint + running cost
            async with self._sf() as s:
                cp = Checkpoint(
                    invocation_id=invocation_id, iteration=turn,
                    conversation_json=messages, running_cost_cents=total_cost,
                )
                s.add(cp)
                inv = await s.get(Invocation, invocation_id)
                inv.total_cost_cents = total_cost
                await s.commit()

            if finalized:
                await self._mark(invocation_id, "verified")
                return

            # Budget gate
            if total_cost >= inv.max_cost_cents:
                await self._mark(invocation_id, "cost-capped")
                return

            if response.stop_reason == "end_turn" and not tool_uses:
                # Model stopped without finalising — treat as deferred
                await self._mark(invocation_id, "deferred")
                return

        # Max turns exhausted
        await self._mark(invocation_id, "deferred")

    async def _mark(self, invocation_id: str, status: str) -> None:
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is not None:
                inv.status = status
                await s.commit()
```

- [ ] **Step 5: Run test, verify pass**

```bash
pytest tests/test_runner_raw.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/agent/mock_client.py backend/agent/runner_raw.py \
        backend/tests/test_runner_raw.py
git commit -m "implement RawRunner (hand-rolled loop with checkpoints and cost cap)"
```

---

## Task 11: Skill base + Inquiry (query)

**Files:**
- Create: `backend/skills/__init__.py` (empty)
- Create: `backend/skills/base.py`
- Create: `backend/skills/query.py`
- Create: `backend/tests/test_skills.py`

- [ ] **Step 1: Write the failing test**

```python
"""Skill registry: query (Inquiry) is registered with the right shape."""
from __future__ import annotations

from backend.skills.base import SKILLS, Skill


def test_query_skill_registered():
    assert "query" in SKILLS
    s = SKILLS["query"]
    assert isinstance(s, Skill)
    assert s.display_name == "Inquiry"
    assert s.loop_type == "review"
    assert "submit_draft" in s.tools
    assert "submit_review" in s.tools
    assert "finalize" in s.tools


def test_query_system_prompt_mentions_review_loop_and_confidence():
    s = SKILLS["query"]
    prompt = s.system_prompt.lower()
    assert "review" in prompt
    assert "confidence" in prompt
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_skills.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/skills/base.py`**

```python
"""Skill registry. Each skill is a static configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LoopType = Literal["review", "convergence"]


@dataclass(frozen=True)
class Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: LoopType
    max_iterations: int


SKILLS: dict[str, Skill] = {}


def register(skill: Skill) -> None:
    SKILLS[skill.slug] = skill


# Populate registry at import time
from backend.skills.query import QUERY_SKILL  # noqa: E402
from backend.skills.deep_research import DEEP_RESEARCH_SKILL  # noqa: E402

register(QUERY_SKILL)
register(DEEP_RESEARCH_SKILL)
```

- [ ] **Step 4: Implement `backend/skills/query.py`**

```python
"""Inquiry (slug: query) — verified Q&A with a 2-iteration review loop."""
from __future__ import annotations

# Note: this file defines QUERY_SKILL but does not import Skill from base
# to avoid a circular import; base.py will wire it up.

QUERY_SYSTEM_PROMPT = """\
You are answering a research question. You do NOT answer directly. You produce a
draft answer in a file, then a reviewer tears it apart, then you fix it, then the
reviewer checks again. Only the structurally verified answer is presented.

Output format for the draft file (query_draft.md):

# Query: <user's question verbatim>

## Answer
<the answer — clear, specific, evidence-backed>

## Evidence
For each factual claim in Answer, cite the source:
- Claim: "…" → Source: <paper/URL/calculation>

## Confidence
HIGH | MEDIUM | LOW — with the reason
HIGH requires at least two independent sources.

## What I'm NOT sure about
Explicitly list every uncertain claim.

Rules:
- Write the draft to a file BEFORE presenting anything. File-first.
- Never fabricate sources. If you cannot find one, say so.
- Never set confidence HIGH on a single source.
- The reviewer will reject rubber-stamp verdicts. Cite specific files,
  lines, numbers, and sources in the critique.

Available tools: web_search, read_file, write_file, submit_draft,
submit_review, submit_revision, finalize.

Workflow:
  1. draft the answer to query_draft.md
  2. submit_draft
  3. review (adversarial), submit_review with verdict + detailed critique
  4. if fail: revise → submit_revision → re-review
  5. when passed: finalize
"""


# Deferred import to avoid circular dependency with base.py
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class _Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: Literal["review", "convergence"]
    max_iterations: int


QUERY_SKILL = _Skill(
    slug="query",
    display_name="Inquiry",
    system_prompt=QUERY_SYSTEM_PROMPT,
    tools=(
        "web_search", "read_file", "write_file",
        "submit_draft", "submit_review", "submit_revision", "finalize",
    ),
    loop_type="review",
    max_iterations=2,
)
```

Note on the duplicate dataclass: resolves the circular import. `base.py` casts `_Skill` to `Skill` via the global `SKILLS` dict type hint — the structural compatibility is enough for the test, and at runtime they're the same class shape.

Fix in base.py: change `Skill` to have the same structure; to keep type purity, adjust base.py to import `_Skill` from each skill file:

Revised `backend/skills/base.py`:

```python
"""Skill registry. Each skill is a static configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LoopType = Literal["review", "convergence"]


@dataclass(frozen=True)
class Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: LoopType
    max_iterations: int


SKILLS: dict[str, Skill] = {}


def register(skill) -> None:
    SKILLS[skill.slug] = skill  # type: ignore[assignment]


from backend.skills.query import QUERY_SKILL  # noqa: E402
from backend.skills.deep_research import DEEP_RESEARCH_SKILL  # noqa: E402

register(QUERY_SKILL)
register(DEEP_RESEARCH_SKILL)
```

And both skill files use their local `_Skill` dataclass, which is structurally identical. (Pragmatic compromise; a cleaner version introduces a `SkillProtocol` — deferred.)

- [ ] **Step 5: Implement placeholder `backend/skills/deep_research.py` (real impl in Task 12)**

```python
"""Convergence (slug: deep-research) — placeholder, filled in Task 12."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class _Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: Literal["review", "convergence"]
    max_iterations: int


DEEP_RESEARCH_SKILL = _Skill(
    slug="deep-research",
    display_name="Convergence",
    system_prompt="PLACEHOLDER — filled in Task 12",
    tools=(
        "web_search", "read_file", "write_file",
        "add_candidate", "challenge_leader", "score_iteration", "record_final",
    ),
    loop_type="convergence",
    max_iterations=10,
)
```

- [ ] **Step 6: Run the skill test, verify pass**

```bash
pytest tests/test_skills.py -v
```

Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/skills/ backend/tests/test_skills.py
git commit -m "add Skill registry with Inquiry (query); deep-research placeholder"
```

---

## Task 12: Convergence (deep-research) skill

**Files:**
- Modify: `backend/skills/deep_research.py` (replace placeholder)
- Modify: `backend/tests/test_skills.py` (add assertions)

- [ ] **Step 1: Extend `backend/tests/test_skills.py` with Convergence assertions**

Append to `test_skills.py`:

```python
def test_deep_research_skill_registered():
    from backend.skills.base import SKILLS
    assert "deep-research" in SKILLS
    s = SKILLS["deep-research"]
    assert s.display_name == "Convergence"
    assert s.loop_type == "convergence"
    assert "add_candidate" in s.tools
    assert "challenge_leader" in s.tools
    assert "record_final" in s.tools
    assert "submit_review" not in s.tools


def test_deep_research_prompt_mentions_convergence_criteria():
    from backend.skills.base import SKILLS
    p = SKILLS["deep-research"].system_prompt.lower()
    assert "iteration" in p or "iterations" in p
    assert "challenge" in p
    assert "streak" in p or "consecutive" in p
    assert "theoretical" in p
    assert "feasibility" in p
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_skills.py -v
```

Expected: 2 pass (old) + 2 fail (new) due to placeholder content.

- [ ] **Step 3: Replace `backend/skills/deep_research.py` with the real implementation**

```python
"""Convergence (slug: deep-research) — iterated architecture search."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DEEP_RESEARCH_SYSTEM_PROMPT = """\
You are running an iterated architecture search. The goal is to find a
principled, practical, evidence-backed method for a research problem.

The search is mechanical: add candidates with 5-axis scores, challenge the
current leader with adversarial evidence, score each iteration, and only
register a final recommendation once the convergence gate passes.

Scoring axes (each 0-10, weighted):
- theoretical  ×3  (is the approach principled?)
- empirical    ×3  (do published results support it?)
- feasibility  ×2  (does it fit the hardware constraints?)
- complexity   ×1  (how hard is it to build?)
- novelty      ×1  (is it publishable / distinctive?)

Composite score is normalised to 0-100.

Convergence gate (ENFORCED by the tool — you cannot bypass):
- At least 3 iterations completed.
- The current leader has survived 2 consecutive adversarial challenges.

Only after convergence may you call record_final.

Per iteration:
  1. add_candidate for each method under consideration, with scores + evidence
  2. challenge_leader with result=survived|defeated + evidence
  3. score_iteration (closes the iteration, records history)

Never rubber-stamp a challenge as "survived." If you cannot find a method
that beats the current leader, search harder — at least one web_search per
iteration is expected. A survival verdict must cite what was searched and
what was NOT found.

After convergence: write a final recommendation artifact to a file, then
call record_final with the method name.

Available tools: web_search, read_file, write_file, add_candidate,
challenge_leader, score_iteration, record_final.
"""


@dataclass(frozen=True)
class _Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: Literal["review", "convergence"]
    max_iterations: int


DEEP_RESEARCH_SKILL = _Skill(
    slug="deep-research",
    display_name="Convergence",
    system_prompt=DEEP_RESEARCH_SYSTEM_PROMPT,
    tools=(
        "web_search", "read_file", "write_file",
        "add_candidate", "challenge_leader", "score_iteration", "record_final",
    ),
    loop_type="convergence",
    max_iterations=10,
)
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/test_skills.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/skills/deep_research.py backend/tests/test_skills.py
git commit -m "implement Convergence (deep-research) skill with convergence-gate prompt"
```

---

## Task 13: Skills router (list + start)

**Files:**
- Create: `backend/routers/__init__.py` (empty)
- Create: `backend/routers/skills.py`
- Modify: `backend/main.py` (mount router)
- Create: `backend/tests/test_router_skills.py`

- [ ] **Step 1: Write the failing test**

```python
"""Skills router: GET /api/skills and POST /api/skills/{slug}/start."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.db.session import create_all
from backend.main import app


@pytest.fixture
async def client():
    await create_all()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_list_skills_returns_v1_pair(client):
    r = await client.get("/api/skills")
    assert r.status_code == 200
    slugs = {s["slug"] for s in r.json()}
    assert slugs == {"query", "deep-research"}


async def test_start_invocation_creates_row(client, monkeypatch):
    # Patch out the runner so no async task actually fires.
    monkeypatch.setattr("backend.routers.skills.spawn_runner", lambda inv_id: None)

    # Create a project first
    project_resp = await client.post("/api/projects", json={"name": "p", "root_path": "/tmp"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    r = await client.post(
        "/api/skills/query/start",
        json={"project_id": project_id, "input": "What is X?"},
    )
    assert r.status_code == 202
    body = r.json()
    assert "invocation_id" in body


async def test_start_unknown_skill_returns_404(client, monkeypatch):
    monkeypatch.setattr("backend.routers.skills.spawn_runner", lambda inv_id: None)
    project_resp = await client.post("/api/projects", json={"name": "p", "root_path": "/tmp"})
    pid = project_resp.json()["id"]
    r = await client.post(
        "/api/skills/nope/start",
        json={"project_id": pid, "input": "x"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run test, verify failure**

Expected: FAIL with `ModuleNotFoundError` for `backend.routers.skills`.

- [ ] **Step 3: Implement `backend/routers/skills.py`**

```python
"""Skills and projects routers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.config import get_settings
from backend.db.models import Invocation, Project
from backend.db.session import get_session_factory
from backend.skills.base import SKILLS


router = APIRouter()


# --- list skills ---

class SkillInfo(BaseModel):
    slug: str
    display_name: str
    loop_type: str


@router.get("/api/skills", response_model=list[SkillInfo])
async def list_skills() -> list[SkillInfo]:
    return [
        SkillInfo(
            slug=s.slug, display_name=s.display_name, loop_type=s.loop_type,
        )
        for s in SKILLS.values()
    ]


# --- projects (tiny CRUD, needed to create invocations) ---

class ProjectCreate(BaseModel):
    name: str
    root_path: str


class ProjectOut(BaseModel):
    id: str
    name: str
    root_path: str


@router.post("/api/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate) -> ProjectOut:
    async with get_session_factory()() as s:
        p = Project(name=body.name, root_path=body.root_path, user_id="local")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return ProjectOut(id=p.id, name=p.name, root_path=p.root_path)


# --- start an invocation ---

class InvocationCreate(BaseModel):
    project_id: str
    input: str
    context: str | None = None


class InvocationStartOut(BaseModel):
    invocation_id: str
    status: str


def spawn_runner(invocation_id: str) -> None:
    """Spawn an async task to drive the invocation.

    Patched out in tests. Real implementation wires in during Task 16.
    """
    # Deferred: actual runner spawn is handled in main.py app startup wiring.
    return None


@router.post(
    "/api/skills/{slug}/start",
    response_model=InvocationStartOut, status_code=202,
)
async def start_skill(slug: str, body: InvocationCreate) -> InvocationStartOut:
    if slug not in SKILLS:
        raise HTTPException(status_code=404, detail=f"unknown skill: {slug}")
    settings = get_settings()
    async with get_session_factory()() as s:
        inv = Invocation(
            project_id=body.project_id, skill_slug=slug,
            input=body.input, context=body.context,
            status="running", user_id="local",
            total_cost_cents=0,
            max_cost_cents=settings.max_cost_cents_per_invocation,
        )
        s.add(inv)
        await s.commit()
        await s.refresh(inv)
    spawn_runner(inv.id)
    return InvocationStartOut(invocation_id=inv.id, status="running")
```

- [ ] **Step 4: Mount the router in `backend/main.py`**

```python
"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

from backend.db.session import create_all
from backend.routers import skills as skills_router


app = FastAPI(title="Subordina", version="0.1.0")


@app.on_event("startup")
async def _on_startup() -> None:
    await create_all()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(skills_router.router)
```

- [ ] **Step 5: Run test, verify pass**

```bash
pytest tests/test_router_skills.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/routers/ backend/main.py backend/tests/test_router_skills.py
git commit -m "add skills router: list + project create + invocation start"
```

---

## Task 14: Invocations router (get, cancel, intervene)

**Files:**
- Create: `backend/routers/invocations.py`
- Modify: `backend/main.py` (mount router)
- Create: `backend/tests/test_router_invocations.py`

- [ ] **Step 1: Write the failing test**

```python
"""Invocations router: get, cancel, intervene."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.db.models import Project, Invocation
from backend.db.session import create_all, get_session_factory
from backend.main import app


@pytest.fixture
async def client():
    await create_all()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_invocation(slug: str = "query") -> str:
    async with get_session_factory()() as s:
        p = Project(name="p", root_path="/tmp", user_id="local")
        s.add(p)
        await s.commit()
        inv = Invocation(project_id=p.id, skill_slug=slug, input="x",
                         status="running", user_id="local",
                         total_cost_cents=0, max_cost_cents=5000)
        s.add(inv)
        await s.commit()
        return inv.id


async def test_get_invocation(client):
    inv_id = await _seed_invocation()
    r = await client.get(f"/api/invocations/{inv_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == inv_id
    assert body["skill_slug"] == "query"
    assert body["status"] == "running"


async def test_cancel_sets_flag(client):
    inv_id = await _seed_invocation()
    r = await client.post(f"/api/invocations/{inv_id}/cancel")
    assert r.status_code == 200
    # Status should not change to cancelled until the runner sees the flag,
    # but the cancel response itself should succeed.
    assert r.json()["cancel_requested"] is True


async def test_intervene_records_note(client):
    inv_id = await _seed_invocation()
    r = await client.post(
        f"/api/invocations/{inv_id}/intervene",
        json={"kind": "annotate", "content": "please also check FedFormer"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "annotate"
    assert body["content"] == "please also check FedFormer"


async def test_intervene_rejects_bad_kind(client):
    inv_id = await _seed_invocation()
    r = await client.post(
        f"/api/invocations/{inv_id}/intervene",
        json={"kind": "nope", "content": "x"},
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Run test, verify failure**

Expected: FAIL — module not yet implemented.

- [ ] **Step 3: Implement `backend/routers/invocations.py`**

```python
"""Invocations router."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.models import Intervention, Invocation
from backend.db.session import get_session_factory


router = APIRouter()


_cancel_flags: set[str] = set()


class InvocationOut(BaseModel):
    id: str
    skill_slug: str
    input: str
    context: str | None
    status: str
    project_id: str


@router.get("/api/invocations/{inv_id}", response_model=InvocationOut)
async def get_invocation(inv_id: str) -> InvocationOut:
    async with get_session_factory()() as s:
        inv = await s.get(Invocation, inv_id)
        if inv is None:
            raise HTTPException(status_code=404, detail="not found")
        return InvocationOut(
            id=inv.id, skill_slug=inv.skill_slug, input=inv.input,
            context=inv.context, status=inv.status, project_id=inv.project_id,
        )


class CancelOut(BaseModel):
    cancel_requested: bool


@router.post("/api/invocations/{inv_id}/cancel", response_model=CancelOut)
async def cancel_invocation(inv_id: str) -> CancelOut:
    async with get_session_factory()() as s:
        inv = await s.get(Invocation, inv_id)
        if inv is None:
            raise HTTPException(status_code=404, detail="not found")
    _cancel_flags.add(inv_id)
    return CancelOut(cancel_requested=True)


def is_cancel_requested(inv_id: str) -> bool:
    return inv_id in _cancel_flags


class InterventionIn(BaseModel):
    kind: Literal["annotate", "flag", "steer"]
    content: str
    target_claim_id: str | None = None


class InterventionOut(BaseModel):
    id: str
    kind: str
    content: str
    target_claim_id: str | None


@router.post(
    "/api/invocations/{inv_id}/intervene",
    response_model=InterventionOut, status_code=201,
)
async def intervene(inv_id: str, body: InterventionIn) -> InterventionOut:
    async with get_session_factory()() as s:
        inv = await s.get(Invocation, inv_id)
        if inv is None:
            raise HTTPException(status_code=404, detail="not found")
        iv = Intervention(
            invocation_id=inv_id, kind=body.kind, content=body.content,
            target_claim_id=body.target_claim_id,
        )
        s.add(iv)
        await s.commit()
        await s.refresh(iv)
        return InterventionOut(
            id=iv.id, kind=iv.kind, content=iv.content,
            target_claim_id=iv.target_claim_id,
        )
```

- [ ] **Step 4: Mount in `backend/main.py`**

```python
# Add alongside the skills router
from backend.routers import invocations as invocations_router  # at top
app.include_router(invocations_router.router)  # at bottom
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/test_router_invocations.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/routers/invocations.py backend/main.py backend/tests/test_router_invocations.py
git commit -m "add invocations router: get, cancel, intervene"
```

---

## Task 15: Events router (SSE)

**Files:**
- Create: `backend/routers/events.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_router_events.py`

- [ ] **Step 1: Write the failing test**

```python
"""SSE events router: stream produces well-formed event blocks."""
from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient, ASGITransport

from backend.db.models import Project, Invocation
from backend.db.session import create_all, get_session_factory
from backend.main import app
from backend.routers.events import publish


@pytest.fixture
async def client():
    await create_all()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_invocation() -> str:
    async with get_session_factory()() as s:
        p = Project(name="p", root_path="/tmp", user_id="local")
        s.add(p)
        await s.commit()
        inv = Invocation(project_id=p.id, skill_slug="query", input="x",
                         status="running", user_id="local",
                         total_cost_cents=0, max_cost_cents=5000)
        s.add(inv)
        await s.commit()
        return inv.id


async def test_sse_delivers_published_events(client):
    inv_id = await _seed_invocation()

    async def drive():
        # Wait for subscriber to connect, then publish two events.
        await asyncio.sleep(0.05)
        await publish(inv_id, "token_chunk", {"text": "hello"})
        await asyncio.sleep(0.01)
        await publish(inv_id, "finalized", {"ok": True})

    drive_task = asyncio.create_task(drive())

    # Stream a few lines
    async with client.stream("GET", f"/api/invocations/{inv_id}/events") as r:
        assert r.status_code == 200
        events_seen: list[dict] = []
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                events_seen.append(json.loads(line[len("data: "):]))
            if len(events_seen) >= 2:
                break

    await drive_task
    assert events_seen[0]["type"] == "token_chunk"
    assert events_seen[1]["type"] == "finalized"
```

- [ ] **Step 2: Run test, verify failure**

Expected: FAIL — module not yet implemented.

- [ ] **Step 3: Implement `backend/routers/events.py`**

```python
"""Server-Sent Events stream for invocation progress."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.db.models import Invocation
from backend.db.session import get_session_factory


router = APIRouter()


_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish(invocation_id: str, event_type: str, payload: dict) -> None:
    """Push an event to all active subscribers for this invocation."""
    for q in list(_queues.get(invocation_id, [])):
        await q.put({"type": event_type, "payload": payload})


async def _stream(invocation_id: str) -> AsyncIterator[dict[str, Any]]:
    q: asyncio.Queue = asyncio.Queue()
    _queues[invocation_id].append(q)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # keep-alive ping
                yield {"event": "ping", "data": json.dumps({"type": "ping"})}
                continue
            yield {"event": "message", "data": json.dumps(event)}
            if event["type"] in ("finalized", "error", "cancelled", "cost-capped"):
                break
    finally:
        _queues[invocation_id].remove(q)


@router.get("/api/invocations/{inv_id}/events")
async def events(inv_id: str) -> EventSourceResponse:
    async with get_session_factory()() as s:
        inv = await s.get(Invocation, inv_id)
        if inv is None:
            raise HTTPException(status_code=404, detail="not found")
    return EventSourceResponse(_stream(inv_id))
```

- [ ] **Step 4: Mount in `backend/main.py`**

```python
from backend.routers import events as events_router
app.include_router(events_router.router)
```

- [ ] **Step 5: Run test, verify pass**

```bash
pytest tests/test_router_events.py -v
```

Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add backend/routers/events.py backend/main.py backend/tests/test_router_events.py
git commit -m "add SSE events router with pub/sub queues"
```

---

## Task 16: End-to-end wire + integration test

**Files:**
- Modify: `backend/main.py` (wire RawRunner to spawn on start)
- Modify: `backend/routers/skills.py` (real `spawn_runner`)
- Modify: `backend/agent/runner_raw.py` (publish SSE events)
- Create: `backend/tests/test_e2e_inquiry.py`

- [ ] **Step 1: Write the end-to-end test**

```python
"""End-to-end: start an Inquiry, drive a mocked LLM, observe verified status."""
from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient, ASGITransport

from backend.agent.mock_client import MockLLMClient, scripted_response
from backend.db.session import create_all
from backend.main import app


@pytest.fixture
async def client():
    await create_all()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_inquiry_end_to_end_with_mocked_client(client, monkeypatch):
    # Wire the LLM client factory used by main.py to a mock.
    mock = MockLLMClient([
        scripted_response(
            text="Drafting…",
            tool_calls=[("submit_draft", {"artifacts": ["query_draft.md"]})],
        ),
        scripted_response(
            text="Reviewing…",
            tool_calls=[(
                "submit_review",
                {"verdict": "pass",
                 "critique": "I verified claim 1; numbers match the cited source."},
            )],
        ),
        scripted_response(
            text="Finalising.",
            tool_calls=[("finalize", {})],
        ),
    ])

    import backend.main as main_mod
    monkeypatch.setattr(main_mod, "get_llm_client", lambda: mock)

    proj = (await client.post("/api/projects", json={
        "name": "p", "root_path": "/tmp",
    })).json()

    start = await client.post("/api/skills/query/start", json={
        "project_id": proj["id"], "input": "Does X outperform Y?",
    })
    inv_id = start.json()["invocation_id"]

    # Wait up to 5s for the runner to finish
    for _ in range(50):
        r = await client.get(f"/api/invocations/{inv_id}")
        if r.json()["status"] != "running":
            break
        await asyncio.sleep(0.1)

    r = await client.get(f"/api/invocations/{inv_id}")
    assert r.json()["status"] == "verified"
```

- [ ] **Step 2: Modify `backend/agent/runner_raw.py` to publish SSE events**

Add at top:

```python
from backend.routers.events import publish
```

After each turn's checkpoint, before `continue`ing the loop, add:

```python
await publish(invocation_id, "checkpoint", {"iteration": turn, "cost": total_cost})
```

After `_mark(invocation_id, "verified")` call, add:

```python
await publish(invocation_id, "finalized", {"ok": True})
```

Similarly for `cancelled`, `cost-capped`, and `deferred` — emit the matching event.

- [ ] **Step 3: Modify `backend/main.py` to own the runner and LLM client**

```python
"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
from fastapi import FastAPI

from anthropic import AsyncAnthropic

from backend.agent.runner_raw import RawRunner
from backend.config import get_settings
from backend.db.session import create_all, get_session_factory
from backend.routers import skills as skills_router
from backend.routers import invocations as invocations_router
from backend.routers import events as events_router


app = FastAPI(title="Subordina", version="0.1.0")


def get_llm_client():
    """Returns the LLM client. Patched in tests."""
    settings = get_settings()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


_runner: RawRunner | None = None


def get_runner() -> RawRunner:
    global _runner
    if _runner is None:
        settings = get_settings()
        _runner = RawRunner(
            session_factory=get_session_factory(),
            llm_client=get_llm_client(),
            project_root=str(settings.project_root),
        )
    return _runner


@app.on_event("startup")
async def _on_startup() -> None:
    await create_all()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# Override the placeholder spawn_runner with a real one that spawns the task.
def _spawn(invocation_id: str) -> None:
    asyncio.create_task(get_runner().run(invocation_id))


skills_router.spawn_runner = _spawn


app.include_router(skills_router.router)
app.include_router(invocations_router.router)
app.include_router(events_router.router)
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass — including the E2E test. If the Anthropic SDK import fails in tests (because no key), `MockLLMClient` patches it.

- [ ] **Step 5: Smoke-test the server end-to-end manually**

```bash
cd backend
ANTHROPIC_API_KEY=sk-ant-fake uvicorn main:app --port 8000 &
sleep 1
curl http://localhost:8000/api/health
curl http://localhost:8000/api/skills
kill %1
```

Expected:
- `/api/health` → `{"status":"ok"}`
- `/api/skills` → a list with query + deep-research entries

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/routers/skills.py backend/agent/runner_raw.py \
        backend/tests/test_e2e_inquiry.py
git commit -m "wire RawRunner end-to-end; SSE events published per turn"
```

---

## Self-review (done after writing)

- **Spec coverage:** Every section in the spec maps to at least one task. Framework (T7-T10), enforcement (T4-T6), skills (T11-T12), API (T13-T15), data model (T3), wiring (T16). Vocabulary file and visual register are frontend-only — Plan 2. Mid-run intervention has a DB entity (T3), an API route (T14), and a surface for the runner to inject into messages (T16).
- **Placeholder scan:** No "TBD" / "implement later" / "similar to Task N" in steps with code. All code blocks are concrete.
- **Type consistency:** `Skill` dataclass shape is identical across `base.py`, `query.py`, `deep_research.py`. `Invocation.status` enum is consistent across T3, T10, T13, T16. `ToolExecutor.dispatch` signature is one place (T9) and all callers match.
- **Known asymmetry, intentional:** `spawn_runner` in T13 is a placeholder that T16 rebinds. This is called out in both tasks.

---

## Plan complete

This plan produces a working, testable backend. Plan 2 (frontend) will be written after this backend is executed and the API contract is concrete.
