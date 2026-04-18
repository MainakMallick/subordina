"""Subordina CLI banner — block-character Saturn mark + letterspaced wordmark.

The real logo is a vector file at ``assets/logo.svg`` (used in README /
website / favicon). The terminal can't render vector art, so this banner
approximates the logo with chunky Unicode block characters and two ring
lines, all painted in the signature amber-gold.

Narrow terminals (< 80 cols) fall back to a compact rounded-box banner.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import click


MAX_WIDTH = 120
WIDE_THRESHOLD = 80

# Signature colour — amber / gold. Matches assets/logo.svg's #d4a017.
BRAND_COLOR = "yellow"


# Block-character planet with two rings, 6 rows tall, 20 columns wide.
# Row 3 has a ring piercing through the planet; row 6 is an orbital ring.
# Quarter-block characters (▗ ▖ ▘ ▝ ▟ ▙ ▜ ▛) round the corners of the
# planet body.
PLANET_ART = [
    "      \u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584      ",
    "   \u2597\u2584\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2584\u2596   ",
    "\u2550\u2550\u255f\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2562\u2550\u2550",
    "   \u259d\u2580\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2580\u2598   ",
    "      \u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580      ",
    "   \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550   ",
]

# Letterspaced wordmark — bold but not figlet. Reads as a logotype.
WORDMARK = "S U B O R D I N A"
TAGLINE = "rigorous ML research, verified."


def _term_width() -> int:
    w = shutil.get_terminal_size((100, 24)).columns
    return max(40, min(w, MAX_WIDTH))


def _shorten_cwd(cwd_display: str, max_len: int) -> str:
    if len(cwd_display) <= max_len:
        return cwd_display
    return "..." + cwd_display[-(max_len - 3):]


def print_banner(*, cwd: Path | None = None) -> None:
    """Print the Subordina banner sized to the current terminal width."""
    width = _term_width()
    actual_cwd = cwd or Path.cwd()
    cwd_display = _shorten_cwd(str(actual_cwd), width - 12)

    if width < WIDE_THRESHOLD:
        _print_compact(cwd_display)
        return

    _print_wide(width, cwd_display)


def _print_wide(width: int, cwd_display: str) -> None:
    rule_char = "\u2550"  # ═

    click.echo()
    click.secho(rule_char * width, fg=BRAND_COLOR)
    click.echo()

    # Wordmark appears on the middle row of the planet art; tagline on the
    # row below. Other rows have spaces after the planet.
    wordmark_row = 2  # zero-indexed
    tagline_row = 3

    for i, planet_row in enumerate(PLANET_ART):
        prefix = "    "
        styled_planet = click.style(planet_row, fg=BRAND_COLOR, bold=True)
        if i == wordmark_row:
            suffix = "    " + click.style(WORDMARK, bold=True)
        elif i == tagline_row:
            suffix = "    " + click.style(TAGLINE, dim=True)
        else:
            suffix = ""
        click.echo(prefix + styled_planet + suffix)

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


def _print_compact(cwd_display: str) -> None:
    """Compact rounded-box banner for narrow terminals (< 80 cols)."""
    tl, tr, bl, br = "\u256d", "\u256e", "\u2570", "\u256f"
    h, v = "\u2500", "\u2502"
    glyph = "\u25c9"  # ◉

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
    """Print ``lines`` with a small delay between them on a TTY."""
    if not sys.stdout.isatty():
        delay = 0.0
    for line in lines:
        click.echo(line)
        sys.stdout.flush()
        if delay:
            time.sleep(delay)
