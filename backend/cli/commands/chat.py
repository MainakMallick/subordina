"""`subordina chat ...` — chat management commands for the current project."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import click
from sqlalchemy import func, select

from backend.cli._db import (
    find_project_db,
    open_session,
    project_root_for,
    run,
)
from backend.db.models import Chat, Invocation, Project


SHORT_ID_LEN = 8


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


def _default_title() -> str:
    # Human-readable local timestamp, e.g. "Chat 2026-04-17 14:32".
    return datetime.now().strftime("Chat %Y-%m-%d %H:%M")


def _short(id_: str) -> str:
    return id_[:SHORT_ID_LEN]


def _relative_or_iso(ts: datetime, now: datetime | None = None) -> str:
    """Human-friendly timestamp for list view.

    Returns things like "just now", "5 min ago", "3 hr ago" for events within
    the last 24h; falls back to an ISO date for older events.
    """
    # Normalise tz — DB-produced timestamps are stored as UTC via our
    # TimestampedMixin, but SQLite may return naive datetimes. Treat naive
    # values as UTC.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = now - ts
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    # Older than 24h — show ISO date (drop microseconds).
    return ts.astimezone(timezone.utc).date().isoformat()


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_chat_folder(project_root: Path, folder: str) -> str:
    """Resolve `--folder` arg to an absolute path string.

    If the given path is absolute, use it as-is; otherwise resolve it against
    the project root so relative paths are project-relative rather than
    cwd-relative (which would be surprising for a stored override).
    """
    p = Path(folder)
    if not p.is_absolute():
        p = project_root / p
    return str(p.resolve())


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


# --------------------------------------------------------------------------- #
# Async worker functions                                                      #
# --------------------------------------------------------------------------- #

async def _create_chat(
    db_path: Path, title: str, folder_override: str | None
) -> tuple[str, str]:
    """Create a chat, return (short_id, title)."""
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            project = (await session.execute(select(Project))).scalars().first()
            if project is None:
                # Shouldn't happen — init would have created one. Guard anyway.
                raise click.ClickException(
                    "Project row is missing from the database. "
                    "Re-run `subordina init`."
                )
            chat = Chat(
                project_id=project.id,
                title=title,
                root_path=folder_override,
                user_id="local",
            )
            session.add(chat)
            await session.commit()
            return chat.id, chat.title


async def _list_chats(db_path: Path) -> list[tuple[Chat, str]]:
    """Return list of (chat, project_root_path) newest first."""
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            project = (await session.execute(select(Project))).scalars().first()
            project_root = project.root_path if project else ""
            result = await session.execute(
                select(Chat).order_by(Chat.created_at.desc())
            )
            chats = list(result.scalars().all())
            return [(c, project_root) for c in chats]


async def _show_chat(db_path: Path, prefix: str) -> dict[str, str] | list[str]:
    """Look up a chat by ID prefix.

    Returns the formatted detail dict on unique match, or the list of
    matching full IDs if ambiguous, or an empty list if none match.
    """
    async with open_session(db_path) as (_engine, factory):
        async with factory() as session:
            result = await session.execute(
                select(Chat).where(Chat.id.like(f"{prefix}%"))
            )
            matches = list(result.scalars().all())
            if len(matches) == 0:
                return []
            if len(matches) > 1:
                return [c.id for c in matches]

            chat = matches[0]
            project = (
                await session.execute(
                    select(Project).where(Project.id == chat.project_id)
                )
            ).scalars().one()
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(Invocation)
                    .where(Invocation.chat_id == chat.id)
                )
            ).scalar_one()

            if chat.root_path:
                folder = f"{chat.root_path} (chat override)"
            else:
                folder = f"{project.root_path} (project default)"

            return {
                "title": chat.title,
                "id": chat.id,
                "created": _iso(chat.created_at),
                "updated": _iso(chat.updated_at),
                "project": project.name,
                "folder": folder,
                "invocations": str(count),
            }


# --------------------------------------------------------------------------- #
# Click commands                                                              #
# --------------------------------------------------------------------------- #

@click.group("chat")
def chat_group() -> None:
    """Manage chats inside the current Subordina project."""


@chat_group.command("new")
@click.option("--title", "title", type=str, default=None, help="Chat title.")
@click.option(
    "--folder",
    "folder",
    type=str,
    default=None,
    help=(
        "Chat-specific working folder (absolute or project-relative). "
        "Defaults to inheriting the project root."
    ),
)
def chat_new(title: str | None, folder: str | None) -> None:
    """Create a new chat in the current project."""
    db_path = _require_project_db()
    project_root = project_root_for(db_path)

    chat_title = title if title else _default_title()
    folder_override = (
        _resolve_chat_folder(project_root, folder) if folder else None
    )
    chat_id, final_title = run(_create_chat(db_path, chat_title, folder_override))
    click.echo(f"Created chat '{final_title}' ({_short(chat_id)})")


@chat_group.command("list")
def chat_list() -> None:
    """List chats in the current project, newest first."""
    db_path = _require_project_db()
    pairs = run(_list_chats(db_path))
    if not pairs:
        click.echo("No chats yet. Run `subordina chat new` to create one.")
        return
    rows: list[list[str]] = []
    for chat, _project_root in pairs:
        folder = chat.root_path if chat.root_path else "(project default)"
        rows.append(
            [_short(chat.id), chat.title, _relative_or_iso(chat.created_at), folder]
        )
    _print_table(["ID", "TITLE", "CREATED", "FOLDER"], rows)


@chat_group.command("show")
@click.argument("chat_id", metavar="ID")
def chat_show(chat_id: str) -> None:
    """Show metadata for a single chat (matched by ID prefix)."""
    db_path = _require_project_db()
    result = run(_show_chat(db_path, chat_id))
    if isinstance(result, list):
        if not result:
            click.echo(f"No chat found matching prefix '{chat_id}'.", err=True)
            raise click.exceptions.Exit(1)
        click.echo(
            f"Ambiguous chat ID '{chat_id}' matches {len(result)} chats:",
            err=True,
        )
        for full_id in result:
            click.echo(f"  {full_id}", err=True)
        raise click.exceptions.Exit(1)

    click.echo(f"Chat: {result['title']}")
    click.echo(f"ID: {result['id']}")
    click.echo(f"Created: {result['created']}")
    click.echo(f"Updated: {result['updated']}")
    click.echo(f"Project: {result['project']}")
    click.echo(f"Folder: {result['folder']}")
    click.echo(f"Invocations: {result['invocations']}")
