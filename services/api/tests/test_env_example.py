""".env.example must mean the same thing to all three of its consumers.

``.env`` is read by three unrelated parsers with three different quoting rules:

  1. bash, via the Makefile's ``set -a && source .env`` (needed by Alembic and
     the seed CLI, which take configuration from the process environment).
  2. ``docker compose --env-file``.
  3. python-dotenv, via pydantic-settings, when the API and worker start.

A value that parses differently — or fails to parse — under any one of them
breaks ``make demo`` from a clean clone, which is M0's first acceptance
criterion. This actually happened: an unquoted ``HTTP_USER_AGENT`` containing
``(+https://...)`` is a bash syntax error, so ``make migrate`` died before
Alembic ever ran, on a file that looked completely fine.

These tests are cheap and they close that whole class of bug.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} is what `make setup` copies to .env"


def test_bash_can_source_env_example() -> None:
    """The exact operation the Makefile performs. It must not error."""
    result = subprocess.run(
        ["bash", "-c", f'set -a && source "{ENV_EXAMPLE}" && set +a'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f".env.example is not sourceable by bash, so `make migrate` and `make seed` "
        f"will fail from a clean clone:\n{result.stderr.strip()}"
    )


def _values_via_bash() -> dict[str, str]:
    """Every assignment in .env.example, as bash resolves it."""
    # The child starts with only PATH, so almost everything printed came from the
    # file rather than the ambient shell; the caller intersects with the file's own
    # keys to be certain. `printenv` is used rather than bash's `set` because it
    # emits values verbatim instead of requoting them.
    result = subprocess.run(
        ["bash", "-c", f'set -a && source "{ENV_EXAMPLE}" && set +a && printenv'],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    parsed: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            parsed[key] = value
    return parsed


def test_bash_and_dotenv_agree_on_every_value() -> None:
    """No value may mean one thing to the Makefile and another to the API."""
    dotenv_parsed = dotenv_values(ENV_EXAMPLE)
    bash_parsed = _values_via_bash()

    disagreements = {
        key: (value, bash_parsed.get(key))
        for key, value in dotenv_parsed.items()
        # PATH and friends come from the shell, not the file; only compare keys
        # the file actually declares.
        if key in bash_parsed and bash_parsed[key] != value
    }
    assert not disagreements, (
        f"these keys parse differently under bash and python-dotenv (dotenv, bash): {disagreements}"
    )


def test_no_key_is_declared_twice() -> None:
    """A duplicated key silently takes its last value. Usually a bad merge."""
    seen: list[str] = []
    for raw in ENV_EXAMPLE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        seen.append(line.split("=", 1)[0].removeprefix("export ").strip())
    duplicates = {key for key in seen if seen.count(key) > 1}
    assert not duplicates, f"duplicated keys in .env.example: {sorted(duplicates)}"


@pytest.mark.parametrize(
    "key",
    [
        # DATABASE_URL and REDIS_URL are deliberately absent: config.py derives
        # them from these parts, and .env.example carries the derivation as a
        # commented-out example. Asserting the parts is what matters.
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_PORT",
        "REDIS_PORT",
        "HTTP_USER_AGENT",
        "OUTBOUND_HTTP_ENABLED",
        "DEV_USER_ID",
        "NEXT_PUBLIC_API_BASE_URL",
    ],
)
def test_required_key_is_present(key: str) -> None:
    """Keys with no safe default. Settings would refuse to construct without them."""
    assert key in dotenv_values(ENV_EXAMPLE), f"{key} missing from .env.example"


def test_env_example_contains_no_plausible_secret() -> None:
    """.env.example is committed. Only local-development values belong in it."""
    values = dotenv_values(ENV_EXAMPLE)
    for key, value in values.items():
        if value is None:
            continue
        assert not value.startswith(("sk-", "ghp_", "github_pat_", "AKIA", "xoxb-")), (
            f"{key} looks like a real credential"
        )
    # The one password present is the docker-compose local default. It is named
    # so that it cannot be mistaken for a real one, and config.py refuses to boot
    # with it when NIGHTSHIFT_ENV=production.
    assert values.get("POSTGRES_PASSWORD") == "nightshift_dev_only"
    assert values.get("OUTBOUND_HTTP_ENABLED") == "false", (
        "a clean clone must not be able to reach the network until asked"
    )
