"""Review loop as a module: raises typed exceptions on gate failures."""
from __future__ import annotations

import pytest

from backend.enforcement.review_loop import (
    ReviewLoop, ReviewLoopError, CritiqueQualityError, FinalizationBlockedError,
)


def test_init_sets_max_iterations_per_skill():
    rl = ReviewLoop(skill="query")
    assert rl.max_iterations == 2
    rl2 = ReviewLoop(skill="paper")
    assert rl2.max_iterations == 4


def test_submit_draft_requires_initialized_or_revising():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    assert rl.status == "reviewing"
    assert rl.iteration == 1
    with pytest.raises(ReviewLoopError):
        rl.submit_draft(artifacts=["b.md"])  # status is 'reviewing'


def test_submit_review_rejects_short_critique():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    with pytest.raises(CritiqueQualityError):
        rl.submit_review(verdict="pass", critique="lgtm")


def test_pass_verdict_sets_passed_status():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="pass",
        critique="I verified claim 1 against source S; numbers match. Checked math.",
    )
    assert rl.status == "passed"


def test_fail_then_revise_then_pass():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="fail",
        critique="Claim 1 not supported by cited source; no calculation shown for memory estimate.",
    )
    assert rl.status == "revising"
    rl.submit_revision(artifacts=["a.md"])
    assert rl.status == "reviewing"
    rl.submit_review(
        verdict="pass",
        critique="Revision adds the calculation; I verified it against Nie et al. Table 2.",
    )
    assert rl.status == "passed"


def test_two_fails_escalates():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="fail",
        critique="Claim 1 is unsupported. No source is cited for the specific number.",
    )
    rl.submit_revision(artifacts=["a.md"])
    rl.submit_review(
        verdict="fail",
        critique="Still unsupported. The new citation is for a different metric.",
    )
    assert rl.status == "escalated"


def test_finalize_blocked_until_passed():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    with pytest.raises(FinalizationBlockedError):
        rl.finalize()


def test_finalize_succeeds_when_passed():
    rl = ReviewLoop(skill="query")
    rl.submit_draft(artifacts=["a.md"])
    rl.submit_review(
        verdict="pass",
        critique="I verified both claims against cited sources; math checked.",
    )
    rl.finalize()
    assert rl.finalized is True
