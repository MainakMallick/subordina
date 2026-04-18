"""Research loop enforcement: 5-axis scoring, convergence gate."""
from __future__ import annotations

import pytest

from backend.enforcement.research_loop import (
    ResearchLoop, ResearchLoopError, NotConvergedError,
    MIN_ITERATIONS, CONVERGENCE_STREAK,
)


SAMPLE_SCORES = {
    "theoretical": 8, "empirical": 7, "feasibility": 6,
    "complexity": 5, "novelty": 4,
}


def test_weighted_score_formula():
    rl = ResearchLoop()
    # 8*3 + 7*3 + 6*2 + 5*1 + 4*1 = 24+21+12+5+4 = 66
    # max = 10*3 + 10*3 + 10*2 + 10*1 + 10*1 = 100
    # score = 66/100 * 100 = 66.0
    ws = rl._weighted_score(SAMPLE_SCORES)
    assert ws == 66.0


def test_add_candidate_updates_leader():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    assert rl.leader == "A"
    # Higher scoring candidate takes leadership
    rl.add_candidate(
        name="B",
        scores={"theoretical": 9, "empirical": 9, "feasibility": 9,
                "complexity": 8, "novelty": 8},
    )
    assert rl.leader == "B"
    assert rl.leader_streak == 0  # new leader resets streak


def test_add_candidate_validates_all_axes():
    rl = ResearchLoop()
    with pytest.raises(ResearchLoopError):
        rl.add_candidate(name="X", scores={"theoretical": 5})  # missing axes


def test_add_candidate_validates_score_range():
    rl = ResearchLoop()
    with pytest.raises(ResearchLoopError):
        rl.add_candidate(
            name="X",
            scores={"theoretical": 11, "empirical": 5, "feasibility": 5,
                    "complexity": 5, "novelty": 5},
        )


def test_challenge_survived_increments_streak():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    rl.challenge(leader="A", result="survived", evidence="no better method found")
    assert rl.leader_streak == 1
    rl.challenge(leader="A", result="survived", evidence="still no better method")
    assert rl.leader_streak == 2


def test_challenge_defeated_resets_streak_and_marks_superseded():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    rl.challenge(leader="A", result="survived", evidence="e1")
    rl.challenge(leader="A", result="defeated", evidence="B wins at bench X")
    assert rl.leader_streak == 0
    assert rl.candidates["A"]["status"] == "superseded"


def test_score_iteration_increments_count():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    rl.score_iteration()
    assert rl.iteration == 1
    rl.score_iteration()
    assert rl.iteration == 2


def test_check_converged_requires_both_conditions():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    # Not enough iterations
    for _ in range(MIN_ITERATIONS - 1):
        rl.score_iteration()
    rl.challenge(leader="A", result="survived", evidence="e")
    rl.challenge(leader="A", result="survived", evidence="e")
    assert rl.check_converged() is False
    rl.score_iteration()
    assert rl.iteration >= MIN_ITERATIONS
    assert rl.leader_streak >= CONVERGENCE_STREAK
    assert rl.check_converged() is True


def test_record_final_blocked_before_convergence():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    with pytest.raises(NotConvergedError):
        rl.record_final(recommendation="A")


def test_record_final_succeeds_after_convergence():
    rl = ResearchLoop()
    rl.add_candidate(name="A", scores=SAMPLE_SCORES)
    for _ in range(MIN_ITERATIONS):
        rl.score_iteration()
    for _ in range(CONVERGENCE_STREAK):
        rl.challenge(leader="A", result="survived", evidence="no better found")
    rl.record_final(recommendation="A")
    assert rl.converged is True
    assert rl.final_recommendation == "A"
