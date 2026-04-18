"""Database models: insert + read-back covers the essential fields."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from backend.db.models import (
    Base, Project, Chat, Invocation, Checkpoint, Message,
    ReviewLoopState, Candidate,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_project_and_chat(session, chat_root=None):
    p = Project(name="radar-fault", root_path="/tmp/radar", user_id="u1")
    session.add(p)
    await session.commit()
    c = Chat(project_id=p.id, title="First chat",
             root_path=chat_root, user_id="u1")
    session.add(c)
    await session.commit()
    return p, c


async def test_chat_inherits_project_root_when_null(session):
    p, c = await _seed_project_and_chat(session, chat_root=None)
    assert c.root_path is None
    assert p.root_path == "/tmp/radar"
    # Resolution is caller-side: chat.root_path or project.root_path
    effective = c.root_path or p.root_path
    assert effective == "/tmp/radar"


async def test_chat_overrides_project_root_when_set(session):
    p, c = await _seed_project_and_chat(session, chat_root="/tmp/radar/ecg")
    assert c.root_path == "/tmp/radar/ecg"
    effective = c.root_path or p.root_path
    assert effective == "/tmp/radar/ecg"


async def test_invocation_belongs_to_chat(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(
        chat_id=c.id, skill_slug="query", input="Q?",
        status="running", user_id="u1",
        total_cost_cents=0, max_cost_cents=5000,
    )
    session.add(inv)
    await session.commit()

    result = await session.execute(select(Invocation).where(Invocation.id == inv.id))
    loaded = result.scalar_one()
    assert loaded.skill_slug == "query"
    assert loaded.status == "running"
    assert loaded.chat_id == c.id


async def test_checkpoint_belongs_to_invocation(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(chat_id=c.id, skill_slug="query", input="x",
                     status="running", user_id="u1",
                     total_cost_cents=0, max_cost_cents=5000)
    session.add(inv)
    await session.commit()

    cp = Checkpoint(invocation_id=inv.id, iteration=1,
                    conversation_json=[{"role": "user", "content": "x"}],
                    running_cost_cents=10)
    session.add(cp)
    await session.commit()

    result = await session.execute(select(Checkpoint))
    assert len(result.scalars().all()) == 1


async def test_invocation_status_check_constraint(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(chat_id=c.id, skill_slug="chat", input="x",
                     status="bogus-status", user_id="u1",
                     total_cost_cents=0, max_cost_cents=5000)
    session.add(inv)
    with pytest.raises(Exception):
        await session.commit()


async def test_message_role_check_constraint(session):
    p, c = await _seed_project_and_chat(session)
    inv = Invocation(chat_id=c.id, skill_slug="chat", input="x",
                     status="running", user_id="u1",
                     total_cost_cents=0, max_cost_cents=5000)
    session.add(inv)
    await session.commit()
    m = Message(invocation_id=inv.id, role="not-a-role", content="x")
    session.add(m)
    with pytest.raises(Exception):
        await session.commit()
