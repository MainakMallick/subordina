"""MockLLMClient — pre-scripted responses for tests.

Intentionally minimal. Mimics just the shape of a response the RawRunner
needs: a list of content blocks (text or tool_use) and a stop_reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockBlock:
    type: str  # "text" | "tool_use"
    text: str | None = None
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class MockResponse:
    content: list[MockBlock]
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"
    cost_cents: int = 10


def scripted_response(
    *,
    text: str = "",
    tool_calls: list[tuple[str, dict]] | None = None,
    stop_reason: str | None = None,
    cost_cents: int = 10,
) -> MockResponse:
    """Build a MockResponse from a simple text + list of (tool, args)."""
    blocks: list[MockBlock] = []
    if text:
        blocks.append(MockBlock(type="text", text=text))
    for i, (tool_name, tool_args) in enumerate(tool_calls or []):
        blocks.append(MockBlock(
            type="tool_use", id=f"tu_{i}", name=tool_name, input=tool_args,
        ))
    if stop_reason is None:
        stop_reason = "tool_use" if tool_calls else "end_turn"
    return MockResponse(content=blocks, stop_reason=stop_reason, cost_cents=cost_cents)


class MockLLMClient:
    """Returns pre-scripted responses in sequence; safe fallback when exhausted."""

    def __init__(self, responses: list[MockResponse]):
        self._responses = list(responses)
        self._i = 0

    async def create(self, **_: Any) -> MockResponse:
        if self._i >= len(self._responses):
            # Safety: pretend end_turn so the loop terminates in tests.
            return MockResponse(content=[], stop_reason="end_turn", cost_cents=0)
        r = self._responses[self._i]
        self._i += 1
        return r
