"""Convergence (slug: deep-research) — placeholder.

Task 12 replaces `DEEP_RESEARCH_SYSTEM_PROMPT` with the real iterated-
architecture-search prompt. The skill is still registered (tool list,
loop_type, max_iterations all final) so routers and runner tests can
exercise it; only the `system_prompt` is a placeholder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DEEP_RESEARCH_SYSTEM_PROMPT = (
    "PLACEHOLDER - Task 12 will supply the real Convergence prompt. "
    "This skill runs an iterated architecture search with 5-axis scoring, "
    "adversarial challenges against the current leader, and a convergence "
    "gate (>=3 iterations AND 2 consecutive survived challenges) before "
    "record_final may be called."
)


@dataclass(frozen=True)
class _Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: Literal["plain", "review", "convergence"]
    max_iterations: int


DEEP_RESEARCH_SKILL = _Skill(
    slug="deep-research",
    display_name="Convergence",
    system_prompt=DEEP_RESEARCH_SYSTEM_PROMPT,
    tools=(
        "web_search", "read_file", "write_file",
        "add_candidate", "challenge_leader", "score_iteration", "record_final",
    ),
    loop_type="convergence",
    max_iterations=10,
)
