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
import math
import os
import socket
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

#: The bearer token this run authenticates with, filled in by `sign_in()`.
#:
#: M5b (ADR 0037) closed every route except `/health` and `/auth`, so `verify`
#: has to sign in like anything else. It uses the bearer path rather than the
#: cookie one because `urllib` has no cookie jar here and because that is the
#: path a non-browser client takes — the same one M5c's MCP server will use, so
#: this script exercises it on every acceptance run rather than leaving it
#: covered only by unit tests.
TOKEN: str | None = None

#: The signed-in account's id. Needed because the corpus now holds more than one
#: person's rows — `make seed` plants two accounts so `make demo` can show that
#: they cannot see each other — and a check about "my scores" that counts
#: everybody's is asserting the wrong number.
USER_ID: str | None = None


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def sign_in() -> bool:
    """Get a token for the seeded demo account. Fails loudly rather than 401ing.

    A failure here would otherwise surface as forty unrelated checks reporting
    401, which says "the API is broken" when the truth is "the seed did not
    run" or "the password is not the one in .env".
    """
    global TOKEN, USER_ID
    email = os.environ.get("DEV_USER_EMAIL", "dev@nightshift.local")
    password = os.environ.get("DEV_USER_PASSWORD", "nightshift-demo-password")
    status_code, body = send_json(
        "/auth/token", "POST", {"email": email, "password": password}
    )
    if status_code == 200 and isinstance(body, dict) and body.get("access_token"):
        TOKEN = str(body["access_token"])
        me_code, me = get_json("/auth/me")
        if me_code != 200 or not isinstance(me, dict):
            return check(False, "signed in", f"GET /auth/me returned {me_code}")
        USER_ID = str(me["id"])
        return check(True, "signed in", f"as {email}")
    return check(
        False,
        "signed in",
        f"POST /auth/token returned {status_code} for {email} — has `make seed` run?",
    )


def check(ok: bool, label: str, detail: str = "") -> bool:
    mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {mark} {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))
    if not ok:
        failures.append(label)
    return ok


