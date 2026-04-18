"""SQLAlchemy models for Subordinate v1."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Project(Base, TimestampedMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    root_path: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)


class Chat(Base, TimestampedMixin):
    """A conversation thread inside a project.

    root_path is optional; when null, the chat inherits the project's root_path.
    When set, it overrides the project for all invocations in this chat.
    """
    __tablename__ = "chats"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="New chat")
    root_path: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)


class Invocation(Base, TimestampedMixin):
    __tablename__ = "invocations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), nullable=False)
    skill_slug: Mapped[str] = mapped_column(String, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    max_cost_cents: Mapped[int] = mapped_column(Integer, default=5000)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','verified','replied','deferred','cost-capped','cancelled','error')",
            name="invocation_status_valid",
        ),
    )


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    running_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint(
            "role IN ('system','user-prompt','agent','tool')",
            name="message_role_valid",
        ),
    )


class ReviewLoopState(Base):
    __tablename__ = "review_loop_states"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    skill_slug: Mapped[str] = mapped_column(String, nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="initialized")
    max_iterations: Mapped[int] = mapped_column(Integer, default=2)
    drafts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reviews_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invocation_id: Mapped[str] = mapped_column(
        ForeignKey("invocations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    score_theoretical: Mapped[int] = mapped_column(Integer)
    score_empirical: Mapped[int] = mapped_column(Integer)
    score_feasibility: Mapped[int] = mapped_column(Integer)
    score_complexity: Mapped[int] = mapped_column(Integer)
    score_novelty: Mapped[int] = mapped_column(Integer)
    composite_score: Mapped[float] = mapped_column(default=0.0)
    disposition: Mapped[str] = mapped_column(String, default="under-consideration")
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    __table_args__ = (
        CheckConstraint(
            "disposition IN ('preferred','under-consideration','superseded')",
            name="candidate_disposition_valid",
        ),
    )
