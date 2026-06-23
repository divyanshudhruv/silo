import click

from ..utils import find_silo_dir
from ..theme import t, err


class ColorGroup(click.Group):
    def format_help(self, ctx, formatter):
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_commands(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def format_commands(self, ctx, formatter):
        commands: list[tuple[str, click.Command]] = []
        for sub in self.list_commands(ctx):
            cmd: click.Command | None = self.get_command(ctx, sub)
            if cmd is None or cmd.hidden:
                continue
            commands.append((sub, cmd))
        if commands:
            limit = formatter.width - 6 - max(len(c[0]) for c in commands)
            rows: list[tuple[str, str]] = [(t(s, "command"), cmd.get_short_help_str(limit))
                                           for s, cmd in commands]
            with formatter.section("Commands"):
                formatter.write_dl(rows)

    def format_options(self, ctx, formatter):
        opts: list[tuple[str, str]] = []
        for param in self.get_params(ctx):
            rv: tuple[str, str] | None = param.get_help_record(ctx)
            if rv is not None:
                opts.append((t(rv[0], "option"), rv[1] if len(rv) > 1 else ""))
        if opts:
            with formatter.section("Options"):
                formatter.write_dl(opts)


def require_silo():
    silo_dir = find_silo_dir()
    if not silo_dir:
        err("not a silo repository")
    return silo_dir
