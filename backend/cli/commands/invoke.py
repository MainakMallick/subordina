"""`subordina say / inquiry / convergence` — skill invocation commands.

Each command:

1. Walks up from ``cwd`` to find a Subordina project (`.subordina/state.db`).
2. Resolves the target chat (explicit ``--chat <short-id>`` or the most
   recently-created chat; error if none exist yet).
3. Creates an ``Invocation`` row (``skill_slug`` determined by the command).
4. Instantiates an ``AgentRunner`` (default ``agent_sdk``, override with
   ``--runner raw`` for dev dry-run).
5. Runs the loop to completion, streaming reasoning-trace output to stdout
   where the runner supports it (AgentSdkRunner -> live; RawRunner -> dumps
   the final assistant text once the run completes).
6. Prints the verified artifact (for review/convergence loops) or the
   assistant reply text (for plain chat).

Exit codes follow ``TERMINAL_STATUS_EXIT_CODE``:
- ``0`` on ``verified`` / ``replied`` / ``deferred`` (the run completed in a
  user-visible way, even if deferred means no finalization)
- ``1`` on ``error`` / ``cost-capped`` / ``cancelled``.

Note: the task brief uses ``/inquiry`` and ``/convergence`` as web-chat
conventions; the CLI uses bare names because shells treat ``/foo`` as a path.
"""
from __future__ import annotations

from pathlib import Path

import click
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.cli._db import find_project_db, run
from backend.cli._runner import (
    _short,
    create_invocation,
    exit_code_for,
    fetch_final_text,
    fetch_invocation_status,
    get_cli_runner,
    make_stdout_streamer,
    resolve_chat,
    resolve_runner_name,
)
from backend.config import get_settings


# Mapping: command name -> skill slug + header display label.
_SKILL_SLUG_BY_COMMAND: dict[str, str] = {
    "say": "chat",
    "inquiry": "query",
    "convergence": "deep-research",
}

_DISPLAY_LABEL: dict[str, str] = {
    "say": "Plain chat",
    "inquiry": "Inquiry",
    "convergence": "Convergence",
}


# --------------------------------------------------------------------------- #
# Shared invocation helper                                                    #
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


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


async def _run_invocation(
    *,
    db_path: Path,
    chat_folder: str,
    invocation_id: str,
    runner_name: str | None,
) -> None:
    """Drive the runner to completion.

    Constructs one engine bound to ``db_path``, passes the bound session
    factory to the runner (so the runner's checkpoint writes hit the same DB
    the CLI wraps around), then disposes the engine on exit (A9).

    Tests monkeypatch ``backend.cli.commands.invoke.get_cli_runner`` to inject
    a ``RawRunner`` with a ``MockLLMClient`` — no branching on a
    ``mock_responses`` keyword is needed at call time.
    """
    chosen = resolve_runner_name(runner_name)
    on_message = make_stdout_streamer() if chosen == "agent_sdk" else None

    engine = create_async_engine(_sqlite_url(db_path), future=True)
    try:
        factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
        runner = get_cli_runner(
            runner_name,
            session_factory=factory,
            project_root=chat_folder,
            on_message=on_message,
        )
        await runner.run(invocation_id)
    finally:
        await engine.dispose()


def _read_artifact(folder: str, relative: str) -> str | None:
    p = Path(folder) / relative
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _terminal_symbol(status: str) -> str:
    # ASCII-only — Windows cp1252 consoles can't render the nicer unicode
    # check/cross/warn glyphs, and the task brief says "simple ANSI chars".
    return {
        "verified": "[OK]",
        "replied": "[OK]",
        "deferred": "[!]",
        "cost-capped": "[!]",
        "cancelled": "[!]",
        "error": "[x]",
    }.get(status, "[?]")


def _print_header(
    *,
    command: str,
    chat_id: str,
    runner_name: str,
) -> None:
    label = _DISPLAY_LABEL[command]
    click.echo(
        f">> {label} | chat {_short(chat_id)} | runner={runner_name}"
    )


def _print_footer(status: str, *, extra: str = "") -> None:
    sym = _terminal_symbol(status)
    suffix = f" | {extra}" if extra else ""
    click.echo(f"\n{sym} {status}{suffix}")


