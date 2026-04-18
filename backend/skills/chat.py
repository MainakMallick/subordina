"""Chat (slug: chat) — plain conversation, no review loop.

Added per amendment A3 in the v1 backend plan. This is the escape-hatch
skill the user hits when they do NOT want the Inquiry / Convergence
verification machinery; it answers directly in a single turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CHAT_SYSTEM_PROMPT = """\
You are a research assistant in a research project. Answer the user's question or
request directly and concisely. You may use web_search to check facts, and
read_file / write_file within the current project folder.

Keep responses focused and admit uncertainty when applicable — this is plain chat,
not a verified inquiry. The user can invoke a verified method (/inquiry,
/convergence) when they want rigorous verification with a reviewer loop.
"""


@dataclass(frozen=True)
class _Skill:
    slug: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...]
    loop_type: Literal["plain", "review", "convergence"]
    max_iterations: int


CHAT_SKILL = _Skill(
    slug="chat",
    display_name="Chat",
    system_prompt=CHAT_SYSTEM_PROMPT,
    tools=("web_search", "read_file", "write_file"),
    loop_type="plain",
    max_iterations=1,
)
