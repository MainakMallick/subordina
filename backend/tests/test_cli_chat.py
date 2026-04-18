"""Tests for `subordina chat new/list/show`."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from click.testing import CliRunner

from backend.cli.__main__ import cli


def _run(args: list[str]) -> tuple[int, str, str]:
    runner = CliRunner()
    result = runner.invoke(cli, args, catch_exceptions=False)
    return result.exit_code, result.stdout or "", result.stderr or ""


def _init_project(tmp_path: Path, name: str = "proj") -> Path:
    target = tmp_path / name
    target.mkdir()
    code, _stdout, _stderr = _run(["init", str(target)])
    assert code == 0
    return target


def _chdir(monkeypatch, path: Path) -> None:
    monkeypatch.chdir(path)


def _chat_rows(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return list(
            conn.execute(
                "SELECT id, title, root_path FROM chats ORDER BY created_at"
            ).fetchall()
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# chat new                                                                    #
# --------------------------------------------------------------------------- #

def test_chat_new_without_project_errors_with_helpful_message(tmp_path, monkeypatch):
    empty = tmp_path / "not-a-project"
    empty.mkdir()
    _chdir(monkeypatch, empty)

    code, stdout, stderr = _run(["chat", "new"])

    assert code == 1
    combined = stdout + stderr
    assert "No Subordina project found" in combined
    assert "subordina init" in combined


def test_chat_new_creates_chat_with_default_title(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "default-title-proj")
    _chdir(monkeypatch, target)

    code, stdout, _ = _run(["chat", "new"])
    assert code == 0, stdout

    # Title should match the default pattern "Chat YYYY-MM-DD HH:MM".
    m = re.search(r"Created chat 'Chat \d{4}-\d{2}-\d{2} \d{2}:\d{2}' \(([0-9a-f]{8})\)", stdout)
    assert m, f"Unexpected output: {stdout!r}"

    rows = _chat_rows(target / ".subordina" / "state.db")
    assert len(rows) == 1
    chat_id, title, root_path = rows[0]
    assert chat_id.startswith(m.group(1))
    assert title.startswith("Chat ")
    assert root_path is None  # Inherits from project by default.


def test_chat_new_with_custom_title_and_folder(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "custom-proj")
    _chdir(monkeypatch, target)

    subfolder = target / "experiments"
    subfolder.mkdir()

    # Relative folder should resolve against project root.
    code, stdout, _ = _run(
        ["chat", "new", "--title", "My chat", "--folder", "experiments"]
    )
    assert code == 0, stdout
    assert "Created chat 'My chat'" in stdout

    rows = _chat_rows(target / ".subordina" / "state.db")
    assert len(rows) == 1
    _id, title, root_path = rows[0]
    assert title == "My chat"
    assert Path(root_path) == subfolder.resolve()


def test_chat_new_with_absolute_folder(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "abs-proj")
    _chdir(monkeypatch, target)

    other = tmp_path / "somewhere-else"
    other.mkdir()

    code, stdout, _ = _run(
        ["chat", "new", "--title", "Abs", "--folder", str(other)]
    )
    assert code == 0, stdout

    rows = _chat_rows(target / ".subordina" / "state.db")
    assert len(rows) == 1
    _id, _title, root_path = rows[0]
    assert Path(root_path) == other.resolve()


# --------------------------------------------------------------------------- #
# chat list                                                                   #
# --------------------------------------------------------------------------- #

def test_chat_list_empty_project(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "empty-proj")
    _chdir(monkeypatch, target)

    code, stdout, _ = _run(["chat", "list"])
    assert code == 0
    assert "No chats yet" in stdout


def test_chat_list_shows_created_chats_newest_first(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "listed-proj")
    _chdir(monkeypatch, target)

    # Create two chats with a pause so their timestamps differ.
    _run(["chat", "new", "--title", "First"])
    time.sleep(1.1)
    _run(["chat", "new", "--title", "Second"])

    code, stdout, _ = _run(["chat", "list"])
    assert code == 0
    # Header present.
    assert "ID" in stdout and "TITLE" in stdout
    # Newest first: "Second" should appear before "First" in the output.
    idx_first = stdout.index("First")
    idx_second = stdout.index("Second")
    assert idx_second < idx_first, f"Newest-first ordering failed:\n{stdout}"
    # Default folder annotation.
    assert "(project default)" in stdout


def test_chat_list_without_project_errors(tmp_path, monkeypatch):
    empty = tmp_path / "bare"
    empty.mkdir()
    _chdir(monkeypatch, empty)

    code, stdout, stderr = _run(["chat", "list"])
    assert code == 1
    assert "No Subordina project found" in stdout + stderr


# --------------------------------------------------------------------------- #
# chat show                                                                   #
# --------------------------------------------------------------------------- #

def _first_chat_id(db_path: Path) -> str:
    rows = _chat_rows(db_path)
    assert rows, "Expected at least one chat row"
    return rows[0][0]


def test_chat_show_by_full_id(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "show-proj")
    _chdir(monkeypatch, target)
    _run(["chat", "new", "--title", "Findable"])

    full_id = _first_chat_id(target / ".subordina" / "state.db")

    code, stdout, _ = _run(["chat", "show", full_id])
    assert code == 0, stdout
    assert "Chat: Findable" in stdout
    assert f"ID: {full_id}" in stdout
    assert "Project: show-proj" in stdout
    assert "Invocations: 0" in stdout
    assert "(project default)" in stdout


def test_chat_show_by_short_prefix(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "short-proj")
    _chdir(monkeypatch, target)
    _run(["chat", "new", "--title", "Prefix"])

    full_id = _first_chat_id(target / ".subordina" / "state.db")
    short = full_id[:8]

    code, stdout, _ = _run(["chat", "show", short])
    assert code == 0, stdout
    assert "Chat: Prefix" in stdout
    assert f"ID: {full_id}" in stdout


def test_chat_show_ambiguous_prefix_errors(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "ambig-proj")
    _chdir(monkeypatch, target)

    # Manually insert two chats with IDs that share a prefix so we can test
    # ambiguity deterministically.
    db_path = target / ".subordina" / "state.db"
    conn = sqlite3.connect(db_path)
    try:
        # Discover the project_id.
        project_id = conn.execute("SELECT id FROM projects").fetchone()[0]
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO chats "
            "(id, project_id, title, root_path, user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("abcd1234-aaaa-aaaa-aaaa-aaaaaaaaaaaa", project_id,
             "One", None, "local", now, now),
        )
        conn.execute(
            "INSERT INTO chats "
            "(id, project_id, title, root_path, user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("abcd1234-bbbb-bbbb-bbbb-bbbbbbbbbbbb", project_id,
             "Two", None, "local", now, now),
        )
        conn.commit()
    finally:
        conn.close()

    code, stdout, stderr = _run(["chat", "show", "abcd1234"])
    assert code == 1, stdout
    combined = stdout + stderr
    assert "Ambiguous" in combined
    assert "abcd1234-aaaa" in combined
    assert "abcd1234-bbbb" in combined


def test_chat_show_no_match_errors(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "nomatch-proj")
    _chdir(monkeypatch, target)

    code, stdout, stderr = _run(["chat", "show", "deadbeef"])
    assert code == 1
    combined = stdout + stderr
    assert "No chat found" in combined
