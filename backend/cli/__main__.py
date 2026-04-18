"""Subordina CLI entrypoint.

Run `subordina --help` after `pip install -e .`.
"""
from __future__ import annotations

import click

from backend import __version__
from backend.cli.commands.chat import chat_group
from backend.cli.commands.project import init_command


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "Subordina — rigorous ML research workflows on the command line.\n\n"
        "Commands for managing projects, chats, and verified inquiries. "
        "Run `subordina <command> --help` for details.\n\n"
        "Coming in later tasks: `say`, `/inquiry`, `/convergence`, `history`, `show`."
    ),
)
@click.version_option(__version__, "-V", "--version", prog_name="subordina")
def cli() -> None:
    """Entry point for the subordina CLI."""


@cli.command()
def version() -> None:
    """Print the installed Subordina version."""
    click.echo(f"Subordina v{__version__}")


cli.add_command(init_command)
cli.add_command(chat_group)


if __name__ == "__main__":
    cli()
