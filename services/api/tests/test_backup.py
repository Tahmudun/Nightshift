"""scripts/backup.py: the only copy of a person's job search.

The properties under test are the ones a backup tool fails silently on:

* a dump that did not complete must never become "the newest backup";
* a dump that cannot be read back is a failure, not a file;
* resetting takes two decisions — FORCE skips the question, never the backup.

``docker compose`` is replaced by a shell one-liner that behaves like
``pg_dump`` / ``pg_restore --list``, so these run without a database. The live
round trip (dump → mutate → restore → mutation gone; truncated dump → restore
fails and the database is untouched) is recorded in PROGRESS.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("backup", ROOT / "scripts" / "backup.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["backup"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def backup() -> Any:
    return _load()


def _fake_compose(
    *,
    dump: str = "printf 'PGDMP-fake'",
    listing: str = "echo '1; 0 0 TABLE DATA public jobs nightshift'",
) -> list[str]:
    """A stand-in for `docker compose`: arguments are appended after `sh`, so
    `$*` is the pg_dump / pg_restore command line the script asked for."""
    script = (
        f'case "$*" in *pg_dump*) {dump} ;; '
        f'*"pg_restore --list"*) cat >/dev/null; {listing} ;; esac'
    )
    return ["sh", "-c", script, "sh"]


NOW = datetime(2026, 10, 2, 5, 15, 0, tzinfo=UTC)


def test_backup_names_sort_in_time_order(backup: Any) -> None:
    earlier = backup.backup_name(datetime(2026, 1, 9, 23, 0, tzinfo=UTC))
    later = backup.backup_name(datetime(2026, 10, 2, 5, 15, tzinfo=UTC))
    assert later == "nightshift-20261002T051500Z.dump"
    assert sorted([later, earlier]) == [earlier, later]


def test_latest_backup_ignores_partials_and_strangers(backup: Any, tmp_path: Path) -> None:
    assert backup.latest_backup(tmp_path / "missing") is None
    assert backup.latest_backup(tmp_path) is None
    old = tmp_path / "nightshift-20260101T000000Z.dump"
    new = tmp_path / "nightshift-20261001T000000Z.dump"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    (tmp_path / "nightshift-20261231T000000Z.dump.partial").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not a backup")
    assert backup.latest_backup(tmp_path) == new


def test_a_good_dump_lands_under_its_final_name(backup: Any, tmp_path: Path) -> None:
    path = backup.dump(tmp_path, compose=_fake_compose(), now=NOW)
    assert path == tmp_path / "nightshift-20261002T051500Z.dump"
    assert path.read_bytes() == b"PGDMP-fake"
    assert list(tmp_path.iterdir()) == [path]


def test_a_failed_pg_dump_leaves_nothing_behind(backup: Any, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        backup.dump(tmp_path, compose=_fake_compose(dump="printf 'PGDMP-half'; exit 1"), now=NOW)
    assert list(tmp_path.iterdir()) == []
    assert backup.latest_backup(tmp_path) is None


def test_an_empty_dump_is_a_failure(backup: Any, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="empty"):
        backup.dump(tmp_path, compose=_fake_compose(dump="true"), now=NOW)
    assert list(tmp_path.iterdir()) == []


def test_a_dump_that_does_not_read_back_is_a_failure(backup: Any, tmp_path: Path) -> None:
    """pg_dump exited 0 but the file holds no table data — not a backup."""
    with pytest.raises(RuntimeError, match="did not read back"):
        backup.dump(tmp_path, compose=_fake_compose(listing="echo '; nothing here'"), now=NOW)
    assert list(tmp_path.iterdir()) == []


def test_restore_refuses_a_missing_or_empty_file(backup: Any, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no such backup"):
        backup.restore(tmp_path / "nope.dump", compose=_fake_compose())
    empty = tmp_path / "nightshift-20261002T051500Z.dump"
    empty.write_bytes(b"")
    with pytest.raises(RuntimeError, match="no such backup"):
        backup.restore(empty, compose=_fake_compose())


def test_confirmation_needs_the_word_or_force(backup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORCE", raising=False)
    assert backup.confirm("x", ask=lambda _: "RESET", interactive=True)
    assert not backup.confirm("x", ask=lambda _: "yes", interactive=True)
    assert not backup.confirm("x", ask=lambda _: "reset", interactive=True)
    # nobody at a terminal: refuse rather than guess
    assert not backup.confirm("x", ask=lambda _: "RESET", interactive=False)
    monkeypatch.setenv("FORCE", "1")
    assert backup.confirm("x", ask=lambda _: "no", interactive=False)


def test_force_skips_the_question_but_not_the_backup(
    backup: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reset whose backup fails is aborted even with FORCE=1."""
    monkeypatch.setenv("FORCE", "1")
    monkeypatch.delenv("SKIP_BACKUP", raising=False)
    monkeypatch.setenv("NIGHTSHIFT_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(backup, "compose_command", lambda: _fake_compose(dump="exit 1"))
    assert backup.main(["backup.py", "guard-reset"]) == 1

    monkeypatch.setattr(backup, "compose_command", lambda: _fake_compose())
    assert backup.main(["backup.py", "guard-reset"]) == 0
    assert backup.latest_backup(tmp_path) is not None


def test_skipping_the_backup_is_its_own_decision(
    backup: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FORCE", "1")
    monkeypatch.setenv("SKIP_BACKUP", "1")
    monkeypatch.setenv("NIGHTSHIFT_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(backup, "compose_command", lambda: _fake_compose(dump="exit 1"))
    assert backup.main(["backup.py", "guard-reset"]) == 0
    assert backup.latest_backup(tmp_path) is None


def test_backups_default_outside_the_repository(
    backup: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NIGHTSHIFT_BACKUP_DIR", raising=False)
    assert ROOT not in backup.backup_dir().parents
