"""Shared test fixtures.

Tests must not read the developer's ``.env``. A suite whose result depends on a
local file is a suite that passes on one machine and fails in CI, so every
:class:`Settings` here is built with ``_env_file=None`` and explicit values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.config import Settings, get_settings

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def make_settings(**overrides: Any) -> Settings:
    """Hermetic settings for tests. Ignores ``.env`` entirely."""
    defaults: dict[str, Any] = {
        "nightshift_env": "test",
        "outbound_http_enabled": False,
        "http_user_agent": "Nightshift/0.1-test (+https://github.com/Tahmudun/Nightshift)",
        # The configured ceiling, so the limiter spaces requests 50ms apart and
        # the suite stays fast. Not higher: the ceiling is a real politeness
        # guardrail (§7.3) and tests do not get to relax product constraints.
        "source_requests_per_second": 20.0,
        "http_max_retries": 2,
        "http_backoff_base_seconds": 0.01,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[call-arg]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    """Config is a process singleton; leaking one test's config into the next is a trap."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def load_json_fixture(*parts: str) -> Any:
    return json.loads((FIXTURE_DIR.joinpath(*parts)).read_text())


@pytest.fixture(scope="session")
def greenhouse_board_payload() -> dict[str, Any]:
    """The committed Datadog board response (see the sibling .meta.json for provenance)."""
    payload = load_json_fixture("greenhouse", "datadog_board.json")
    assert payload["jobs"], "fixture is empty"
    return payload  # type: ignore[no-any-return]
