"""Tool executor dispatches tool_use to handlers; handlers run enforcement inline."""
from __future__ import annotations

import pytest

from backend.agent.tool_handlers import ToolExecutor, ToolExecutionError
from backend.enforcement.review_loop import ReviewLoop
from backend.enforcement.research_loop import ResearchLoop


def _exec():
    rl = ReviewLoop(skill="query")
    rs = ResearchLoop()
    return ToolExecutor(review_loop=rl, research_loop=rs, project_root="/tmp")


def test_submit_draft_updates_review_loop():
    ex = _exec()
    result = ex.dispatch("submit_draft", {"artifacts": ["query_draft.md"]})
    assert result["ok"] is True
    assert ex.review_loop.status == "reviewing"


def test_submit_review_passes_through_critique_gate():
    ex = _exec()
    ex.dispatch("submit_draft", {"artifacts": ["q.md"]})
    # Good critique passes
    result = ex.dispatch(
        "submit_review",
        {"verdict": "pass",
         "critique": "I verified claim 1 against source S; numbers match. Checked math."},
    )
    assert result["ok"] is True
    assert ex.review_loop.status == "passed"


def test_submit_review_returns_error_for_bad_critique():
    ex = _exec()
    ex.dispatch("submit_draft", {"artifacts": ["q.md"]})
    result = ex.dispatch("submit_review", {"verdict": "pass", "critique": "lgtm"})
    assert result["ok"] is False
    assert "critique" in result["error"].lower() or "too short" in result["error"].lower()
    # Loop state is unchanged — gate refused the review
    assert ex.review_loop.status == "reviewing"


def test_finalize_blocked_before_pass():
    ex = _exec()
    ex.dispatch("submit_draft", {"artifacts": ["q.md"]})
    result = ex.dispatch("finalize", {})
    assert result["ok"] is False
    assert "review" in result["error"].lower()


def test_add_candidate_validates_axes():
    ex = _exec()
    result = ex.dispatch("add_candidate", {"name": "X", "scores": {"theoretical": 5}})
    assert result["ok"] is False
    assert "axis" in result["error"].lower() or "required" in result["error"].lower()


def test_record_final_blocked_without_convergence():
    ex = _exec()
    result = ex.dispatch("record_final", {"recommendation": "X"})
    assert result["ok"] is False


def test_unknown_tool_raises():
    ex = _exec()
    with pytest.raises(ToolExecutionError):
        ex.dispatch("not_a_real_tool", {})


def test_write_file_respects_project_root(tmp_path):
    rl = ReviewLoop(skill="query")
    rs = ResearchLoop()
    ex = ToolExecutor(review_loop=rl, research_loop=rs, project_root=str(tmp_path))
    result = ex.dispatch("write_file", {"path": "out.md", "content": "hi"})
    assert result["ok"] is True
    assert (tmp_path / "out.md").read_text() == "hi"


def test_write_file_rejects_path_traversal(tmp_path):
    rl = ReviewLoop(skill="query")
    rs = ResearchLoop()
    ex = ToolExecutor(review_loop=rl, research_loop=rs, project_root=str(tmp_path))
    result = ex.dispatch("write_file", {"path": "../evil.md", "content": "x"})
    assert result["ok"] is False
