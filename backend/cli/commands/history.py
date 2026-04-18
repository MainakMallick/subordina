"""`subordina history` and `subordina show` — past-invocation retrieval.

These are DB read-only commands (no runner invocation). They inspect the
current project's invocations and their artifacts.

Design:

- Short IDs are 8-char prefixes of the full UUIDs — same convention as
  ``backend/cli/commands/chat.py``. Prefix resolution uses the same
  ``LIKE 'prefix%'`` query with an ambiguity guard.
- Artifact rendering is per-skill: Inquiry -> ``query_draft.md``,
  Convergence -> ``final_recommendation.md``, plain chat -> text blocks
  from the last checkpoint. Non-terminal invocations print a diagnostic
  view with no file read attempt.
- All output is ASCII-only (``>>``, ``---``, ``[OK]``) for cross-platform
  terminals. Matches the choice made in Task 15.
- Engine disposal via ``open_session`` — avoids ResourceWarning under
  ``-W error`` (A9).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import click
from sqlalchemy import func, select

from backend.cli._db import (
    find_project_db,
    open_session,
    run,
)
from backend.db.models import Chat, Checkpoint, Invocation, Project


SHORT_ID_LEN = 8

# Invocation.status values considered "done, artifact-renderable".
TERMINAL_STATUSES = frozenset(
    {"verified", "replied", "deferred", "cost-capped", "cancelled", "error"}
)

# Map skill_slug -> display label used in the METHOD column / show header.
_METHOD_LABEL: dict[str, str] = {
    "chat": "chat",
    "query": "Inquiry",
    "deep-research": "Convergence",
}

# Map skill_slug -> known artifact filename (relative to chat folder).
_ARTIFACT_FILENAME: dict[str, str] = {
    "query": "query_draft.md",
    "deep-research": "final_recommendation.md",
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _require_project_db() -> Path:
    """Return the current project DB path or exit with a helpful error."""
    db = find_project_db()
    if db is None:
        click.echo(
            "No Subordina project found. Run `subordina init` first.",
            err=True,
        )
        raise click.exceptions.Exit(1)
    return db


def _short(id_: str) -> str:
    return id_[:SHORT_ID_LEN]


def _method_label(skill_slug: str) -> str:
    return _METHOD_LABEL.get(skill_slug, skill_slug)


def _truncate(text: str, width: int = 50) -> str:
    """Collapse newlines and truncate ``text`` with an ellipsis if too long."""
    flat = " ".join(text.split())  # collapse all whitespace (incl. newlines)
    if len(flat) <= width:
        return flat
    # Preserve ``width`` as the total visible width (ellipsis included).
    if width <= 3:
        return flat[:width]
    return flat[: width - 3] + "..."


def _relative_or_iso(ts: datetime, now: datetime | None = None) -> str:
    """Human-friendly delta like ``5 min ago``; falls back to ISO after 24h.

    Mirrors the helper in ``commands/chat.py`` — we deliberately duplicate the
    function instead of importing it to keep this module self-contained.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = now - ts
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    # Older than 24h — show ISO date.
    return ts.astimezone(timezone.utc).date().isoformat()


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Minimal column-padded table — no tabulate dep."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    for row in rows:
        click.echo(fmt.format(*row))


def _extract_last_assistant_text(convo: Any) -> str:
    """Return the last assistant text from a Checkpoint.conversation_json.

    The two runner shapes both serialise to JSON:

    - ``RawRunner`` stores a list of ``{"role", "content"}`` messages; we walk
      backwards to the last ``assistant`` turn and join its ``text`` blocks.
    - ``AgentSdkRunner`` stores a bare list of block dicts per checkpoint
      (each checkpoint = one assistant message).

    Returns "" if no text blocks are present.
    """
    if not convo:
        return ""

    if (
        isinstance(convo, list)
        and convo
        and isinstance(convo[0], dict)
        and convo[0].get("type") in {"text", "tool_use", "other"}
    ):
        blocks = convo
    else:
        blocks = []
        for msg in reversed(convo or []):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content", [])
                # Content may be a plain string (some stubs) or a list of
                # block dicts.
                if isinstance(content, str):
                    return content.strip()
                blocks = content
                break

    text_parts = [
        b["text"] for b in blocks
        if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
    ]
    return "\n".join(text_parts).strip()


