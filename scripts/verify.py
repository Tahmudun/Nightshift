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


def send_json(
    path: str, method: str, payload: Any = None, timeout: float = 10.0
) -> tuple[int, Any]:
    """POST/PATCH with the method set explicitly. No new dependency for this."""
    import json

    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{BASE}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, None


def send_delete(path: str, timeout: float = 10.0) -> int:
    """DELETE, returning only the status. A 204 has no body to decode."""
    request = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def check_daily_queue() -> None:
    """M2d over HTTP: the queue shows what is true and names what it cannot do.

    Written to compare **before and after** rather than to assert an absolute
    state, for the reason `check_profile_confirmation` records: asserting "the
    queue is empty" would pass vacuously on a fresh database and fail on a
    developer's own, which is a check that reports success for the wrong reason.

    It leaves nothing behind. The next action it sets is cleared again, and the
    application it may have created is left saved rather than archived —
    `check_application_tracking` leaves an archived row and says so; this one
    does not need to.
    """
    print("\nthe daily queue")
    status_code, queue = get_json("/queue")
    if not (status_code == 200 and isinstance(queue, dict)):
        check(False, "the queue answers", f"HTTP {status_code}")
        return
    check(True, "the queue answers", f"HTTP {status_code}")

    keys = [section["key"] for section in queue["sections"]]
    check(
        keys == ["follow_up", "interviews_approaching", "stale_saved", "closed_while_saved"],
        "four sections, always",
        ", ".join(keys),
    )

    deferred = queue["deferred_rows"]
    check(
        len(deferred) == 4 and all(row["reason"].strip() for row in deferred),
        "four deferred rows, each with a reason",
        str(len(deferred)),
    )
    # I4 and I7: a count beside a row that does not exist reads as a real,
    # empty result rather than as an absence.
    check(
        not any(character.isdigit() for row in deferred for character in row["name"]),
        "no deferred row carries a number",
    )

    thresholds = queue["thresholds"]
    check(
        thresholds["follow_up_silent_days"] > 0
        and thresholds["stale_saved_days"] > thresholds["follow_up_silent_days"],
        "the thresholds are coherent",
        f"{thresholds['follow_up_silent_days']} / {thresholds['stale_saved_days']}"
        f" / {thresholds['interview_horizon_days']}",
    )

    def follow_up_count() -> int:
        _, body = get_json("/queue")
        section = next(s for s in body["sections"] if s["key"] == "follow_up")
        return int(section["total"])

    before = follow_up_count()

    status_code, jobs = get_json("/jobs?limit=1&offset=4&status=open")
    if not (status_code == 200 and isinstance(jobs, dict) and jobs.get("items")):
        check(False, "a job exists to queue", f"HTTP {status_code}")
        return
    job_id = jobs["items"][0]["id"]

    code, saved = send_json("/applications", "POST", {"job_id": job_id})
    if code not in (200, 201):
        check(False, "saving a job succeeds", f"HTTP {code}")
        return
    application_id = saved["id"]
    # Entry normalisation, not exit tidiness: a previous run that died halfway
    # must not make this one fail.
    if saved.get("archived_at") is not None:
        send_json(f"/applications/{application_id}/restore", "POST")

    code, _ = send_json(
        f"/applications/{application_id}",
        "PATCH",
        {"next_action_at": "2020-01-01T00:00:00+00:00"},
    )
    if code != 200:
        check(False, "a next action can be set", f"HTTP {code}")
        return

    after = follow_up_count()
    check(
        after == before + 1,
        "a past next action adds exactly one follow-up",
        f"{before} -> {after}",
    )

    _, body = get_json("/queue")
    rows = [row for s in body["sections"] for row in s["rows"]]
    check(
        all(row["because"].strip() and row["job_title"].strip() for row in rows),
        "every row says why it is there",
        f"{len(rows)} rows",
    )
    mine = [row for row in rows if row["application_id"] == application_id]
    check(
        any("next action" in row["because"] for row in mine),
        "the row names the reason it was added",
        mine[0]["because"] if mine else "row not found",
    )

    send_json(f"/applications/{application_id}", "PATCH", {"next_action_at": None})
    restored = follow_up_count()
    check(
        restored == before,
        "clearing the next action removes the row again",
        f"{after} -> {restored}",
    )

    # Not archived, and no date left set. Unlike `check_application_tracking`,
    # this check leaves the database exactly as it found it.
    _, final = get_json(f"/applications/{application_id}")
    check(
        final["archived_at"] is None and final["next_action_at"] is None,
        "the application is left as it was found",
        "nothing is left behind",
    )


RESUME_FIXTURE = API_DIR / "tests" / "fixtures" / "resumes" / "nadia_okonkwo.txt"


