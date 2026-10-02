#!/usr/bin/env python3
"""Back up and restore the database — the only copy of a person's job search.

Everything Nightshift knows about *you* lives in one Docker volume: applications
and their stage history, interviews, notes, the profile and confirmed resume
facts, captures, MCP tokens, and the company offices typed into
``data/company-locations.yaml`` and geocoded. The corpus can be re-polled; none
of that can. Until this script there was no copy of it anywhere, and
``make reset-db`` deleted it with one word.

    backup.py dump              write a verified dump to the backup directory
    backup.py restore [FILE]    restore FILE, or the newest dump (asks first)
    backup.py guard-reset       back up, then ask; exits non-zero to abort a reset

Three properties, each tested:

* **A dump that did not finish never looks like a backup.** It is written to a
  temporary name, read back with ``pg_restore --list``, and only then renamed
  into place, so "the newest file" is always a complete, readable dump.
* **A restore that fails changes nothing.** ``--single-transaction`` makes the
  whole restore commit or roll back as one.
* **Destroying data takes two separate decisions.** ``FORCE=1`` skips the
  question; it does not skip the backup. Skipping the backup is ``SKIP_BACKUP=1``,
  a second, deliberate setting — a stopped database cannot be backed up, and
  the answer to that is not to delete it anyway by default.

Backups go to ``~/nightshift-backups`` (override with ``NIGHTSHIFT_BACKUP_DIR``),
outside the repository on purpose: they are personal data, and the tree is one
``git add -A`` away from a public remote. Nothing is ever deleted from that
directory by this script.

Standard library only, so it runs before ``make setup`` has built the venv.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

PREFIX = "nightshift-"
SUFFIX = ".dump"
CONFIRM_WORD = "RESET"


def backup_dir() -> Path:
    override = os.environ.get("NIGHTSHIFT_BACKUP_DIR")
    return Path(override).expanduser() if override else Path.home() / "nightshift-backups"


def backup_name(now: datetime) -> str:
    """``nightshift-20261002T051500Z.dump`` — UTC, so names sort in time order."""
    return f"{PREFIX}{now.astimezone(UTC):%Y%m%dT%H%M%SZ}{SUFFIX}"


def latest_backup(directory: Path) -> Path | None:
    """The newest complete dump, or None. Temporary files never qualify."""
    if not directory.is_dir():
        return None
    dumps = sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.name.startswith(PREFIX) and p.name.endswith(SUFFIX)
    )
    return dumps[-1] if dumps else None


def compose_command() -> list[str]:
    """The same `docker compose` invocation the Makefile uses, passed in by it."""
    raw = os.environ.get(
        "NIGHTSHIFT_COMPOSE", "docker compose --env-file .env -f infra/docker-compose.yml"
    )
    return shlex.split(raw)


def _db_args() -> list[str]:
    return [
        "-U",
        os.environ.get("POSTGRES_USER", "nightshift"),
        "-d",
        os.environ.get("POSTGRES_DB", "nightshift"),
    ]


def _exec(compose: Sequence[str], *argv: str) -> list[str]:
    return [*compose, "exec", "-T", "postgres", *argv]


def dump(directory: Path, *, compose: Sequence[str], now: datetime | None = None) -> Path:
    """Write a verified custom-format dump and return its path. Raises on failure."""
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / backup_name(now or datetime.now(UTC))
    partial = final.with_name(final.name + ".partial")
    try:
        with partial.open("wb") as handle:
            result = subprocess.run(
                _exec(compose, "pg_dump", "--format=custom", "--no-owner", *_db_args()),
                stdout=handle,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip() or result.returncode
            raise RuntimeError(f"pg_dump failed: {detail}")
        if partial.stat().st_size == 0:
            raise RuntimeError("pg_dump produced an empty file")
        with partial.open("rb") as handle:
            listing = subprocess.run(
                _exec(compose, "pg_restore", "--list"),
                stdin=handle,
                capture_output=True,
                check=False,
            )
        entries = listing.stdout.decode(errors="replace")
        if listing.returncode != 0 or "TABLE DATA" not in entries:
            raise RuntimeError("the dump did not read back as a database with data in it")
        partial.replace(final)
    finally:
        partial.unlink(missing_ok=True)
    return final


def restore(path: Path, *, compose: Sequence[str]) -> None:
    """Replace the database's contents with ``path``, in one transaction."""
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"no such backup: {path}")
    with path.open("rb") as handle:
        result = subprocess.run(
            _exec(
                compose,
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--single-transaction",
                *_db_args(),
            ),
            stdin=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(
            "restore failed and was rolled back — the database is unchanged: "
            + result.stderr.decode(errors="replace").strip()[-800:]
        )


def confirm(
    prompt: str, *, ask: Callable[[str], str] = input, interactive: bool | None = None
) -> bool:
    """True only for ``FORCE=1`` or the confirm word typed at a terminal."""
    if os.environ.get("FORCE") == "1":
        return True
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print(
            "refusing: not a terminal, so nobody can answer. Re-run with FORCE=1 if you mean it.",
            file=sys.stderr,
        )
        return False
    return ask(f"{prompt}\nType {CONFIRM_WORD} to continue: ").strip() == CONFIRM_WORD


def _human(size: int) -> str:
    return f"{size / 1_048_576:.1f} MB" if size >= 1_048_576 else f"{size / 1024:.0f} KB"


def main(argv: Sequence[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    compose = compose_command()
    directory = backup_dir()

    if command == "dump":
        try:
            path = dump(directory, compose=compose)
        except RuntimeError as err:
            print(f"backup FAILED: {err}", file=sys.stderr)
            return 1
        print(f"==> backed up to {path} ({_human(path.stat().st_size)})")
        return 0

    if command == "restore":
        target = (
            Path(argv[2]).expanduser() if len(argv) > 2 and argv[2] else latest_backup(directory)
        )
        if target is None:
            print(f"no backups in {directory} — nothing to restore", file=sys.stderr)
            return 1
        if not confirm(f"This replaces EVERYTHING in the database with {target}."):
            print("restore cancelled")
            return 1
        try:
            restore(target, compose=compose)
        except RuntimeError as err:
            print(f"restore FAILED: {err}", file=sys.stderr)
            return 1
        print(f"==> restored {target}")
        return 0

    if command == "guard-reset":
        if os.environ.get("SKIP_BACKUP") == "1":
            print("SKIP_BACKUP=1: resetting without a backup.")
        else:
            try:
                path = dump(directory, compose=compose)
            except RuntimeError as err:
                print(
                    f"reset ABORTED: could not back up first ({err}). Nothing was deleted.\n"
                    "Fix the database, or re-run with SKIP_BACKUP=1 to reset without a copy.",
                    file=sys.stderr,
                )
                return 1
            print(f"==> backed up to {path} ({_human(path.stat().st_size)})")
            print(f"    `make restore FILE={path}` undoes this reset")
        if not confirm(
            "reset-db DELETES the database volume: applications, interviews, notes,\n"
            "profile, resumes, captures, typed company offices and every MCP token\n"
            "(Claude Desktop will need re-linking)."
        ):
            print("reset cancelled — nothing was deleted")
            return 1
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
