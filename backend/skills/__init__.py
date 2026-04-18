"""Skills package.

Populates the `SKILLS` registry at import time by pulling each skill
module and calling `register()` on its exported skill instance. Callers
read the registry via `from backend.skills.base import SKILLS`.
"""
from __future__ import annotations

from backend.skills.base import SKILLS, Skill, register  # noqa: F401
from backend.skills.chat import CHAT_SKILL
from backend.skills.query import QUERY_SKILL
from backend.skills.deep_research import DEEP_RESEARCH_SKILL

register(CHAT_SKILL)
register(QUERY_SKILL)
register(DEEP_RESEARCH_SKILL)