# --------------------------------------------------------------------------- #
# Async DB workers                                                            #
# --------------------------------------------------------------------------- #

async def _resolve_chat_id(
    session, prefix: str
) -> tuple[str | None, list[str]]:
    """Return (chat_id, matches).

    - ``(id, [id])`` on unique match.
    - ``(None, [])`` if no match.
    - ``(None, [id1, id2, ...])`` if ambiguous.
    """
    result = await session.execute(
        select(Chat).where(Chat.id.like(f"{prefix}%"))
    )
    matches = list(result.scalars().all())
    if not matches:
        return None, []
    if len(matches) > 1:
        return None, [c.id for c in matches]
    return matches[0].id, [matches[0].id]


async def _list_history(
    db_path: Path, chat_prefix: str | None, limit: int
) -> tuple[list[dict[str, Any]], list[str] | None]:
    """Return (rows, ambiguous_match_ids_or_None).

    ``ambiguous_match_ids`` is set only when ``chat_prefix`` resolves to
    multiple chats; callers render the ambiguity error and exit.
    """
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            chat_id: str | None = None
            if chat_prefix is not None:
                chat_id, matches = await _resolve_chat_id(session, chat_prefix)
                if chat_id is None:
                    # No match or ambiguous — signal by returning matches.
                    return [], matches

            stmt = select(Invocation, Chat).join(
                Chat, Chat.id == Invocation.chat_id
            )
            if chat_id is not None:
                stmt = stmt.where(Invocation.chat_id == chat_id)
            stmt = stmt.order_by(Invocation.created_at.desc()).limit(limit)

            result = await session.execute(stmt)
            rows: list[dict[str, Any]] = []
            for inv, chat in result.all():
                rows.append(
                    {
                        "invocation_id": inv.id,
                        "chat_id": chat.id,
                        "chat_title": chat.title,
                        "skill_slug": inv.skill_slug,
                        "input": inv.input,
                        "status": inv.status,
                        "created_at": inv.created_at,
                    }
                )
            return rows, None


async def _show_invocation(
    db_path: Path, prefix: str
) -> dict[str, Any] | list[str]:
    """Look up an invocation by ID prefix.

    Returns:
    - ``dict`` of rendering fields on unique match
    - ``list[str]`` of matching full IDs on ambiguity
    - empty ``list[]`` if no match
    """
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            result = await session.execute(
                select(Invocation).where(Invocation.id.like(f"{prefix}%"))
            )
            matches = list(result.scalars().all())
            if len(matches) == 0:
                return []
            if len(matches) > 1:
                return [m.id for m in matches]

            inv = matches[0]
            chat = (
                await session.execute(
                    select(Chat).where(Chat.id == inv.chat_id)
                )
            ).scalars().one()
            project = (
                await session.execute(
                    select(Project).where(Project.id == chat.project_id)
                )
            ).scalars().one()

            cp_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Checkpoint)
                    .where(Checkpoint.invocation_id == inv.id)
                )
            ).scalar_one()

            # Pull the last checkpoint's conversation_json — needed for plain
            # ``chat`` artifact rendering. Cheap: ordered + limit 1.
            last_cp_row = (
                await session.execute(
                    select(Checkpoint)
                    .where(Checkpoint.invocation_id == inv.id)
                    .order_by(Checkpoint.iteration.desc())
                    .limit(1)
                )
            ).scalars().first()

            chat_folder = chat.root_path or project.root_path
            return {
                "invocation_id": inv.id,
                "chat_id": chat.id,
                "chat_title": chat.title,
                "skill_slug": inv.skill_slug,
                "input": inv.input,
                "status": inv.status,
                "created_at": inv.created_at,
                "updated_at": inv.updated_at,
                "checkpoint_count": int(cp_count),
                "chat_folder": chat_folder,
                "last_conversation_json": (
                    last_cp_row.conversation_json if last_cp_row else None
                ),
            }


# --------------------------------------------------------------------------- #
# Click commands                                                              #
# --------------------------------------------------------------------------- #

