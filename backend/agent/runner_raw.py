"""v1 hand-rolled agent loop.

Owns the per-invocation loop: model turn -> tool dispatch with inline
enforcement -> DB checkpoint -> next turn. Honours cancellation flags and
cost caps between turns only. Writes one Checkpoint row per model turn.

Loop-type semantics (per plan amendments A3/A4):
- ``plain``       -> no review/research loop; after the first ``end_turn``
                     response with no tool calls, mark the invocation
                     ``replied`` and exit.
- ``review``      -> per-invocation ``ReviewLoop(skill=slug)`` drives the
                     draft -> review -> revise -> finalize protocol.
- ``convergence`` -> per-invocation ``ResearchLoop()`` drives the
                     candidate / challenge / score / record_final protocol.

Finalization detection: a ``finalize`` or ``record_final`` tool_use whose
result returns ``{"ok": True, ...}`` flips the invocation to ``verified``
and ends the loop. A failed tool result (``{"ok": False, ...}``) never
counts as a finalization — the gate is visible to the model as
``is_error: true`` and the model may retry.
"""
from __future__ import annotations

from typing import Any

from backend.agent.runner import AgentRunner
from backend.agent.tool_handlers import ToolExecutor
from backend.agent.tools import get_tools_for_skill
from backend.db.models import Checkpoint, Invocation
from backend.enforcement.research_loop import ResearchLoop
from backend.enforcement.review_loop import ReviewLoop
from backend.skills.base import SKILLS


class RawRunner(AgentRunner):
    """Hand-rolled async loop implementing ``AgentRunner``.

    ``project_root`` is a v1-test convenience: tests instantiate one runner
    per test and pass a ``tmp_path`` directly. In production (Task 16) the
    runner will resolve the folder per-invocation as
    ``chat.root_path or project.root_path`` (see plan amendment A8) — the
    constructor arg becomes a fallback or disappears entirely.
    """

    def __init__(
        self,
        *,
        session_factory,
        llm_client,
        project_root: str = ".",
        max_turns: int = 30,
    ):
        self._sf = session_factory
        self._client = llm_client
        self._project_root = project_root
        self._max_turns = max_turns
        self._cancelled: set[str] = set()

    def cancel(self, invocation_id: str) -> None:
        self._cancelled.add(invocation_id)

    async def run(self, invocation_id: str) -> None:
        # Load invocation + skill config.
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is None:
                return
            skill = SKILLS.get(inv.skill_slug)
            if skill is None:
                inv.status = "error"
                await s.commit()
                return
            skill_slug = inv.skill_slug
            user_input = inv.input
            max_cost_cents = inv.max_cost_cents

        # Per-invocation enforcement state.
        review_loop = (
            ReviewLoop(skill=skill_slug) if skill.loop_type == "review" else None
        )
        research_loop = (
            ResearchLoop() if skill.loop_type == "convergence" else None
        )
        executor = ToolExecutor(
            review_loop=review_loop,
            research_loop=research_loop,
            project_root=self._project_root,
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_input},
        ]
        tool_schemas = get_tools_for_skill(skill_slug)
        total_cost = 0

        for turn in range(1, self._max_turns + 1):
            # Cancellation is checked between turns only — never mid-tool.
            if invocation_id in self._cancelled:
                await self._mark(invocation_id, "cancelled")
                return

            response = await self._client.create(
                model=None,
                system=skill.system_prompt,
                tools=tool_schemas,
                messages=messages,
                max_tokens=4096,
            )
            total_cost += getattr(response, "cost_cents", 0)

            # Append assistant turn to messages.
            assistant_content: list[dict[str, Any]] = []
            tool_uses: list = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    tool_uses.append(block)
            messages.append({"role": "assistant", "content": assistant_content})

            # Dispatch tools (if any) with inline enforcement. A gate-fail
            # surfaces as {"ok": False, ...} and becomes an error tool_result
            # block so the model can self-correct; it never finalizes.
            finalized = False
            for tu in tool_uses:
                result = executor.dispatch(tu.name, tu.input)
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": str(result),
                        "is_error": not result["ok"],
                    }],
                })
                if tu.name in ("finalize", "record_final") and result.get("ok"):
                    finalized = True

            # Checkpoint is written per model turn, even with zero tool uses.
            async with self._sf() as s:
                cp = Checkpoint(
                    invocation_id=invocation_id,
                    iteration=turn,
                    conversation_json=messages,
                    running_cost_cents=total_cost,
                )
                s.add(cp)
                inv = await s.get(Invocation, invocation_id)
                if inv is not None:
                    inv.total_cost_cents = total_cost
                await s.commit()

            if finalized:
                await self._mark(invocation_id, "verified")
                return

            # Budget gate (checked after checkpoint write, between turns).
            if total_cost >= max_cost_cents:
                await self._mark(invocation_id, "cost-capped")
                return

            # Plain-loop early exit (A4): one text response, no tool calls.
            if (
                skill.loop_type == "plain"
                and response.stop_reason == "end_turn"
                and not tool_uses
            ):
                await self._mark(invocation_id, "replied")
                return

            # Non-plain: model stopped without finalising -> deferred.
            if response.stop_reason == "end_turn" and not tool_uses:
                await self._mark(invocation_id, "deferred")
                return

        # Max turns exhausted without finalization.
        await self._mark(invocation_id, "deferred")

    async def _mark(self, invocation_id: str, status: str) -> None:
        async with self._sf() as s:
            inv = await s.get(Invocation, invocation_id)
            if inv is not None:
                inv.status = status
                await s.commit()
