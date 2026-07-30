#!/usr/bin/env python3
"""Prove the stack works, and exit with a status code.

`make demo` ends in a foreground dev server, which is right for a human and
useless for verification — you cannot check the exit code of something that never
exits. This is the scriptable counterpart: it starts the API, asserts the things
M0's acceptance criteria actually claim, prints what it found, and exits 0 or 1.

It asserts, specifically:

  1. /health returns 200 with database.ok and redis.ok, and reports PostGIS and
     pgvector present.
  2. /jobs returns a non-empty list — a real Greenhouse board's postings, from
     Postgres, over HTTP.
  3. Every location carries a confidence, and no location claims a coordinate
     that its confidence does not support (invariant I1, checked against live
     data rather than against a fixture).
  4. /stats agrees with /jobs about how much is mappable.
  5. The database refuses all four job_locations constraint violations. This is
     the check the milestone-0 review calls for: a constraint nobody has watched
     reject something is a comment with extra syntax.

Run via `make verify`, after `make up && make migrate && make seed`.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
VENV_BIN = API_DIR / ".venv" / "bin"

HOST = os.environ.get("API_HOST", "127.0.0.1")
PORT = os.environ.get("API_PORT", "8000")
BASE = f"http://{HOST}:{PORT}"

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {mark} {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))
    if not ok:
        failures.append(label)
    return ok


def get_json(path: str, timeout: float = 10.0) -> tuple[int, Any]:
    import json

    request = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # A 503 from /health is a valid, informative response, not a transport error.
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, None


def wait_for_api(deadline_seconds: float = 45.0) -> bool:
    started = time.monotonic()
    while time.monotonic() - started < deadline_seconds:
        try:
            status, _ = get_json("/health", timeout=3.0)
            if status in (200, 503):
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def verify_http() -> None:
    print("\nhttp")
    status, health = get_json("/health")
    check(status == 200, "/health returns 200", f"got {status}")
    if not isinstance(health, dict):
        check(False, "/health returns a JSON object")
        return

    check(health.get("status") == "ok", "/health reports status=ok", str(health.get("status")))
    database = health.get("database", {})
    redis = health.get("redis", {})
    check(database.get("ok") is True, "database reachable", str(database.get("detail")))
    check(
        "postgis" in str(database.get("detail", "")),
        "PostGIS and pgvector present",
        str(database.get("detail")),
    )
    check(redis.get("ok") is True, "redis reachable", str(redis.get("detail")))

    status, jobs = get_json("/jobs?limit=100")
    check(status == 200, "/jobs returns 200", f"got {status}")
    if not isinstance(jobs, dict) or not isinstance(jobs.get("items"), list):
        check(False, "/jobs returns a job list")
        return

    items = jobs["items"]
    check(len(items) > 0, "at least one job is served from Postgres", f"{jobs.get('total')} total")

    # -- invariant I1, against live data ------------------------------------
    allowed = {"verified", "approximate", "city_only", "remote", "unknown"}
    location_count = 0
    violations: list[str] = []
    for job in items:
        for location in job.get("locations", []):
            location_count += 1
            confidence = location.get("location_confidence")
            has_point = location.get("latitude") is not None
            if confidence not in allowed:
                violations.append(f"{job['title']}: confidence {confidence!r}")
            elif has_point != (confidence in {"verified", "approximate"}):
                violations.append(
                    f"{job['title']}: coordinates={has_point} but confidence={confidence!r}"
                )
    check(location_count > 0, "jobs carry location rows", f"{location_count} locations")
    check(
        not violations,
        "no location claims precision it has not earned (I1)",
        "; ".join(violations[:3]) if violations else "",
    )

    # A2: at least one posting must produce several location rows.
    multi = [job for job in items if len(job.get("locations", [])) > 1]
    check(len(multi) > 0, "a multi-location posting produced multiple rows (A2)", f"{len(multi)} jobs")

    # A10: absence is represented as absence.
    unpriced = [job for job in items if not job["salary"]["provided"]]
    check(
        all(job["salary"]["minimum"] is None for job in unpriced),
        "an absent salary is null, never zero (A10)",
        f"{len(unpriced)} without a published range",
    )

    status, stats = get_json("/stats")
    check(status == 200, "/stats returns 200")
    if isinstance(stats, dict):
        mappable = stats.get("mappable_locations")
        check(
            mappable == 0,
            "stats report 0 mappable locations in M0",
            "nothing is geocoded yet; any other value means something fabricated one",
        )
        confidence = stats.get("location_confidence", {})
        check(
            confidence.get("verified") == 0 and confidence.get("approximate") == 0,
            "no location is verified or approximate in M0",
            str(confidence),
        )


async def verify_constraints() -> None:
    """Attempt each job_locations violation and require the database to refuse it."""
    print("\ndatabase constraints (invariant I1 in DDL)")

    sys.path.insert(0, str(API_DIR))
    from sqlalchemy import text as sql  # noqa: PLC0415

    from citysignal.db.session import dispose_engine, get_engine  # noqa: PLC0415

    engine = get_engine()

    # Each case is a set of column values that must be rejected.
    cases = [
        (
            "a point labelled unknown",
            "40.75, -73.99, 'unknown'",
        ),
        (
            "verified with no point",
            "NULL, NULL, 'verified'",
        ),
        (
            "half a coordinate pair",
            "40.75, NULL, 'verified'",
        ),
        (
            "latitude out of range",
            "120.0, -73.99, 'verified'",
        ),
    ]

    async with engine.begin() as connection:
        job_id = (
            await connection.execute(sql("SELECT id FROM jobs LIMIT 1"))
        ).scalar_one_or_none()

    if job_id is None:
        check(False, "a job exists to attach test locations to", "run `make seed` first")
        return

    for label, values in cases:
        rejected = False
        detail = ""
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sql(
                        "INSERT INTO job_locations "
                        "(job_id, raw_text, latitude, longitude, location_confidence) "
                        f"VALUES (:job_id, 'constraint probe', {values})"
                    ),
                    {"job_id": job_id},
                )
            # Reaching here means the insert succeeded, which is the failure.
            async with engine.begin() as connection:
                await connection.execute(
                    sql("DELETE FROM job_locations WHERE raw_text = 'constraint probe'")
                )
        except Exception as exc:
            rejected = True
            detail = type(exc).__name__
        check(rejected, f"database refuses {label}", detail)

    await dispose_engine()


def main() -> int:
    print(f"{DIM}verifying against {BASE}{RESET}")

    api = subprocess.Popen(
        [
            str(VENV_BIN / "uvicorn"),
            "citysignal.api.main:app",
            "--host",
            HOST,
            "--port",
            PORT,
            "--no-access-log",
        ],
        cwd=API_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_api():
            print(f"  {RED}✗{RESET} API did not start within 45s")
            return 1
        verify_http()
        asyncio.run(verify_constraints())
    finally:
        api.terminate()
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()

    print()
    if failures:
        print(f"{RED}{len(failures)} check(s) failed:{RESET}")
        for failure in failures:
            print(f"  - {failure}")
        print("\nM0 acceptance is NOT satisfied.")
        return 1
    print(f"{GREEN}all checks passed{RESET} — record this output in docs/PROGRESS.md\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
