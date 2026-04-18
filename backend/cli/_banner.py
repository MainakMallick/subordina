"""Subordina banner — wide, full-terminal-width banner with planet+rings logo.

Spans the full terminal width with horizontal rules above and below.
Left logo is a ringed planet (two rings). Right is a figlet wordmark
of "SUBORDINA". Signature colour is amber-gold (scholarly + Saturn-like).

Narrow terminals (< 80 cols) fall back to a compact boxed banner so the
layout never wraps awkwardly.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import click


# Layout
WIDE_THRESHOLD = 80
MAX_WIDTH = 120

# Signature colour — amber/gold. Evokes Saturn's rings + scholarly warmth.
BRAND_COLOR = "yellow"


# Ringed planet, 5 rows tall. First ring pierces the planet body;
# second ring orbits below. Matches the figlet-wordmark height.
PLANET_ART = [
    "    \u256d\u2500\u2500\u2500\u256e    ",
    " \u2550\u2550\u2561     \u255e\u2550\u2550 ",
    "   \u2502 \u25c9\u25c9\u25c9 \u2502   ",
    "   \u2570\u2500\u2500\u2500\u2500\u2500\u256f   ",
    " \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550 ",
]

# Figlet "Standard" wordmark for SUBORDINA — 5 rows, 51 columns wide.
SUBORDINA_ART = [
    r" ____        _                     _ _             ",
    r"/ ___| _   _| |__   ___  _ __ _ __(_|_)_ __   __ _ ",
    r"\___ \| | | | '_ \ / _ \| '__| '__| | | '_ \ / _` |",
    r" ___) | |_| | |_) | (_) | |  | |  | | | | | | (_| |",
    r"|____/ \__,_|_.__/ \___/|_|  |_|  |_|_|_| |_|\__,_|",
]

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
    cwd_display = str(actual_cwd)

    if width < WIDE_THRESHOLD:
        _print_compact(_shorten_cwd(cwd_display, width - 12))
        return

    _print_wide(width, _shorten_cwd(cwd_display, width - 12))


def _print_wide(width: int, cwd_display: str) -> None:
    rule_char = "\u2550"  # ═

    click.echo()
    click.secho(rule_char * width, fg=BRAND_COLOR)
    click.echo()

    for planet_row, text_row in zip(PLANET_ART, SUBORDINA_ART):
        styled_planet = click.style(planet_row, fg=BRAND_COLOR, bold=True)
        click.echo("   " + styled_planet + "    " + text_row)

    click.echo()
    tagline_line = "                    " + click.style(TAGLINE, dim=True)
    click.echo(tagline_line)
    click.echo()

    click.secho(rule_char * width, fg=BRAND_COLOR)
    click.echo()

    hint_line = (
        "    "
        + click.style("subordina --help", bold=True)
        + "  for commands"
    )
    click.echo(hint_line)
    click.echo(f"    cwd: {cwd_display}")
    click.echo()


def _print_compact(cwd_display: str) -> None:
    """Compact rounded-box banner for narrow terminals."""
    tl, tr, bl, br = "\u256d", "\u256e", "\u2570", "\u256f"
    h, v = "\u2500", "\u2502"
    glyph = "\u2726"  # ✦

    box_width = 62

    click.echo()
    click.echo(tl + (h * box_width) + tr)

    name_plain = f"  {glyph} Subordina"
    pad = " " * (box_width - len(name_plain))
    click.echo(
        v
        + "  "
        + click.style(glyph, fg=BRAND_COLOR, bold=True)
        + " "
        + click.style("Subordina", bold=True)
        + pad
        + v
    )
    click.echo(v + (" " * box_width) + v)

    tag_content = "    " + TAGLINE
    click.echo(
        v
        + "    "
        + click.style(TAGLINE, dim=True)
        + " " * (box_width - len(tag_content))
        + v
    )
    click.echo(v + (" " * box_width) + v)

    hint_content = "    subordina --help  for commands"
    click.echo(v + hint_content + " " * (box_width - len(hint_content)) + v)

    cwd_content = "    cwd: " + cwd_display
    if len(cwd_content) > box_width:
        cwd_content = cwd_content[: box_width - 3] + "..."
    click.echo(v + cwd_content + " " * (box_width - len(cwd_content)) + v)

    click.echo(bl + (h * box_width) + br)
    click.echo()


def paced_lines(lines: list[str], delay: float = 0.12) -> None:
    """Print ``lines`` with a small delay between them on a TTY.

    Non-tty stdout collapses the delay to 0 so piped output doesn't wait.
    """
    if not sys.stdout.isatty():
        delay = 0.0
    for line in lines:
        click.echo(line)
        sys.stdout.flush()
        if delay:
            time.sleep(delay)
