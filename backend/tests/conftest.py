"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def env_setup(tmp_path, monkeypatch):
    """Reset env to a known state for every test."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DEFAULT_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MAX_COST_CENTS_PER_INVOCATION", "5000")
