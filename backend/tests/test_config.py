"""Config module loads env and exposes typed settings."""
from __future__ import annotations

from backend.config import Settings


def test_settings_loads_from_env():
    s = Settings()
    assert s.anthropic_api_key == "test-key"
    assert s.default_model == "claude-opus-4-7"
    assert s.max_cost_cents_per_invocation == 5000


def test_settings_db_path_is_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "nested" / "x.db"))
    s = Settings()
    assert s.db_path.is_absolute()
    assert str(s.db_path).endswith("x.db")