def get_json(path: str, timeout: float = 10.0) -> tuple[int, Any]:
    import json

    request = urllib.request.Request(
        f"{BASE}{path}", headers={"Accept": "application/json", **auth_headers()}
    )
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
    headers = {"Accept": "application/json", **auth_headers()}
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
    request = urllib.request.Request(f"{BASE}{path}", method="DELETE", headers=auth_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


async def rescore_corpus() -> int:
    """Recompute every (person, posting) pair with no current score.

    Lifted to module level at M3d Task 7, when a second check came to depend on
    a scored corpus. `check_profile_confirmation` runs before the queue and
    edits a profile column, and **every score is deleted when a scoring input
    moves** — so without this the queue's three score-backed rows were asserted
    against an empty table and every one of them passed vacuously.
    """
    from nightshift.db.session import session_scope  # noqa: PLC0415
    from nightshift.domain.matching import recompute_pending  # noqa: PLC0415

    async with session_scope() as session:
        report = await recompute_pending(session)
        return report.scored


async def check_daily_queue() -> None:
    """M2d and M3d Task 7 over HTTP: the queue shows what is true and names what
    it cannot do.

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
    # Three of the rows below are computed from match scores, and the checks
    # before this one have invalidated every score on their way past. Asserting
    # against that is asserting against nothing.
    scored = await rescore_corpus()
    # Disposed here, not at the end: everything below this line is HTTP, and an
    # engine left open across the `asyncio.run` boundary is bound to a loop that
    # has closed by the time the next check asks for it.
    from nightshift.db.session import dispose_engine  # noqa: PLC0415

    await dispose_engine()
    # `> 0`, not `>= 0`. M3d Task 8 found this written as the latter — a check
    # that cannot fail, added by the commit whose subject was three checks that
    # could not fail. Every pair in the seeded corpus is invalidated by the
    # checks above this one, so a zero here means the rescore did not happen and
    # the three score-backed rows below are about to be asserted against nothing.
    check(scored > 0, "the corpus is scored before the score-backed rows are read", str(scored))
    status_code, queue = get_json("/queue")
    if not (status_code == 200 and isinstance(queue, dict)):
        check(False, "the queue answers", f"HTTP {status_code}")
        return
    check(True, "the queue answers", f"HTTP {status_code}")

    keys = [section["key"] for section in queue["sections"]]
    check(
        keys
        == [
            "todays_one_thing",
            "follow_up",
            "interviews_approaching",
            "stale_saved",
            "closed_while_saved",
            "requirement_gaps",
            "best_new_internships",
        ],
        "every section, always",
        ", ".join(keys),
    )

    deferred = queue["deferred_rows"]
    check(
        bool(deferred) and all(row["reason"].strip() for row in deferred),
        "every deferred row carries a reason",
        str(len(deferred)),
    )
    # M3d Task 7. A deferral is a claim with a date on it. One left standing
    # after the thing that blocked it was built is a false statement the page
    # keeps making, and nothing local can see it.
    check(
        not (set(keys) & {row["name"].strip().lower().replace(" ", "_") for row in deferred}),
        "no section is both built and deferred",
        ", ".join(row["name"] for row in deferred),
    )
    # I4 and I7: a count beside a row that does not exist reads as a real,
    # empty result rather than as an absence.
    check(
        not any(character.isdigit() for row in deferred for character in row["name"]),
        "no deferred row carries a number",
    )

    # M3d Task 7: the score-backed section, and the three promises it makes.
    internships = next(s for s in queue["sections"] if s["key"] == "best_new_internships")
    check(
        bool(internships["note"]),
        "the suggested section explains what it is a list of",
        (internships["note"] or "")[:60],
    )
    spots = internships["blind_spots"]
    check(
        len(spots) == 2 and all(spot["because"].strip() for spot in spots),
        "it says what it could not see, with a sentence per count",
        ", ".join(f"{spot['name']}={spot['count']}" for spot in spots),
    )
    # I4: the ranking that produced these rows is not shown as a number here,
    # because a queue row has no room for the breakdown behind one. The band is
    # a verdict and travels; the score does not.
    check(
        all(
            row["application_id"] is None and row["eligibility"] is not None
            for row in internships["rows"]
        ),
        "each suggestion carries a state and no application",
        f"{len(internships['rows'])} rows, {internships['total']} before the cap",
    )

    # ADR 0019, and the reason PRODUCT-SPEC's "resume mismatch warnings" ships
    # under another name: the list is differenced against confirmed skills, and
    # calling it a resume problem is a true statement about a database rendered
    # as a false one about a document. The *rows* of this section are checked
    # further down, once this script has a tracked role for them to be about.
    gaps = next(s for s in queue["sections"] if s["key"] == "requirement_gaps")
    check(
        "confirmed" in (gaps["note"] or "").lower()
        and "resume" not in (gaps["note"] or "").lower(),
        "the gap row says it reads confirmed skills, and never says resume",
        (gaps["note"] or "")[:60],
    )

    # M3d Task 7. The row PRODUCT-SPEC called the least honest to fake. It is
    # honest exactly when it invents nothing, so the check is that the row it
    # shows is a row that exists below it, character for character.
    one_thing = next(s for s in queue["sections"] if s["key"] == "todays_one_thing")
    below = [
        (row["job_id"], row["because"])
        for s in queue["sections"]
        if s["key"] != "todays_one_thing"
        for row in s["rows"]
    ]
    check(
        len(one_thing["rows"]) <= 1
        and all((row["job_id"], row["because"]) in below for row in one_thing["rows"]),
        "the one thing repeats a row from a list below, and never composes one",
        one_thing["rows"][0]["because"] if one_thing["rows"] else "nothing waiting",
    )
    check(
        "picked in this order" in (one_thing["note"] or ""),
        "it says which order it picked by",
        (one_thing["note"] or "")[:60],
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

    # The gap row, now that a role is tracked for it to be about. Before this
    # point in the script there is no live application at all, so asserting on
    # its rows earlier was asserting on an empty list — the vacuous-check
    # failure this file keeps having to relearn.
    gaps_now = next(s for s in body["sections"] if s["key"] == "requirement_gaps")
    check(
        all("nothing you have confirmed" in row["because"] for row in gaps_now["rows"]),
        "every gap row names what went unanswered",
        f"{len(gaps_now['rows'])} of {len(rows)} rows are gaps",
    )
    check(
        all(
            spot["because"].strip() and spot["name"] == "not_yet_scored"
            for spot in gaps_now["blind_spots"]
        ),
        "the gap row says how many tracked roles it could not read",
        ", ".join(f"{s['name']}={s['count']}" for s in gaps_now["blind_spots"]),
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


#: The six `users` columns the gate reads, and the only ones this check writes.
#: Named rather than derived so that a seventh gate input added later fails the
#: parity assertion below instead of being silently left out of the snapshot.
GATE_FIELDS = (
    "graduation_year",
    "graduation_month",
    "degree",
    "years_experience",
    "is_enrolled",
    "work_authorization",
)

#: A profile that contradicts several stated bars at once, chosen from what the
#: seeded corpus states rather than invented: it holds a posting requiring
#: current enrollment inside a 2026-2028 window, and several stating a years
#: minimum. A 2024 graduate who is not enrolled fails all three.
BLOCKED_PROFILE: dict[str, Any] = {
    "graduation_year": 2024,
    "graduation_month": 5,
    "degree": "BS in Computer Science",
    "years_experience": 0,
    "is_enrolled": False,
    "work_authorization": "needs_sponsorship",
}

#: Every gate field cleared. `work_authorization` clears to `unspecified` rather
#: than to null — the column is not nullable and `unspecified` *is* its "has not
#: said" value, which is the whole reason the authorization rule refuses to read
#: it as "needs sponsorship".
EMPTY_PROFILE: dict[str, Any] = {
    "graduation_year": None,
    "graduation_month": None,
    "degree": None,
    "years_experience": None,
    "is_enrolled": None,
    "work_authorization": "unspecified",
}


def _corpus_verdicts() -> list[dict[str, Any]]:
    """Every seeded posting's detail payload, read one at a time.

    `/jobs` does not carry the verdict — it is computed per posting on read —
    so there is no bulk form of this and there should not be one.
    """
    code, listed = get_json("/jobs?limit=100")
    if code != 200 or not isinstance(listed, dict):
        return []
    details = []
    for item in listed.get("items", []):
        code, detail = get_json(f"/jobs/{item['id']}")
        if code == 200 and isinstance(detail, dict):
            details.append(detail)
    return details


def check_city_placement() -> None:
    """Somebody's role has to be standing on a real building.

    Added 2026-08-19, and the reason is the whole of it. `company_locations`
    is filled by `make offices`, which was not part of `seed`, `demo`,
    `reset-db` or `acceptance`. A reseed emptied it. `GET /city/signals` came
    back **31 of 31 `unresolved`**, the renderer drew 31 columns floating in
    the sky with nothing under them — which is exactly what `city.md` §4.8
    says an unplaced role should look like, so the renderer was right — and
    every check in this file, every unit test and every browser test stayed
    green. The city was empty and nothing anywhere said so.

    The gap was that nothing asserted the *promotion path* end to end: a
    human's address in `data/company-locations.yaml` → a geocode → a
    `company_locations` row → a signal whose placement is a building. It has
    four hops and each one was tested in isolation.

    This deliberately does **not** assert that every role is placed. Most are
    not and must not be: eleven of the seeded roles are at an employer whose
    address nobody has confirmed, and I1 says those float. What it asserts is
    that the path can carry anything at all.
    """
    status, payload = get_json("/city/signals")
    check(status == 200, "/city/signals returns 200", f"got {status}")
    if not isinstance(payload, dict) or not isinstance(payload.get("signals"), list):
        check(False, "/city/signals returns a signal list")
        return

    signals = payload["signals"]
    placed = [s for s in signals if s.get("placement", {}).get("kind") == "building"]
    floating = [s for s in signals if s.get("placement", {}).get("kind") == "unresolved"]

    check(
        len(placed) > 0,
        "at least one role stands on a real building",
        f"{len(placed)} placed, {len(floating)} floating of {len(signals)}"
        + ("  — did `seed` load data/company-locations.yaml?" if not placed else ""),
    )

    # I1, at the surface that draws the coordinate. A building placement that
    # carries no BIN is a marker floating over a neighbourhood being drawn as
    # if it were on a tower, which is the fabrication the invariant forbids and
    # is indistinguishable from a correct one by eye.
    unbacked = [
        s["job_id"]
        for s in placed
        if not s["placement"].get("building_id")
        or s["placement"].get("latitude") is None
        or s["placement"].get("location_confidence") != "verified"
    ]
    check(
        not unbacked,
        "every placed role carries a verified coordinate and a BIN (I1)",
        f"{len(unbacked)} without: {unbacked[:3]}" if unbacked else "",
    )

    # And the counterpart, which is the invariant's other half: a role with no
    # confirmed office must NOT acquire a coordinate on its way to the map.
    invented = [
        s["job_id"] for s in floating if s["placement"].get("latitude") is not None
    ]
    check(
        not invented,
        "no unplaced role was given a coordinate (I1)",
        f"{len(invented)} invented: {invented[:3]}" if invented else "",
    )


def check_eligibility_gate() -> None:
    """M3b over HTTP: a verdict about a person, against the seeded corpus.

    Four of these assertions exist because they cannot be made anywhere else.
    The unit suite grades the gate against 60 recorded postings and a fixed set
    of profiles; the browser walk drives one posting at a time. Neither one
    sweeps the corpus the developer actually has in front of them, and none of
    them can check what happens to a *real* profile row when the answer changes.

      1. **An empty profile blocks nobody.** Zero `ineligible`, as an equality,
         over every seeded posting. A13's worst output is a wrong `ineligible`,
         and a person who has typed nothing has contradicted nothing — so every
         block against them is wrong by construction. Task 7 asserted this
         against the answer key; this asserts it against live data, which is the
         only place a bad reading of a real description can show up.
      2. **No verdict without its breakdown (I4).** A state with nothing under
         it is a bare number with extra letters.
      3. **Every unknown names a field the profile actually has, or names
         none.** The dead-end guard: "tell us your years of experience" beside a
         profile with nowhere to say it is M2c's 404'ing provenance link one
         milestone on, and a null `profile_field` is now a legitimate answer, so
         the check has to allow exactly that one and no other miss.
      4. **The verdict follows the profile and is stored nowhere.** Changing a
         column changes the answer to the same URL, and putting the column back
         restores the previous payload byte for byte. No worker runs and no
         cache is cleared in between (ADR 0017).

    **It writes to the developer's own profile**, which only
    `check_profile_confirmation` otherwise does, and it restores the six columns
    it touched. The limit is stated rather than implied: killed mid-run, the
    profile keeps this function's values and nothing on disk remembers what
    preceded them. Six columns on a single-user development database, and the
    honest mitigation is that it is written down.
    """
    print("\nthe eligibility gate")

    code, before = get_json("/profile")
    if code != 200 or not isinstance(before, dict):
        check(False, "the profile is readable", f"HTTP {code}")
        return
    missing = [field for field in GATE_FIELDS if field not in before]
    if not check(
        not missing,
        "the profile carries every field the gate reads",
        ", ".join(missing) if missing else f"{len(GATE_FIELDS)} fields",
    ):
        return
    snapshot = {field: before[field] for field in GATE_FIELDS}

    try:
        # -- 1. the day-one user, against every seeded posting ---------------
        code, _ = send_json("/profile", "PATCH", EMPTY_PROFILE)
        if not check(code == 200, "the gate fields can be cleared", f"HTTP {code}"):
            return

        corpus = _corpus_verdicts()
        if not check(len(corpus) > 0, "the corpus has postings to judge", f"{len(corpus)} read"):
            return

        judged = [job for job in corpus if job.get("eligibility") is not None]
        unread = [job for job in corpus if job.get("eligibility") is None]
        check(
            all(not job.get("requirements") for job in unread),
            "a posting with no verdict is a posting with nothing extracted from it",
            f"{len(judged)} judged, {len(unread)} unread",
        )

        states = [job["eligibility"]["state"] for job in judged]
        tally = ", ".join(
            f"{state} {states.count(state)}" for state in sorted(set(states))
        )
        check(
            states.count("ineligible") == 0,
            "invariant A13: an empty profile is blocked from nothing",
            tally,
        )
        # The opposite failure, and the reason the line above is not enough on
        # its own: a gate answering `uncertain` to everything satisfies it,
        # forever, having decided nothing (`matching.md` §3.3).
        check(
            len(set(states)) > 1,
            "the corpus reaches more than one state",
            tally,
        )

        # -- 2 and 3, over both profiles -------------------------------------
        code, _ = send_json("/profile", "PATCH", BLOCKED_PROFILE)
        if not check(code == 200, "the gate fields can be set", f"HTTP {code}"):
            return
        blocked_corpus = _corpus_verdicts()
        blocked_judged = [j for j in blocked_corpus if j.get("eligibility") is not None]
        blocked_states = [job["eligibility"]["state"] for job in blocked_judged]
        check(
            blocked_states.count("ineligible") > 0,
            "a profile that contradicts a stated bar is blocked by it",
            ", ".join(
                f"{state} {blocked_states.count(state)}" for state in sorted(set(blocked_states))
            ),
        )

        bare: list[str] = []
        dead_ends: list[str] = []
        unquoted: list[str] = []
        drifted: list[str] = []
        for job in judged + blocked_judged:
            verdict = job["eligibility"]
            hard = [b for b in verdict["blockers"] if b["outcome"] == "blocks"]
            soft = [b for b in verdict["blockers"] if b["outcome"] == "soft_blocks"]
            if verdict["state"] in ("ineligible", "likely_ineligible") and not (hard or soft):
                bare.append(f"{job['title']}: {verdict['state']} with no blocker")
            if verdict["state"] == "uncertain" and not verdict["unknowns"]:
                bare.append(f"{job['title']}: uncertain with no unknown")
            if verdict["state"] == "eligible" and verdict["blockers"]:
                bare.append(f"{job['title']}: eligible with a blocker")
            if not verdict["gate_version"]:
                bare.append(f"{job['title']}: no gate version")

            for unknown in verdict["unknowns"]:
                field = unknown["profile_field"]
                # `None` is the answer for a dimension no field could settle —
                # "or equivalent experience". Anything else must be a column the
                # person can actually reach.
                if field is not None and field not in before:
                    dead_ends.append(f"{job['title']}: asks for {field!r}")
                if not unknown["why"].strip():
                    bare.append(f"{job['title']}: an unknown with no reason")

            text = job.get("description_text") or ""
            for blocker in verdict["blockers"]:
                if blocker["posting_says"] is None:
                    unquoted.append(f"{job['title']}: {blocker['dimension']}")
                    continue
                # `char_start`/`char_end` on the wire, not the domain object's
                # `posting_span` tuple — `EligibilityBlockerOut` flattens it, the
                # same shape `job_requirements` already uses. The first draft of
                # this loop read `posting_span` and raised `KeyError` on its
                # first ever run, which is the whole argument for this file
                # existing beside a passing unit suite.
                start, end = blocker["char_start"], blocker["char_end"]
                if start is None or end is None or text[start:end] != blocker["posting_says"]:
                    drifted.append(f"{job['title']}: {blocker['dimension']}")

        check(not bare, "invariant I4: no verdict without its breakdown", "; ".join(bare[:3]))
        check(
            not dead_ends,
            "every unknown names a profile field that exists, or names none",
            "; ".join(dead_ends[:3]),
        )
        check(
            not unquoted,
            "every blocker quotes the posting",
            "; ".join(unquoted[:3]),
        )
        check(
            not drifted,
            "every blocker's quote is the text its span points at",
            "; ".join(drifted[:3]) if drifted else "checked against description_text",
        )

        # -- 4. computed on read, stored nowhere ------------------------------
        subject = next(
            (j for j in blocked_judged if j["eligibility"]["state"] == "ineligible"),
            blocked_judged[0] if blocked_judged else None,
        )
        if subject is None:
            check(False, "a posting exists to re-read")
            return
        path = f"/jobs/{subject['id']}"
        _, again = get_json(path)
        check(
            again["eligibility"] == subject["eligibility"],
            "the same request twice gives the same verdict",
            subject["eligibility"]["state"],
        )

        send_json("/profile", "PATCH", EMPTY_PROFILE)
        _, cleared = get_json(path)
        check(
            cleared["eligibility"]["state"] != subject["eligibility"]["state"],
            "clearing the profile changes the answer to the same URL",
            f"{subject['eligibility']['state']} -> {cleared['eligibility']['state']}",
        )

        send_json("/profile", "PATCH", BLOCKED_PROFILE)
        _, restored = get_json(path)
        check(
            restored["eligibility"] == subject["eligibility"],
            "and putting it back restores the verdict exactly",
            "no worker ran, no cache was cleared (ADR 0017)",
        )
    finally:
        code, _ = send_json("/profile", "PATCH", snapshot)
        _, final = get_json("/profile")
        check(
            code == 200 and all(final.get(f) == snapshot[f] for f in GATE_FIELDS),
            "the profile is left as it was found",
            "nothing is left behind",
        )


def port_is_taken() -> bool:
    """Is something already listening where this script is about to start a server?

    **This function exists because its absence cost a whole verification run.**
    On 2026-08-09 a `uvicorn` started by hand on 2026-08-05 was still holding
    port 8000. This script launched its own, that one died instantly with
    `[Errno 48] Address already in use` — into `DEVNULL`, so silently —
    `wait_for_api` got a healthy `/health` from the squatter, and 73 checks
    passed **against code that was three days old**. Two of them were newly
    written that morning and could not have passed against the running binary.

    `CLAUDE.md` §4 states the rule as a habit for humans: verify from a clean
    shell, because a server you started an hour ago makes a broken target look
    like a passing one. A habit is not a guard. This is the guard.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        return probe.connect_ex((HOST, int(PORT))) == 0


def wait_for_api(process: subprocess.Popen[bytes], deadline_seconds: float = 45.0) -> bool:
    """Wait for *this* process's API, and give up the moment it is not this one.

    The `process.poll()` line is the second half of `port_is_taken`'s lesson and
    the more general half: the port check refuses a squatter that is already
    there, and this refuses one that appears — or, far more likely, catches our
    own server dying for any reason at all while a stale one answers in its
    place. Polling `/health` alone cannot tell the two apart, because `/health`
    does not say who is serving it.
    """
    started = time.monotonic()
    while time.monotonic() - started < deadline_seconds:
        if process.poll() is not None:
            print(f"  {RED}✗{RESET} the API this script started exited with {process.returncode}")
            return False
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
            "no job_locations row carries coordinates",
            # Reworded at M4a. This said "nothing is geocoded yet", which was
            # true through M3 and stopped being true the moment a geocoder
            # existed. The number is still 0, and now for a stronger reason
            # worth guarding: `city.md` §4.4 decided that a job inheriting its
            # employer's office is a read-time join, never a stored row, so
            # `load_offices` writes to `company_locations` and never here.
            # A non-zero value means something started materialising a
            # placement the posting itself never claimed.
            "the loader writes offices, not job locations (city.md §4.4)",
        )
        confidence = stats.get("location_confidence", {})
        check(
            confidence.get("verified") == 0 and confidence.get("approximate") == 0,
            "no job location claims verified or approximate precision",
            str(confidence),
        )


