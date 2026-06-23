import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

# ── Edit this list to add your own commands: each item is (label, command) ────
# Use DOUBLE quotes for args with spaces (cmd.exe style), not single quotes.

STEPS: list[tuple[str, str]] = [
    # ── init ──
    ("init",                 "silo init ."),
    ("status (empty)",       "silo status"),

    # ── commit ──
    ("commit first",         "echo hello > a.txt & silo commit first"),
    ("commit second",        "echo world > b.txt & silo commit second"),
    ("commit third",         "echo foo > c.txt & silo commit third"),
    ("commit --co",          "echo co > co.txt & silo commit \"co-authored\" --co \"Alice <alice@x.com>\""),
    ("status --noignore",    "silo status --noignore"),

    # ── log ──
    ("log --oneline",        "silo log --oneline"),
    ("log full",             "silo log"),
    ("log --graph",          "silo log --graph"),
    ("log -n 2",             "silo log -n 2"),
    ("log --grep first",     "silo log --grep first"),
    ("log --since",          "silo log --since 2020-01-01"),

    # ── show ──
    ("show HEAD",            "silo show"),
    ("show <hash>",          "for /f %a in ('silo log --oneline') do silo show %a & exit /b"),

    # ── diff ──
    ("diff",                 "silo diff"),
    ("diff --stat",          "silo diff --stat"),
    ("diff HEAD~1",          "silo diff HEAD~1"),
    ("diff commits",         "silo diff HEAD~1 HEAD~2"),
    ("diff --noignore",      "silo diff --noignore"),

    # ── amend ──
    ("amend",                "silo amend first-edited"),
    ("amend <hash>",         "for /f %a in ('silo log --oneline') do silo amend \"edited-again\" %a & exit /b"),

    # ── branch ──
    ("branch create dev",    "silo branch create dev"),
    ("branch create at ref", "silo branch create bugfix HEAD~1"),
    ("branch list",          "silo branch list"),
    ("switch dev",           "silo switch dev"),
    ("commit on dev",        "echo dev-work > dev.txt & silo commit dev-work"),
    ("switch main",          "silo switch main"),
    ("branch rename",        "silo branch rename dev feature"),
    ("branch delete",        "silo branch delete feature"),
    ("branch list after",    "silo branch list"),

    # ── note ──
    ("note create",          "silo note create research-needed"),
    ("note weld to HEAD",
     "for /f %a in ('silo note list') do silo note weld %a HEAD & exit /b"),
    ("note unweld from HEAD",
     "for /f %a in ('silo note list') do silo note unweld %a HEAD & exit /b"),
    ("note add",             "silo note add quick-thought"),
    ("note list",            "silo note list"),
    ("note show",            "for /f %a in ('silo note list') do silo note show %a & exit /b"),
    ("note edit",
     "for /f %a in ('silo note list') do silo note edit %a revised-text & exit /b"),
    ("note delete",
     "for /f %a in ('silo note list') do silo note delete %a & exit /b"),

    # ── tag ──
    ("tag create v1",        "silo tag create v1"),
    ("tag create rc",        "silo tag create rc"),
    ("tag weld v1",          "silo tag weld v1 HEAD"),
    ("tag weld --branch",    "silo tag weld rc --branch main"),
    ("tag list",             "silo tag list"),
    ("tag show v1",          "silo tag show v1"),
    ("tag unweld v1",        "silo tag unweld v1 HEAD"),
    ("tag unweld --branch",  "silo tag unweld rc --branch main"),
    ("tag add",              "silo tag add hotfix HEAD"),
    ("tag rename",           "silo tag rename rc v2"),
    ("tag delete",           "silo tag delete hotfix"),

    # ── snapshot ──
    ("snapshot",             "silo snapshot"),
    ("snapshot --noignore",  "silo snapshot --noignore"),

    # ── config ──
    ("config set",           "silo config set use_gitignore true"),
    ("config list",          "silo config list"),
    ("config set theme",     "silo config set theme dark"),
    ("config list",          "silo config list"),
    ("config set name",      "silo config set name \"Test User\""),
    ("config set email",     "silo config set email \"test@test.com\""),

    # ── info / verify / cleanup / gc ──
    ("info",                 "silo info"),
    ("verify",               "silo verify"),
    ("cleanup",              "silo cleanup"),
    ("gc --force",           "silo gc --force"),

    # ── freeze / unfreeze ──
    ("freeze",               "silo freeze"),
    ("unfreeze",             "silo unfreeze"),

    # ── bridge ──
    ("bridge status",        "silo bridge status"),

    # ── reset (on throwaway branch) ──
    ("branch create reset-test", "silo branch create reset-test"),
    ("switch reset-test",        "silo switch reset-test"),
    ("commit pre-reset",         "echo pre-reset > reset.txt & silo commit \"pre-reset\""),
    ("reset HEAD~1",             "silo reset HEAD~1"),
    ("log after reset",          "silo log --oneline"),
    ("switch main",              "echo y | silo switch main"),
    ("branch delete reset-test", "silo branch delete reset-test"),

]

# ── Nothing to edit below this line ──────────────────────────────────────────

if __name__ == "__main__":
    sandbox: Path = Path(tempfile.mkdtemp(
        suffix="_silo_demo"))  # type: ignore[arg-type]
    ok: int = 0
    fail: int = 0
    shell: bool = sys.platform == "win32"

    print(f"\n  sandbox: {sandbox}\n")

    for label, cmd in STEPS:
        print(f"  {'-' * 60}")
        print(f"  [{label}]")
        print(f"  $ {cmd}")
        print(f"  {'-' * 60}")

        result: subprocess.CompletedProcess[str] = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(sandbox),
        )
        out: str = (result.stdout + result.stderr).strip()
        if out:
            for line in out.splitlines():
                print(f"    {line}")
        else:
            print(f"    (no output)")

        if result.returncode == 0:
            ok += 1
            print(f"  OK  (exit 0)\n")
        else:
            fail += 1
            nfo: list[str] = result.stdout.strip().splitlines(
            )[-1:] if result.stdout.strip() else []
            nfo += result.stderr.strip().splitlines(
            )[-1:] if result.stderr.strip() else []
            if nfo:
                print(f"    {nfo[0]}")
            print(f"  FAIL (exit {result.returncode})\n")

    print(f"  {'=' * 50}")
    print(f"  Done: {ok} OK, {fail} FAIL ({ok+fail} total)\n")

    shutil.rmtree(sandbox, ignore_errors=True)
    sys.exit(1 if fail else 0)