def _run_one(
    *,
    command: str,
    user_input: str,
    chat_flag: str | None,
    runner_flag: str | None,
) -> None:
    """Shared body for ``say``, ``inquiry``, ``convergence``."""
    db_path = _require_project_db()
    skill_slug = _SKILL_SLUG_BY_COMMAND[command]

    # Resolve chat (by prefix or most-recent) -> errors if none exist.
    chat_id, _chat_title, _project_name, chat_folder = run(
        resolve_chat(db_path, chat_flag)
    )

    # Create the Invocation row so the runner has something to update.
    # ``get_settings()`` reads env + .env; for the raw runner we don't need
    # ``ANTHROPIC_API_KEY`` at all, so a missing key should still allow dry
    # runs (and should produce a helpful error, not a stack trace, for the
    # real runner).
    try:
        settings = get_settings()
        max_cost_cents = settings.max_cost_cents_per_invocation
    except Exception:
        effective_runner_peek = resolve_runner_name(runner_flag)
        if effective_runner_peek == "agent_sdk":
            raise click.ClickException(
                "ANTHROPIC_API_KEY is not set. Set it in your environment "
                "or a `.env` file, or re-run with `--runner raw` for a dry "
                "run that doesn't call the API."
            )
        max_cost_cents = 5000  # raw dry-run default; tokens aren't spent
    invocation_id = run(
        create_invocation(
            db_path,
            chat_id=chat_id,
            skill_slug=skill_slug,
            user_input=user_input,
            max_cost_cents=max_cost_cents,
        )
    )

    effective_runner = resolve_runner_name(runner_flag)
    _print_header(
        command=command, chat_id=chat_id, runner_name=effective_runner,
    )

    # Drive the loop.
    run(
        _run_invocation(
            db_path=db_path,
            chat_folder=chat_folder,
            invocation_id=invocation_id,
            runner_name=runner_flag,
        )
    )

    status = run(fetch_invocation_status(db_path, invocation_id))
    _print_footer(status)

    # Per-command artifact / text rendering. Only emit when we actually have
    # something to show.
    if command == "say":
        # Plain chat: final assistant text. For AgentSdkRunner we've already
        # streamed this, but re-printing the cleaned-up text is simpler than
        # threading state through the streamer.
        if effective_runner == "raw":
            text = run(fetch_final_text(db_path, invocation_id))
            if text:
                click.echo("\n--- Reply ---")
                click.echo(text)
    elif command == "inquiry":
        artifact = _read_artifact(chat_folder, "query_draft.md")
        if artifact:
            click.echo("\n--- Answer ---")
            click.echo(artifact)
        else:
            # Fall back to the model's last text so the user sees something.
            text = run(fetch_final_text(db_path, invocation_id))
            if text and effective_runner == "raw":
                click.echo("\n--- Reply (no draft written) ---")
                click.echo(text)
    elif command == "convergence":
        # The deep-research system prompt tells Claude to write a final
        # recommendation artifact; we don't hard-code the exact filename but
        # we do look for the most plausible names in order.
        artifact = None
        for candidate in (
            "final_recommendation.md",
            "recommendation.md",
            "final.md",
        ):
            artifact = _read_artifact(chat_folder, candidate)
            if artifact is not None:
                break
        if artifact:
            click.echo("\n--- Recommendation ---")
            click.echo(artifact)
        else:
            text = run(fetch_final_text(db_path, invocation_id))
            if text and effective_runner == "raw":
                click.echo(
                    "\n--- Reply (no recommendation artifact) "
                    "---"
                )
                click.echo(text)

    raise click.exceptions.Exit(exit_code_for(status))


# --------------------------------------------------------------------------- #
# Click commands                                                              #
# --------------------------------------------------------------------------- #

_RUNNER_CHOICE = click.Choice(["raw", "agent_sdk"], case_sensitive=False)


@click.command("say")
@click.argument("message", type=str)
@click.option(
    "--chat",
    "chat_id",
    type=str,
    default=None,
    help="Chat ID prefix. Defaults to the most recently-created chat.",
)
@click.option(
    "--runner",
    "runner",
    type=_RUNNER_CHOICE,
    default=None,
    help="Agent runner to use. Default: agent_sdk (real API).",
)
def say_command(message: str, chat_id: str | None, runner: str | None) -> None:
    """Send a plain chat MESSAGE to the current project's chat.

    Uses the `chat` skill (no review/convergence loop). The runner replies in
    one turn and the result is written to the DB as a ``replied`` invocation.
    """
    _run_one(
        command="say",
        user_input=message,
        chat_flag=chat_id,
        runner_flag=runner,
    )


@click.command("inquiry")
@click.argument("question", type=str)
@click.option(
    "--chat",
    "chat_id",
    type=str,
    default=None,
    help="Chat ID prefix. Defaults to the most recently-created chat.",
)
@click.option(
    "--runner",
    "runner",
    type=_RUNNER_CHOICE,
    default=None,
    help="Agent runner to use. Default: agent_sdk (real API).",
)
def inquiry_command(question: str, chat_id: str | None, runner: str | None) -> None:
    """Run a verified Inquiry (review loop) on QUESTION.

    Drives the `query` skill's draft -> review -> revise -> finalize protocol.
    On success, prints the verified answer from ``query_draft.md``.
    """
    _run_one(
        command="inquiry",
        user_input=question,
        chat_flag=chat_id,
        runner_flag=runner,
    )


@click.command("convergence")
@click.argument("problem", type=str)
@click.option(
    "--chat",
    "chat_id",
    type=str,
    default=None,
    help="Chat ID prefix. Defaults to the most recently-created chat.",
)
@click.option(
    "--runner",
    "runner",
    type=_RUNNER_CHOICE,
    default=None,
    help="Agent runner to use. Default: agent_sdk (real API).",
)
def convergence_command(
    problem: str, chat_id: str | None, runner: str | None
) -> None:
    """Run iterated architecture search (Convergence) on PROBLEM.

    Drives the `deep-research` skill's candidate / challenge / score loop
    until the convergence gate passes, then prints the final recommendation
    artifact.
    """
    _run_one(
        command="convergence",
        user_input=problem,
        chat_flag=chat_id,
        runner_flag=runner,
    )
