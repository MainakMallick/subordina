"""Subordina banner + paced output helpers.

Scholarly register: letterspaced wordmark, a thin rule, a quiet tagline.
No unicode glyphs that break on cp1252 Windows consoles — the banner uses
ASCII box-drawing only (``-``, ``.``, ``'``, letters, spaces).
"""
from __future__ import annotations

import sys
import time

import click


# Letterspaced wordmark. Rendered on a single line so it survives narrow
# terminals without wrapping.
WORDMARK = "S U B O R D I N A"
RULE = "-" * len(WORDMARK)
TAGLINE = "rigorous research .  verified"


def print_banner() -> None:
    """Print the Subordina wordmark, a thin rule, and the tagline."""
    click.echo()
    click.secho(WORDMARK, bold=True)
    click.echo(RULE)
    click.secho(TAGLINE, dim=True)
    click.echo()


def paced_lines(lines: list[str], delay: float = 0.12) -> None:
    """Print ``lines`` one per line with a short delay between them.

    Gives the init / setup moment a measured pace without being noisy.
    Each line is written as it's emitted (flushed) so the cadence is
    visible in real time. On a non-tty stdout the delay collapses to 0
    so CI / piped output doesn't pay the wait tax.
    """
    if not sys.stdout.isatty():
        delay = 0.0
    for line in lines:
        click.echo(line)
        sys.stdout.flush()
        if delay:
            time.sleep(delay)
