"""Skill registry.

`Skill` is the canonical dataclass shape every runner expects (slug,
display_name, system_prompt, tools, loop_type, max_iterations). Each
skill module defines a structurally-identical `_Skill` dataclass and
exports a single instance; registration happens at package import time
(`backend/skills/__init__.py`).

The `SKILLS` dict is keyed by slug and is the only public interface the
runners consume (see `backend/agent/runner_raw.py` and
`runner_agent_sdk.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LoopType = Literal["plain", "review", "convergence"]


@dataclass(frozen=True)
class Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: LoopType
    max_iterations: int


SKILLS: dict[str, Skill] = {}


def register(skill) -> None:
    """Register a skill by slug.

    Accepts any object that is structurally compatible with `Skill`
    (same attribute names) — each skill module defines its own local
    `_Skill` dataclass to avoid circular imports.
    """
    SKILLS[skill.slug] = skill  # type: ignore[assignment]
