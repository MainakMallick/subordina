"""Tests for `subordina say / inquiry / convergence`.

These tests exercise the CLI invocation commands end-to-end against a tmp
project+chat, using the ``RawRunner`` + ``MockLLMClient`` stack. We monkeypatch
``backend.cli.commands.invoke.get_cli_runner`` so the CLI path doesn't try to
spawn the real Claude Code subprocess, and so we can script exactly what the
"model" does per turn.

The RawRunner writes ``Checkpoint`` rows and flips ``Invocation.status`` itself
— we just assert the DB end-state.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from backend.agent.mock_client import MockLLMClient, scripted_response
from backend.agent.runner_raw import RawRunner
from backend.cli.__main__ import cli


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
    code, _stdout, _stderr = _run(["init", str(target)])
    assert code == 0
    return target


def _chdir(monkeypatch, path: Path) -> None:
    monkeypatch.chdir(path)


def _fetch_invocations(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return list(
            conn.execute(
                "SELECT id, chat_id, skill_slug, input, status FROM invocations "
                "ORDER BY created_at"
            ).fetchall()
        )
    finally:
        conn.close()


def _fetch_chats(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return list(
            conn.execute("SELECT id, title FROM chats ORDER BY created_at").fetchall()
        )
    finally:
        conn.close()


def _install_mock_runner(
    monkeypatch, mock_responses: list, project_root_override: str | None = None
) -> dict:
    """Monkeypatch ``get_cli_runner`` to hand back a ``RawRunner``.

    The ``RawRunner`` is constructed with the session_factory the CLI builds
    from the project's DB, so its checkpoint writes land in the same DB the
    test asserts against. Returns a dict the caller can inspect to confirm the
    patched function was actually called.
    """
    calls: dict = {"count": 0, "project_root": None}

    def _fake_get_runner(
        name,
        *,
        session_factory,
        project_root,
        mock_responses=None,  # noqa: ARG001 - shadow the real kwarg
        on_message=None,  # noqa: ARG001
    ):
        calls["count"] += 1
        calls["project_root"] = project_root
        client = MockLLMClient(mock_responses if mock_responses is not None
                               else list(_fake_get_runner.responses))
        return RawRunner(
            session_factory=session_factory,
            llm_client=client,
            project_root=project_root_override or project_root,
        )

    _fake_get_runner.responses = mock_responses  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "backend.cli.commands.invoke.get_cli_runner", _fake_get_runner,
    )
    # Force the effective-runner string shown in the header to be "raw" so
    # the streaming-callback branch doesn't try to import the Claude SDK.
    monkeypatch.setenv("AGENT_RUNNER", "raw")
    return calls


# --------------------------------------------------------------------------- #
# say                                                                         #
# --------------------------------------------------------------------------- #

def test_say_runs_plain_chat_end_to_end_with_mock_client(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "plain-proj")
    _chdir(monkeypatch, target)
    _run(["chat", "new", "--title", "Plain"])

    # One turn: text, no tool calls, stop_reason=end_turn -> "replied".
    _install_mock_runner(
        monkeypatch,
        [scripted_response(text="2 + 2 equals 4.", tool_calls=[])],
    )

    code, stdout, stderr = _run(["say", "What's 2+2?"])

    assert code == 0, stdout + stderr
    # Header, status line, reply body.
    assert "Plain chat" in stdout
    assert "runner=raw" in stdout
    assert "replied" in stdout
    assert "2 + 2 equals 4." in stdout

    # DB: one invocation row, status=replied, skill=chat.
    invs = _fetch_invocations(target / ".subordina" / "state.db")
    assert len(invs) == 1
    _id, _chat_id, skill, inp, status = invs[0]
    assert skill == "chat"
    assert inp == "What's 2+2?"
    assert status == "replied"


def test_say_without_chat_errors(tmp_path, monkeypatch):
    # Project exists but has no chats yet.
    target = _init_project(tmp_path, "no-chat-proj")
    _chdir(monkeypatch, target)

    # We don't need a mock runner — the command should error out before
    # reaching the runner path.
    monkeypatch.setenv("AGENT_RUNNER", "raw")

    code, stdout, stderr = _run(["say", "hi"])

    combined = stdout + stderr
    assert code != 0
    assert "No chats yet" in combined
    assert "subordina chat new" in combined


def test_say_outside_project_errors(tmp_path, monkeypatch):
    # No .subordina/ anywhere above us.
    bare = tmp_path / "bare"
    bare.mkdir()
    _chdir(monkeypatch, bare)

    monkeypatch.setenv("AGENT_RUNNER", "raw")

    code, stdout, stderr = _run(["say", "hi"])

    combined = stdout + stderr
    assert code == 1
    assert "No Subordina project found" in combined


# --------------------------------------------------------------------------- #
# inquiry                                                                     #
# --------------------------------------------------------------------------- #

def test_inquiry_runs_review_loop_end_to_end_with_mock_client(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "inq-proj")
    _chdir(monkeypatch, target)
    _run(["chat", "new", "--title", "Q"])

    # Three scripted turns: write draft, submit_draft -> pass review ->
    # finalize. The critique must be >= 50 chars and use a verification word
    # (per critique_quality gate) for a "pass" verdict.
    _install_mock_runner(
        monkeypatch,
        [
            scripted_response(
                text="Writing draft.",
                tool_calls=[
                    (
                        "write_file",
                        {
                            "path": "query_draft.md",
                            "content": (
                                "# Query: Why?\n\n"
                                "## Answer\nBecause.\n\n"
                                "## Evidence\n- Source A\n\n"
                                "## Confidence\nMEDIUM\n\n"
                                "## What I'm NOT sure about\nNothing.\n"
                            ),
                        },
                    ),
                    ("submit_draft", {"artifacts": ["query_draft.md"]}),
                ],
            ),
            scripted_response(
                text="Reviewing.",
                tool_calls=[(
                    "submit_review",
                    {
                        "verdict": "pass",
                        "critique": (
                            "I verified claim 1 against the source URL; "
                            "numbers match and the calculation is consistent."
                        ),
                    },
                )],
            ),
            scripted_response(
                text="Finalising.",
                tool_calls=[("finalize", {})],
            ),
        ],
    )

    code, stdout, stderr = _run(["inquiry", "Why?"])

    assert code == 0, stdout + stderr
    assert "Inquiry" in stdout
    assert "runner=raw" in stdout
    assert "verified" in stdout
    # Draft content should be echoed verbatim under the "Answer" section.
    assert "Answer" in stdout
    assert "Because." in stdout

    # DB side: invocation verified.
    invs = _fetch_invocations(target / ".subordina" / "state.db")
    assert len(invs) == 1
    _id, _chat_id, skill, inp, status = invs[0]
    assert skill == "query"
    assert inp == "Why?"
    assert status == "verified"

    # And the draft file lives in the chat folder (== project root here).
    assert (target / "query_draft.md").is_file()


def test_inquiry_with_specific_chat_id(tmp_path, monkeypatch):
    target = _init_project(tmp_path, "inq-chat-proj")
    _chdir(monkeypatch, target)

    # Create two chats, both with folders inside the project.
    _run(["chat", "new", "--title", "First"])
    _run(["chat", "new", "--title", "Second"])

    db_path = target / ".subordina" / "state.db"
    chats = _fetch_chats(db_path)
    assert len(chats) == 2
    first_id = chats[0][0]  # oldest first per _fetch_chats ordering
    first_short = first_id[:8]

    _install_mock_runner(
        monkeypatch,
        [
            scripted_response(
                text="Drafting.",
                tool_calls=[
                    (
                        "write_file",
                        {
                            "path": "query_draft.md",
                            "content": (
                                "# Query: ?\n\n## Answer\nX\n\n"
                                "## Evidence\n- A\n\n## Confidence\nLOW\n\n"
                                "## What I'm NOT sure about\nAll of it.\n"
                            ),
                        },
                    ),
                    ("submit_draft", {"artifacts": ["query_draft.md"]}),
                ],
            ),
            scripted_response(
                text="Reviewing.",
                tool_calls=[(
                    "submit_review",
                    {
                        "verdict": "pass",
                        "critique": (
                            "Checked the single evidence source, the claim is "
                            "consistent with the cited paragraph. Confidence "
                            "is appropriately LOW; verified."
                        ),
                    },
                )],
            ),
            scripted_response(
                text="Done.",
                tool_calls=[("finalize", {})],
            ),
        ],
    )

    # Target the FIRST chat by short prefix.
    code, stdout, stderr = _run(["inquiry", "?", "--chat", first_short])
    assert code == 0, stdout + stderr

    # The invocation should be attached to `first_id`, not the latest chat.
    invs = _fetch_invocations(db_path)
    assert len(invs) == 1
    _inv_id, inv_chat_id, skill, _inp, status = invs[0]
    assert inv_chat_id == first_id
    assert skill == "query"
    assert status == "verified"


# --------------------------------------------------------------------------- #
# convergence                                                                 #
# --------------------------------------------------------------------------- #

def test_convergence_runs_convergence_loop_end_to_end_with_mock_client(
    tmp_path, monkeypatch,
):
    target = _init_project(tmp_path, "conv-proj")
    _chdir(monkeypatch, target)
    _run(["chat", "new", "--title", "C"])

    # Convergence gate: iteration >= 3 AND leader_streak >= 2 consecutive
    # "survived" challenges. So we need: add_candidate, then three iterations
    # where the same leader survives twice, then write the final
    # recommendation file + record_final.
    scored_for = {
        "theoretical": 8, "empirical": 7, "feasibility": 6,
        "complexity": 5, "novelty": 6,
    }
    _install_mock_runner(
        monkeypatch,
        [
            # Turn 1: add candidate, challenge survives, score iter 1.
            scripted_response(
                text="Iter 1.",
                tool_calls=[
                    ("add_candidate",
                     {"name": "Alpha", "scores": scored_for}),
                    ("challenge_leader",
                     {"leader": "Alpha", "result": "survived",
                      "evidence": "Searched for method X and Y; "
                                  "neither beats Alpha on composite."}),
                    ("score_iteration", {}),
                ],
            ),
            # Turn 2: challenge survives again, score iter 2 (streak=2).
            scripted_response(
                text="Iter 2.",
                tool_calls=[
                    ("challenge_leader",
                     {"leader": "Alpha", "result": "survived",
                      "evidence": "Checked a second class of methods (Z) "
                                  "and they underperform Alpha on the "
                                  "feasibility axis."}),
                    ("score_iteration", {}),
                ],
            ),
            # Turn 3: one more survived challenge + score iter 3, then write
            # the recommendation artifact and record_final.
            scripted_response(
                text="Iter 3 + record.",
                tool_calls=[
                    ("challenge_leader",
                     {"leader": "Alpha", "result": "survived",
                      "evidence": "Third round: searched the 2025 literature "
                                  "for new candidates; Alpha still leads."}),
                    ("score_iteration", {}),
                    ("write_file",
                     {"path": "final_recommendation.md",
                      "content": (
                          "# Recommendation: Alpha\n\n"
                          "Alpha wins on the composite score.\n\n"
                          "## Why this wins\n- Theoretical basis X\n"
                          "- Empirical result Y\n"
                      )}),
                    ("record_final", {"recommendation": "Alpha"}),
                ],
            ),
        ],
    )

    code, stdout, stderr = _run(["convergence", "Which method?"])

    assert code == 0, stdout + stderr
    assert "Convergence" in stdout
    assert "runner=raw" in stdout
    assert "verified" in stdout
    # The recommendation artifact should be echoed at the bottom.
    assert "Recommendation: Alpha" in stdout

    # DB side: invocation verified and skill=deep-research.
    invs = _fetch_invocations(target / ".subordina" / "state.db")
    assert len(invs) == 1
    _id, _chat_id, skill, inp, status = invs[0]
    assert skill == "deep-research"
    assert inp == "Which method?"
    assert status == "verified"

    # And the recommendation file is on disk in the chat folder.
    assert (target / "final_recommendation.md").is_file()
