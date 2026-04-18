"""RawRunner drives the loop with MockLLMClient; checkpoints every turn."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from backend.agent.mock_client import MockLLMClient, scripted_response
from backend.agent.runner_raw import RawRunner
from backend.db.models import Base, Chat, Checkpoint, Invocation, Project


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        # A9: dispose the engine on teardown so aiosqlite Connection.__del__
        # doesn't fire ResourceWarning/PytestUnraisableExceptionWarning on GC,
        # which fails the suite under `-W error`.
        await engine.dispose()


async def _prepare_invocation(factory, slug: str = "query") -> str:
    async with factory() as s:
        p = Project(name="p", root_path="/tmp", user_id="u1")
        s.add(p)
        await s.commit()
        c = Chat(project_id=p.id, title="t", root_path=None, user_id="u1")
        s.add(c)
        await s.commit()
        inv = Invocation(
            chat_id=c.id,
            skill_slug=slug,
            input="test question",
            status="running",
            user_id="u1",
            total_cost_cents=0,
            max_cost_cents=5000,
        )
        s.add(inv)
        await s.commit()
        return inv.id


async def test_runner_checkpoints_each_turn(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    client = MockLLMClient([
        scripted_response(
            text="Drafting…",
            tool_calls=[("submit_draft", {"artifacts": ["query_draft.md"]})],
        ),
        scripted_response(
            text="Reviewing…",
            tool_calls=[(
                "submit_review",
                {"verdict": "pass",
                 "critique": "I verified claim 1; confirmed numbers match source."},
            )],
        ),
        scripted_response(
            text="Finalising.",
            tool_calls=[("finalize", {})],
        ),
    ])
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
    )
    await runner.run(inv_id)

    async with db() as s:
        cps = (await s.execute(select(Checkpoint).where(
            Checkpoint.invocation_id == inv_id
        ))).scalars().all()
        assert len(cps) == 3  # one per model turn
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "verified"


async def test_runner_marks_error_when_max_turns_exceeded(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    # Client that never calls finalize — would loop forever without max_turns.
    # Responses include a tool_use so stop_reason is "tool_use" and the runner
    # doesn't early-exit on end_turn; it runs until max_turns.
    client = MockLLMClient(
        [scripted_response(
            text="thinking",
            tool_calls=[("read_file", {"path": "nonexistent.txt"})],
        )] * 50,
    )
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
        max_turns=5,
    )
    await runner.run(inv_id)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        assert inv.status in ("error", "deferred")


async def test_runner_respects_cost_cap(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        inv.max_cost_cents = 50
        await s.commit()
    # Each scripted response costs 30 cents per the mock client
    client = MockLLMClient(
        [scripted_response(
            text="x",
            tool_calls=[("read_file", {"path": "nonexistent.txt"})],
            cost_cents=30,
        )] * 10,
    )
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
        max_turns=20,
    )
    await runner.run(inv_id)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "cost-capped"


async def test_runner_cancel_between_turns(db, tmp_path):
    inv_id = await _prepare_invocation(db)
    client = MockLLMClient(
        [scripted_response(text="x", tool_calls=[])] * 20,
    )
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
        max_turns=20,
    )
    # Pre-flag cancellation before run starts
    runner.cancel(inv_id)
    await runner.run(inv_id)
    async with db() as s:
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "cancelled"


async def test_plain_chat_skill_replies_in_one_turn(db, tmp_path):
    # Chat skill (loop_type=plain): one text response, stop_reason=end_turn,
    # no tool calls; invocation status becomes 'replied' after one turn.
    inv_id = await _prepare_invocation(db, slug="chat")
    client = MockLLMClient([
        scripted_response(text="plain reply.", tool_calls=[]),
    ])
    runner = RawRunner(
        session_factory=db, llm_client=client, project_root=str(tmp_path),
    )
    await runner.run(inv_id)
    async with db() as s:
        cps = (await s.execute(select(Checkpoint).where(
            Checkpoint.invocation_id == inv_id
        ))).scalars().all()
        assert len(cps) == 1
        inv = await s.get(Invocation, inv_id)
        assert inv.status == "replied"
