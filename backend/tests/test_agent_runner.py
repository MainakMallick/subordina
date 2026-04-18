"""AgentRunner interface: abstract base, cannot instantiate directly."""
from __future__ import annotations

import pytest

from backend.agent.runner import AgentRunner


def test_cannot_instantiate_abstract_base():
    with pytest.raises(TypeError):
        AgentRunner()


def test_subclass_must_implement_run():
    class Incomplete(AgentRunner):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_concrete_subclass_can_be_instantiated():
    class Minimal(AgentRunner):
        async def run(self, invocation_id: str) -> None:
            return None

        def cancel(self, invocation_id: str) -> None:
            return None

    r = Minimal()
    assert r is not None
