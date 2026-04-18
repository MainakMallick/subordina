"""Integration tests for ``AgentSdkRunner``.

These tests spawn a real Claude Code subprocess and hit the Anthropic API; they
are expensive, slow, and require a valid ``ANTHROPIC_API_KEY`` plus the Claude
Code CLI installed on ``$PATH``. They are skipped by default.

Enable with::

    RUN_INTEGRATION=1 pytest -v backend/tests/test_runner_agent_sdk.py

Per plan amendment A10: do **not** add unit tests that mock the SDK subprocess.
Loop semantics are covered by ``test_runner_raw.py``; this file's only job is
to prove the real-subprocess path still drives a skill through to
``verified`` / ``replied``.
"""
from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="set RUN_INTEGRATION=1 to run real-API integration tests",
)


@pytest.mark.integration
async def test_smoke_plain_chat_runs_to_completion() -> None:
    """Minimal end-to-end smoke: plain-chat skill -> ``replied`` + checkpoint.

    TODO (Task 16 / CI hardening): wire a test Anthropic API key in CI,
    stand up a sqlite DB, seed Project/Chat/Invocation, run the runner, and
    assert ``inv.status == "replied"``, ``>=1`` checkpoint exists, and
    ``inv.total_cost_cents > 0``.
    """
    pytest.skip("TODO: stub — fill in when we have a test Anthropic key in CI")


@pytest.mark.integration
async def test_review_loop_reaches_verified() -> None:
    """End-to-end: ``query`` skill drives ReviewLoop to pass -> ``verified``.

    TODO: feed a small, bounded prompt that the model can finish within the
    ``max_turns=15`` budget, assert ``inv.status == "verified"`` and that the
    final ``finalize`` call was observed via PostToolUse hook.
    """
    pytest.skip("TODO: stub — depends on real API key + bounded prompt fixture")
