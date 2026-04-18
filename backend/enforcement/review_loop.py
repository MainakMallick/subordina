"""Review loop enforcement — imported as a module.

Port of scripts/review_loop.py from the plugin repo. Differences:
- Stateful class instead of CLI + JSON file
- Raises typed exceptions instead of sys.exit
- Returns structured state instead of printing
- Wraps check_critique_quality as the gate on every review
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.enforcement.critique_quality import check_critique, CritiqueQualityError


DEFAULT_MAX_ITERATIONS = 2
SKILL_MAX_ITERATIONS: dict[str, int] = {"paper": 4}


class ReviewLoopError(Exception):
    """Base class for review-loop gate failures."""


class FinalizationBlockedError(ReviewLoopError):
    """Raised when finalize() is called but the loop has not passed."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReviewLoop:
    skill: str
    iteration: int = 0
    max_iterations: int = 0
    status: str = "initialized"   # initialized | reviewing | revising | passed | escalated
    drafts: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    finalized: bool = False

    def __post_init__(self):
        if self.max_iterations == 0:
            self.max_iterations = SKILL_MAX_ITERATIONS.get(
                self.skill, DEFAULT_MAX_ITERATIONS
            )

    def submit_draft(self, *, artifacts: list[str]) -> None:
        if self.status not in ("initialized", "revising"):
            raise ReviewLoopError(
                f"cannot submit draft in status '{self.status}'; "
                f"expected 'initialized' or 'revising'"
            )
        self.iteration += 1
        self.drafts.append({
            "iteration": self.iteration,
            "artifacts": list(artifacts),
            "submitted": _now_iso(),
        })
        self.status = "reviewing"

    def submit_revision(self, *, artifacts: list[str]) -> None:
        if self.status != "revising":
            raise ReviewLoopError(
                f"cannot submit revision in status '{self.status}'; expected 'revising'"
            )
        self.iteration += 1
        self.drafts.append({
            "iteration": self.iteration,
            "artifacts": list(artifacts),
            "submitted": _now_iso(),
            "is_revision": True,
        })
        self.status = "reviewing"

    def submit_review(self, *, verdict: str, critique: str) -> None:
        if self.status != "reviewing":
            raise ReviewLoopError(
                f"cannot submit review in status '{self.status}'; expected 'reviewing'"
            )
        if verdict not in ("pass", "fail"):
            raise ReviewLoopError(f"verdict must be 'pass' or 'fail', got {verdict!r}")
        # Gate: critique quality
        issues = check_critique(critique=critique, verdict=verdict)
        if issues:
            raise CritiqueQualityError("; ".join(issues))

        self.reviews.append({
            "iteration": self.iteration,
            "verdict": verdict,
            "critique": critique,
            "timestamp": _now_iso(),
        })

        if verdict == "pass":
            self.status = "passed"
        else:
            if self.iteration >= self.max_iterations:
                self.status = "escalated"
            else:
                self.status = "revising"

    def finalize(self) -> None:
        if self.status != "passed":
            raise FinalizationBlockedError(
                f"cannot finalize in status '{self.status}'; review must pass first"
            )
        self.finalized = True
