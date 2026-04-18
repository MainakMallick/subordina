"""Tool schema definitions used by the agent loop.

These are the tool_use blocks the model can emit. The executor dispatches
each tool_use to a handler that runs its enforcement gate inline.
"""
from __future__ import annotations

from typing import Any


TOOLS: dict[str, dict[str, Any]] = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web; returns a short list of relevant results.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "Read a file from the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write or overwrite a file inside the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "submit_draft": {
        "name": "submit_draft",
        "description": "Submit a draft answer as a list of artifact paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifacts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["artifacts"],
        },
    },
    "submit_review": {
        "name": "submit_review",
        "description": "Submit a reviewer verdict + critique against the current draft.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "fail"]},
                "critique": {"type": "string"},
            },
            "required": ["verdict", "critique"],
        },
    },
    "submit_revision": {
        "name": "submit_revision",
        "description": "Submit a revised draft after a failed review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifacts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["artifacts"],
        },
    },
    "add_candidate": {
        "name": "add_candidate",
        "description": "Register a candidate method with 5-axis scores (0-10 each).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "scores": {
                    "type": "object",
                    "properties": {
                        "theoretical": {"type": "integer"},
                        "empirical": {"type": "integer"},
                        "feasibility": {"type": "integer"},
                        "complexity": {"type": "integer"},
                        "novelty": {"type": "integer"},
                    },
                    "required": [
                        "theoretical",
                        "empirical",
                        "feasibility",
                        "complexity",
                        "novelty",
                    ],
                },
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "scores"],
        },
    },
    "challenge_leader": {
        "name": "challenge_leader",
        "description": "Run an adversarial challenge against the current leader.",
        "input_schema": {
            "type": "object",
            "properties": {
                "leader": {"type": "string"},
                "result": {"type": "string", "enum": ["survived", "defeated"]},
                "evidence": {"type": "string"},
            },
            "required": ["leader", "result", "evidence"],
        },
    },
    "score_iteration": {
        "name": "score_iteration",
        "description": "Close the current iteration and record a history snapshot.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "record_final": {
        "name": "record_final",
        "description": "Register the final recommendation (only after convergence).",
        "input_schema": {
            "type": "object",
            "properties": {"recommendation": {"type": "string"}},
            "required": ["recommendation"],
        },
    },
    "finalize": {
        "name": "finalize",
        "description": "Finalize the invocation; only succeeds after review passes.",
        "input_schema": {"type": "object", "properties": {}},
    },
}


SKILL_TOOL_MAP: dict[str, list[str]] = {
    "chat": [
        "web_search",
        "read_file",
        "write_file",
    ],
    "query": [
        "web_search",
        "read_file",
        "write_file",
        "submit_draft",
        "submit_review",
        "submit_revision",
        "finalize",
    ],
    "deep-research": [
        "web_search",
        "read_file",
        "write_file",
        "add_candidate",
        "challenge_leader",
        "score_iteration",
        "record_final",
    ],
}


def get_tool_schema(name: str) -> dict[str, Any]:
    """Return the tool schema for `name`; raises KeyError if unknown."""
    return TOOLS[name]


def get_tools_for_skill(skill_slug: str) -> list[dict[str, Any]]:
    """Return the list of tool schemas enabled for `skill_slug`.

    Raises KeyError if the skill slug is not registered.
    """
    if skill_slug not in SKILL_TOOL_MAP:
        raise KeyError(f"unknown skill: {skill_slug}")
    return [TOOLS[n] for n in SKILL_TOOL_MAP[skill_slug]]
