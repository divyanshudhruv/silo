import click

from ..database import get_config, save_config, get_global_config_dir, load_config_file, log_action
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="View and edit configuration")
def config():
    pass


@config.command("set", help="Set a config value")
@click.argument("key")
@click.argument("value")
@click.option("--global", "-g", "global_", is_flag=True, help="Set global config (user-wide)")
def config_set(key, value, global_):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if global_:
        global_dir = get_global_config_dir()
        cfg = load_config_file(global_dir / "config.json")
    else:
        cfg = get_config(silo_dir, include_global=False)

    cfg.set(key, value)
    save_config(silo_dir, cfg, global_=global_)
    log_action(silo_dir, "config", f"{'global ' if global_ else ''}{key}={value}")
    ok(f"{'global ' if global_ else ''}config {t(key, 'file')}={t(value, 'modified')}")


@config.command("list", help="List config values (local overrides global)")
@click.option("--global", "-g", "global_", is_flag=True, help="Show only global config")
def config_list(global_):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if global_:
        global_dir = get_global_config_dir()
        cfg = load_config_file(global_dir / "config.json")
        click.echo(t(f"# global config ({global_dir})", "dim"))
    else:
        cfg = get_config(silo_dir)

    for k, v in cfg.data.items():
        click.echo(f"{k}={v}")
