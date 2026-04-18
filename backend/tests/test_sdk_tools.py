"""Unit tests for the SDK tool adapter (``backend.agent.sdk_tools``).

These tests invoke the adapter's ``@tool``-decorated async handlers directly
via the ``build_enforcement_tools`` helper — no Claude Code subprocess, no
``create_sdk_mcp_server`` wrapping, no real MCP transport. The goal is to
nail down the adapter's error-path contract: on any enforcement gate failure
the returned dict must carry ``is_error=True`` (snake_case) so the SDK's
``create_sdk_mcp_server.call_tool`` handler forwards the failure as an MCP
error to the model. The camelCase variant ``isError`` silently drops the
flag and voids the entire enforcement layer.
"""
from __future__ import annotations

import json

from backend.agent.sdk_tools import _adapt, build_enforcement_tools
from backend.agent.tool_handlers import ToolExecutor
from backend.enforcement.research_loop import ResearchLoop
from backend.enforcement.review_loop import ReviewLoop


def _executor(tmp_path):
    return ToolExecutor(
        review_loop=ReviewLoop(skill="query"),
        research_loop=ResearchLoop(),
        project_root=str(tmp_path),
    )


def _tools_by_name(executor):
    """Return {tool_name: SdkMcpTool} for the adapter tools bound to ``executor``."""
    return {t.name: t for t in build_enforcement_tools(executor)}


# ---------------------------------------------------------------------------
# _adapt() — pure-function contract
# ---------------------------------------------------------------------------


def test_adapt_success_omits_is_error():
    result = _adapt({"ok": True, "result": {"status": "reviewing"}})
    assert "is_error" not in result
    assert "isError" not in result
    assert result["content"][0]["type"] == "text"
    # Non-string payload is JSON-encoded.
    assert json.loads(result["content"][0]["text"]) == {"status": "reviewing"}


def test_adapt_failure_uses_snake_case_is_error():
    """Regression test for the camelCase bug.

    The adapter MUST use ``is_error`` (snake_case) because the SDK's
    ``create_sdk_mcp_server.call_tool`` reads ``result.get("is_error", False)``
    to populate the MCP ``CallToolResult.isError`` field. CamelCase here is
    silently ignored and the model sees the failure as a successful tool
    result.
    """
    result = _adapt({"ok": False, "error": "gate failed: critique too short"})
    assert result["is_error"] is True, (
        f"adapter must emit is_error (snake_case); got keys: {list(result.keys())}"
    )
    # Belt-and-suspenders: the camelCase key must not be present. Its presence
    # alongside is_error would not re-introduce the bug, but would indicate a
    # sloppy merge.
    assert "isError" not in result
    assert result["content"][0]["text"] == "gate failed: critique too short"


def test_adapt_failure_default_message_when_error_missing():
    result = _adapt({"ok": False})
    assert result["is_error"] is True
    assert result["content"][0]["text"] == "unknown error"


# ---------------------------------------------------------------------------
# End-to-end through the @tool-decorated async handlers
# ---------------------------------------------------------------------------


async def test_submit_review_bad_critique_returns_is_error(tmp_path):
    """A critique-quality gate failure must propagate through the adapter
    with ``is_error=True`` (snake_case). This is the exact path that
    silently broke under the camelCase bug.
    """
    tools = _tools_by_name(_executor(tmp_path))
    # Move the review loop into 'reviewing' so submit_review is legal.
    draft_result = await tools["submit_draft"].handler({"artifacts": ["x.md"]})
    assert draft_result.get("is_error") is not True
    assert draft_result.get("isError") is not True

    # Now submit a no-op critique — the critique-quality gate fails.
    review_result = await tools["submit_review"].handler(
        {"verdict": "pass", "critique": "lgtm"},
    )
    assert review_result.get("is_error") is True, (
        "adapter must flag gate failure with is_error (snake_case); "
        f"got keys: {list(review_result.keys())}"
    )
    # Explicitly assert the camelCase variant is NOT used: if a future refactor
    # reintroduces the bug this assertion catches it immediately.
    assert "isError" not in review_result


async def test_finalize_blocked_returns_is_error(tmp_path):
    """``finalize`` before the loop has passed raises
    ``FinalizationBlockedError`` — must surface as ``is_error=True``."""
    tools = _tools_by_name(_executor(tmp_path))
    await tools["submit_draft"].handler({"artifacts": ["x.md"]})
    result = await tools["finalize"].handler({})
    assert result.get("is_error") is True
    assert "isError" not in result


async def test_record_final_blocked_returns_is_error(tmp_path):
    """``record_final`` before research-loop convergence must also surface
    as ``is_error=True``."""
    tools = _tools_by_name(_executor(tmp_path))
    result = await tools["record_final"].handler({"recommendation": "X"})
    assert result.get("is_error") is True
    assert "isError" not in result


async def test_add_candidate_invalid_axes_returns_is_error(tmp_path):
    """Missing scoring axes -> ValueError -> ``is_error=True``."""
    tools = _tools_by_name(_executor(tmp_path))
    result = await tools["add_candidate"].handler(
        {"name": "X", "scores": {"theoretical": 5}, "evidence": []},
    )
    assert result.get("is_error") is True
    assert "isError" not in result


async def test_submit_draft_happy_path_has_no_error_flag(tmp_path):
    """Happy path must not carry either error key."""
    tools = _tools_by_name(_executor(tmp_path))
    result = await tools["submit_draft"].handler({"artifacts": ["x.md"]})
    assert "is_error" not in result
    assert "isError" not in result
    # And it returns the expected MCP content-block shape.
    assert result["content"][0]["type"] == "text"


async def test_write_file_path_traversal_returns_is_error(tmp_path):
    """Path-traversal attempts raise ValueError in the handler; the adapter
    must flag them as errors to the model."""
    tools = _tools_by_name(_executor(tmp_path))
    result = await tools["write_file"].handler(
        {"path": "../evil.md", "content": "x"},
    )
    assert result.get("is_error") is True
    assert "isError" not in result


# ---------------------------------------------------------------------------
# Sanity: build_enforcement_tools surfaces the full tool registry
# ---------------------------------------------------------------------------


def test_build_enforcement_tools_exposes_all_eleven(tmp_path):
    names = {t.name for t in build_enforcement_tools(_executor(tmp_path))}
    assert names == {
        "web_search",
        "read_file",
        "write_file",
        "submit_draft",
        "submit_review",
        "submit_revision",
        "finalize",
        "add_candidate",
        "challenge_leader",
        "score_iteration",
        "record_final",
    }
