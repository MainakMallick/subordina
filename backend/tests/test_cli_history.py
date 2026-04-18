"""Tests for `subordina history` and `subordina show`.

These commands are DB-read-only — no runner interaction. We seed the schema
(via `subordina init`) and then insert rows directly through an async session.
That's much faster than driving ``_run_one`` end-to-end and keeps this test
file scoped to the read-side behaviour the task brief asks for.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from click.testing import CliRunner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.cli.__main__ import cli
from backend.db.models import Chat, Checkpoint, Invocation, Project


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _run(args: list[str]) -> tuple[int, str, str]:
    runner = CliRunner()
    result = runner.invoke(cli, args, catch_exceptions=False)
    return result.exit_code, result.stdout or "", result.stderr or ""


def _init_project(tmp_path: Path, name: str = "proj") -> Path:
    target = tmp_path / name
    target.mkdir()
    code, _out, _err = _run(["init", str(target)])
    assert code == 0
    return target


def _chdir(monkeypatch, path: Path) -> None:
    monkeypatch.chdir(path)


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


async def _seed_async(
    db_path: Path, seeder
) -> Any:
    engine = create_async_engine(_sqlite_url(db_path), future=True)
    try:
        factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
        async with factory() as session:
            result = await seeder(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


def _seed(db_path: Path, seeder) -> Any:
    """Synchronous wrapper so tests can read naturally."""
    return asyncio.run(_seed_async(db_path, seeder))


async def _get_project(session: AsyncSession) -> Project:
    return (await session.execute(select(Project))).scalars().one()


def _make_chat(
    *,
    project_id: str,
    title: str,
    chat_id: str | None = None,
    root_path: str | None = None,
    created_at: datetime | None = None,
) -> Chat:
    kwargs: dict[str, Any] = {
        "project_id": project_id,
        "title": title,
        "root_path": root_path,
        "user_id": "local",
    }
    if chat_id is not None:
        kwargs["id"] = chat_id
    if created_at is not None:
        kwargs["created_at"] = created_at
        kwargs["updated_at"] = created_at
    return Chat(**kwargs)


def _make_invocation(
    *,
    chat_id: str,
    skill_slug: str,
    input_: str,
    status: str,
    invocation_id: str | None = None,
    created_at: datetime | None = None,
) -> Invocation:
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "skill_slug": skill_slug,
        "input": input_,
        "status": status,
        "user_id": "local",
        "total_cost_cents": 0,
        "max_cost_cents": 5000,
    }
    if invocation_id is not None:
        kwargs["id"] = invocation_id
    if created_at is not None:
        kwargs["created_at"] = created_at
        kwargs["updated_at"] = created_at
    return Invocation(**kwargs)


# --------------------------------------------------------------------------- #
# history                                                                     #
# --------------------------------------------------------------------------- #

def test_history_without_project_errors(tmp_path, monkeypatch):
    empty = tmp_path / "nope"
    empty.mkdir()
    _chdir(monkeypatch, empty)

    code, stdout, stderr = _run(["history"])
    assert code == 1
    assert "No Subordina project found" in stdout + stderr


def test_history_empty_project(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "empty-proj")
    _chdir(monkeypatch, target)

    code, stdout, _ = _run(["history"])
    assert code == 0
    assert "No invocations yet" in stdout
    assert "subordina say" in stdout
    assert "subordina inquiry" in stdout
    assert "subordina convergence" in stdout


def test_history_lists_invocations_newest_first(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "listed-proj")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    now = datetime.now(timezone.utc)

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="Main")
        session.add(chat)
        await session.flush()
        # Newest-first ordering is the contract: seed three invocations with
        # explicit timestamps so ordering doesn't rely on insert speed.
        a = _make_invocation(
            chat_id=chat.id,
            skill_slug="chat",
            input_="hello there friend",
            status="replied",
            created_at=now - timedelta(hours=2),
        )
        b = _make_invocation(
            chat_id=chat.id,
            skill_slug="query",
            input_="what is attention?",
            status="verified",
            created_at=now - timedelta(hours=1),
        )
        c = _make_invocation(
            chat_id=chat.id,
            skill_slug="deep-research",
            input_="best optimizer for small batch?",
            status="error",
            created_at=now,
        )
        session.add_all([a, b, c])

    _seed(db_path, seed)

    code, stdout, _ = _run(["history"])
    assert code == 0, stdout
    assert "ID" in stdout and "METHOD" in stdout and "STATUS" in stdout

    # Newest first -> Convergence row before Inquiry before chat.
    idx_conv = stdout.index("Convergence")
    idx_inq = stdout.index("Inquiry")
    idx_chat = stdout.index("chat")
    assert idx_conv < idx_inq < idx_chat, f"Bad ordering:\n{stdout}"

    # Subject text / statuses rendered.
    assert "best optimizer" in stdout
    assert "what is attention?" in stdout
    assert "hello there friend" in stdout
    assert "verified" in stdout
    assert "replied" in stdout
    assert "error" in stdout


def test_history_filter_by_chat(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "filter-proj")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat_a = _make_chat(
            project_id=project.id,
            title="Alpha",
            chat_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        chat_b = _make_chat(
            project_id=project.id,
            title="Beta",
            chat_id="bbbbbbbb-0000-0000-0000-000000000002",
        )
        session.add_all([chat_a, chat_b])
        await session.flush()
        session.add_all([
            _make_invocation(
                chat_id=chat_a.id,
                skill_slug="chat",
                input_="in alpha",
                status="replied",
            ),
            _make_invocation(
                chat_id=chat_b.id,
                skill_slug="chat",
                input_="in beta",
                status="replied",
            ),
        ])

    _seed(db_path, seed)

    code, stdout, _ = _run(["history", "--chat", "aaaaaaaa"])
    assert code == 0, stdout
    assert "in alpha" in stdout
    assert "in beta" not in stdout

    code, stdout, _ = _run(["history", "--chat", "bbbbbbbb"])
    assert code == 0, stdout
    assert "in beta" in stdout
    assert "in alpha" not in stdout


def test_history_filter_by_missing_chat_errors(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "missing-proj")
    _chdir(monkeypatch, target)

    code, stdout, stderr = _run(["history", "--chat", "deadbeef"])
    assert code == 1
    assert "No chat found" in stdout + stderr


def test_history_limit_caps_output(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "limit-proj")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="Main")
        session.add(chat)
        await session.flush()
        base = datetime.now(timezone.utc)
        for i in range(30):
            session.add(
                _make_invocation(
                    chat_id=chat.id,
                    skill_slug="chat",
                    input_=f"msg-{i:02d}",
                    status="replied",
                    created_at=base - timedelta(minutes=30 - i),
                )
            )

    _seed(db_path, seed)

    code, stdout, _ = _run(["history", "--limit", "5"])
    assert code == 0, stdout
    # Only the 5 newest (msg-25..29) should be present.
    present = [i for i in range(30) if f"msg-{i:02d}" in stdout]
    assert len(present) == 5
    assert set(present) == {25, 26, 27, 28, 29}


# --------------------------------------------------------------------------- #
# show                                                                        #
# --------------------------------------------------------------------------- #

def test_show_by_full_id(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "show-full")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    # Write the expected Inquiry artifact to the chat's effective folder
    # (== project root, since the chat has no override).
    (target / "query_draft.md").write_text(
        "# Verified answer\n\nAttention is dot-product mixing.\n",
        encoding="utf-8",
    )

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="Main")
        session.add(chat)
        await session.flush()
        inv = _make_invocation(
            chat_id=chat.id,
            skill_slug="query",
            input_="what is attention?",
            status="verified",
            invocation_id="12345678-1111-1111-1111-111111111111",
        )
        session.add(inv)
        session.add(
            Checkpoint(
                invocation_id=inv.id,
                iteration=0,
                conversation_json=[],
                running_cost_cents=0,
            )
        )

    _seed(db_path, seed)

    code, stdout, _ = _run(["show", "12345678-1111-1111-1111-111111111111"])
    assert code == 0, stdout
    assert "Method: Inquiry" in stdout
    assert "Chat: Main (" in stdout
    assert "Subject: what is attention?" in stdout
    assert "Status: verified" in stdout
    assert "Iterations: 1" in stdout
    assert "--- Artifact ---" in stdout
    assert "Verified answer" in stdout
    assert "Attention is dot-product mixing." in stdout


def test_show_by_short_prefix(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "show-short")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    (target / "query_draft.md").write_text("artifact body", encoding="utf-8")

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="C")
        session.add(chat)
        await session.flush()
        session.add(
            _make_invocation(
                chat_id=chat.id,
                skill_slug="query",
                input_="q",
                status="verified",
                invocation_id="abcd0001-1111-1111-1111-111111111111",
            )
        )

    _seed(db_path, seed)

    code, stdout, _ = _run(["show", "abcd0001"])
    assert code == 0, stdout
    assert "Method: Inquiry" in stdout
    assert "artifact body" in stdout


def test_show_ambiguous_prefix_errors(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "show-ambig")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="C")
        session.add(chat)
        await session.flush()
        session.add_all([
            _make_invocation(
                chat_id=chat.id,
                skill_slug="chat",
                input_="one",
                status="replied",
                invocation_id="dead1234-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ),
            _make_invocation(
                chat_id=chat.id,
                skill_slug="chat",
                input_="two",
                status="replied",
                invocation_id="dead1234-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            ),
        ])

    _seed(db_path, seed)

    code, stdout, stderr = _run(["show", "dead1234"])
    assert code == 1
    combined = stdout + stderr
    assert "Ambiguous" in combined
    assert "dead1234-aaaa" in combined
    assert "dead1234-bbbb" in combined


def test_show_no_match_errors(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "show-miss")
    _chdir(monkeypatch, target)

    code, stdout, stderr = _run(["show", "deadbeef"])
    assert code == 1
    assert "No invocation found" in stdout + stderr


def test_show_running_invocation_shows_diagnostic_not_artifact(
    tmp_path, monkeypatch
):
    target = _init_project(tmp_path, "show-running")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    # Deliberately *don't* write query_draft.md. Running status should not
    # try to open it.
    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="C")
        session.add(chat)
        await session.flush()
        session.add(
            _make_invocation(
                chat_id=chat.id,
                skill_slug="query",
                input_="running one",
                status="running",
                invocation_id="beef0000-1111-1111-1111-111111111111",
            )
        )

    _seed(db_path, seed)

    code, stdout, _ = _run(["show", "beef0000"])
    assert code == 0, stdout
    assert "Status: running" in stdout
    assert "not in a terminal state" in stdout
    # Critically: no artifact block header printed and no crash.
    assert "--- Artifact ---" not in stdout


def test_show_plain_chat_reads_last_checkpoint_text(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "show-chat")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="C")
        session.add(chat)
        await session.flush()
        inv = _make_invocation(
            chat_id=chat.id,
            skill_slug="chat",
            input_="say hi",
            status="replied",
            invocation_id="ca11ab1e-1111-1111-1111-111111111111",
        )
        session.add(inv)
        # RawRunner-shaped conversation: list of {role, content-blocks}.
        session.add(
            Checkpoint(
                invocation_id=inv.id,
                iteration=0,
                conversation_json=[
                    {"role": "user", "content": "say hi"},
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Hello from the past!"}
                        ],
                    },
                ],
                running_cost_cents=0,
            )
        )

    _seed(db_path, seed)

    code, stdout, _ = _run(["show", "ca11ab1e"])
    assert code == 0, stdout
    assert "Method: chat" in stdout
    assert "Status: replied" in stdout
    assert "--- Artifact ---" in stdout
    assert "Hello from the past!" in stdout


def test_show_missing_artifact_file_shows_diagnostic(tmp_path, monkeypatch):
    """A verified Inquiry with no ``query_draft.md`` should not crash."""
    target = _init_project(tmp_path, "show-noartifact")
    _chdir(monkeypatch, target)
    db_path = target / ".subordina" / "state.db"

    async def seed(session: AsyncSession):
        project = await _get_project(session)
        chat = _make_chat(project_id=project.id, title="C")
        session.add(chat)
        await session.flush()
        session.add(
            _make_invocation(
                chat_id=chat.id,
                skill_slug="query",
                input_="q",
                status="verified",
                invocation_id="f00d0000-1111-1111-1111-111111111111",
            )
        )

    _seed(db_path, seed)

    code, stdout, _ = _run(["show", "f00d0000"])
    assert code == 0, stdout
    assert "--- Artifact ---" in stdout
    assert "no artifact file" in stdout
