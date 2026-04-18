"""Subordina banner — Claude-Code-inspired rounded-box welcome.

Shows a branded rounded box (Unicode box-drawing) with a colored glyph,
name, tagline, help hint, and current working directory — same shape as
Claude Code's startup screen, distinct glyph + color for Subordina.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import click


# Box-drawing characters (Unicode). Renders in Windows Terminal,
# PowerShell 7+, modern cmd.exe with UTF-8 code page, macOS/Linux.
_TL, _TR, _BL, _BR = "\u256d", "\u256e", "\u2570", "\u256f"   # ╭ ╮ ╰ ╯
_H, _V = "\u2500", "\u2502"                                    # ─ │

# Brand glyph — U+2726 BLACK FOUR POINTED STAR.
# Distinct from Claude Code's teardrop-spoked asterisk.
BRAND_GLYPH = "\u2726"

BOX_WIDTH = 62  # inner column count; outer width = BOX_WIDTH + 2


def _pad_plain(text: str, width: int) -> str:
    """Pad `text` on the right to `width` visible columns."""
    if len(text) >= width:
        return text
    return text + " " * (width - len(text))


def print_banner(*, cwd: Path | None = None) -> None:
    """Print the Subordina welcome box.

    Format (modelled on Claude Code's startup):

        ╭──────────────────────────────────────────────────────────────╮
        │  ✦ Subordina                                                 │
        │                                                              │
        │    rigorous ML research, verified.                           │
        │                                                              │
        │    subordina --help  for commands                            │
        │    cwd: <current folder>                                     │
        ╰──────────────────────────────────────────────────────────────╯
    """
    actual_cwd = cwd or Path.cwd()
    cwd_display = str(actual_cwd)
    # Room is BOX_WIDTH minus the "    cwd: " (9 chars) prefix and 1 char padding.
    max_cwd_len = BOX_WIDTH - 10
    if len(cwd_display) > max_cwd_len:
        cwd_display = "..." + cwd_display[-(max_cwd_len - 3):]

    click.echo()
    click.echo(_TL + (_H * BOX_WIDTH) + _TR)

    # Name line: "  " + glyph (yellow) + " " + "Subordina" (bold). Pad the rest.
    name_plain = f"  {BRAND_GLYPH} Subordina"
    name_pad = " " * (BOX_WIDTH - len(name_plain))
    click.echo(
        _V
        + "  "
        + click.style(BRAND_GLYPH, fg="yellow", bold=True)
        + " "
        + click.style("Subordina", bold=True)
        + name_pad
        + _V
    )

    _blank_line()

    tagline = "rigorous ML research, verified."
    tag_plain = f"    {tagline}"
    tag_pad = " " * (BOX_WIDTH - len(tag_plain))
    click.echo(
        _V
        + "    "
        + click.style(tagline, dim=True)
        + tag_pad
        + _V
    )

    _blank_line()

    hint = "subordina --help  for commands"
    click.echo(_V + _pad_plain("    " + hint, BOX_WIDTH) + _V)

    cwd_line = "    cwd: " + cwd_display
    click.echo(_V + _pad_plain(cwd_line, BOX_WIDTH) + _V)

    click.echo(_BL + (_H * BOX_WIDTH) + _BR)
    click.echo()


def _blank_line() -> None:
    click.echo(_V + (" " * BOX_WIDTH) + _V)


def paced_lines(lines: list[str], delay: float = 0.12) -> None:
    """Print ``lines`` one per line with a short delay between them.

    Non-tty stdout collapses the delay to 0 so CI / piped output doesn't
    wait. Gives the init moment a measured pace without being noisy.
    """
    if not sys.stdout.isatty():
        delay = 0.0
    for line in lines:
        click.echo(line)
        sys.stdout.flush()
        if delay:
            time.sleep(delay)
