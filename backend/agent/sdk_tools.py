"""Agent SDK adapter for the 11 enforcement tools.

Thin wrapper only: each adapter dispatches to the existing ``ToolExecutor._h_*``
handler and translates the ``{"ok": bool, ...}`` shape into the MCP content-block
shape the Claude Agent SDK expects. Enforcement remains inline in the handlers
(see ``backend/agent/tool_handlers.py``) — this module does not reimplement any
gate.

Usage:

    from backend.agent.tool_handlers import ToolExecutor
    from backend.agent.sdk_tools import make_enforcement_mcp_server

    executor = ToolExecutor(review_loop=..., research_loop=..., project_root=...)
    server = make_enforcement_mcp_server(executor)

The returned object is an in-process SDK MCP server, suitable for passing to
``ClaudeAgentOptions(mcp_servers={"subordina-enforcement": server})``.
"""
from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from backend.agent.tool_handlers import ToolExecutor


def _adapt(result: dict[str, Any]) -> dict[str, Any]:
    """Translate a ToolExecutor result into an SDK content-block response.

    Success -> {"content": [{"type": "text", "text": <json-or-string>}]}
    Failure -> same shape plus ``"isError": True``; the model sees the error and
    can retry. Failure never finalizes (matches RawRunner semantics).
    """
    if result.get("ok"):
        payload = result.get("result", "")
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return {"content": [{"type": "text", "text": text}]}
    return {
        "content": [{"type": "text", "text": result.get("error", "unknown error")}],
        "isError": True,
    }


def make_enforcement_mcp_server(executor: ToolExecutor):
    """Build an in-process MCP server exposing the 11 enforcement tools.

    The ``executor`` carries the per-invocation ReviewLoop / ResearchLoop /
    project_root state, so one server is built per invocation.
    """

    # ---- file / search ----

    @tool("web_search", "Search the web for information.", {"query": str})
    async def _web_search(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("web_search", args))

    @tool(
        "read_file",
        "Read a UTF-8 text file relative to the chat's working folder.",
        {"path": str},
    )
    async def _read_file(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("read_file", args))

    @tool(
        "write_file",
        "Write (or overwrite) a UTF-8 text file relative to the chat's working folder.",
        {"path": str, "content": str},
    )
    async def _write_file(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("write_file", args))

    # ---- review loop ----

    @tool(
        "submit_draft",
        "Submit the first draft of the artifact(s) for review.",
        {"artifacts": list},
    )
    async def _submit_draft(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("submit_draft", args))

    @tool(
        "submit_review",
        "Submit a review verdict ('pass'|'fail') and critique on the current draft.",
        {"verdict": str, "critique": str},
    )
    async def _submit_review(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("submit_review", args))

    @tool(
        "submit_revision",
        "Submit a revised artifact after a failing review.",
        {"artifacts": list},
    )
    async def _submit_revision(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("submit_revision", args))

    @tool(
        "finalize",
        "Finalize the invocation. Blocks (returns isError) unless the review loop has passed.",
        {},
    )
    async def _finalize(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("finalize", args))

    # ---- research loop ----

    @tool(
        "add_candidate",
        "Register a candidate method with five-axis scores and supporting evidence.",
        {"name": str, "scores": dict, "evidence": list},
    )
    async def _add_candidate(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("add_candidate", args))

    @tool(
        "challenge_leader",
        "Challenge the current leader with a named result and evidence.",
        {"leader": str, "result": str, "evidence": str},
    )
    async def _challenge_leader(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("challenge_leader", args))

    @tool(
        "score_iteration",
        "Close the current convergence iteration; advances the iteration counter.",
        {},
    )
    async def _score_iteration(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("score_iteration", args))

    @tool(
        "record_final",
        "Record the final recommendation. Blocks (returns isError) unless the research loop has converged.",
        {"recommendation": str},
    )
    async def _record_final(args: dict[str, Any]) -> dict[str, Any]:
        return _adapt(executor.dispatch("record_final", args))

    return create_sdk_mcp_server(
        name="subordina-enforcement",
        version="1.0.0",
        tools=[
            _web_search,
            _read_file,
            _write_file,
            _submit_draft,
            _submit_review,
            _submit_revision,
            _finalize,
            _add_candidate,
            _challenge_leader,
            _score_iteration,
            _record_final,
        ],
    )
