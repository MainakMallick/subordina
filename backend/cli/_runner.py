"""Runner instantiation + invocation-orchestration helpers for the CLI.

A single end-to-end path the three invocation commands (``say``, ``inquiry``,
``convergence``) share:

    resolve current project + chat
      -> create an ``Invocation`` row
      -> instantiate the appropriate ``AgentRunner`` subclass
      -> drive it to completion (streaming reasoning-trace output to stdout
         where possible)
      -> re-read the ``Invocation`` status
      -> return the chat folder path (so callers can load the artifact).

The RawRunner doesn't support a streaming callback — it runs to completion
silently, then we dump the final checkpoint's text blocks after the fact. The
AgentSdkRunner takes an ``on_message`` callback (added in Task 15) and prints
text/tool_use blocks live as they arrive.

Design decision (per task brief): the CLI defaults to ``agent_sdk`` regardless
of ``Settings.agent_runner``. Users invoking the CLI want the real thing; the
``raw`` runner is kept behind an explicit ``--runner raw`` flag (and under
``AGENT_RUNNER=raw`` when honoured by the caller). This matches the "v1 is
shipped to users, not tests" framing in the task brief.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import click
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.agent.mock_client import MockLLMClient, scripted_response
from backend.agent.runner import AgentRunner
from backend.agent.runner_raw import RawRunner
from backend.cli._db import open_session, project_root_for
from backend.config import get_settings
from backend.db.models import Chat, Checkpoint, Invocation, Project


SHORT_ID_LEN = 8


def _short(id_: str) -> str:
    return id_[:SHORT_ID_LEN]


# --------------------------------------------------------------------------- #
# Runner construction                                                         #
# --------------------------------------------------------------------------- #

def resolve_runner_name(cli_flag: str | None) -> str:
    """Pick which runner the CLI should use.

    - Explicit ``--runner <name>`` flag always wins.
    - Otherwise honour ``AGENT_RUNNER`` env (loaded via ``Settings``) only
      when it is set to ``raw``; otherwise default to ``agent_sdk`` because
      CLI users expect the real runner by default.
    """
    if cli_flag:
        return cli_flag
    # AGENT_RUNNER=raw explicitly opts out of spending tokens; otherwise
    # default to agent_sdk for real end-user runs.
    env = os.environ.get("AGENT_RUNNER", "").strip().lower()
    if env == "raw":
        return "raw"
    return "agent_sdk"


def get_cli_runner(
    name: str | None,
    *,
    session_factory: async_sessionmaker,
    project_root: str,
    mock_responses: list | None = None,
    on_message: Callable[[Any], None] | None = None,
) -> AgentRunner:
    """Instantiate an ``AgentRunner`` for the CLI.

    Parameters
    ----------
    name
        ``"raw"`` | ``"agent_sdk"`` | ``None`` (resolve via ``resolve_runner_name``).
    session_factory
        ``async_sessionmaker`` bound to the per-project SQLite engine. The
        runner will open its own sessions from this factory.
    project_root
        The resolved working folder (``chat.root_path or project.root_path``).
    mock_responses
        For tests only. If provided, forces a ``RawRunner`` with a
        ``MockLLMClient`` regardless of the runner name. Lets the CLI test
        suite keep hermetic without monkeypatching the whole module.
    on_message
        Optional streaming callback, passed through to ``AgentSdkRunner``.
        ``RawRunner`` ignores this (no streaming interface).
    """
    chosen = resolve_runner_name(name)

    if mock_responses is not None:
        # Forced raw with mocks — short-circuit regardless of the chosen name.
        client = MockLLMClient(mock_responses)
        return RawRunner(
            session_factory=session_factory,
            llm_client=client,
            project_root=project_root,
        )

    if chosen == "raw":
        # Dev dry-run with a no-op mock response that just end_turns.
        client = MockLLMClient([scripted_response(text="", tool_calls=[])])
        return RawRunner(
            session_factory=session_factory,
            llm_client=client,
            project_root=project_root,
        )

    if chosen == "agent_sdk":
        # Lazy import so tests that only use the raw runner don't pay the
        # claude-agent-sdk import cost (and don't need it on the path).
        from backend.agent.runner_agent_sdk import AgentSdkRunner

        settings = get_settings()
        return AgentSdkRunner(
            session_factory=session_factory,
            model=settings.default_model,
            on_message=on_message,
        )

    raise click.ClickException(
        f"Unknown runner '{chosen}' — use 'raw' or 'agent_sdk'"
    )


# --------------------------------------------------------------------------- #
# Chat / project resolution                                                   #
# --------------------------------------------------------------------------- #

async def resolve_chat(
    db_path: Path, chat_id_prefix: str | None
) -> tuple[str, str, str, str]:
    """Return (chat_id, chat_title, project_name, chat_folder).

    If ``chat_id_prefix`` is None, picks the most recently-created chat in
    the project. Raises ``click.ClickException`` on missing/ambiguous matches.

    ``chat_folder`` is ``chat.root_path or project.root_path`` — the working
    directory the invocation runs against.
    """
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            project = (await session.execute(select(Project))).scalars().first()
            if project is None:
                raise click.ClickException(
                    "Project row missing. Re-run `subordina init`."
                )

            if chat_id_prefix is None:
                result = await session.execute(
                    select(Chat).order_by(Chat.created_at.desc()).limit(1)
                )
                chat = result.scalars().first()
                if chat is None:
                    raise click.ClickException(
                        "No chats yet. Run `subordina chat new` first."
                    )
            else:
                result = await session.execute(
                    select(Chat).where(Chat.id.like(f"{chat_id_prefix}%"))
                )
                matches = list(result.scalars().all())
                if not matches:
                    raise click.ClickException(
                        f"No chat found matching prefix '{chat_id_prefix}'."
                    )
                if len(matches) > 1:
                    ids = ", ".join(m.id for m in matches)
                    raise click.ClickException(
                        f"Ambiguous chat prefix '{chat_id_prefix}' "
                        f"matches: {ids}"
                    )
                chat = matches[0]

            folder = chat.root_path or project.root_path
            return chat.id, chat.title, project.name, folder


async def create_invocation(
    db_path: Path,
    *,
    chat_id: str,
    skill_slug: str,
    user_input: str,
    max_cost_cents: int,
) -> str:
    """Insert a running ``Invocation`` row and return its id."""
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            inv = Invocation(
                chat_id=chat_id,
                skill_slug=skill_slug,
                input=user_input,
                status="running",
                user_id="local",
                total_cost_cents=0,
                max_cost_cents=max_cost_cents,
            )
            session.add(inv)
            await session.commit()
            return inv.id


async def fetch_invocation_status(db_path: Path, invocation_id: str) -> str:
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            inv = await session.get(Invocation, invocation_id)
            if inv is None:
                return "error"
            return inv.status


async def fetch_final_text(db_path: Path, invocation_id: str) -> str:
    """Return the last text block from the last checkpoint, or ''.

    For the raw runner (which doesn't stream to stdout), the CLI uses this to
    dump "what the model said" after the run. Tool-use blocks are ignored; the
    caller is expected to fall back to an artifact file if present.
    """
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            result = await session.execute(
                select(Checkpoint)
                .where(Checkpoint.invocation_id == invocation_id)
                .order_by(Checkpoint.iteration.desc())
                .limit(1)
            )
            cp = result.scalars().first()
            if cp is None:
                return ""
            # conversation_json for RawRunner is the full messages list. The
            # final assistant turn is the last role=="assistant" entry. For
            # AgentSdkRunner, each checkpoint's conversation_json is a single
            # assistant message (a list of block dicts).
            convo = cp.conversation_json
            if not convo:
                return ""

            # AgentSdkRunner shape: a bare list of block dicts.
            if isinstance(convo, list) and convo and isinstance(convo[0], dict) \
                    and convo[0].get("type") in {"text", "tool_use", "other"}:
                blocks = convo
            else:
                # RawRunner shape: list of {role, content} messages. Walk back
                # to the last assistant turn.
                blocks = []
                for msg in reversed(convo):
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        blocks = msg.get("content", [])
                        break
            text_parts = [
                b["text"] for b in blocks
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
            ]
            return "\n".join(text_parts).strip()


# --------------------------------------------------------------------------- #
# Streaming callback for AgentSdkRunner                                       #
# --------------------------------------------------------------------------- #

def make_stdout_streamer() -> Callable[[Any], None]:
    """Return an ``on_message`` callback that prints blocks to stdout.

    Imports the SDK types lazily — if the CLI is invoked with ``--runner raw``
    we never hit this path, so we never need the import.
    """
    try:
        from claude_agent_sdk import (
            AssistantMessage,
            TextBlock,
            ToolUseBlock,
        )
    except Exception:
        # Fallback: dump repr. Keeps the CLI useful even without the SDK.
        def _fallback(msg: Any) -> None:
            click.echo(repr(msg))
        return _fallback

    def _stream(msg: Any) -> None:
        if isinstance(msg, AssistantMessage):
            for block in getattr(msg, "content", []) or []:
                if isinstance(block, TextBlock):
                    text = getattr(block, "text", "")
                    if text:
                        click.echo(text)
                elif isinstance(block, ToolUseBlock):
                    name = getattr(block, "name", "?")
                    click.echo(f"[tool]   {name}")
    return _stream


# --------------------------------------------------------------------------- #
# Exit-code mapping                                                           #
# --------------------------------------------------------------------------- #

TERMINAL_STATUS_EXIT_CODE: dict[str, int] = {
    "verified": 0,
    "replied": 0,
    "deferred": 0,
    "cost-capped": 1,
    "cancelled": 1,
    "error": 1,
}


def exit_code_for(status: str) -> int:
    return TERMINAL_STATUS_EXIT_CODE.get(status, 1)


# --------------------------------------------------------------------------- #
# Project resolution wrapper                                                  #
# --------------------------------------------------------------------------- #

def resolve_project_root(db_path: Path) -> Path:
    """Filesystem project root for a given DB path."""
    return project_root_for(db_path)


# Short helpers re-exported so commands don't have to reach into this module
# for common operations.
__all__ = [
    "get_cli_runner",
    "resolve_runner_name",
    "resolve_chat",
    "create_invocation",
    "fetch_invocation_status",
    "fetch_final_text",
    "make_stdout_streamer",
    "exit_code_for",
    "resolve_project_root",
    "_short",
    "SHORT_ID_LEN",
]
