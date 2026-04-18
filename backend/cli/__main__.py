"""Subordina CLI entrypoint.

Run `subordina --help` after `pip install -e .`.
"""
from __future__ import annotations

import click

from backend import __version__
from backend.cli._banner import print_banner
from backend.cli.commands.chat import chat_group
from backend.cli.commands.history import history_command, show_command
from backend.cli.commands.invoke import (
    convergence_command,
    inquiry_command,
    say_command,
)
from backend.cli.commands.project import init_command


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
    help=(
        "Subordina -- rigorous ML research workflows on the command line.\n\n"
        "Commands for managing projects, chats, and verified inquiries. "
        "Run `subordina <command> --help` for details."
    ),
)
@click.version_option(__version__, "-V", "--version", prog_name="subordina")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Entry point for the subordina CLI."""
    # When `subordina` is invoked with no subcommand, show the banner and help.
    if ctx.invoked_subcommand is None:
        print_banner()
        click.echo(ctx.get_help())


@cli.command()
def version() -> None:
    """Print the installed Subordina version."""
    click.echo(f"Subordina v{__version__}")


cli.add_command(init_command)
cli.add_command(chat_group)
cli.add_command(say_command)
cli.add_command(inquiry_command)
cli.add_command(convergence_command)
cli.add_command(history_command)
cli.add_command(show_command)


if __name__ == "__main__":
    cli()