async def check_job_requirements() -> None:
    """M3a over HTTP and then over the database: what a posting requires.

    Two halves, because the milestone makes two different claims and only one of
    them is reachable through the API. The read half asks `/jobs/{id}` and checks
    the response is internally consistent — every span quoting the description
    sent beside it. The write half changes a description and checks the rows
    follow it, which no endpoint exposes and which is the property most likely to
    rot: a span is an offset, and the text it indexes into is written by every
    re-poll.

    Compared **before and after** throughout, for the reason `check_daily_queue`
    records: asserting "this job has four requirements" would pass vacuously on a
    fresh database and fail on a developer's own.

    **It leaves nothing behind.** The description it edits is written back and
    the requirements re-derived, then the resulting rows are compared as a set
    against the ones it found. Row ids change — they are derived rows and are
    replaced wholesale — so the comparison is on (kind, value, span), which is
    what "unchanged" means for this table.
    """
    print("\nwhat a posting requires")

    status_code, jobs = get_json("/jobs?limit=100&status=open")
    if not (status_code == 200 and isinstance(jobs, dict) and jobs.get("items")):
        check(False, "the corpus has jobs to read", f"HTTP {status_code}")
        return

    # Not simply the first posting with any requirements. The first run of this
    # check picked one whose three rows were all `mentioned`, and the
    # necessity assertion below then read "0 required, 0 preferred" — a green
    # tick for a comparison with nothing on either side. Prefer a posting that
    # can actually fail it, and print the mix either way so a vacuous case is
    # visible in the output rather than hidden by a passing line.
    detail = None
    best = -1
    for item in jobs["items"]:
        code, body = get_json(f"/jobs/{item['id']}")
        if code != 200 or not body.get("requirements"):
            continue
        kinds = {r["necessity"] for r in body["requirements"]}
        score = len(kinds & {"required", "preferred"}) * 100 + len(body["requirements"])
        if score > best:
            detail, best = body, score
        if kinds >= {"required", "preferred"}:
            break

    if detail is None:
        check(False, "a seeded posting states requirements", "none of the corpus does")
        return
    mix = ", ".join(
        f"{n} {necessity}"
        for necessity in ("required", "preferred", "mentioned")
        if (n := sum(1 for r in detail["requirements"] if r["necessity"] == necessity))
    )
    check(True, "the job detail answers", f"HTTP 200, {mix}")

    check(
        bool(detail["requirements_extractor_version"]),
        "requirements carry an extractor version",
        str(detail["requirements_extractor_version"]),
    )

    # The response must be internally consistent. Checking the row against the
    # database would test the trigger; checking it against the description in
    # the same payload tests what the browser actually highlights.
    text = detail["description_text"] or ""
    drifted = [
        row
        for row in detail["requirements"]
        if text[row["char_start"] : row["char_end"]] != row["raw_text"]
    ]
    check(
        not drifted,
        "every span quotes the description it points at",
        f"{len(detail['requirements'])} spans" if not drifted else f"{len(drifted)} drifted",
    )

    required = {r["value"] for r in detail["requirements"] if r["necessity"] == "required"}
    preferred = {r["value"] for r in detail["requirements"] if r["necessity"] == "preferred"}
    # A value under both headings is the posting's own doing and proves nothing.
    # What must not happen is a row claiming both necessities at once.
    both = {
        (r["value"], r["char_start"])
        for r in detail["requirements"]
        if r["necessity"] == "required"
    } & {
        (r["value"], r["char_start"])
        for r in detail["requirements"]
        if r["necessity"] == "preferred"
    }
    check(
        not both,
        "no single span is both required and preferred",
        f"{len(required)} required, {len(preferred)} preferred",
    )

    sys.path.insert(0, str(API_DIR))
    from sqlalchemy import text as sql  # noqa: PLC0415

    from nightshift.db.session import dispose_engine, get_engine  # noqa: PLC0415

    engine = get_engine()
    job_id = detail["id"]

    async def rows() -> set[tuple[str, str, int, int]]:
        async with engine.begin() as connection:
            result = await connection.execute(
                sql(
                    "SELECT kind::text, value, char_start, char_end FROM job_requirements "
                    "WHERE job_id = :job_id"
                ),
                {"job_id": job_id},
            )
            return {(k, v, s, e) for k, v, s, e in result.all()}

    before = await rows()

    async with engine.begin() as connection:
        original = (
            await connection.execute(
                sql("SELECT description_text FROM jobs WHERE id = :job_id"), {"job_id": job_id}
            )
        ).scalar_one()
        await connection.execute(
            sql("UPDATE jobs SET description_text = :new WHERE id = :job_id"),
            {"new": "REQUIREMENTS Proficiency in Python.", "job_id": job_id},
        )

    # The trigger fires on that UPDATE and clears the rows. Asserted on its own,
    # because "replaced" and "cleared then refilled" are different guarantees and
    # only the second one leaves no window where a span points at moved text.
    cleared = await rows()
    check(
        not cleared,
        "changing the description clears the old requirements",
        f"{len(before)} -> {len(cleared)}",
    )

    from nightshift.db.models import Job  # noqa: PLC0415
    from nightshift.db.session import session_scope  # noqa: PLC0415
    from nightshift.domain.ingestion import sync_requirements  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    async with session_scope() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        await sync_requirements(session, job)
        await session.commit()

    replaced = await rows()
    check(
        bool(replaced) and replaced != before,
        "a description change replaces the requirements",
        f"{len(before)} -> {len(replaced)}",
    )

    async with session_scope() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        job.description_text = original
        await session.flush()
        await sync_requirements(session, job)
        await session.commit()

    after = await rows()
    check(
        after == before,
        "the job is left as it was found",
        "nothing is left behind" if after == before else f"{len(before)} -> {len(after)}",
    )

    await dispose_engine()


