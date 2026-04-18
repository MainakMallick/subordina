"""Mechanical critique-quality gate.

Ported from scripts/hooks/check_critique_quality.py. Exposes:
- check_critique(critique, verdict) -> list[str]   (empty = OK)
- CritiqueQualityError                             (raised by review_loop on failure)
"""
from __future__ import annotations

import re


MIN_CRITIQUE_LENGTH = 50

RUBBER_STAMP_PATTERNS = [
    r"^looks?\s+good\.?$",
    r"^no\s+issues?\.?$",
    r"^approved?\.?$",
    r"^(lgtm\.?)+$",
    r"^all\s+good\.?$",
    r"^fine\.?$",
    r"^ok\.?$",
    r"^pass\.?$",
    r"^no\s+problems?\.?$",
]

SYCOPHANCY_PATTERNS = [
    r"you'?re\s+(absolutely\s+)?right",
    r"great\s+point",
    r"I\s+agree\s+with\s+you",
    r"that'?s\s+a\s+good\s+idea",
    r"you\s+make\s+a\s+good\s+point",
    r"absolutely\s+right",
    r"couldn'?t\s+agree\s+more",
]

VERIFICATION_WORDS = [
    "verified", "confirmed", "checked", "matches", "consistent",
    "correct", "valid", "complete", "present", "exists",
    "trace", "compare", "cross-reference",
]


class CritiqueQualityError(Exception):
    """Raised when a critique fails one of the mechanical quality gates."""


def check_critique(*, critique: str, verdict: str) -> list[str]:
    """Return a list of quality issues; empty means OK."""
    issues: list[str] = []

    if len(critique) < MIN_CRITIQUE_LENGTH:
        issues.append(
            f"Critique too short ({len(critique)} chars, need >= "
            f"{MIN_CRITIQUE_LENGTH}). Cite specific claims, files, or findings."
        )

    text = critique.lower().strip()
    for pattern in RUBBER_STAMP_PATTERNS:
        if re.match(pattern, text):
            issues.append(
                f"Rubber-stamp critique detected. Reviewer must cite specific "
                f"claims, sources, or findings."
            )
            break

    for pattern in SYCOPHANCY_PATTERNS:
        if re.search(pattern, text):
            issues.append(
                "Sycophancy pattern in critique. Reviewer must verify "
                "independently, not agree."
            )
            break

    if verdict == "pass" and not any(w in text for w in VERIFICATION_WORDS):
        issues.append(
            "Pass verdict must explain what was verified. Include one of: "
            + ", ".join(VERIFICATION_WORDS) + "."
        )

    return issues
