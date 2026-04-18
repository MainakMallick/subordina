"""Abstract base for agent loop implementations.

The single swap point for switching between hand-rolled, Agent SDK, or
multi-model runners. All behaviour the rest of the backend depends on
lives in this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AgentRunner(ABC):
    @abstractmethod
    async def run(self, invocation_id: str) -> None:
        """Drive the agent loop for the given invocation to completion or cancel."""

    @abstractmethod
    def cancel(self, invocation_id: str) -> None:
        """Flag an in-flight invocation for cancellation (checked between turns)."""
