import click

from ._common import ColorGroup
from .core import init, commit, status, log, diff, amend, show
from .vcs import branch, switch, reset
from .stash import stash
from .tag import tag
from .note import note
from .config import config
from .ops import snapshot, purge, cleanup, freeze, unfreeze, info, gc, verify
from .import_ import import_cmd
from .bridge import bridge


@click.group(cls=ColorGroup)
def cli():
    pass


cli.add_command(init)
cli.add_command(commit)
cli.add_command(status)
cli.add_command(log)
cli.add_command(diff)
cli.add_command(show)
cli.add_command(branch)
cli.add_command(switch)
cli.add_command(reset)
cli.add_command(amend)
cli.add_command(stash)
cli.add_command(tag)
cli.add_command(note)
cli.add_command(config)
cli.add_command(snapshot)
cli.add_command(purge)
cli.add_command(cleanup)
cli.add_command(gc)
cli.add_command(verify)
cli.add_command(info)
cli.add_command(freeze)
cli.add_command(unfreeze)
cli.add_command(import_cmd)
cli.add_command(bridge)


def main():
    cli()
