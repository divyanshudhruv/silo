import shutil
import sys

import click

from ..theme import ok, err, warn, t
from ._common import require_silo, ColorGroup


def _hook_content():
    exe = shutil.which("silo")
    if not exe:
        exe = f'"{sys.executable}" -m silo'
    else:
        exe = f'"{exe}"'
    return f"""#!/bin/sh
{exe} commit "auto: $(git log -1 --format=%s)" --co "$(git log -1 --format='%an <%ae>')" >/dev/null 2>&1 || true
"""


def _git_dir(silo_dir):
    d = silo_dir.parent / ".git"
    if d.is_dir():
        return d
    return None


@click.group(cls=ColorGroup, help="Bridge between git and silo (auto-commit on git hooks)")
def bridge():
    pass


@bridge.command("enable", help="Install git post-commit hook for auto silo commits")
def bridge_enable():
    silo_dir = require_silo()
    if not silo_dir:
        return

    gd = _git_dir(silo_dir)
    if not gd:
        err("no .git directory found (not a git repository?)")
        return

    hooks_dir = gd / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-commit"

    hook_path.write_text(_hook_content())
    try:
        hook_path.chmod(0o755)
    except Exception:
        warn("could not set executable permission on hook")

    ok(f"bridge enabled: {t('post-commit', 'file')} hook installed")
    click.echo("  every git commit will auto-create a silo commit")


@bridge.command("disable", help="Remove git post-commit hook")
def bridge_disable():
    silo_dir = require_silo()
    if not silo_dir:
        return

    gd = _git_dir(silo_dir)
    if not gd:
        err("no .git directory found")
        return

    hook_path = gd / "hooks" / "post-commit"
    if not hook_path.exists():
        err("no bridge hook found")
        return

    hook_path.unlink()
    ok(f"bridge disabled: {t('post-commit', 'file')} hook removed")


@bridge.command("status", help="Check if bridge hook is installed")
def bridge_status():
    silo_dir = require_silo()
    if not silo_dir:
        return

    gd = _git_dir(silo_dir)
    if not gd:
        click.echo(f"git:    {t('no .git directory', 'error')}")
        click.echo(f"bridge: {t('disabled', 'dim')}")
        return

    hook_path = gd / "hooks" / "post-commit"
    if hook_path.exists():
        click.echo(f"git:    {t(gd, 'file')}")
        click.echo(f"bridge: {t('enabled', 'ok')}")
    else:
        click.echo(f"git:    {t(gd, 'file')}")
        click.echo(f"bridge: {t('disabled', 'dim')}")
