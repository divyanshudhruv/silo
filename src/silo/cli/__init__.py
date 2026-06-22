import click

from .._version import __version__
from ._common import ColorGroup
from .core import init, commit, status, log, diff, amend, show
from .vcs import branch, switch, reset
from .tag import tag
from .note import note
from .config import config
from .ops import snapshot, reinit, cleanup, freeze, unfreeze, info, gc, verify
from .import_ import import_cmd
from .bridge import bridge


def _print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(__version__)
    ctx.exit()


@click.group(cls=ColorGroup)
@click.option("--version", is_flag=True, callback=_print_version,
              expose_value=False, is_eager=True, help="Show the version and exit.")
def cli():
    pass


for _cmd in [init, commit, status, log, diff, show, branch, switch, reset, amend,
             tag, note, config, snapshot, reinit, cleanup, gc, verify,
             info, freeze, unfreeze, import_cmd, bridge]:
    cli.add_command(_cmd)


def main():
    cli()
