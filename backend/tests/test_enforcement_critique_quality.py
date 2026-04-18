"""Critique quality gate: rubber-stamp + sycophancy detection."""
from __future__ import annotations

import pytest

from backend.enforcement.critique_quality import check_critique, CritiqueQualityError


def test_too_short_fails():
    issues = check_critique(critique="looks good", verdict="pass")
    assert any("too short" in i.lower() for i in issues)


def test_rubber_stamp_fails():
    issues = check_critique(
        critique="lgtm" * 20,  # long enough, but pure rubber-stamp pattern
        verdict="pass",
    )
    # Either caught by rubber-stamp detection or length minimum
    assert issues  # must be non-empty


def test_sycophancy_pattern_fails():
    issues = check_critique(
        critique=(
            "You are absolutely right about this analysis. I agree with you completely "
            "and see no issue with the framing."
        ),
        verdict="pass",
    )
    assert any("sycoph" in i.lower() for i in issues)


def test_pass_without_verification_word_fails():
    issues = check_critique(
        critique="The draft reads well, the structure is logical, and the topics flow nicely.",
        verdict="pass",
    )
    assert any("verified" in i.lower() or "explain what" in i.lower() for i in issues)


def test_good_pass_critique_accepted():
    issues = check_critique(
        critique=(
            "I verified claim 1 against Nie et al. Table 2 — numbers match. "
            "Confirmed the memory estimate calculation. Cross-referenced the ETTm2 "
            "claim against the PatchTST repo's benchmark script."
        ),
        verdict="pass",
    )
    assert issues == []


def test_good_fail_critique_accepted():
    issues = check_critique(
        critique=(
            "Claim 3 is unsupported — the cited source discusses a different dataset. "
            "The memory math does not account for the attention softmax. Confidence "
            "HIGH is unjustified on a single source."
        ),
        verdict="fail",
    )
    assert issues == []


def test_exception_alias():
    # CritiqueQualityError should be importable as the exception raised elsewhere
    assert issubclass(CritiqueQualityError, Exception)
