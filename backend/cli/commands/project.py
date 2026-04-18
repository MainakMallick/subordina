"""`subordina init` — create a `.subordina/state.db` in a target folder."""
from __future__ import annotations

from pathlib import Path

import click
from sqlalchemy import select

from backend.cli._banner import paced_lines, print_banner
from backend.cli._db import (
    SUBORDINA_DIRNAME,
    STATE_DB_FILENAME,
    open_session,
    run,
)
from backend.db.models import Base, Project


async def _init_project(folder: Path) -> tuple[str, bool]:
    """Create the `.subordina/` dir, DB, schema, and project row if missing.

    Returns (project_name, already_existed).
    """
    subdir = folder / SUBORDINA_DIRNAME
    subdir.mkdir(parents=True, exist_ok=True)
    db_path = subdir / STATE_DB_FILENAME

    async with open_session(db_path) as (engine, factory):
        # Create all tables (idempotent).
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with factory() as session:
            existing = (await session.execute(select(Project))).scalars().first()
            if existing is not None:
                return existing.name, True

            name = folder.name
            project = Project(
                name=name,
                root_path=str(folder),
                user_id="local",
            )
            session.add(project)
            await session.commit()
            return project.name, False


@click.command("init")
@click.argument(
    "folder",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
def init_command(folder: Path | None) -> None:
    """Initialize a Subordina project in FOLDER (default: current directory)."""
    target = (folder if folder is not None else Path.cwd()).resolve()
    target.mkdir(parents=True, exist_ok=True)

    print_banner()
    paced_lines([
        f"  > preparing project at {target}",
        f"  > creating {SUBORDINA_DIRNAME}/{STATE_DB_FILENAME}",
        "  > writing schema",
    ])

    name, already = run(_init_project(target))

    click.echo()
    if already:
        click.secho(f"[ok] project already initialized at {target}", bold=True)
    else:
        click.secho(f"[ok] initialized project '{name}' at {target}", bold=True)