def check_profile_confirmation() -> None:
    """Invariant I2 over HTTP: reading a resume changes nothing about a person.

    The shape is deliberate. It records the profile *before* pasting, pastes,
    and asserts the profile is byte-identical afterwards — that is the criterion,
    and asserting "no skills" instead would pass vacuously on a fresh database
    and fail on a developer's own.

    **It leaves nothing behind.** The resume it creates is deleted, and so is
    the one skill it confirms — but only if that skill was not already there,
    because deleting a skill somebody added by hand would be this script
    damaging the database it is verifying. `check_application_tracking` leaves
    an archived row and says so; this one does not need to.
    """
    print("\nprofile and resume confirmation")
    if not RESUME_FIXTURE.is_file():
        check(False, "the fixture resume exists", str(RESUME_FIXTURE))
        return

    # Entry normalisation, not exit tidiness. A previous run that died halfway
    # must not make this one fail — the lesson M2b's browser test recorded.
    code, listed = get_json("/resumes")
    if code == 200 and isinstance(listed, dict):
        for row in listed.get("items", []):
            if row["name"] == "verify.py fixture":
                send_delete(f"/resumes/{row['id']}")

    code, before = get_json("/profile")
    if code != 200:
        check(False, "the profile is readable", f"HTTP {code}")
        return
    skills_before = {skill["name"] for skill in before["skills"]}
    check(True, "the profile is readable", f"{len(skills_before)} confirmed skill(s) already")

    text = RESUME_FIXTURE.read_text(encoding="utf-8")
    code, resume = send_json(
        "/resumes/paste", "POST", {"name": "verify.py fixture", "text": text}
    )
    if code not in (200, 201):
        check(False, "pasting a resume succeeds", f"HTTP {code}")
        return
    check(True, "pasting a resume succeeds", f"HTTP {code}")

    proposals = resume["extractions"]
    check(len(proposals) > 0, "the resume produced proposals", f"{len(proposals)}")
    check(
        all(
            resume["parsed_text"][row["char_start"] : row["char_end"]] == row["quoted_text"]
            for row in proposals
        ),
        "every proposal quotes the text it points at",
    )
    check(
        all(row["status"] == "pending" for row in proposals),
        "invariant I2: every proposal is still pending",
    )

    code, after_paste = get_json("/profile")
    check(
        {skill["name"] for skill in after_paste["skills"]} == skills_before,
        "invariant I2: reading a resume confirmed nothing",
    )

    skill_proposals = [row for row in proposals if row["kind"] == "skill"]
    chosen = next(
        (row for row in skill_proposals if row["value"]["name"] not in skills_before), None
    )
    if chosen is None:
        check(False, "a skill proposal exists that is not already confirmed")
        send_delete(f"/resumes/{resume['id']}")
        return

    code, result = send_json(
        f"/resumes/{resume['id']}/confirm",
        "POST",
        {"decisions": [{"extraction_id": chosen["id"], "decision": "confirm"}]},
    )
    check(code == 200 and result["confirmed"] == 1, "confirming one proposal succeeds")

    code, confirmed = get_json("/profile")
    names = {skill["name"] for skill in confirmed["skills"]}
    check(
        names == skills_before | {chosen["value"]["name"]},
        "exactly the confirmed skill was added, and nothing else",
        chosen["value"]["name"],
    )
    added = next(skill for skill in confirmed["skills"] if skill["name"] == chosen["value"]["name"])
    check(
        added["source_reference"].startswith(f"resume:{resume['id']}#"),
        "the confirmed skill points back at the words it came from",
        added["source_reference"],
    )

    check(send_delete(f"/resumes/{resume['id']}") == 204, "deleting the resume succeeds")
    code, survived = get_json("/profile")
    check(
        chosen["value"]["name"] in {skill["name"] for skill in survived["skills"]},
        "a confirmed skill survives deleting the resume it came from",
    )

    check(
        send_delete(f"/profile/skills/{added['id']}") == 204,
        "the skill this check added is removed again",
        "nothing is left behind",
    )


def check_application_tracking() -> None:
    """The loop, over HTTP, exactly as the browser does it.

    Written to be idempotent: `POST /applications` answers 201 the first time
    and 200 afterwards, and this asserts the resulting state rather than the
    status code. `make acceptance` runs against the developer's own database
    and must not fail on its second invocation.

    It leaves one archived application behind. That is stated rather than
    hidden; `make reset-db` clears it.
    """
    print("\napplication tracking")
    status_code, jobs = get_json("/jobs?limit=1&status=open")
    if not (status_code == 200 and isinstance(jobs, dict) and jobs.get("items")):
        check(False, "a job exists to track", f"HTTP {status_code}")
        return
    check(True, "a job exists to track")
    job_id = jobs["items"][0]["id"]

    code, saved = send_json("/applications", "POST", {"job_id": job_id})
    if code not in (200, 201):
        check(False, "saving a job succeeds", f"HTTP {code}")
        return
    check(True, "saving a job succeeds", f"HTTP {code}")
    application_id = saved["id"]

    code, detail = get_json(f"/applications/{application_id}")
    check(detail["job"]["id"] == job_id, "the application carries its job")

    # Restore first: a previous run archived it, and an archived application
    # refuses every change until somebody puts it back. Idempotence has to
    # survive this script's own exit state, not just a clean database.
    if detail.get("archived_at") is not None:
        send_json(f"/applications/{application_id}/restore", "POST")

    code, _ = send_json(
        f"/applications/{application_id}/stage", "PATCH", {"to_stage": "preparing"}
    )
    check(code in (200, 409), "a stage change is accepted or already there", f"HTTP {code}")

    code, detail = get_json(f"/applications/{application_id}")
    kinds = [event["event_type"] for event in detail["events"]]
    check("saved" in kinds, "the history records the save")
    check(
        all(event["actor"] == "user" for event in detail["events"] if event["to_stage"]),
        "invariant I5: no stage in this history was set by the system",
    )
    check(
        detail["current_stage"] == "preparing",
        "the stage the API reports is the one that was set",
        detail["current_stage"],
    )

    code, _ = send_json(f"/applications/{application_id}/archive", "POST")
    check(code == 200, "archiving succeeds", "leaves 1 archived row; make reset-db clears it")

    code, listed = get_json("/applications")
    check(
        all(item["id"] != application_id for item in listed["items"]),
        "an archived application is out of the default list",
    )
    check(listed["archived_count"] >= 1, "and is counted rather than forgotten")


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

    from nightshift.db.session import dispose_engine, get_engine  # noqa: PLC0415

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
            "nightshift.api.main:app",
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
        check_application_tracking()
        check_profile_confirmation()
        check_daily_queue()
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
