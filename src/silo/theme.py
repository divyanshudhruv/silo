import os

import click

STYLES: dict[str, dict[str, str]] = {
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

_NO_COLOR: bool = os.environ.get("NO_COLOR") == "1"


def t(text: str, key: str) -> str:
    if _NO_COLOR:
        return text
    return click.style(text, **STYLES.get(key, {})) # type: ignore[arg-type]


def ok(msg: str) -> None:
    click.echo(t("silo:", "prefix") + " " + msg) # type: ignore[arg-type]


def err(msg: str) -> None:
    click.echo(t("silo:", "error") + " " + msg, err=True) # type: ignore[arg-type]


def warn(msg: str) -> None:
    click.echo(t("silo:", "warn") + " " + msg, err=True) # type: ignore[arg-type]
