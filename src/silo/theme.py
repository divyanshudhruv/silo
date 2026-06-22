import os

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
    "tag": {"fg": "green"},
    "dim": {"fg": "white"},
    "ok": {"fg": "green"},
    "command": {"fg": "cyan"},
    "option": {"fg": "yellow"},
    "auto": {"fg": "black", "bg": "yellow"},
}

_NO_COLOR = os.environ.get("NO_COLOR") == "1"


def t(text, key):
    if _NO_COLOR:
        return text
    return click.style(text, **STYLES.get(key, {}))


def ok(msg):
    click.echo(t("silo:", "prefix") + " " + msg)


def err(msg):
    click.echo(t("silo:", "error") + " " + msg, err=True)


def warn(msg):
    click.echo(t("silo:", "warn") + " " + msg, err=True)
