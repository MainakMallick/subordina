"""Tests for the CLI scaffold."""
from __future__ import annotations

from click.testing import CliRunner

from backend.cli.__main__ import cli


def test_help_exits_zero_and_mentions_subordina():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "subordina" in result.output.lower()


def test_version_subcommand():
    result = CliRunner().invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "Subordina v" in result.output


def test_version_flag():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output or "subordina" in result.output.lower()
