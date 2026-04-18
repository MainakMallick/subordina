"""Agent SDK runner — drives skill invocations via the Claude Code subprocess.

Second ``AgentRunner`` subclass, introduced in Task 10b per plan amendment A10.
Wraps the ``claude-agent-sdk`` Python package (which spawns the Claude Code CLI
as a subprocess) and registers the 11 enforcement tools as an in-process MCP
server. Enforcement gates remain inline in the existing ``ToolExecutor._h_*``
handlers — this runner only changes *how* the loop is driven, not how gates run.

In production (Task 16 wiring) this is the primary runtime. ``runner_raw.py``
stays in the tree as the unit-tested reference implementation and CI fallback.

Loop-type -> ``max_turns`` mapping (per A10):
    plain       -> 1
    review      -> 15
    convergence -> 30

Finalization detection: a ``PostToolUse`` hook inspects every ``finalize`` and
``record_final`` tool result; when one succeeds (no error flag), the hook sets
a flag and the ``async for`` loop breaks on the next message. Failed tool
results never count as a finalization — the model sees the error and may
retry. We check both ``is_error`` (the adapter's snake_case key and the SDK
Python convention) and ``isError`` (the MCP wire-protocol camelCase key) so
the hook is robust regardless of how the CLI serializes the tool response.

Checkpointing: one ``Checkpoint`` row per ``AssistantMessage`` turn. Plain-chat
invocations (which take a single turn) still get one checkpoint. Cost is
derived from ``ResultMessage.total_cost_usd * 100`` when the SDK reports it.
"""
from __future__ import annotations

from typing import Any, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from backend.agent.runner import AgentRunner
from backend.agent.sdk_tools import make_enforcement_mcp_server
from backend.agent.tool_handlers import ToolExecutor
from backend.db.models import Chat, Checkpoint, Invocation, Project
from backend.enforcement.research_loop import ResearchLoop
from backend.enforcement.review_loop import ReviewLoop
from backend.skills.base import SKILLS


# Loop-type -> max_turns (per plan amendment A10).
MAX_TURNS_BY_LOOP_TYPE: dict[str, int] = {
    "plain": 1,
    "review": 15,
    "convergence": 30,
}

# Full tool IDs as the SDK surfaces them to the model (and to hooks).
_MCP_SERVER_NAME = "subordina-enforcement"
_FINALIZE_TOOL_IDS = {
    f"mcp__{_MCP_SERVER_NAME}__finalize",
    f"mcp__{_MCP_SERVER_NAME}__record_final",
}


