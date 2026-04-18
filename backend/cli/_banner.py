"""Subordina CLI banner — minimal terminal-friendly header.

A proper logo (vector) lives at `assets/logo.svg` for README / website / social
use. Terminals can't render raster or vector art, so the CLI banner stays
minimal: a single-line wordmark with one accent glyph, framed by full-width
rules in the signature amber colour.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import click


MAX_WIDTH = 120

# Signature colour — amber / gold. Saturn-ish, scholarly warmth.
BRAND_COLOR = "yellow"

# Single accent glyph — U+25C9 FISHEYE. Reads as a ringed planet at a glance.
GLYPH = "\u25c9"

WORDMARK = "Subordina"
TAGLINE = "rigorous ML research, verified."


def _term_width() -> int:
    w = shutil.get_terminal_size((100, 24)).columns
    return max(40, min(w, MAX_WIDTH))


def _shorten_cwd(cwd_display: str, max_len: int) -> str:
    if len(cwd_display) <= max_len:
        return cwd_display
    return "..." + cwd_display[-(max_len - 3):]


def print_banner(*, cwd: Path | None = None) -> None:
    """Print the Subordina banner, sized to the current terminal width."""
    width = _term_width()
    actual_cwd = cwd or Path.cwd()
    cwd_display = _shorten_cwd(str(actual_cwd), width - 12)

    rule_char = "\u2550"  # ═

    click.echo()
    click.secho(rule_char * width, fg=BRAND_COLOR)
    click.echo()

    # Wordmark line: "    <glyph>   Subordina"
    # Glyph is amber bold; wordmark is bold default colour.
    click.echo(
        "    "
        + click.style(GLYPH, fg=BRAND_COLOR, bold=True)
        + "   "
        + click.style(WORDMARK, bold=True)
    )
    # Tagline line: aligned under the wordmark (8 spaces to match the glyph+gap).
    click.echo("        " + click.style(TAGLINE, dim=True))
    click.echo()

    click.secho(rule_char * width, fg=BRAND_COLOR)
    click.echo()

    click.echo(
        "    "
        + click.style("subordina --help", bold=True)
        + "  for commands"
    )
    click.echo(f"    cwd: {cwd_display}")
    click.echo()


def paced_lines(lines: list[str], delay: float = 0.12) -> None:
    """Print ``lines`` with a small delay between them on a TTY."""
    if not sys.stdout.isatty():
        delay = 0.0
    for line in lines:
        click.echo(line)
        sys.stdout.flush()
        if delay:
            time.sleep(delay)
