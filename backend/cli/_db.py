"""Helpers for per-project async DB engines used by the CLI.

The CLI is short-lived and per-project: each command builds its own engine
bound to the `.subordina/state.db` of the target project, then disposes it
on exit (see AMENDMENT A9 — otherwise ResourceWarning under `-W error`).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

T = TypeVar("T")


SUBORDINA_DIRNAME = ".subordina"
STATE_DB_FILENAME = "state.db"


def find_project_db(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default: cwd) looking for a `.subordina/state.db`.

    Returns the absolute path to `state.db` or None if no project is found
    up to the filesystem root.
    """
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        candidate = d / SUBORDINA_DIRNAME / STATE_DB_FILENAME
        if candidate.is_file():
            return candidate
    return None


def project_root_for(db_path: Path) -> Path:
    """Given a `.subordina/state.db` path, return the project root folder."""
    # db_path = <project_root>/.subordina/state.db
    return db_path.parent.parent


def _sqlite_url(db_path: Path) -> str:
    # Use POSIX-style path for SQLAlchemy URL on Windows too.
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


@asynccontextmanager
async def open_session(db_path: Path):
    """Async context manager yielding (engine, session_factory) for a DB path.

    Ensures the engine is disposed on exit.
    """
    engine = create_async_engine(_sqlite_url(db_path), future=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        yield engine, factory
    finally:
        await engine.dispose()


def run(coro: Awaitable[T]) -> T:
    """Run an async coroutine from a sync Click command."""
    return asyncio.run(coro)
