"""Minimal Skill registry stub for Task 10.

Task 11 will replace the placeholder skills with full system prompts and
add the `deep-research` skill. For now we expose the `Skill` dataclass
shape used across the runner (slug, display_name, system_prompt, tools,
loop_type, max_iterations) and pre-register the three skills the Task 10
runner tests exercise: `chat` (plain), `query` (review), `deep-research`
(convergence).

Kept deliberately small; Task 11 owns the real prompts.
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


def register(skill: Skill) -> None:
    SKILLS[skill.slug] = skill


# --- Task 10 stubs (Task 11 will extend / replace prompts) -----------------

_CHAT_SKILL = Skill(
    slug="chat",
    display_name="Chat",
    system_prompt=(
        "You are answering a question in a research context; use file/web "
        "tools as needed; keep responses concise and honest about uncertainty."
    ),
    tools=("web_search", "read_file", "write_file"),
    loop_type="plain",
    max_iterations=1,
)

_QUERY_SKILL = Skill(
    slug="query",
    display_name="Inquiry",
    system_prompt="PLACEHOLDER — Task 11 will supply the Inquiry prompt.",
    tools=(
        "web_search", "read_file", "write_file",
        "submit_draft", "submit_review", "submit_revision", "finalize",
    ),
    loop_type="review",
    max_iterations=2,
)

_DEEP_RESEARCH_SKILL = Skill(
    slug="deep-research",
    display_name="Convergence",
    system_prompt="PLACEHOLDER — Task 12 will supply the Convergence prompt.",
    tools=(
        "web_search", "read_file", "write_file",
        "add_candidate", "challenge_leader", "score_iteration", "record_final",
    ),
    loop_type="convergence",
    max_iterations=10,
)

register(_CHAT_SKILL)
register(_QUERY_SKILL)
register(_DEEP_RESEARCH_SKILL)