async def check_match_results() -> None:
    """M3c over HTTP and then over the database: the score, and what it rests on.

    Four claims, and none of them is reachable from the unit suite, the component
    tests or the browser walk:

      1. **`matching.md` §7.2, as an equality over every stored row.** Every
         `match_evidence.job_span_text` is the literal text at the offsets it
         recorded, in the field it named; every `user_span_text` is a literal
         substring of a *confirmed* record — a `user_skills.name` or a
         `user_projects.evidence` — and never of `resume_extractions`, which
         holds proposals. The unit suite asserts this about what the scorer
         returns. This asserts it about what is in the table, which is where a
         description edited after a score, or a row somebody inserted by hand,
         would show up. §7.2 is explicit that it is not a rate: one violation
         fails.
      2. **No stored row was proposed by an embedding** (ADR 0018), asserted
         against the whole corpus rather than against a fixture pair.

         **Its reach is smaller than it looks and the limit is worth stating.**
         Every check above this one edits a profile column or a confirmed skill,
         each of which deletes every `match_result` row, so by the time this runs
         the only rows in the table are the ones it rescored itself moments
         earlier. It therefore asserts that *the scorer, over 31 real postings,
         stores no such row* — and it cannot catch one somebody inserted by hand,
         which the database will accept: a fabricated **span** is refused by a
         trigger on INSERT and on UPDATE, and a fabricated **source** is refused
         by nothing but this code. Both halves were probed directly to find that
         out (M3c review §2).
      3. **I4 against live rows.** Six component assessments per score, a total
         that is its own parts, a `penalty_score` that is the sum of the
         penalties beneath it, and no positive component without evidence.
      4. **ADR 0019: the score is stored, and a profile change withdraws it.**
         This is the exact opposite of `check_eligibility_gate`'s last three
         lines and the pairing is the point — a verdict is recomputed on read
         and a score is not, so the only honest thing to do with a score whose
         inputs moved is to delete it. Editing a scoring-relevant column empties
         the table and `/jobs/{id}` reports `match: null`; editing a display name
         leaves every row alone; the sweep puts back exactly what it removed.

    **It writes to the developer's own profile and to `match_results`**, and it
    restores both — the profile columns from a snapshot, the scores by running
    the same `recompute_pending` the ARQ cron calls. The limit is the one
    `check_eligibility_gate` states: killed mid-run, the profile keeps this
    function's values. The scores are safe either way, because they are derived
    and `make seed` recomputes them.

    Ordered last in `main` deliberately. Everything above it that touches a
    profile column or a confirmed skill invalidates every score on the way past
    — `check_profile_confirmation` does it twice — so a scoring check anywhere
    else in the list would be reading a table something after it was about to
    empty.
    """
    print("\nthe score, and what it rests on")

    sys.path.insert(0, str(API_DIR))
    from sqlalchemy import text as sql  # noqa: PLC0415

    from nightshift.db.session import (  # noqa: PLC0415
        dispose_engine,
        get_engine,
        session_scope,
    )

    engine = get_engine()

    def ranked_now() -> dict[str, tuple[int, int, str]]:
        """Every scored posting's number, keyed by posting. One request."""
        _, body = get_json("/matches?limit=200")
        return {
            row["job"]["id"]: (
                row["match"]["overall_score"],
                row["match"]["assessed_out_of"],
                row["match"]["eligibility_status"],
            )
            for band in body["bands"]
            for row in band["items"]
        }

    async def score_count() -> int:
        """How many scores **this account** has.

        Scoped to `USER_ID` since M5b. `make seed` plants two accounts, so an
        unscoped count is 64 where the checks below mean 32 — and "editing a
        scoring input withdraws every score" would read as a failure because
        the *other* person's scores are, correctly, still there.
        """
        async with engine.begin() as connection:
            return int(
                (
                    await connection.execute(
                        sql("SELECT count(*) FROM match_results WHERE user_id = :user_id"),
                        {"user_id": USER_ID},
                    )
                ).scalar_one()
            )

    code, before_profile = get_json("/profile")
    if code != 200 or not isinstance(before_profile, dict):
        check(False, "the profile is readable", f"HTTP {code}")
        await dispose_engine()
        return
    snapshot = {field: before_profile[field] for field in GATE_FIELDS}
    display_name = before_profile.get("display_name")
    #: Filled once the corpus has been scored, and compared against again in the
    #: `finally` — §7.1's ranking-stability row, asserted against a running stack
    #: rather than against a golden file. The golden test proves the *scorer* is
    #: deterministic; this proves that deleting every row and computing them
    #: again from the same profile lands on the same numbers, which is the thing
    #: a person actually does when they edit a field and change it back.
    as_found: dict[str, tuple[int, int, str]] = {}

    try:
        # Everything before this point in `main` has changed a profile column or
        # a confirmed skill at least once, so the table is empty by now. Putting
        # it back is this check's first act rather than an assumption.
        await rescore_corpus()
        # Counted per account, not taken from the sweep's return value. The
        # sweep reports pairs scored **across every user**, and `make seed`
        # plants two — so on the first sweep it reports both people's work and
        # on a later one only this person's. Comparing those two numbers is
        # what made "the sweep rebuilds what the edit removed" fail at M5b,
        # with nothing wrong except the arithmetic.
        restored = await score_count()
        if not check(restored > 0, "the corpus scores", f"{restored} pair(s) scored"):
            return

        # -- 1. the ranked list, and the order it claims ---------------------
        code, ranking = get_json("/matches?limit=200")
        if code != 200 or not isinstance(ranking, dict):
            check(False, "/matches returns a ranking", f"HTTP {code}")
            return
        bands = ranking["bands"]
        tally = ", ".join(f"{b['state']} {len(b['items'])}" for b in bands if b["items"])
        check(ranking["total"] > 0, "the ranking has postings in it", tally)
        check(
            ranking["not_yet_scored"] == 0,
            "every open posting is scored",
            f"{ranking['not_yet_scored']} not yet scored",
        )

        # **The key is read off the response, never assumed.** This check asserted
        # a plain descending `fraction` until M3d Task 7 found it red: Task 6 had
        # changed the ordering to the coverage-weighted one and moved on, and
        # `make acceptance` was failing on a correct list. Reading `ordering`
        # first means the next change to the sort turns this into a loud refusal
        # rather than a wrong assertion about a right answer.
        check(
            ranking["ordering"] == "coverage_weighted_fraction",
            "the list says what it is sorted by",
            ranking["ordering"],
        )

        from nightshift.domain.scoring import coverage_weighted_fraction  # noqa: PLC0415

        def rank_key(row: dict[str, Any]) -> float | None:
            """`matching.md` §5.3's key, applied to the two numbers on the wire.

            Recomputed from the response rather than trusted, which is the point:
            the displayed `fraction` and the ordering key are deliberately
            different, so a 17% can sit above a 30% and only this arithmetic can
            tell that apart from a broken list.

            **The arithmetic is imported, not restated.** M3d Task 7 wrote it out
            here a second time and Task 8 found a third copy in the ranking-quality
            grader that had been a whole task out of date. One definition, called
            by everything that is not SQL.
            """
            return coverage_weighted_fraction(
                row["match"]["overall_score"], row["match"]["assessed_out_of"]
            )

        def tied(earlier: float, later: float) -> bool:
            """Two float pipelines computing one quantity, held to a tie.

            The list is ordered by Postgres evaluating
            `overall / (sqrt(assessed_out_of) * 10)`; this check re-derives the
            same quantity from the wire through `coverage_weighted_fraction`,
            which spells it `fraction * sqrt(assessed_out_of / 100)`. The two
            are algebraically identical and are **not** bit-identical, because
            they round in a different order.

            Found on 2026-08-19, when the seeded corpus gained a 15-of-90 pair
            beside an existing 10-of-40 one. Both are exactly 1/(2*sqrt(10)).
            Postgres makes them equal to the last bit and orders them either
            way, correctly; Python makes them differ by one unit in the last
            place, and a strict comparison read that as a broken list.

            The tolerance is 1e-12 relative — roughly ten thousand times the
            error two double pipelines can accumulate on this expression, and
            roughly a billionth of the smallest gap between two genuinely
            different keys this corpus produces. A real inversion is nowhere
            near it.
            """
            return math.isclose(earlier, later, rel_tol=1e-12, abs_tol=1e-15)

        misordered: list[str] = []
        for band in bands:
            keys = [rank_key(row) for row in band["items"]]
            # `None` sorts last and is never compared as a number — a pair
            # nothing could be assessed on is not a pair that scored zero.
            ranked = [key for key in keys if key is not None]
            # Pairwise rather than `!= sorted(...)`: a tie is ordered either
            # way and both ways are right, and only a pairwise walk can tell a
            # tie from an inversion.
            if any(
                later > earlier and not tied(earlier, later)
                for earlier, later in zip(ranked, ranked[1:], strict=False)
            ):
                misordered.append(band["state"])
            if any(key is None for key in keys) and ranked != [
                key for key in keys[: len(ranked)] if key is not None
            ]:
                misordered.append(f"{band['state']}: an unassessed row sorts above a scored one")
        check(
            not misordered,
            "each band is ordered on the key the list says it uses",
            "; ".join(misordered[:3]),
        )

        # Non-vacuity for the check above: on a corpus where every denominator
        # was 100 the coverage weighting is the identity, and the assertion would
        # pass for the ordering it was written to replace.
        printed = [
            row["match"]["fraction"]
            for band in bands
            for row in band["items"]
            if row["match"]["fraction"] is not None
        ]
        check(
            printed != sorted(printed, reverse=True),
            "the printed share really is not the sort key (M3d Task 6)",
            f"{len({row['match']['assessed_out_of'] for b in bands for row in b['items']})}"
            " distinct denominators across the bands",
        )

        # The claim above is only worth making if this corpus can distinguish
        # the two orderings. `assessed_out_of` varies here — 20, 30, 40, 50, 90,
        # 100 — so sorting on `overall_score` gives a different answer, and
        # saying so in the output stops a green tick standing for a comparison
        # with one possible result.
        rows = [row for band in bands for row in band["items"]]
        by_fraction = [
            r["job"]["id"] for r in rows if r["match"]["fraction"] is not None
        ]
        by_total = [
            r["job"]["id"]
            for r in sorted(
                (r for r in rows if r["match"]["fraction"] is not None),
                key=lambda r: -r["match"]["overall_score"],
            )
        ]
        check(
            by_fraction != by_total,
            "sorting on the fraction is not the same as sorting on the total",
            f"{len({r['match']['assessed_out_of'] for r in rows})} distinct denominators",
        )

        # -- 2. the two surfaces agree ---------------------------------------
        subject = max(
            (r for r in rows if r["match"]["fraction"] is not None),
            key=lambda r: r["match"]["fraction"],
            default=None,
        )
        if subject is None:
            check(False, "a scored posting exists to open")
            return
        code, detail = get_json(f"/jobs/{subject['job']['id']}")
        listed, opened = subject["match"], detail.get("match")
        check(
            opened is not None
            and (opened["overall_score"], opened["assessed_out_of"], opened["ruleset_version"])
            == (listed["overall_score"], listed["assessed_out_of"], listed["ruleset_version"]),
            "the ranked row and the job detail report one score",
            f"{listed['overall_score']} of {listed['assessed_out_of']}",
        )

        # -- 3. I4 against every stored row -----------------------------------
        bare: list[str] = []
        for row in rows:
            match = row["match"]
            title = row["job"]["title"]
            components = match["components"]
            if len(components) != 6:
                bare.append(f"{title}: {len(components)} components, not 6")
            if match["overall_score"] != max(
                0, sum(c["points"] for c in components) + match["penalty_score"]
            ):
                bare.append(f"{title}: the total is not its parts")
            if match["penalty_score"] != sum(p["points"] for p in match["penalties"]):
                bare.append(f"{title}: the penalty total is not its penalties")
            for component in components:
                if component["points"] > 0 and not component["evidence"]:
                    bare.append(f"{title}: {component['component']} scored with no evidence")
                if not component["assessable"] and component["points"] != 0:
                    bare.append(f"{title}: {component['component']} scored while unassessable")
                if not component["why"].strip():
                    bare.append(f"{title}: {component['component']} has no sentence")
            if not match["ruleset_version"]:
                bare.append(f"{title}: no ruleset version")
        check(
            not bare,
            "invariant I4: no score without its breakdown",
            "; ".join(bare[:3]) if bare else f"{len(rows)} scores decomposed",
        )

        # -- 4. §7.2, as an equality over the table ---------------------------
        async with engine.begin() as connection:
            evidence = (
                await connection.execute(
                    sql(
                        "SELECT e.component::text, e.job_span_field::text, e.job_span_text, "
                        "       e.job_char_start, e.job_char_end, e.user_span_text, "
                        "       e.proposed_by::text, j.title, j.description_text "
                        "FROM match_evidence e "
                        "JOIN match_results m ON m.id = e.match_result_id "
                        "JOIN jobs j ON j.id = m.job_id"
                    )
                )
            ).all()
            confirmed = (
                await connection.execute(
                    sql(
                        "SELECT name FROM user_skills "
                        "UNION ALL SELECT evidence FROM user_projects WHERE evidence IS NOT NULL "
                        "UNION ALL SELECT name FROM user_projects "
                        # `preferred_roles` is the user span the role component
                        # quotes and `preferred_locations` feeds the location
                        # one. Both are JSONB arrays of strings a person typed,
                        # so they are confirmed records in exactly §7.2's sense.
                        "UNION ALL SELECT jsonb_array_elements_text(preferred_roles) FROM users "
                        "UNION ALL SELECT jsonb_array_elements_text(preferred_locations) FROM users"
                    )
                )
            ).scalars().all()

        check(len(evidence) > 0, "the corpus produced evidence rows", f"{len(evidence)} rows")
        drifted: list[str] = []
        unconfirmed: list[str] = []
        for component, field, span, start, end, user_span, proposed_by, title, body in evidence:
            if span is not None:
                text = title if field == "title" else (body or "")
                if start is None or end is None or text[start:end] != span:
                    drifted.append(f"{title}: {component} quotes {span!r}")
            if user_span is not None and not any(user_span in row for row in confirmed):
                unconfirmed.append(f"{title}: {component} quotes {user_span!r}")
        # Read-time re-assertion of something the database already enforces on
        # write. Kept because the two guards fail differently: the trigger reads
        # `jobs.description_text` as it is at INSERT, and this reads it as the
        # API serves it now. A probe confirmed the trigger refuses both a
        # rewritten span and moved offsets, so this line is a second opinion
        # rather than the only one.
        check(
            not drifted,
            "every job span is the text at the offsets it recorded (§7.2)",
            "; ".join(drifted[:3]) if drifted else f"{sum(1 for r in evidence if r[2])} job spans",
        )
        check(
            not unconfirmed,
            "every user span quotes a confirmed record, never a proposal (§7.2)",
            "; ".join(unconfirmed[:3])
            if unconfirmed
            else f"{sum(1 for r in evidence if r[5])} user spans",
        )
        proposed = sorted({row[6] for row in evidence})
        check(
            "embedding" not in proposed,
            "the scorer stored no evidence row proposed by an embedding (ADR 0018)",
            ", ".join(proposed),
        )

        # -- 5. ADR 0019: stored, and withdrawn when its inputs move ----------
        as_found = ranked_now()
        stored_before = await score_count()
        code, _ = send_json("/profile", "PATCH", {"display_name": "verify.py"})
        check(
            code == 200 and await score_count() == stored_before,
            "editing a display name withdraws no score",
            f"{stored_before} rows",
        )
        send_json("/profile", "PATCH", {"display_name": display_name})

        code, _ = send_json("/profile", "PATCH", {"years_experience": 12})
        emptied = await score_count()
        check(
            code == 200 and emptied == 0,
            "editing a scoring input withdraws every score",
            f"{stored_before} -> {emptied}",
        )
        code, withdrawn = get_json(f"/jobs/{subject['job']['id']}")
        check(
            withdrawn.get("match") is None,
            "and the posting reads as not-yet-scored, never as a stale number",
            "ADR 0019",
        )
        code, empty_ranking = get_json("/matches?limit=200")
        check(
            empty_ranking["total"] == 0 and empty_ranking["not_yet_scored"] > 0,
            "the ranked list counts them as unscored rather than dropping them",
            f"{empty_ranking['not_yet_scored']} awaiting the sweep",
        )

        await rescore_corpus()
        again = await score_count()
        code, rescored = get_json(f"/jobs/{subject['job']['id']}")
        check(
            again == restored and rescored.get("match") is not None,
            "the sweep rebuilds what the edit removed",
            f"{again} of this account's pair(s) rescored",
        )

        # And the sweep really read the new profile, rather than rebuilding the
        # same numbers regardless.
        #
        # Asserted over the corpus and not over the posting opened above, which
        # is what the first version of this line did — it picked the
        # highest-scoring pair, that posting states no years minimum, and twelve
        # years is correctly no answer at all to a question nobody asked. The
        # check went red on its first run for a reason that was not a defect,
        # which is its own kind of wrong assertion: a claim about the profile
        # being read has to be made where the profile is read.
        with_twelve_years = ranked_now()
        moved = [
            job_id for job_id, before in as_found.items() if with_twelve_years.get(job_id) != before
        ]
        check(
            len(moved) > 0,
            "twelve years of experience is a different answer to the corpus",
            f"{len(moved)} of {len(as_found)} postings moved",
        )
    finally:
        code, _ = send_json("/profile", "PATCH", snapshot)
        _, final = get_json("/profile")
        put_back = await rescore_corpus()
        check(
            code == 200
            and all(final.get(f) == snapshot[f] for f in GATE_FIELDS)
            and put_back > 0,
            "the profile and the scores are left as they were found",
            f"{put_back} pair(s) rescored, nothing left behind",
        )
        if as_found:
            # §7.1's stability row, on a stack. Every score in the corpus was
            # deleted twice and recomputed twice between here and where
            # `as_found` was taken, from a profile put back to the same values —
            # so the same numbers are the only acceptable answer.
            again = ranked_now()
            differing = [job_id for job_id, row in as_found.items() if again.get(job_id) != row]
            check(
                not differing,
                "and the same profile scores the same corpus identically (§7.1)",
                f"{len(as_found)} postings, {len(differing)} differ",
            )
        await dispose_engine()


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

    # Refused rather than reused. A server already on this port is not this
    # script's server, nothing here knows what code it is running, and the one
    # time that was allowed to slide it was three days stale. Naming the process
    # in the message, because "port in use" without a PID sends the reader to a
    # search engine and `lsof` sends them to the answer.
    if port_is_taken():
        print(f"  {RED}✗{RESET} something is already listening on {BASE}")
        print(f"    {DIM}this script starts its own API and will not verify somebody else's.{RESET}")
        print(f"    {DIM}find it with:  lsof -nP -iTCP:{PORT} -sTCP:LISTEN{RESET}")
        return 1

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
        if not wait_for_api(api):
            print(f"  {RED}✗{RESET} API did not start within 45s")
            return 1
        # First, because every check after it needs a session (ADR 0037), and a
        # failure here should say so once rather than forty times.
        if not sign_in():
            print(f"    {DIM}every check below needs a session; stopping here.{RESET}")
            return 1
        verify_http()
        check_application_tracking()
        check_profile_confirmation()
        asyncio.run(check_daily_queue())
        check_city_placement()
        check_eligibility_gate()
        asyncio.run(check_job_requirements())
        asyncio.run(verify_constraints())
        # Last, and the docstring says why: everything above it invalidates
        # scores on its way past, so this is the only position from which it is
        # reading a table nothing is about to empty.
        asyncio.run(check_match_results())
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