class AgentSdkRunner(AgentRunner):
    """``AgentRunner`` implementation that delegates to the Claude Code CLI.

    ``on_message`` is an optional callback invoked for every message streamed by
    the underlying ``ClaudeSDKClient`` (both ``AssistantMessage`` and
    ``ResultMessage``). Default ``None`` keeps the historical silent behaviour;
    the CLI passes a callback that prints text/tool_use blocks as they arrive.
    Callback exceptions are swallowed so a broken sink never crashes a run.
    """

    def __init__(
        self,
        *,
        session_factory,
        model: str,
        on_message: Callable[[Any], None] | None = None,
    ):
        self._sf = session_factory
        self._model = model
        self._on_message = on_message
        self._cancelled: set[str] = set()

    def cancel(self, invocation_id: str) -> None:
        self._cancelled.add(invocation_id)

    async def run(self, invocation_id: str) -> None:
        # Load invocation + chat + project so we can resolve the working folder
        # (chat.root_path overrides project.root_path per amendment A8).
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is None:
                return
            chat = await s.get(Chat, inv.chat_id)
            project = await s.get(Project, chat.project_id) if chat else None

        skill = SKILLS.get(inv.skill_slug)
        if skill is None:
            await self._mark(invocation_id, "error")
            return

        project_root = (chat.root_path if chat else None) or (
            project.root_path if project else "."
        )
        review_loop = (
            ReviewLoop(skill=inv.skill_slug) if skill.loop_type == "review" else None
        )
        research_loop = (
            ResearchLoop() if skill.loop_type == "convergence" else None
        )
        executor = ToolExecutor(
            review_loop=review_loop,
            research_loop=research_loop,
            project_root=project_root,
        )
        server = make_enforcement_mcp_server(executor)

        # Mutable finalize flag, flipped by the PostToolUse hook.
        finalized = {"done": False}

        async def _post_tool_hook(input_data, tool_use_id, context):
            # PostToolUseHookInput is a TypedDict with top-level tool_name and
            # tool_response keys. A failed tool result carries an error flag.
            # We check both ``is_error`` (SDK Python convention; what the
            # adapter in sdk_tools.py emits) and ``isError`` (MCP wire-protocol
            # camelCase) so finalization detection works regardless of which
            # shape the CLI hands us.
            try:
                tool_name = input_data.get("tool_name", "") if isinstance(
                    input_data, dict
                ) else ""
                if tool_name in _FINALIZE_TOOL_IDS:
                    response = input_data.get("tool_response", {})
                    is_err = isinstance(response, dict) and (
                        response.get("is_error") or response.get("isError")
                    )
                    if not is_err:
                        finalized["done"] = True
            except Exception:
                # Hook exceptions must not crash the run; finalize simply stays false.
                pass
            return {}

        options = ClaudeAgentOptions(
            model=self._model,
            system_prompt=skill.system_prompt,
            mcp_servers={_MCP_SERVER_NAME: server},
            allowed_tools=[
                f"mcp__{_MCP_SERVER_NAME}__{t}" for t in skill.tools
            ],
            max_turns=MAX_TURNS_BY_LOOP_TYPE.get(skill.loop_type, 15),
            max_budget_usd=inv.max_cost_cents / 100.0,
            hooks={
                "PostToolUse": [HookMatcher(matcher=None, hooks=[_post_tool_hook])],
            },
            cwd=project_root,
        )

        turn = 0
        total_cost_cents = 0
        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(inv.input)
                async for msg in client.receive_response():
                    if invocation_id in self._cancelled:
                        await self._mark(invocation_id, "cancelled")
                        return
                    if self._on_message is not None:
                        try:
                            self._on_message(msg)
                        except Exception:
                            # Streaming callbacks must never crash the loop.
                            pass
                    if isinstance(msg, AssistantMessage):
                        turn += 1
                        # Checkpoint after every assistant turn (even plain chat).
                        async with self._sf() as s:
                            cp = Checkpoint(
                                invocation_id=invocation_id,
                                iteration=turn,
                                conversation_json=_serialize_message(msg),
                                running_cost_cents=total_cost_cents,
                            )
                            s.add(cp)
                            await s.commit()
                    elif isinstance(msg, ResultMessage):
                        total_usd = getattr(msg, "total_cost_usd", None)
                        if total_usd is not None:
                            total_cost_cents = int(total_usd * 100)
                        break
                    if finalized["done"]:
                        # Finalize succeeded — stop consuming further messages.
                        break
        except Exception:
            # Any unhandled SDK error -> mark error, re-raise so callers see it.
            async with self._sf() as s:
                inv_err = await s.get(Invocation, invocation_id)
                if inv_err is not None and inv_err.status == "running":
                    inv_err.status = "error"
                    await s.commit()
            raise

        # Decide final status based on what actually happened.
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is None:
                return
            inv.total_cost_cents = total_cost_cents
            if inv.status == "running":
                if finalized["done"]:
                    inv.status = "verified"
                elif skill.loop_type == "plain" and turn >= 1:
                    inv.status = "replied"
                else:
                    inv.status = "deferred"
            await s.commit()

    async def _mark(self, invocation_id: str, status: str) -> None:
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is not None:
                inv.status = status
                await s.commit()


def _serialize_message(msg: Any) -> list[dict[str, Any]]:
    """Best-effort serialization of an ``AssistantMessage`` for checkpoint JSON.

    Only known block types (``TextBlock``, ``ToolUseBlock``) get a typed
    representation; anything else falls back to a ``repr()`` stub so we never
    crash on an unexpected SDK content block.
    """
    out: list[dict[str, Any]] = []
    for block in getattr(msg, "content", []) or []:
        if isinstance(block, TextBlock):
            out.append({"type": "text", "text": block.text})
        elif isinstance(block, ToolUseBlock):
            out.append(
                {
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                }
            )
        else:
            out.append({"type": "other", "repr": repr(block)})
    return out
