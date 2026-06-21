import click

from .core import init, commit, status, log, diff
from .vcs import branch, switch, revert
from .stash import stash
from .tag import tag
from .note import note
from .config import config
from .ops import snapshot, purge, cleanup, grid, freeze, unfreeze
from .import_ import import_cmd


@click.group()
def cli():
    pass


cli.add_command(init)
cli.add_command(commit)
cli.add_command(status)
cli.add_command(log)
cli.add_command(diff)
cli.add_command(branch)
cli.add_command(switch)
cli.add_command(revert)
cli.add_command(stash)
cli.add_command(tag)
cli.add_command(note)
cli.add_command(config)
cli.add_command(snapshot)
cli.add_command(purge)
cli.add_command(cleanup)
cli.add_command(grid)
cli.add_command(freeze)
cli.add_command(unfreeze)
cli.add_command(import_cmd)


def main():
    cli()
