import click

from .. import __version__
from ._common import ColorGroup
from .core import init, commit, status, log, diff, amend, show
from .vcs import branch, switch, reset
from .stash import stash
from .tag import tag
from .note import note
from .config import config
from .ops import snapshot, reinit, cleanup, freeze, unfreeze, info, gc, verify
from .import_ import import_cmd
from .bridge import bridge


@click.group(cls=ColorGroup)
@click.version_option(version=__version__, prog_name="silo")
def cli():
    pass


for _cmd in [init, commit, status, log, diff, show, branch, switch, reset, amend,
             stash, tag, note, config, snapshot, reinit, cleanup, gc, verify,
             info, freeze, unfreeze, import_cmd, bridge]:
    cli.add_command(_cmd)


def main():
    cli()
