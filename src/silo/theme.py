import click

STYLES = {
    "prefix": {"fg": "cyan"},
    "error": {"fg": "red"},
    "warn": {"fg": "yellow"},
    "hash": {"fg": "yellow"},
    "branch": {"fg": "green"},
    "file": {"fg": "cyan"},
    "added": {"fg": "green"},
    "modified": {"fg": "yellow"},
    "removed": {"fg": "red"},
    "highlight": {"fg": "cyan"},
    "dim": {"fg": "white"},
    "ok": {"fg": "green"},
}


def t(text, key):
    return click.style(text, **STYLES.get(key, {}))


def ok(msg):
    click.echo(t("silo:", "prefix") + " " + msg)


def err(msg):
    click.echo(t("silo:", "error") + " " + msg, err=True)


def warn(msg):
    click.echo(t("silo:", "warn") + " " + msg)
