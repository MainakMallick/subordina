"""Skill registry tests.

Task 11: chat + query (Inquiry) have real system prompts, deep-research
is still a placeholder (Task 12 replaces it).
"""
from __future__ import annotations

import pytest


# Importing the package triggers registration of all three skills.
import backend.skills  # noqa: F401
from backend.skills.base import SKILLS, Skill


# --- Registration -----------------------------------------------------------


def test_all_three_skills_registered():
    assert set(SKILLS.keys()) == {"chat", "query", "deep-research"}


def test_chat_skill_loop_type_and_tools():
    s = SKILLS["chat"]
    assert s.slug == "chat"
    assert s.display_name == "Chat"
    assert s.loop_type == "plain"
    assert s.max_iterations == 1
    assert tuple(s.tools) == ("web_search", "read_file", "write_file")


def test_query_skill_loop_type_and_tools():
    s = SKILLS["query"]
    assert s.slug == "query"
    assert s.display_name == "Inquiry"
    assert s.loop_type == "review"
    assert s.max_iterations == 2
    required = {
        "web_search", "read_file", "write_file",
        "submit_draft", "submit_review", "submit_revision", "finalize",
    }
    assert required.issubset(set(s.tools))


def test_deep_research_skill_loop_type_and_tools():
    s = SKILLS["deep-research"]
    assert s.slug == "deep-research"
    assert s.display_name == "Convergence"
    assert s.loop_type == "convergence"
    assert s.max_iterations == 10
    required = {
        "web_search", "read_file", "write_file",
        "add_candidate", "challenge_leader", "score_iteration", "record_final",
    }
    assert required.issubset(set(s.tools))
    # review-loop tools must NOT bleed into deep-research
    assert "submit_review" not in s.tools
    assert "submit_draft" not in s.tools


# --- System prompt content --------------------------------------------------


def test_chat_prompt_is_short_and_mentions_plain():
    p = SKILLS["chat"].system_prompt
    # Short: one paragraph, plain-chat semantics; keep it under 1500 chars.
    assert len(p) < 1500, f"chat prompt is {len(p)} chars — expected <1500"
    assert "plain" in p.lower()


def test_query_prompt_mentions_review_and_confidence():
    p = SKILLS["query"].system_prompt.lower()
    assert "review" in p
    assert "confidence" in p
    # Spot-check that the draft-file structure is actually described.
    assert "query_draft.md" in p
    assert "evidence" in p


def test_deep_research_prompt_is_still_placeholder():
    # Task 12 replaces this with the real Convergence prompt.
    p = SKILLS["deep-research"].system_prompt
    assert "PLACEHOLDER" in p


# --- Structural shape -------------------------------------------------------


def test_registered_skills_have_required_attributes():
    required_attrs = ("slug", "display_name", "system_prompt", "tools",
                      "loop_type", "max_iterations")
    for slug, skill in SKILLS.items():
        for attr in required_attrs:
            assert hasattr(skill, attr), f"{slug} missing {attr}"
        # loop_type must be one of the three literals
        assert skill.loop_type in ("plain", "review", "convergence")


def test_skill_dataclass_shape_exported():
    # base.py must expose the canonical Skill dataclass so runners and
    # tests can type-check against it.
    assert Skill is not None
    fields = {f for f in Skill.__dataclass_fields__}
    assert fields == {"slug", "display_name", "system_prompt", "tools",
                      "loop_type", "max_iterations"}
