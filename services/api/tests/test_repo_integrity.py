"""Every source file that exists on disk must also exist in the repository.

Written because it did not, and nothing caught it.

`.gitignore` carried an unanchored `coverage/` — intended for vitest's output
directory — and an unanchored pattern matches a directory of that name at *any*
depth. It swallowed `apps/web/src/app/analyze/coverage/page.tsx`, the entire
coverage route, for the whole of M1c. `git add -A` skipped it without a word,
`make check` passed, `make acceptance` passed, and 16 seeded browser tests
passed, because every one of those reads the working tree, where the file
exists. CI built from a clean checkout and got a 404.

That is the whole failure mode: **a local test suite cannot see a file that is
missing from the repository, because it is not missing locally.** This test is
the one place that asks git rather than the filesystem, so the answer is about
the repository rather than about this machine.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Trees whose contents are the product. Anything here that git does not know
#: about is either a mistake or an ignore rule that is too broad.
SOURCE_TREES = (
    ("apps/web/src", (".ts", ".tsx", ".css")),
    ("apps/web/e2e", (".ts",)),
    ("apps/web/e2e-seeded", (".ts",)),
    ("services/api/nightshift", (".py",)),
    ("data", (".yaml",)),
)


def _tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return set(result.stdout.splitlines())


@pytest.mark.parametrize("tree,suffixes", SOURCE_TREES, ids=lambda value: str(value)[:40])
def test_every_source_file_is_tracked_by_git(tree: str, suffixes: tuple[str, ...]) -> None:
    """A file the repository does not contain cannot run anywhere but here."""
    root = REPO_ROOT / tree
    if not root.exists():
        pytest.skip(f"{tree} does not exist")

    tracked = _tracked_files()
    untracked = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and "node_modules" not in path.parts
        and "__pycache__" not in path.parts
        and str(path.relative_to(REPO_ROOT)) not in tracked
    )
    assert not untracked, (
        f"these files exist on disk but not in the repository: {untracked}. "
        "Check .gitignore for a pattern that is broader than it looks — an "
        "unanchored directory name matches at every depth."
    )


def test_the_coverage_route_specifically_is_tracked() -> None:
    """Named rather than only covered by the sweep above.

    A generic test can be satisfied by a future ignore rule that excludes the
    whole tree it walks. This one names the file that was actually lost, so the
    regression has to be noticed rather than absorbed.
    """
    page = "apps/web/src/app/analyze/coverage/page.tsx"
    assert (REPO_ROOT / page).exists(), f"{page} is missing from disk"
    assert page in _tracked_files(), f"{page} exists but git does not track it"


def test_gitignore_does_not_carry_an_unanchored_coverage_rule() -> None:
    """The specific rule that caused it, asserted so it cannot come back.

    `coverage/` matches at any depth; `/apps/web/coverage/` matches one place.
    The difference is a whole route directory.
    """
    lines = [
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "coverage/" not in lines, (
        "an unanchored 'coverage/' in .gitignore matches any directory of that "
        "name at any depth, including source routes. Anchor it with a leading slash."
    )
