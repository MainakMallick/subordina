"""Research loop enforcement — convergence loop for the Convergence skill.

Port of scripts/research_loop.py from the plugin repo. Differences:
- Stateful class instead of CLI + JSON file
- Raises typed exceptions instead of sys.exit
- Candidate status values renamed to UI-facing vocabulary:
  plugin "active"   -> module "under-consideration"
  plugin "defeated" -> module "superseded"
  final pick is flagged "preferred" on record_final()
- Convergence gate mechanics preserved exactly:
  iteration >= MIN_ITERATIONS AND leader_streak >= CONVERGENCE_STREAK.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


SCORE_WEIGHTS = {
    "theoretical": 3,
    "empirical": 3,
    "feasibility": 2,
    "complexity": 1,
    "novelty": 1,
}
MIN_ITERATIONS = 3
CONVERGENCE_STREAK = 2  # consecutive survived challenges to converge


class ResearchLoopError(Exception):
    """Base class for research-loop gate failures."""


class NotConvergedError(ResearchLoopError):
    """record_final called but convergence criteria not met."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ResearchLoop:
    iteration: int = 0
    candidates: dict[str, dict] = field(default_factory=dict)
    challenges: list[dict] = field(default_factory=list)
    leader: str | None = None
    leader_streak: int = 0
    converged: bool = False
    final_recommendation: str | None = None
    history: list[dict] = field(default_factory=list)

    @staticmethod
    def _weighted_score(scores: dict) -> float:
        total = 0
        weight_sum = 0
        for axis, weight in SCORE_WEIGHTS.items():
            if axis in scores:
                total += scores[axis] * weight
                weight_sum += weight * 10  # max per axis is 10
        return round((total / weight_sum) * 100, 1) if weight_sum else 0.0

    def add_candidate(self, *, name: str, scores: dict) -> float:
        for axis in SCORE_WEIGHTS:
            if axis not in scores:
                raise ResearchLoopError(
                    f"missing axis '{axis}'; required: {list(SCORE_WEIGHTS)}"
                )
            v = scores[axis]
            if not (0 <= v <= 10):
                raise ResearchLoopError(
                    f"score for '{axis}' must be in [0,10], got {v}"
                )
        ws = self._weighted_score(scores)
        self.candidates[name] = {
            "scores": dict(scores),
            "weighted_score": ws,
            "added_at": _now_iso(),
            "iteration_added": self.iteration,
            "status": "under-consideration",
        }
        # Auto-update leader if this is the new best
        best = max(
            self.candidates,
            key=lambda n: self.candidates[n]["weighted_score"],
        )
        if best != self.leader:
            self.leader = best
            self.leader_streak = 0  # new leader resets streak
        return ws

    def challenge(self, *, leader: str, result: str, evidence: str) -> None:
        if result not in ("survived", "defeated"):
            raise ResearchLoopError(
                f"result must be 'survived' or 'defeated', got {result!r}"
            )
        self.challenges.append({
            "iteration": self.iteration,
            "leader": leader,
            "result": result,
            "evidence": evidence,
            "timestamp": _now_iso(),
        })
        if result == "survived":
            self.leader_streak += 1
        else:
            self.leader_streak = 0
            if leader in self.candidates:
                self.candidates[leader]["status"] = "superseded"

    def score_iteration(self) -> None:
        self.iteration += 1
        leader_score = 0
        if self.leader is not None:
            leader_score = self.candidates.get(self.leader, {}).get(
                "weighted_score", 0
            )
        self.history.append({
            "iteration": self.iteration,
            "leader": self.leader,
            "leader_score": leader_score,
            "active_candidates": sum(
                1
                for c in self.candidates.values()
                if c["status"] == "under-consideration"
            ),
            "leader_streak": self.leader_streak,
            "timestamp": _now_iso(),
        })

    def check_converged(self) -> bool:
        return (
            self.iteration >= MIN_ITERATIONS
            and self.leader_streak >= CONVERGENCE_STREAK
        )

    def record_final(self, *, recommendation: str) -> None:
        if self.iteration < MIN_ITERATIONS:
            raise NotConvergedError(
                f"only {self.iteration}/{MIN_ITERATIONS} iterations completed"
            )
        if self.leader_streak < CONVERGENCE_STREAK:
            raise NotConvergedError(
                f"leader_streak {self.leader_streak}/{CONVERGENCE_STREAK} "
                f"(need {CONVERGENCE_STREAK} consecutive survived challenges)"
            )
        if recommendation in self.candidates:
            self.candidates[recommendation]["status"] = "preferred"
        self.converged = True
        self.final_recommendation = recommendation