@click.command("history")
@click.option(
    "--chat",
    "chat_id",
    type=str,
    default=None,
    help="Filter to invocations in a single chat (ID prefix).",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=20,
    show_default=True,
    help="Maximum number of invocations to list.",
)
def history_command(chat_id: str | None, limit: int) -> None:
    """List past invocations in the current project, newest first."""
    db_path = _require_project_db()

    if limit < 1:
        raise click.BadParameter("--limit must be >= 1")

    rows, ambiguous = run(_list_history(db_path, chat_id, limit))

    if ambiguous is not None:
        # Chat-prefix didn't uniquely resolve.
        if not ambiguous:
            click.echo(
                f"No chat found matching prefix '{chat_id}'.", err=True
            )
            raise click.exceptions.Exit(1)
        click.echo(
            f"Ambiguous chat ID '{chat_id}' matches {len(ambiguous)} chats:",
            err=True,
        )
        for full_id in ambiguous:
            click.echo(f"  {full_id}", err=True)
        raise click.exceptions.Exit(1)

    if not rows:
        click.echo(
            "No invocations yet. Run `subordina say`, `subordina inquiry`, "
            "or `subordina convergence` to start."
        )
        return

    table_rows: list[list[str]] = []
    for r in rows:
        table_rows.append(
            [
                _short(r["invocation_id"]),
                _short(r["chat_id"]),
                _method_label(r["skill_slug"]),
                _truncate(r["input"], 50),
                r["status"],
                _relative_or_iso(r["created_at"]),
            ]
        )
    _print_table(
        ["ID", "CHAT", "METHOD", "SUBJECT", "STATUS", "WHEN"], table_rows
    )


@click.command("show")
@click.argument("invocation_id", metavar="ID")
def show_command(invocation_id: str) -> None:
    """Render a past invocation's artifact (or status diagnostic)."""
    db_path = _require_project_db()
    result = run(_show_invocation(db_path, invocation_id))

    if isinstance(result, list):
        if not result:
            click.echo(
                f"No invocation found matching prefix '{invocation_id}'.",
                err=True,
            )
            raise click.exceptions.Exit(1)
        click.echo(
            f"Ambiguous invocation ID '{invocation_id}' matches "
            f"{len(result)} invocations:",
            err=True,
        )
        for full_id in result:
            click.echo(f"  {full_id}", err=True)
        raise click.exceptions.Exit(1)

    # Header block.
    click.echo(f"Method: {_method_label(result['skill_slug'])}")
    click.echo(
        f"Chat: {result['chat_title']} ({_short(result['chat_id'])})"
    )
    click.echo(f"Subject: {result['input']}")
    click.echo(f"Status: {result['status']}")
    click.echo(f"Iterations: {result['checkpoint_count']}")
    click.echo(f"Started: {_iso(result['created_at'])}")
    click.echo(f"Updated: {_iso(result['updated_at'])}")

    status = result["status"]
    if status not in TERMINAL_STATUSES or status == "running":
        # Still running (or an unknown state) — skip the artifact read.
        click.echo("")
        click.echo(
            f"Invocation is not in a terminal state (status={status}); "
            "no artifact to render."
        )
        click.echo(
            f"Checkpoints written so far: {result['checkpoint_count']}"
        )
        return

    click.echo("")
    click.echo("--- Artifact ---")

    skill_slug = result["skill_slug"]
    if skill_slug in _ARTIFACT_FILENAME:
        # Inquiry / Convergence: known artifact file under the chat folder.
        rel = _ARTIFACT_FILENAME[skill_slug]
        path = Path(result["chat_folder"]) / rel
        if path.is_file():
            try:
                body = path.read_text(encoding="utf-8")
            except OSError as e:
                click.echo(f"(failed to read {path}: {e})")
                return
            click.echo(body)
        else:
            click.echo(
                f"(no artifact file at {path}; run may have completed "
                "without writing one)"
            )
        return

    # Plain chat: extract text from the last checkpoint's conversation_json.
    text = _extract_last_assistant_text(result["last_conversation_json"])
    if text:
        click.echo(text)
    else:
        click.echo("(no assistant text found in last checkpoint)")
