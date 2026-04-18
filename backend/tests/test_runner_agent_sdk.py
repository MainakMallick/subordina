"""End-to-end integration test for the Agent SDK runner.

Skipped by default; set ``RUN_INTEGRATION=1`` and provide ``ANTHROPIC_API_KEY``
to run. This test spawns a real Claude Code subprocess and makes real Anthropic
API calls.

Cost: approximately $0.005-$0.02 per run.

Enable with::

    RUN_INTEGRATION=1 pytest -v backend/tests/test_runner_agent_sdk.py

Per plan amendment A10: do **not** add unit tests that mock the SDK subprocess.
Loop semantics are covered by ``test_runner_raw.py``; this file's only job is
to prove the real-subprocess path still drives a skill through to
``replied`` / ``verified`` with artifacts and DB rows intact.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1"
    or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="set RUN_INTEGRATION=1 and ANTHROPIC_API_KEY to run real-API tests",
)


def _locate_subordina() -> str:
    """Find the installed ``subordina`` console script.

    Prefer the script that sits next to the current interpreter (so the test
    exercises the venv's freshly-installed CLI even when the shell PATH points
    elsewhere). Fall back to ``shutil.which`` so this still works if the test
    is driven via ``python -m pytest`` outside the venv.
    """
    interp_dir = Path(sys.executable).parent
    for name in ("subordina.exe", "subordina"):
        candidate = interp_dir / name
        if candidate.exists():
            return str(candidate)
    resolved = shutil.which("subordina")
    if resolved:
        return resolved
    pytest.skip("`subordina` console script not found on PATH")


@pytest.mark.integration
def test_plain_chat_end_to_end(tmp_path: Path) -> None:
    """Smoke: ``subordina init``, ``chat new``, ``say`` against the real API.

    Verifies the full CLI -> AgentSdkRunner -> Claude Code CLI -> Anthropic API
    -> back to DB -> artifact chain works. Assertions are deliberately tolerant
    of real-model variability: we check structural elements (exit codes, DB
    rows, replied/verified status) rather than exact text or token counts.
    """
    subordina = _locate_subordina()
    # Force the default runner to agent_sdk regardless of ambient env.
    env = {**os.environ, "AGENT_RUNNER": "agent_sdk"}

    def _run(*args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            [subordina, *args],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )

    # 1. Initialize project.
    init_result = _run("init", ".")
    assert init_result.returncode == 0, (
        f"init failed: stdout={init_result.stdout!r} stderr={init_result.stderr!r}"
    )
    combined_init = init_result.stdout + init_result.stderr
    assert "Initialized" in combined_init or "already" in combined_init
    assert (tmp_path / ".subordina" / "state.db").exists()

    # 2. Create a chat.
    chat_result = _run("chat", "new", "--title", "integration-smoke")
    assert chat_result.returncode == 0, (
        f"chat new failed: stdout={chat_result.stdout!r} stderr={chat_result.stderr!r}"
    )
    assert "Created chat" in chat_result.stdout

    # 3. Send a simple plain-chat message. Generous timeout because this
    # spawns a real Claude Code subprocess + API round-trip.
    say_result = _run(
        "say",
        "What is 2 + 2? Answer with just the number, nothing else.",
        timeout=180,
    )
    assert say_result.returncode == 0, (
        f"say failed: stdout={say_result.stdout!r} stderr={say_result.stderr!r}"
    )
    combined_say = (say_result.stdout + say_result.stderr).lower()
    # Status footer should show the terminal success state.
    assert "replied" in combined_say or "[ok]" in combined_say
    # The model should have answered "four" or "4" somewhere in the stream.
    assert "4" in combined_say or "four" in combined_say

    # 4. History lists the invocation.
    history_result = _run("history", "--limit", "5")
    assert history_result.returncode == 0
    assert "chat" in history_result.stdout.lower()  # METHOD column value

    # Expect at least one data row below the header.
    lines = [
        ln for ln in history_result.stdout.splitlines()
        if ln.strip() and not ln.startswith("ID ")
    ]
    assert len(lines) >= 1, (
        f"Expected at least 1 invocation row, got: {history_result.stdout!r}"
    )
