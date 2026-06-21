import click

from ..database import get_config, save_config, log_action
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="View and edit configuration")
def config():
    pass


@config.command("set", help="Set a config value")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    silo_dir = require_silo()
    if not silo_dir:
        return

    cfg = get_config(silo_dir)
    cfg.set(key, value)
    save_config(silo_dir, cfg)
    log_action(silo_dir, "config", f"{key}={value}")
    ok(f"config {t(key, 'file')}={t(value, 'modified')}")


@config.command("list", help="List all config values")
def config_list():
    silo_dir = require_silo()
    if not silo_dir:
        return

    cfg = get_config(silo_dir)
    for k, v in cfg.data.items():
        click.echo(f"{k}={v}")
