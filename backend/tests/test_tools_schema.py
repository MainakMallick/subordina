"""Tool schema definitions: each tool has name, description, input_schema."""
from __future__ import annotations

import pytest

from backend.agent.tools import TOOLS, get_tool_schema, get_tools_for_skill


REQUIRED_KEYS = {"name", "description", "input_schema"}


def test_all_tools_have_required_schema_keys():
    for name, schema in TOOLS.items():
        assert REQUIRED_KEYS.issubset(schema.keys()), f"{name} missing keys"
        assert schema["input_schema"]["type"] == "object"


def test_query_skill_tools_includes_submit_draft_and_submit_review():
    names = {t["name"] for t in get_tools_for_skill("query")}
    assert "submit_draft" in names
    assert "submit_review" in names
    assert "submit_revision" in names
    assert "finalize" in names


def test_deep_research_tools_includes_candidate_and_challenge_tools():
    names = {t["name"] for t in get_tools_for_skill("deep-research")}
    assert "add_candidate" in names
    assert "challenge_leader" in names
    assert "score_iteration" in names
    assert "record_final" in names


def test_chat_skill_has_file_and_web_tools_only():
    names = {t["name"] for t in get_tools_for_skill("chat")}
    assert names == {"web_search", "read_file", "write_file"}


def test_unknown_skill_raises():
    with pytest.raises(KeyError):
        get_tools_for_skill("nope")
