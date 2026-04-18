"""Tests for `subordina init`."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from backend.cli.__main__ import cli


def _run(args: list[str]) -> tuple[int, str]:
    """Invoke the CLI and return (exit_code, combined stdout+stderr)."""
    runner = CliRunner()
    result = runner.invoke(cli, args, catch_exceptions=False)
    return result.exit_code, (result.stdout or "") + (result.stderr or "")


def _list_project_rows(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return list(
            conn.execute("SELECT name, root_path, user_id FROM projects").fetchall()
        )
    finally:
        conn.close()


def test_init_creates_subordina_dir_and_db(tmp_path):
    target = tmp_path / "my-proj"
    target.mkdir()

    code, output = _run(["init", str(target)])

    assert code == 0, output
    assert "Initialized project" in output
    assert str(target) in output
    subdir = target / ".subordina"
    db = subdir / "state.db"
    assert subdir.is_dir(), f".subordina dir missing under {target}"
    assert db.is_file(), f"state.db missing under {subdir}"


def test_init_idempotent_second_run_no_error(tmp_path):
    target = tmp_path / "dup"
    target.mkdir()

    code1, _ = _run(["init", str(target)])
    code2, output2 = _run(["init", str(target)])

    assert code1 == 0
    assert code2 == 0
    assert "already initialized" in output2.lower()

    # And only one project row exists.
    rows = _list_project_rows(target / ".subordina" / "state.db")
    assert len(rows) == 1


def test_init_registers_project_with_folder_basename_as_name(tmp_path):
    target = tmp_path / "radar-fault"
    target.mkdir()

    code, _ = _run(["init", str(target)])
    assert code == 0

    rows = _list_project_rows(target / ".subordina" / "state.db")
    assert len(rows) == 1
    name, root_path, user_id = rows[0]
    assert name == "radar-fault"
    # root_path is the absolute resolved path.
    assert Path(root_path) == target.resolve()
    assert user_id == "local"


def test_init_defaults_to_current_directory(tmp_path, monkeypatch):
    target = tmp_path / "cwd-proj"
    target.mkdir()
    monkeypatch.chdir(target)

    code, output = _run(["init"])

    assert code == 0, output
    assert (target / ".subordina" / "state.db").is_file()
    rows = _list_project_rows(target / ".subordina" / "state.db")
    assert len(rows) == 1
    assert rows[0][0] == "cwd-proj"
