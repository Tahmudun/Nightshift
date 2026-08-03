# M2c — profile and resume: proposals with spans, promoted only by a click

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person pastes or uploads their resume, sees exactly what the system read out of it, and confirms fact by fact which of those claims are true — and nothing that was not confirmed ever reaches their profile.

**Architecture:** Two sets of tables (`command-center.md` §2.2). `resume_extractions` holds *proposals*: "this file appears to say you graduate May 2027, at characters 214–229". `users` / `user_skills` / `user_projects` hold only what a human confirmed. Promotion is a write across the boundary performed by exactly one module, so **no bug in the extractor can produce a confirmed fact — the extractor cannot reach those tables at all.** It cannot even import them; a test asserts that. Every proposal carries `char_start`, `char_end` and `quoted_text`, and a database trigger refuses any row whose span does not literally quote the resume text, so the highlight and the claim cannot disagree.

**Tech Stack:** PostgreSQL 16 (enums, check constraints, a span-integrity trigger), SQLAlchemy 2.0 async, Alembic, FastAPI, Pydantic v2, `pypdf` (new), `python-multipart` (new), Next.js App Router, TanStack Query, Zod, Playwright.

**Design:** `docs/architecture/command-center.md` §2.2, §6 and §8. Read those three first — §6 decides that the extractor is rules-based and that every proposal points at literal words, and that decision is not this plan's to revisit.

**Input formats were decided by the human on 2026-08-03:** paste, PDF, and `.txt`. `.docx` is not supported and the upload control names it as unsupported rather than silently rejecting it.

## Global Constraints

- **I2 — never fabricate a user qualification.** This is the invariant the whole slice exists to serve. Nothing in `users`, `user_skills` or `user_projects` may be written by any path other than `domain/profile.py`, called from a route the user's click reached. Task 5 proves it with a source-level guard, mutation-checked.
- **I2, structurally** — a proposal with no span is unrepresentable (`NOT NULL` on both bounds), and a proposal whose span does not quote the text is refused by a trigger.
- **I1 — never fabricate precision.** A resume that says "May 2027" yields a year and a month. It does not yield a day. `users` therefore has `graduation_year` and `graduation_month`, not §6.1's `graduation_date`. See Task 4 and ADR 0013.
- **I5 — never take an irreversible action for the user.** Confirming is the user's click. The system proposes, highlights, and waits.
- **I7 — never let a mock become the product.** An extraction that proves nothing says so and hands over the manual form. It never populates a field to look successful.
- **I6** — "the code exists" is not evidence. Task 11 records measured output per criterion in `docs/PROGRESS.md`.
- **A3** — no auth until M5, and nothing may assume one user. Every query in this slice filters on `user_id` from `api/deps.py`.
- **A9 — $0 and no API keys.** `pypdf` and `python-multipart` are pure-Python, MIT/Apache, offline. `make demo` must still work with no network. Add both to `docs/architecture/costs.md` in Task 1.
- **Python** — full type annotations, mypy strict clean, ruff clean. Pydantic models at every boundary. Nothing outside `adapters/http.py` imports `httpx`.
- **TypeScript** — strict, no `any`. Every API response parsed through Zod before it reaches a component. Named exports. Colocated `*.test.ts`.
- **Colour** — `paper*` tokens are text, `ink*` tokens are surfaces and never carry text. A new colour token requires a new assertion in `colour-contrast.test.ts`. The highlight styles in Task 9 are text on a surface and need those assertions.
- **Migrations** — reversible and tested both directions. `alembic check` must report no drift once the model and the migration are both in.
- **Time** — `TIMESTAMPTZ` in the database, UTC always, converted at the edge only.
- **TODOs** — must carry a milestone: `TODO(M3): ...`. A bare `TODO` fails lint.
- **Commits** — conventional and scoped, one per task. Run `make check` before each.
- **Before pushing, run three commands, not two.** `make check`, `make acceptance`, **and `make test-e2e`**. The degraded suite needs the API *down*, which is the opposite stack state from acceptance, so neither aggregate target can run it. M2a shipped a red CI run by forgetting this.
- **Personal data.** Uploaded bytes are read in memory and **never written to disk or to the database** — the row keeps the filename, a content hash, and the extracted text. Committed fixture resumes describe invented people. PRODUCT-SPEC §13 applies to every row in this slice.

---

## What this slice deliberately does not build

Name these in the UI rather than hiding them, and repeat them in PROGRESS:

| Not built | Why | Where it lands |
|---|---|---|
| `.docx` upload | A second parser in the slice that already carries the most invariant risk. The upload control names it, with paste offered as the route around it | Unscheduled; a paste covers it today |
| Storing the uploaded file | We need the text, not the bytes. Not storing them is the smallest honest footprint for the only genuinely personal data in M2 (§13) | Never, unless a feature needs the original |
| `user_skills.confidence` (§6.2) | A confirmed skill has no confidence score, and a column that is NULL until M3 is shape with no use. I4 forbids surfacing a number with no breakdown behind it | M3, with the inference path that would populate it |
| `skill_id` FK to a taxonomy (§6.2) | The taxonomy is M3's. M2c stores the canonical name from `data/skills.yaml`, and the version field means growing the vocabulary is a data change | M3 |
| Structured `resumes.structured_profile` (§6.4) | The proposals *are* the structure, and they carry spans. A second denormalised copy could disagree with them | Never |
| Proficiency inference | The extractor cannot know it. `proficiency_level` defaults to `unspecified` and only the user sets it | Never inferred |
| Work-authorization extraction | A resume saying "authorized to work in the US" is a claim about legal status. I2 says a human confirms it in a form; the extractor never proposes it, and `ExtractionKind` has no member for it | Never |
| An LLM anywhere in this path | `command-center.md` §6.1, decided by the human over both an LLM and a no-parsing form | Would need an ADR naming the cost (A9) |
| The daily queue | §7 of the design | M2d |

---

### Task 1: The text layer — paste, `.txt`, PDF, and failing whole

Pure functions over `bytes` and `str`. No database, no ORM, no HTTP. This task also adds both new dependencies and their `costs.md` rows, because they are what it needs to exist.

**Files:**
- Modify: `services/api/pyproject.toml` (dependencies)
- Modify: `docs/architecture/costs.md`
- Create: `services/api/nightshift/domain/resume_text.py`
- Create: `scripts/make_resume_fixtures.py`
- Create: `services/api/tests/fixtures/resumes/nadia_okonkwo.txt`
- Create: `services/api/tests/fixtures/resumes/prose_only.txt`
- Create: `services/api/tests/fixtures/resumes/nadia_okonkwo.pdf` (generated)
- Create: `services/api/tests/fixtures/resumes/no_text_scan.pdf` (generated)
- Create: `services/api/tests/fixtures/resumes/encrypted.pdf` (generated)
- Create: `services/api/tests/fixtures/resumes/corrupt.pdf` (generated)
- Create: `services/api/tests/test_resume_text.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ResumeFormat = Literal["paste", "txt", "pdf"]`; `format_for_filename(filename: str) -> ResumeFormat`; `read_resume_bytes(*, data: bytes, filename: str) -> str`; `normalize_text(raw: str) -> str`; `ResumeTextError(ValueError)` with `.user_message: str`; `UnsupportedResumeFormatError(ResumeTextError)`; `MAX_UPLOAD_BYTES: int`; `MAX_PDF_PAGES: int`.

- [ ] **Step 1: Add the dependencies**

In `services/api/pyproject.toml`, add to `dependencies`, keeping the house comment style that says which milestone earned each one:

```toml
  # M2c: resume text. Pure Python, MIT, no native libraries and no key, so
  # `make demo` still runs offline (A9). pypdf reads only — it never writes a
  # file back, and the uploaded bytes are discarded after extraction.
  "pypdf>=5.1",
  # FastAPI needs this to parse a multipart upload at all. Also pure Python.
  "python-multipart>=0.0.20",
```

Add two rows to `docs/architecture/costs.md` with the columns that file already uses: name, purpose, free tier (`n/a — local library`), what happens at the limit (`nothing; no network call`), replacement plan (`paste-only, which is already a supported input`).

- [ ] **Step 2: Write the synthetic resume fixtures**

`services/api/tests/fixtures/resumes/nadia_okonkwo.txt` — an invented person. The last two sections are **bait**: they are the things the extractor must refuse to propose.

```text
NADIA OKONKWO
Brooklyn, NY | nadia.okonkwo@example.edu | github.com/example

EDUCATION

Hunter College, CUNY - New York, NY
Bachelor of Science in Computer Science
Expected graduation: May 2027
GPA 3.7 / 4.0

TECHNICAL SKILLS

Languages: Python, TypeScript, SQL, Go
Frameworks: React, FastAPI, PostgreSQL
Tools: Docker, Git, Playwright

PROJECTS

Transit Delay Tracker - Python, PostgreSQL
- Ingested MTA real-time feeds every 30 seconds into a time-series table.
- Published a dashboard read by roughly 400 people a week.

Cafe Queue - TypeScript, React
- Built a mobile ordering flow used by a campus coffee shop.
- Wrote the Playwright suite covering the checkout path.

EXPERIENCE

Peer Tutor, Hunter College Computer Science Department
- Tutored 40 students in data structures over two semesters.
- Five years of experience is a phrase this resume deliberately contains.

AUTHORIZATION

Authorized to work in the United States.
```

`services/api/tests/fixtures/resumes/prose_only.txt` — the "nothing could be proven" case. It must contain no vocabulary term and no section heading:

```text
To whom it may concern,

I am a passionate self-starter with five years of experience delivering
results for stakeholders across a fast-paced organisation. I thrive in
ambiguity, own outcomes end to end, and bring a bias for action to every
team I join. I would welcome the chance to discuss how my background could
serve your mission.

Sincerely,
A Candidate
```

- [ ] **Step 3: Write the fixture generator**

`scripts/make_resume_fixtures.py`. Everything is byte-deterministic except the encrypted PDF, and the docstring says which and why — an undocumented non-reproducible fixture is how a diff becomes noise.

```python
"""Generate the committed synthetic resume PDFs from the committed .txt.

Run by hand; the outputs are committed. Everything here is byte-deterministic
except `encrypted.pdf`: PDF encryption seeds a random file ID, so re-running
changes that one file and only that one. Nothing else uses a timestamp, a UUID
or a random value.

    python scripts/make_resume_fixtures.py

The people in these files are invented. Real resumes are never committed and
never written to disk by this project at all.
"""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter

FIXTURES = Path(__file__).resolve().parents[1] / "services/api/tests/fixtures/resumes"


def _escape(line: str) -> str:
    return line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[str]) -> bytes:
    body = ["BT", "/F1 10 Tf", "72 720 Td", "14 TL"]
    for line in lines:
        body.append(f"({_escape(line)}) Tj")
        body.append("T*")
    body.append("ET")
    return "\n".join(body).encode("ascii")


def build_pdf(pages: list[list[str]]) -> bytes:
    """A minimal, valid, uncompressed PDF. One Helvetica text run per line."""
    page_ids = [4 + 2 * index for index in range(len(pages))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, lines in enumerate(pages):
        content = _content_stream(lines)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {page_ids[index] + 1} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> None:
    lines = (FIXTURES / "nadia_okonkwo.txt").read_text(encoding="utf-8").split("\n")
    half = len(lines) // 2
    # Two pages, so the page join is exercised rather than assumed.
    (FIXTURES / "nadia_okonkwo.pdf").write_bytes(build_pdf([lines[:half], lines[half:]]))

    # A page with a text object that draws no glyphs — what a scan looks like
    # to a text extractor.
    (FIXTURES / "no_text_scan.pdf").write_bytes(build_pdf([[]]))

    (FIXTURES / "corrupt.pdf").write_bytes(b"this is not a PDF, it is a sentence.\n" * 8)

    reader = PdfReader(io.BytesIO(build_pdf([["Locked resume"]])))
    writer = PdfWriter(clone_from=reader)
    writer.encrypt("hunter2")
    buffer = io.BytesIO()
    writer.write(buffer)
    (FIXTURES / "encrypted.pdf").write_bytes(buffer.getvalue())

    for name in sorted(path.name for path in FIXTURES.glob("*.pdf")):
        print(f"  wrote {name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it, and read what came out**

```bash
cd services/api && python -m pip install -e '.[dev]' && cd - && python scripts/make_resume_fixtures.py
python -c "
from pypdf import PdfReader
r = PdfReader('services/api/tests/fixtures/resumes/nadia_okonkwo.pdf')
print(len(r.pages), 'pages')
print(repr(r.pages[0].extract_text()[:200]))
"
```

Expected: `2 pages`, and text that visibly contains `NADIA OKONKWO` and `EDUCATION`. **If the extracted text is empty, stop and fix the generator before writing any test** — a fixture that extracts to nothing would make every test in this task pass vacuously.

- [ ] **Step 5: Write the failing tests**

`services/api/tests/test_resume_text.py`:

```python
"""The text layer: three inputs, one output, and failure that is whole."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightshift.domain.resume_text import (
    MAX_UPLOAD_BYTES,
    ResumeTextError,
    UnsupportedResumeFormatError,
    format_for_filename,
    normalize_text,
    read_resume_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"


def test_a_plain_text_upload_is_decoded_as_written() -> None:
    data = (FIXTURES / "nadia_okonkwo.txt").read_bytes()
    text = read_resume_bytes(data=data, filename="nadia_okonkwo.txt")
    assert "Expected graduation: May 2027" in text


def test_a_pdf_yields_the_same_facts_as_its_source_text() -> None:
    """Not byte-equality: a PDF has no line-wrap fidelity to promise.

    What must survive the round trip is the *content* the extractor reads.
    """
    text = read_resume_bytes(
        data=(FIXTURES / "nadia_okonkwo.pdf").read_bytes(), filename="nadia_okonkwo.pdf"
    )
    for phrase in ("NADIA OKONKWO", "EDUCATION", "Bachelor of Science", "May 2027", "Playwright"):
        assert phrase in text, f"the PDF path lost {phrase!r}"


def test_a_scanned_pdf_fails_whole_and_says_why() -> None:
    with pytest.raises(ResumeTextError) as caught:
        read_resume_bytes(
            data=(FIXTURES / "no_text_scan.pdf").read_bytes(), filename="scan.pdf"
        )
    assert "paste" in caught.value.user_message.lower()


def test_a_corrupt_pdf_fails_whole() -> None:
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=(FIXTURES / "corrupt.pdf").read_bytes(), filename="corrupt.pdf")


def test_an_encrypted_pdf_fails_whole_and_names_the_reason() -> None:
    with pytest.raises(ResumeTextError) as caught:
        read_resume_bytes(
            data=(FIXTURES / "encrypted.pdf").read_bytes(), filename="encrypted.pdf"
        )
    assert "password" in caught.value.user_message.lower()


def test_a_docx_is_refused_by_name_rather_than_mangled() -> None:
    with pytest.raises(UnsupportedResumeFormatError) as caught:
        read_resume_bytes(data=b"PK\x03\x04anything", filename="resume.docx")
    message = caught.value.user_message.lower()
    assert ".docx" in message and "paste" in message


def test_an_oversized_upload_is_refused_before_it_is_parsed() -> None:
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=b"x" * (MAX_UPLOAD_BYTES + 1), filename="huge.txt")


def test_undecodable_bytes_fail_whole_rather_than_dropping_characters() -> None:
    """`errors="replace"` would silently turn a name into U+FFFD. I2's spirit."""
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=b"\xff\xfe\x00valid?", filename="resume.txt")


def test_normalisation_is_idempotent() -> None:
    once = normalize_text("Café\r\n\r\n\r\nRésumé  \nfiﬁ")
    assert normalize_text(once) == once


def test_normalisation_folds_ligatures_so_a_skill_can_be_matched() -> None:
    assert normalize_text("conﬁg") == "config"


def test_format_is_decided_by_extension_case_insensitively() -> None:
    assert format_for_filename("Resume.PDF") == "pdf"
    assert format_for_filename("resume.txt") == "txt"
```

- [ ] **Step 6: Run them and watch them fail**

```bash
cd services/api && python -m pytest tests/test_resume_text.py -q
```

Expected: collection error, `ModuleNotFoundError: nightshift.domain.resume_text`.

- [ ] **Step 7: Write the module**

`services/api/nightshift/domain/resume_text.py`:

```python
"""Turning what a person handed us into the text the extractor reads.

Three inputs and one output. A paste is text already; a `.txt` is bytes to
decode; a PDF is bytes for `pypdf`. Anything else is refused **by name**, with
paste offered as the way around it — a format we cannot read is a fact worth
stating, not a silent no-op.

**Failure is whole** (`command-center.md` §6.2). There is no partial parse and
no salvaged first page. A resume half-read is a resume whose missing half looks
exactly like a qualification the person does not have, which is invariant I2
failing quietly instead of loudly.

Nothing here touches the database, and nothing here decides what any of the
text *means*. That is `resume_extraction.py`, which cannot import the ORM.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import PurePosixPath
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import PyPdfError

#: 2 MB. A text resume is a few kilobytes; a PDF with an embedded photograph is
#: a few hundred. Anything past this is not a resume, and parsing it first to
#: find that out is work done on a caller's say-so.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

#: A resume is one or two pages. Twenty is generous and bounds the work a
#: single request can ask for.
MAX_PDF_PAGES = 20

ResumeFormat = Literal["paste", "txt", "pdf"]

#: Extensions people actually try, each answered by name rather than by a
#: generic refusal. `.doc` and `.pages` are here because being told "we do not
#: read .pages, paste instead" is a better experience than "unsupported file".
_NAMED_UNSUPPORTED = (".docx", ".doc", ".rtf", ".odt", ".pages", ".jpg", ".jpeg", ".png", ".heic")


class ResumeTextError(ValueError):
    """A file that could not be read, carrying the sentence the user sees.

    The message is part of the contract: §6.2 requires that failure states its
    reason and offers paste, so the reason travels with the exception rather
    than being reinvented at each call site.
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class UnsupportedResumeFormatError(ResumeTextError):
    """A format this project does not read. Named, not mangled."""


def normalize_text(raw: str) -> str:
    """Canonical form, applied once, before any span is computed.

    Every character offset stored in `resume_extractions` indexes into the
    output of this function, so normalisation may never run twice with
    different results — `test_normalisation_is_idempotent` is what holds that.

    NFKC is not cosmetic here: a PDF renders "config" with an fi-ligature, and
    without folding it the string never matches a vocabulary term.
    """
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Control characters other than tab and newline carry no meaning in a
    # resume and would make a span count characters a reader cannot see.
    text = "".join(
        char for char in text if char in "\n\t" or unicodedata.category(char)[0] != "C"
    )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_for_filename(filename: str) -> ResumeFormat:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".txt", ".text"):
        return "txt"
    if suffix in _NAMED_UNSUPPORTED:
        raise UnsupportedResumeFormatError(
            f"{suffix} files are not supported. Save the file as a PDF, or paste "
            "the text of your resume instead."
        )
    raise UnsupportedResumeFormatError(
        "Upload a PDF or a .txt file, or paste the text of your resume instead."
    )


def _read_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except (PyPdfError, ValueError, OSError) as exc:
        raise ResumeTextError(
            "This file could not be read as a PDF. Paste the text of your resume instead."
        ) from exc

    if reader.is_encrypted:
        raise ResumeTextError(
            "This PDF is password-protected, so its text cannot be read. Save an "
            "unprotected copy, or paste the text instead."
        )
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ResumeTextError(
            f"This PDF has {len(reader.pages)} pages, and {MAX_PDF_PAGES} is the limit."
        )

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except (PyPdfError, ValueError, KeyError) as exc:
            # One unreadable page fails the whole file. Keeping the readable
            # pages would produce a resume with a hole in it that nothing
            # downstream could see.
            raise ResumeTextError(
                "Part of this PDF could not be read. Paste the text of your resume instead."
            ) from exc

    text = normalize_text("\n\n".join(pages))
    if not text:
        raise ResumeTextError(
            "No text could be read from this PDF — it is most likely a scan or an "
            "image. Paste the text of your resume instead."
        )
    return text


def read_resume_bytes(*, data: bytes, filename: str) -> str:
    """Bytes in, normalised text out. Raises rather than returning a partial."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeTextError(
            f"That file is {len(data) // 1024} KB and the limit is "
            f"{MAX_UPLOAD_BYTES // 1024} KB."
        )
    resume_format = format_for_filename(filename)
    if resume_format == "pdf":
        return _read_pdf(data)

    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Deliberately not `errors="replace"`. Replacing turns a person's name
        # into U+FFFD and reports success, which is the failure mode this whole
        # slice is built to avoid.
        raise ResumeTextError(
            "This file is not valid UTF-8 text. Paste the text of your resume instead."
        ) from exc
    text = normalize_text(decoded)
    if not text:
        raise ResumeTextError("That file is empty.")
    return text
```

- [ ] **Step 8: Run the tests until green**

```bash
cd services/api && python -m pytest tests/test_resume_text.py -q
```

Expected: 11 passed.

- [ ] **Step 9: Mutation-check the two claims that matter**

Both of these are the difference between honest failure and a silent lie, so neither may be assumed:

1. In `read_resume_bytes`, change `data.decode("utf-8")` to `data.decode("utf-8", errors="replace")`. Run the suite. **Expected: `test_undecodable_bytes_fail_whole_rather_than_dropping_characters` fails.** Revert.
2. In `_read_pdf`, delete the `if not text:` guard. Run the suite. **Expected: `test_a_scanned_pdf_fails_whole_and_says_why` fails.** Revert.

If either mutation leaves the suite green, the test is not testing what it claims and must be fixed before moving on.

- [ ] **Step 10: Commit**

```bash
make check
git add services/api/pyproject.toml docs/architecture/costs.md \
  services/api/nightshift/domain/resume_text.py scripts/make_resume_fixtures.py \
  services/api/tests/fixtures/resumes services/api/tests/test_resume_text.py
git commit -m "feat(resume): read paste, .txt and PDF — and fail whole"
```

---

### Task 2: The skill vocabulary

A resume may only propose a skill that a committed file already names (`command-center.md` §6.1). Free text is never a skill. This task is the file and the matcher; it has no opinion about resumes.

**Files:**
- Create: `data/skills.yaml`
- Create: `services/api/nightshift/domain/skill_vocabulary.py`
- Create: `services/api/tests/test_skill_vocabulary.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SkillVocabulary` with `.version: str`, `.canonical_names: tuple[str, ...]`, `.match(text: str) -> list[SkillMatch]`; `SkillMatch` frozen dataclass with `.canonical_name: str`, `.char_start: int`, `.char_end: int`; `load_vocabulary(path: Path | None = None) -> SkillVocabulary`; `DEFAULT_VOCABULARY_PATH: Path`.

- [ ] **Step 1: Write the vocabulary file**

`data/skills.yaml`. The `version` field is the point: M3 grows this into the full taxonomy and that must be a data change, not a migration.

```yaml
# The skill vocabulary. A resume may propose a skill only if it appears here,
# by name or by alias (command-center.md §6.1). Free text is never a skill.
#
# `version` is read into every proposal that this file produced, so a
# proposal can be traced to the vocabulary that made it. Bump it whenever an
# entry is added, removed, or renamed — M3 grows this file into the full
# taxonomy and that must stay a data change.
#
# `case_sensitive: true` is for names that are ordinary English words. "Go"
# and "Rust" match a language; "go" and "rust" match prose. Precision is
# traded for recall on purpose here, per §6.1.
version: "2026-08-03.1"
skills:
  - name: Python
    aliases: [python3, cpython]
  - name: TypeScript
    aliases: [ts]
  - name: JavaScript
    aliases: [js, ecmascript]
  - name: Java
  - name: Go
    case_sensitive: true
    aliases: [Golang, golang]
  - name: Rust
    case_sensitive: true
  - name: C++
    aliases: [cpp]
  - name: C#
    aliases: [csharp]
  - name: Swift
    case_sensitive: true
  - name: Kotlin
  - name: Ruby
    case_sensitive: true
  - name: PHP
  - name: Scala
  - name: SQL
  - name: HTML
  - name: CSS
  - name: React
    aliases: [react.js, reactjs]
  - name: Next.js
    aliases: [nextjs]
  - name: Vue
    aliases: [vue.js, vuejs]
  - name: Angular
  - name: Svelte
  - name: Node.js
    aliases: [nodejs, node]
  - name: Django
  - name: Flask
  - name: FastAPI
    aliases: [fast api]
  - name: Spring Boot
    aliases: [springboot]
  - name: Express
    case_sensitive: true
  - name: Rails
    aliases: [ruby on rails]
  - name: Tailwind CSS
    aliases: [tailwind, tailwindcss]
  - name: PostgreSQL
    aliases: [postgres, psql]
  - name: MySQL
  - name: SQLite
  - name: MongoDB
    aliases: [mongo]
  - name: Redis
  - name: Elasticsearch
  - name: DynamoDB
  - name: Snowflake
  - name: Docker
  - name: Kubernetes
    aliases: [k8s]
  - name: Terraform
  - name: AWS
    aliases: [amazon web services]
  - name: Google Cloud
    aliases: [gcp, google cloud platform]
  - name: Azure
  - name: Linux
  - name: Git
  - name: GitHub Actions
  - name: CI/CD
  - name: pandas
  - name: NumPy
    aliases: [numpy]
  - name: PyTorch
    aliases: [pytorch]
  - name: TensorFlow
    aliases: [tensorflow]
  - name: scikit-learn
    aliases: [sklearn]
  - name: Jupyter
  - name: Spark
    case_sensitive: true
    aliases: [pyspark, Apache Spark]
  - name: Airflow
    aliases: [apache airflow]
  - name: dbt
  - name: Tableau
  - name: GraphQL
  - name: REST APIs
    aliases: [rest api, restful]
  - name: gRPC
  - name: Kafka
    aliases: [apache kafka]
  - name: Figma
  - name: Playwright
  - name: Cypress
  - name: Jest
    case_sensitive: true
  - name: pytest
  - name: Selenium
  - name: R
    case_sensitive: true
    minimum_length_override: true
  - name: MATLAB
    aliases: [matlab]
  - name: Excel
    case_sensitive: true
  - name: Data Structures
    aliases: [data structures and algorithms, dsa]
  - name: Machine Learning
    aliases: [ml]
  - name: Distributed Systems
```

- [ ] **Step 2: Write the failing tests**

`services/api/tests/test_skill_vocabulary.py`:

```python
"""The vocabulary, and the precision rules that keep it from matching prose."""

from __future__ import annotations

import pytest

from nightshift.domain.skill_vocabulary import load_vocabulary

VOCABULARY = load_vocabulary()


def test_the_file_declares_a_version() -> None:
    assert VOCABULARY.version


def test_a_term_matches_and_reports_where_it_was_found() -> None:
    text = "Languages: Python, TypeScript"
    matches = {match.canonical_name: match for match in VOCABULARY.match(text)}
    assert set(matches) == {"Python", "TypeScript"}
    found = matches["Python"]
    assert text[found.char_start : found.char_end] == "Python"


def test_an_alias_resolves_to_its_canonical_name_and_quotes_the_alias() -> None:
    text = "Built the API in Golang."
    (match,) = [m for m in VOCABULARY.match(text) if m.canonical_name == "Go"]
    assert text[match.char_start : match.char_end] == "Golang"


def test_a_term_inside_a_longer_word_is_not_a_match() -> None:
    """"github.com" is not the skill Git, and "javascriptural" is not JavaScript."""
    assert VOCABULARY.match("see github.com/example for javascriptural notes") == []


@pytest.mark.parametrize(
    "prose",
    [
        "I go to class every morning",
        "there was some rust on the railing",
        "we express our findings clearly",
    ],
)
def test_ordinary_english_does_not_become_a_skill(prose: str) -> None:
    assert VOCABULARY.match(prose) == []


def test_the_longest_term_wins_when_two_overlap() -> None:
    """"Machine Learning" must not also yield a bare match inside itself."""
    matches = VOCABULARY.match("Coursework: Machine Learning")
    assert [m.canonical_name for m in matches] == ["Machine Learning"]


def test_matches_come_back_in_the_order_they_appear() -> None:
    text = "Docker, then Python, then Redis"
    positions = [match.char_start for match in VOCABULARY.match(text)]
    assert positions == sorted(positions)


def test_matching_the_same_text_twice_gives_the_same_answer() -> None:
    text = "Python, Docker, Python again"
    assert VOCABULARY.match(text) == VOCABULARY.match(text)


def test_every_alias_resolves_to_a_declared_skill() -> None:
    """A typo in the YAML is a silently missing skill, so the file checks itself."""
    for name in VOCABULARY.canonical_names:
        assert name.strip() == name and name
```

- [ ] **Step 3: Run them and watch them fail**

```bash
cd services/api && python -m pytest tests/test_skill_vocabulary.py -q
```

Expected: `ModuleNotFoundError: nightshift.domain.skill_vocabulary`.

- [ ] **Step 4: Write the module**

`services/api/nightshift/domain/skill_vocabulary.py`:

```python
"""The committed skill vocabulary, and the matcher that reads it.

`command-center.md` §6.1: a resume may propose a skill only when the term
matches this file exactly or by alias. Never free text. That rule is what makes
"the extractor proposed Python" checkable rather than a matter of trust.

Two precision rules, both deliberate, both costing recall:

* **Word boundaries.** "github.com" does not contain the skill Git.
* **Case sensitivity for skills that are also English words.** "Go", "Rust",
  "Express" and "R" match only in the case the vocabulary declares. A resume
  written entirely in lower case will lose those, and a lost skill is a click
  away on the manual form — a fabricated one is an invariant violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_VOCABULARY_PATH = Path(__file__).resolve().parents[3] / "data" / "skills.yaml"

#: A one-character term matches everything. Only entries that opt in with
#: `minimum_length_override: true` may be this short, and they must also be
#: case-sensitive — "R" is a language, "r" is a letter.
_MINIMUM_TERM_LENGTH = 2


@dataclass(frozen=True, slots=True)
class SkillMatch:
    canonical_name: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class _Term:
    canonical_name: str
    pattern: re.Pattern[str]
    length: int


class SkillVocabulary:
    def __init__(self, *, version: str, terms: list[_Term], canonical_names: tuple[str, ...]):
        self.version = version
        self.canonical_names = canonical_names
        # Longest first: "Machine Learning" must win over any term inside it.
        self._terms = sorted(terms, key=lambda term: term.length, reverse=True)

    def match(self, text: str) -> list[SkillMatch]:
        """Every non-overlapping vocabulary term in `text`, in reading order.

        One match per canonical name — the first occurrence. A resume listing
        Python four times has one Python skill, and the span points at the
        first place it can be shown.
        """
        claimed: list[tuple[int, int]] = []
        found: dict[str, SkillMatch] = {}
        for term in self._terms:
            for hit in term.pattern.finditer(text):
                start, end = hit.span()
                if any(start < other_end and other_start < end for other_start, other_end in claimed):
                    continue
                claimed.append((start, end))
                if term.canonical_name not in found:
                    found[term.canonical_name] = SkillMatch(
                        canonical_name=term.canonical_name, char_start=start, char_end=end
                    )
        return sorted(found.values(), key=lambda match: (match.char_start, match.canonical_name))


def _compile(term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    # `\b` is wrong beside a non-word character: `\bC++\b` can never match,
    # because there is no word boundary after `+`. Lookarounds on word
    # characters do the same job for every term shape.
    escaped = re.escape(term)
    pattern = rf"(?<![0-9A-Za-z_]){escaped}(?![0-9A-Za-z_])"
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def _load(path: Path) -> SkillVocabulary:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = str(raw["version"])
    terms: list[_Term] = []
    canonical: list[str] = []
    for entry in raw["skills"]:
        name = str(entry["name"])
        canonical.append(name)
        case_sensitive = bool(entry.get("case_sensitive", False))
        allow_short = bool(entry.get("minimum_length_override", False))
        for term in [name, *(str(alias) for alias in entry.get("aliases", []))]:
            if len(term) < _MINIMUM_TERM_LENGTH and not allow_short:
                raise ValueError(f"{term!r} is too short to match precisely; declare the override")
            if len(term) < _MINIMUM_TERM_LENGTH and not case_sensitive:
                raise ValueError(f"{term!r} is short and must also be case-sensitive")
            terms.append(
                _Term(
                    canonical_name=name,
                    pattern=_compile(term, case_sensitive=case_sensitive),
                    length=len(term),
                )
            )
    return SkillVocabulary(version=version, terms=terms, canonical_names=tuple(canonical))


@lru_cache(maxsize=4)
def load_vocabulary(path: Path | None = None) -> SkillVocabulary:
    """Cached: the file is source data and does not change inside a process."""
    return _load(path or DEFAULT_VOCABULARY_PATH)
```

- [ ] **Step 5: Run the tests until green**

```bash
cd services/api && python -m pytest tests/test_skill_vocabulary.py -q
```

Expected: 12 passed (the parametrised case counts three).

**If `test_a_term_inside_a_longer_word_is_not_a_match` fails**, read which term matched before changing the regex — the likely culprit is an alias like `node` inside `nodejs`, which is a vocabulary problem, not a matcher problem.

- [ ] **Step 6: Mutation-check the precision rules**

1. In `_compile`, drop both lookarounds (`pattern = escaped`). **Expected: `test_a_term_inside_a_longer_word_is_not_a_match` fails.** Revert.
2. In `_compile`, ignore `case_sensitive` and always pass `re.IGNORECASE`. **Expected: `test_ordinary_english_does_not_become_a_skill` fails on all three cases.** Revert.
3. In `SkillVocabulary.__init__`, sort ascending instead of descending. **Expected: `test_the_longest_term_wins_when_two_overlap` fails.** Revert.

- [ ] **Step 7: Commit**

```bash
make check
git add data/skills.yaml services/api/nightshift/domain/skill_vocabulary.py \
  services/api/tests/test_skill_vocabulary.py
git commit -m "feat(profile): add the committed skill vocabulary and its matcher"
```

---

### Task 3: The extractor — proposals that can point at the words they came from

Still pure. Text and a vocabulary in; a list of proposals out. **This module may not import `nightshift.db`**, and a test asserts it, because that import is the only way a bug here could ever reach a confirmed fact.

**Files:**
- Create: `services/api/nightshift/domain/resume_extraction.py`
- Create: `services/api/tests/test_resume_extraction.py`
- Create: `services/api/tests/fixtures/resumes/nadia_okonkwo.proposals.json` (golden, generated in step 6)

**Interfaces:**
- Consumes: `SkillVocabulary`, `load_vocabulary` (Task 2).
- Produces: `EXTRACTOR_VERSION: str`; `ProposalKind = Literal["skill", "graduation", "degree", "school", "project"]`; frozen dataclass `Proposal` with `.kind`, `.value: dict[str, object]`, `.char_start: int`, `.char_end: int`, `.quoted_text: str`; `extract_proposals(text: str, *, vocabulary: SkillVocabulary | None = None) -> list[Proposal]`; `find_sections(text: str) -> dict[str, tuple[int, int]]`.

- [ ] **Step 1: Write the failing tests**

`services/api/tests/test_resume_extraction.py`:

```python
"""The extractor. Precision over recall, and every claim points at its words."""

from __future__ import annotations

import json
from pathlib import Path

from nightshift.domain.resume_extraction import (
    EXTRACTOR_VERSION,
    extract_proposals,
    find_sections,
)
from nightshift.domain.resume_text import read_resume_bytes

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"
RESUME = (FIXTURES / "nadia_okonkwo.txt").read_text(encoding="utf-8")


def test_every_proposal_quotes_the_text_it_came_from() -> None:
    """The whole slice rests on this. A span that does not quote is a fabrication."""
    for proposal in extract_proposals(RESUME):
        assert RESUME[proposal.char_start : proposal.char_end] == proposal.quoted_text
        assert proposal.char_end > proposal.char_start


def test_the_same_text_twice_gives_byte_identical_proposals() -> None:
    first = [p.as_dict() for p in extract_proposals(RESUME)]
    second = [p.as_dict() for p in extract_proposals(RESUME)]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_graduation_month_and_year_are_proposed_without_inventing_a_day() -> None:
    (grad,) = [p for p in extract_proposals(RESUME) if p.kind == "graduation"]
    assert grad.value == {"year": 2027, "month": 5}
    assert "May 2027" in grad.quoted_text


def test_the_degree_and_school_come_from_the_education_section() -> None:
    kinds = {p.kind: p for p in extract_proposals(RESUME)}
    assert kinds["degree"].value == {"degree": "Bachelor of Science"}
    assert kinds["school"].value == {"school": "Hunter College"}
    education_start, education_end = find_sections(RESUME)["education"]
    for kind in ("degree", "school", "graduation"):
        assert education_start <= kinds[kind].char_start < education_end


def test_the_skills_are_the_vocabulary_ones_and_nothing_else() -> None:
    names = sorted(
        str(p.value["name"]) for p in extract_proposals(RESUME) if p.kind == "skill"
    )
    assert names == [
        "Docker",
        "FastAPI",
        "Git",
        "Go",
        "PostgreSQL",
        "Playwright",
        "Python",
        "React",
        "SQL",
        "TypeScript",
    ]


def test_both_projects_are_proposed_with_their_bullets_as_evidence() -> None:
    projects = [p for p in extract_proposals(RESUME) if p.kind == "project"]
    assert [p.value["name"] for p in projects] == ["Transit Delay Tracker", "Cafe Queue"]
    assert "MTA real-time feeds" in str(projects[0].value["evidence"])


def test_years_of_experience_is_never_proposed() -> None:
    """A13 and I2: seniority is the hard problem and this is not the slice for it."""
    assert "Five years of experience" in RESUME
    for proposal in extract_proposals(RESUME):
        assert "five years" not in proposal.quoted_text.lower()


def test_work_authorization_is_never_proposed() -> None:
    """A claim about legal status is confirmed in a form, never read off a page."""
    assert "Authorized to work" in RESUME
    kinds = {proposal.kind for proposal in extract_proposals(RESUME)}
    assert "work_authorization" not in kinds
    for proposal in extract_proposals(RESUME):
        assert "authorized" not in proposal.quoted_text.lower()


def test_a_resume_that_proves_nothing_proposes_nothing() -> None:
    prose = (FIXTURES / "prose_only.txt").read_text(encoding="utf-8")
    assert extract_proposals(prose) == []


def test_a_date_outside_an_education_section_is_not_a_graduation_date() -> None:
    text = "EXPERIENCE\n\nSummer analyst, May 2027 cohort\n"
    assert [p for p in extract_proposals(text) if p.kind == "graduation"] == []


def test_the_pdf_and_the_text_agree_on_the_facts_they_propose() -> None:
    """Same person, two file formats. The values must match; the spans must not."""
    from_pdf = extract_proposals(
        read_resume_bytes(
            data=(FIXTURES / "nadia_okonkwo.pdf").read_bytes(), filename="r.pdf"
        )
    )
    from_text = extract_proposals(RESUME)
    assert {(p.kind, json.dumps(p.value, sort_keys=True)) for p in from_pdf} == {
        (p.kind, json.dumps(p.value, sort_keys=True)) for p in from_text
    }


def test_the_extractor_cannot_reach_the_database() -> None:
    """I2's structural claim: a bug here has no path to a confirmed fact."""
    source = (
        Path(__file__).resolve().parents[1]
        / "nightshift"
        / "domain"
        / "resume_extraction.py"
    ).read_text(encoding="utf-8")
    assert "nightshift.db" not in source
    assert "sqlalchemy" not in source


def test_the_version_is_declared() -> None:
    assert EXTRACTOR_VERSION
```

- [ ] **Step 2: Run them and watch them fail**

```bash
cd services/api && python -m pytest tests/test_resume_extraction.py -q
```

Expected: `ModuleNotFoundError: nightshift.domain.resume_extraction`.

- [ ] **Step 3: Write the module**

`services/api/nightshift/domain/resume_extraction.py`:

```python
"""Reading a resume for things it can *prove*, and refusing the rest.

`command-center.md` §6.1 decided the shape of this module over both an LLM and
a no-parsing form: rules, deterministic, $0, no key. Every proposal carries the
character span it came from, so the confirmation screen highlights the literal
words rather than asking anyone to trust a summary.

**Recall is traded for precision on purpose.** "5 years of experience" and
"passionate self-starter" yield nothing. So does a graduation date outside an
education section, and so does a skill that is not in `data/skills.yaml`. A
missed skill costs one click on the manual form; an invented one is invariant
I2 failing, which is the worst outcome available to this project.

Nothing here writes anything. This module cannot import the ORM — that is a
test, not a convention (`test_the_extractor_cannot_reach_the_database`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nightshift.domain.skill_vocabulary import SkillVocabulary, load_vocabulary

#: Bumped whenever the rules change. Stored on every row this module produces,
#: so a proposal can always be traced to the rules that made it.
EXTRACTOR_VERSION = "m2c.1"

ProposalKind = Literal["skill", "graduation", "degree", "school", "project"]

#: Section headings, lower-cased and stripped of punctuation. A line is a
#: heading only if it matches one of these *entirely* — "Education" is a
#: heading, "Education has always mattered to me" is a sentence.
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": ("education", "academics", "academic background"),
    "skills": ("skills", "technical skills", "technologies", "tools", "languages and tools"),
    "projects": ("projects", "personal projects", "selected projects", "side projects"),
    "experience": ("experience", "work experience", "employment", "professional experience"),
}

_DEGREES: tuple[str, ...] = (
    "Bachelor of Science",
    "Bachelor of Arts",
    "Bachelor of Engineering",
    "Master of Science",
    "Master of Arts",
    "Master of Engineering",
    "Doctor of Philosophy",
    "Associate of Science",
    "Associate of Arts",
    "B.S.",
    "B.A.",
    "M.S.",
    "M.A.",
    "Ph.D.",
    "PhD",
    "BSc",
    "MSc",
)

_SCHOOL_KEYWORDS: tuple[str, ...] = ("University", "College", "Institute of Technology", "Academy")

_MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_YEAR = re.compile(
    r"(?<![0-9A-Za-z])(?P<month>"
    + "|".join(sorted(_MONTHS, key=len, reverse=True))
    + r")\.?\s+(?P<year>20\d{2})(?![0-9])",
    re.IGNORECASE,
)
_BARE_YEAR = re.compile(r"(?<![0-9])(?P<year>20\d{2})(?![0-9])")

#: A bare year is only a graduation date beside one of these words. "2027"
#: alone is a number on a page.
_GRADUATION_CUES = re.compile(r"graduat|expected|class of|anticipated", re.IGNORECASE)

_BULLET = re.compile(r"^\s*[-*•–●]\s+")

#: What separates a name from its trailing detail on one line:
#: "Hunter College, CUNY - New York, NY" and "Cafe Queue - TypeScript, React".
_NAME_TAIL = re.compile(r"\s*(?:[,|–—]|\s-\s|\(|·)")


@dataclass(frozen=True, slots=True)
class Proposal:
    kind: ProposalKind
    value: dict[str, object]
    char_start: int
    char_end: int
    quoted_text: str

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "value": self.value,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "quoted_text": self.quoted_text,
        }


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for line in text.split("\n"):
        spans.append((position, position + len(line)))
        position += len(line) + 1
    return spans


def _heading_key(line: str) -> str | None:
    stripped = re.sub(r"[^a-z ]", "", line.strip().lower()).strip()
    if not stripped or len(stripped) > 40:
        return None
    for key, aliases in _SECTION_ALIASES.items():
        if stripped in aliases:
            return key
    return None


def find_sections(text: str) -> dict[str, tuple[int, int]]:
    """Character spans for each recognised section, heading line excluded.

    A section runs from the end of its heading to the start of the next
    heading, or to the end of the document. An unrecognised heading does not
    end a section — it is just a line inside it, which is the conservative
    reading and keeps a stray "Awards" from truncating Education.
    """
    lines = _line_spans(text)
    starts: list[tuple[str, int, int]] = []
    for index, (start, end) in enumerate(lines):
        key = _heading_key(text[start:end])
        if key is not None:
            starts.append((key, start, end))
    sections: dict[str, tuple[int, int]] = {}
    for position, (key, _, heading_end) in enumerate(starts):
        next_start = starts[position + 1][1] if position + 1 < len(starts) else len(text)
        # Last heading of a given name wins: a resume repeating "Projects"
        # would otherwise get a section spanning everything between them.
        sections[key] = (min(heading_end + 1, next_start), next_start)
    return sections


def _quote(text: str, start: int, end: int) -> str:
    return text[start:end]


def _propose_degree(text: str, span: tuple[int, int]) -> Proposal | None:
    section = text[span[0] : span[1]]
    for degree in _DEGREES:
        found = section.find(degree)
        if found != -1:
            start = span[0] + found
            end = start + len(degree)
            return Proposal(
                kind="degree",
                value={"degree": degree},
                char_start=start,
                char_end=end,
                quoted_text=_quote(text, start, end),
            )
    return None


def _propose_school(text: str, span: tuple[int, int]) -> Proposal | None:
    for start, end in _line_spans(text):
        if not (span[0] <= start < span[1]):
            continue
        line = text[start:end]
        if not any(keyword in line for keyword in _SCHOOL_KEYWORDS):
            continue
        cut = _NAME_TAIL.search(line)
        name_end = start + (cut.start() if cut else len(line.rstrip()))
        name_start = start + (len(line) - len(line.lstrip()))
        if name_end <= name_start:
            continue
        return Proposal(
            kind="school",
            value={"school": _quote(text, name_start, name_end)},
            char_start=name_start,
            char_end=name_end,
            quoted_text=_quote(text, name_start, name_end),
        )
    return None


def _propose_graduation(text: str, span: tuple[int, int]) -> Proposal | None:
    """A month and a year. Never a day — a resume does not say one (I1)."""
    for start, end in _line_spans(text):
        if not (span[0] <= start < span[1]):
            continue
        line = text[start:end]
        has_cue = bool(_GRADUATION_CUES.search(line))
        has_degree = any(degree in line for degree in _DEGREES)
        if not (has_cue or has_degree):
            continue
        month_year = _MONTH_YEAR.search(line)
        if month_year is not None:
            return Proposal(
                kind="graduation",
                value={
                    "year": int(month_year.group("year")),
                    "month": _MONTHS[month_year.group("month").lower()],
                },
                char_start=start + month_year.start(),
                char_end=start + month_year.end(),
                quoted_text=_quote(text, start + month_year.start(), start + month_year.end()),
            )
        if not has_cue:
            # A bare year beside a degree is far more often the start of a
            # programme than its end. Only an explicit cue promotes one.
            continue
        bare = _BARE_YEAR.search(line)
        if bare is not None:
            return Proposal(
                kind="graduation",
                value={"year": int(bare.group("year")), "month": None},
                char_start=start + bare.start(),
                char_end=start + bare.end(),
                quoted_text=_quote(text, start + bare.start(), start + bare.end()),
            )
    return None


def _propose_projects(text: str, span: tuple[int, int]) -> list[Proposal]:
    """A heading line with at least one bullet under it. Both are the evidence."""
    proposals: list[Proposal] = []
    lines = [(start, end) for start, end in _line_spans(text) if span[0] <= start < span[1]]
    index = 0
    while index < len(lines):
        start, end = lines[index]
        line = text[start:end]
        if not line.strip() or _BULLET.match(line):
            index += 1
            continue
        bullets: list[tuple[int, int]] = []
        cursor = index + 1
        while cursor < len(lines):
            bullet_start, bullet_end = lines[cursor]
            bullet_line = text[bullet_start:bullet_end]
            if _BULLET.match(bullet_line):
                bullets.append((bullet_start, bullet_end))
                cursor += 1
                continue
            if not bullet_line.strip() and bullets:
                cursor += 1
                continue
            break
        if bullets:
            cut = _NAME_TAIL.search(line)
            name_end = start + (cut.start() if cut else len(line.rstrip()))
            block_end = bullets[-1][1]
            evidence = "\n".join(
                text[bullet_start:bullet_end].strip() for bullet_start, bullet_end in bullets
            )
            proposals.append(
                Proposal(
                    kind="project",
                    value={"name": _quote(text, start, name_end), "evidence": evidence},
                    char_start=start,
                    char_end=block_end,
                    quoted_text=_quote(text, start, block_end),
                )
            )
            index = cursor
            continue
        index += 1
    return proposals


def extract_proposals(
    text: str, *, vocabulary: SkillVocabulary | None = None
) -> list[Proposal]:
    """Everything this resume can prove, in reading order.

    Deterministic: the same text always yields the same list, in the same
    order, with the same spans. That is asserted by
    `test_the_same_text_twice_gives_byte_identical_proposals` and is the same
    property the adapter fixture suites hold for job payloads.
    """
    vocabulary = vocabulary or load_vocabulary()
    sections = find_sections(text)
    proposals: list[Proposal] = []

    education = sections.get("education")
    if education is not None:
        for candidate in (
            _propose_degree(text, education),
            _propose_school(text, education),
            _propose_graduation(text, education),
        ):
            if candidate is not None:
                proposals.append(candidate)

    projects = sections.get("projects")
    if projects is not None:
        proposals.extend(_propose_projects(text, projects))

    for match in vocabulary.match(text):
        proposals.append(
            Proposal(
                kind="skill",
                value={"name": match.canonical_name, "vocabulary_version": vocabulary.version},
                char_start=match.char_start,
                char_end=match.char_end,
                quoted_text=_quote(text, match.char_start, match.char_end),
            )
        )

    return sorted(proposals, key=lambda p: (p.char_start, p.char_end, p.kind))
```

- [ ] **Step 4: Run the tests and fix what the fixture reveals**

```bash
cd services/api && python -m pytest tests/test_resume_extraction.py -q
```

Expect failures on the first run and read each one against the fixture text before touching the rules. Two are predictable and neither is a licence to loosen a rule:

- **The skill list may not match the expected ten.** Print what it found (`pytest -q -k skills -s` with a temporary print) and compare against `data/skills.yaml`. If a term matched inside prose, that is a vocabulary precision bug to fix in Task 2's file. If an expected term is missing, check the case-sensitivity flag.
- **`Cafe Queue`'s bullets may swallow the `EXPERIENCE` heading** if `find_sections` is wrong about where `projects` ends. The section end is the *start* of the next heading line, so a bullet run cannot cross it.

- [ ] **Step 5: Verify the "nothing proven" path against the real fixture**

```bash
cd services/api && python -c "
from pathlib import Path
from nightshift.domain.resume_extraction import extract_proposals
text = Path('tests/fixtures/resumes/prose_only.txt').read_text()
print(extract_proposals(text))
"
```

Expected: `[]`. If anything is proposed, the fixture contains a vocabulary term — fix the fixture, not the rule.

- [ ] **Step 6: Write the golden file and the test that reads it**

```bash
cd services/api && python -c "
import json
from pathlib import Path
from nightshift.domain.resume_extraction import extract_proposals
text = Path('tests/fixtures/resumes/nadia_okonkwo.txt').read_text()
Path('tests/fixtures/resumes/nadia_okonkwo.proposals.json').write_text(
    json.dumps([p.as_dict() for p in extract_proposals(text)], indent=2, sort_keys=True) + '\n'
)
"
```

**Read the generated file before committing it.** A golden file recorded without being read is a rule that says "whatever the code did on Tuesday". Check by eye that every `quoted_text` is a phrase a person would recognise as the source of its `value`. Then append the test:

```python
def test_the_proposals_match_the_committed_golden_file() -> None:
    golden = json.loads((FIXTURES / "nadia_okonkwo.proposals.json").read_text())
    assert [p.as_dict() for p in extract_proposals(RESUME)] == golden
```

- [ ] **Step 7: Mutation-check the three load-bearing rules**

1. In `_propose_graduation`, delete the `if not (has_cue or has_degree): continue` line. **Expected: `test_a_date_outside_an_education_section_is_not_a_graduation_date` still passes** (it is guarded by the section, not the cue) **and nothing else fails** — so add a case that does catch it: a resume line reading `Relocated to New York in May 2027` inside the education section. Add that case to the test file, confirm it fails with the mutation and passes without it, then revert.
2. In `extract_proposals`, replace `vocabulary.match(text)` with a regex that proposes every capitalised word. **Expected: `test_the_skills_are_the_vocabulary_ones_and_nothing_else` fails.** Revert.
3. In `Proposal`, change `quoted_text` to `value` rendered as a string instead of the slice. **Expected: `test_every_proposal_quotes_the_text_it_came_from` fails.** Revert.

- [ ] **Step 8: Commit**

```bash
make check
git add services/api/nightshift/domain/resume_extraction.py \
  services/api/tests/test_resume_extraction.py \
  services/api/tests/fixtures/resumes/nadia_okonkwo.proposals.json
git commit -m "feat(profile): extract only what the resume can prove, with spans"
```

---

### Task 4: The tables — proposals on one side, confirmed facts on the other

Migration `0009`. Five new tables, seven new columns on `users`, one new column on `applications`, and the trigger that makes a lying span impossible to store.

**Files:**
- Modify: `services/api/nightshift/db/base.py` (append to the domain enums section)
- Modify: `services/api/nightshift/db/models.py`
- Create: `services/api/migrations/versions/20260803_2100_profile_and_resumes.py`
- Create: `services/api/tests/test_profile_models.py`

**Interfaces:**
- Consumes: Task 1's `ResumeFormat` values (`paste` / `txt` / `pdf`), Task 3's `ProposalKind` values.
- Produces: models `UserSkill`, `UserProject`, `Resume`, `ResumeExtraction`; enums `WorkAuthorization`, `RemotePreference`, `ProficiencyLevel`, `SkillSourceType`, `ProjectStatus`, `ResumeSourceKind`, `ResumeVariant`, `ExtractionKind`, `ExtractionStatus`; `User` columns `graduation_year`, `graduation_month`, `degree`, `school`, `work_authorization`, `home_location_text`, `remote_preference`, `minimum_salary`, `preferred_roles`, `preferred_locations`; `Application.selected_resume_id`.

- [ ] **Step 1: Add the enums**

Append to `services/api/nightshift/db/base.py`, after `ApplicationEventType`:

```python
class WorkAuthorization(enum.StrEnum):
    """A claim about legal status, and therefore never inferred (I2).

    The extractor has no member for this and no rule that could produce one.
    `unspecified` is the default and the honest answer until a person picks
    another in a form.
    """

    UNSPECIFIED = "unspecified"
    US_CITIZEN = "us_citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    F1_STUDENT = "f1_student"
    OTHER_AUTHORIZED = "other_authorized"
    NEEDS_SPONSORSHIP = "needs_sponsorship"


class RemotePreference(enum.StrEnum):
    NO_PREFERENCE = "no_preference"
    ON_SITE = "on_site"
    HYBRID = "hybrid"
    REMOTE = "remote"


class ProficiencyLevel(enum.StrEnum):
    """Only the user sets this. Nothing reads a level off a resume."""

    UNSPECIFIED = "unspecified"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class SkillSourceType(enum.StrEnum):
    """PRODUCT-SPEC §6.2's list.

    ``inferred_pending_confirmation`` exists here and is **refused** by a check
    constraint on ``user_skills``: that table holds confirmed facts only, and a
    pending one belongs in ``resume_extractions``. The value is kept so the
    refusal is expressible rather than implicit.
    """

    MANUAL = "manual"
    RESUME = "resume"
    PROJECT = "project"
    COURSEWORK = "coursework"
    ASSESSMENT = "assessment"
    GITHUB = "github"
    INFERRED_PENDING_CONFIRMATION = "inferred_pending_confirmation"


class ProjectStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ResumeSourceKind(enum.StrEnum):
    """How the text arrived. Matches `resume_text.ResumeFormat` exactly."""

    PASTE = "paste"
    TXT = "txt"
    PDF = "pdf"


class ResumeVariant(enum.StrEnum):
    """PRODUCT-SPEC §6.4's variants. The user picks; nothing classifies."""

    GENERAL_SWE = "general_swe"
    BACKEND = "backend"
    FULL_STACK = "full_stack"
    DATA_ML = "data_ml"
    INFRASTRUCTURE = "infrastructure"
    CUSTOM = "custom"


class ExtractionKind(enum.StrEnum):
    """What a proposal is about. Matches `resume_extraction.ProposalKind`.

    There is no member for work authorization, seniority, or years of
    experience, and adding one is a migration — which is the point (I2).
    """

    SKILL = "skill"
    GRADUATION = "graduation"
    DEGREE = "degree"
    SCHOOL = "school"
    PROJECT = "project"


class ExtractionStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
```

- [ ] **Step 2: Write the failing tests**

`services/api/tests/test_profile_models.py`. These are database tests; they follow the existing `conftest.py` session fixture used by `test_application_models.py`.

```python
"""The schema half of invariant I2: what the database itself refuses."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ExtractionKind,
    ExtractionStatus,
    ResumeSourceKind,
    SkillSourceType,
)
from nightshift.db.models import Resume, ResumeExtraction, UserSkill
from nightshift.domain.resume_text import ResumeFormat

pytestmark = pytest.mark.integration

PARSED = "Skills: Python and Docker.\n"


async def _resume(session: AsyncSession, user_id: uuid.UUID) -> Resume:
    resume = Resume(
        user_id=user_id,
        name="test resume",
        source_kind=ResumeSourceKind.PASTE,
        parsed_text=PARSED,
        content_hash="0" * 64,
    )
    session.add(resume)
    await session.flush()
    return resume


async def test_a_proposal_must_quote_the_resume_text(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    """The trigger. A span that does not quote the text cannot be stored."""
    resume = await _resume(db_session, dev_user_id)
    db_session.add(
        ResumeExtraction(
            user_id=dev_user_id,
            resume_id=resume.id,
            kind=ExtractionKind.SKILL,
            value={"name": "Rust"},
            char_start=8,
            char_end=14,
            quoted_text="Rust",  # the text at 8..14 is "Python"
            extractor_version="test",
        )
    )
    with pytest.raises(DBAPIError, match="does not quote"):
        await db_session.flush()


async def test_a_proposal_whose_span_runs_past_the_text_is_refused(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    resume = await _resume(db_session, dev_user_id)
    db_session.add(
        ResumeExtraction(
            user_id=dev_user_id,
            resume_id=resume.id,
            kind=ExtractionKind.SKILL,
            value={"name": "Python"},
            char_start=0,
            char_end=len(PARSED) + 50,
            quoted_text=PARSED,
            extractor_version="test",
        )
    )
    with pytest.raises(DBAPIError, match="runs past"):
        await db_session.flush()


async def test_a_proposal_with_an_empty_span_is_refused(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    """"A proposal with no span is unrepresentable" (command-center.md §6.1)."""
    resume = await _resume(db_session, dev_user_id)
    db_session.add(
        ResumeExtraction(
            user_id=dev_user_id,
            resume_id=resume.id,
            kind=ExtractionKind.SKILL,
            value={"name": "Python"},
            char_start=8,
            char_end=8,
            quoted_text="",
            extractor_version="test",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_span_that_quotes_the_text_is_accepted(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    resume = await _resume(db_session, dev_user_id)
    db_session.add(
        ResumeExtraction(
            user_id=dev_user_id,
            resume_id=resume.id,
            kind=ExtractionKind.SKILL,
            value={"name": "Python"},
            char_start=8,
            char_end=14,
            quoted_text="Python",
            extractor_version="test",
        )
    )
    await db_session.flush()  # must not raise


async def test_a_confirmed_skill_cannot_be_marked_pending(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    """`user_skills` holds confirmed facts. A pending one belongs elsewhere."""
    db_session.add(
        UserSkill(
            user_id=dev_user_id,
            name="Python",
            normalized_name="python",
            source_type=SkillSourceType.INFERRED_PENDING_CONFIRMATION,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_skill_per_user_per_name(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    for _ in range(2):
        db_session.add(
            UserSkill(
                user_id=dev_user_id,
                name="Python",
                normalized_name="python",
                source_type=SkillSourceType.MANUAL,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_graduation_month_requires_a_year(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    """A month with no year is not a date, it is a fragment (I1)."""
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("UPDATE users SET graduation_month = 5, graduation_year = NULL WHERE id = :id"),
            {"id": dev_user_id},
        )


async def test_the_enum_and_the_reader_agree_on_format_names() -> None:
    """A drift here would store a `source_kind` nothing can read back."""
    assert {kind.value for kind in ResumeSourceKind} == set(ResumeFormat.__args__)


async def test_deleting_a_resume_takes_its_proposals_and_leaves_confirmed_facts(
    db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    resume = await _resume(db_session, dev_user_id)
    db_session.add(
        ResumeExtraction(
            user_id=dev_user_id,
            resume_id=resume.id,
            kind=ExtractionKind.SKILL,
            value={"name": "Python"},
            char_start=8,
            char_end=14,
            quoted_text="Python",
            extractor_version="test",
            status=ExtractionStatus.CONFIRMED,
        )
    )
    db_session.add(
        UserSkill(
            user_id=dev_user_id,
            name="Python",
            normalized_name="python",
            source_type=SkillSourceType.RESUME,
        )
    )
    await db_session.flush()
    await db_session.delete(resume)
    await db_session.flush()
    remaining = (
        await db_session.execute(text("SELECT count(*) FROM user_skills WHERE user_id = :id"),
                                 {"id": dev_user_id})
    ).scalar_one()
    assert remaining == 1, "a confirmed fact belongs to the person, not to the file"
```

- [ ] **Step 3: Run them and watch them fail**

```bash
cd services/api && python -m pytest tests/test_profile_models.py -q
```

Expected: `ImportError` on `UserSkill`. If instead every test *skips*, Postgres is unreachable — run `make up && make migrate` first, because a skipped guard is not a guard.

- [ ] **Step 4: Add the models**

In `services/api/nightshift/db/models.py`, extend `User` and add the four tables. Follow the file's existing style: docstrings that say why, `_enum(...)` for PG enums, explicit `Index` / `UniqueConstraint` / `CheckConstraint` in `__table_args__`.

```python
class UserSkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A skill the user **confirmed**. Never a proposal (invariant I2).

    `skill_id` is deliberately absent: the taxonomy is M3's, and this table
    stores the canonical name from `data/skills.yaml` with the vocabulary
    version that produced it. `confidence` from §6.2 is also absent — a
    confirmed skill has no confidence score, and a NULL-until-M3 column is
    shape with no use.
    """

    __tablename__ = "user_skills"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_user_skills_user_id_normalized_name"),
        CheckConstraint(
            "source_type <> 'inferred_pending_confirmation'",
            name="ck_user_skills_confirmed_only",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    proficiency_level: Mapped[ProficiencyLevel] = mapped_column(
        _enum(ProficiencyLevel, "proficiency_level"),
        nullable=False,
        server_default=text("'unspecified'"),
    )
    source_type: Mapped[SkillSourceType] = mapped_column(
        _enum(SkillSourceType, "skill_source_type"), nullable=False
    )
    #: Where it came from, in a form a human can follow back:
    #: ``resume:<uuid>#214-229`` or ``manual``.
    source_reference: Mapped[str | None] = mapped_column(String(200))
    vocabulary_version: Mapped[str | None] = mapped_column(String(40))
```

`UserProject` mirrors §6.3 (`name`, `summary`, `repository_url`, `demo_url`, `technologies` as `JSONB` array, `evidence` text, `start_date`, `end_date`, `status`), with a `UniqueConstraint("user_id", "name")` so confirming the same project twice updates rather than duplicates.

`Resume` carries `user_id`, `name`, `variant_type` (default `custom`), `source_kind`, `original_filename` (nullable — a paste has none), `parsed_text`, `content_hash` (`String(64)`, unique per user), `is_default`, with a docstring stating that **the uploaded bytes are never stored**.

`ResumeExtraction` carries `user_id`, `resume_id` (`ondelete="CASCADE"`), `kind`, `value` (`JSONB`), `char_start`, `char_end`, `quoted_text`, `extractor_version`, `status` (default `pending`), `decided_at` (nullable `UTCDateTime`), with:

```python
    __table_args__ = (
        CheckConstraint("char_start >= 0", name="ck_resume_extractions_span_starts_in_the_text"),
        CheckConstraint("char_end > char_start", name="ck_resume_extractions_span_is_not_empty"),
        CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL)",
            name="ck_resume_extractions_decided_rows_carry_a_time",
        ),
        Index("ix_resume_extractions_resume_id_status", "resume_id", "status"),
    )
```

On `User`, add:

```python
    #: A resume says "May 2027". It does not say a day, and inventing one to
    #: fill a DATE column is exactly the fabrication I1 forbids — the same
    #: reasoning that moved location off `jobs` in AMENDMENTS A2. M3's
    #: eligibility window needs a month and a year, which is what a resume
    #: actually says. ADR 0013.
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger)
    graduation_month: Mapped[int | None] = mapped_column(SmallInteger)
```

plus `degree`, `school`, `home_location_text` (`String`), `work_authorization` and `remote_preference` (PG enums, defaulted), `minimum_salary` (`Integer`, nullable), and `preferred_roles` / `preferred_locations` as `JSONB` arrays defaulting to `[]` — with a comment that nothing filters on them in M2, so a table would be shape with no use (`command-center.md` §2.3).

On `Application`, add:

```python
    #: M2b deferred this because there was no `resumes` table to point at and a
    #: dangling UUID is worse than an absent column (CLAUDE.md §7: FKs
    #: everywhere). M2c adds the column and its foreign key together.
    selected_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL")
    )
```

Table-level `CheckConstraint` on `users`:

```python
        CheckConstraint(
            "graduation_month IS NULL OR graduation_year IS NOT NULL",
            name="ck_users_graduation_month_needs_a_year",
        ),
        CheckConstraint(
            "graduation_month IS NULL OR graduation_month BETWEEN 1 AND 12",
            name="ck_users_graduation_month_is_a_month",
        ),
```

- [ ] **Step 5: Autogenerate the migration, then read every line of it**

```bash
cd services/api && alembic revision --autogenerate -m "profile and resumes"
```

Rename the file to `20260803_2100_profile_and_resumes.py` to match the house convention. **Then read it.** The note at the head of migration `0002` exists because autogenerate has twice emitted `nightshift.db.types.UTCDateTime` with no import, which is a `NameError` at upgrade time. Check specifically:

- every `sa.Enum(...)` has `create_type=False` handled the way the existing migrations do it, and each new PG enum type is created in `upgrade` and dropped in `downgrade`;
- `UTCDateTime` is imported if it appears;
- the `users` columns are added, not recreated.

- [ ] **Step 6: Add the trigger by hand**

Autogenerate cannot know about it. Append to the migration's `upgrade()`, after the tables exist:

```python
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_resume_span_must_quote_the_text()
        RETURNS trigger AS $$
        DECLARE
            source_text text;
        BEGIN
            SELECT parsed_text INTO source_text FROM resumes WHERE id = NEW.resume_id;
            IF source_text IS NULL THEN
                RAISE EXCEPTION 'resume % has no parsed text', NEW.resume_id;
            END IF;
            IF NEW.char_end > length(source_text) THEN
                RAISE EXCEPTION
                    'span [%,%) runs past the % characters of resume %',
                    NEW.char_start, NEW.char_end, length(source_text), NEW.resume_id;
            END IF;
            IF substring(source_text FROM NEW.char_start + 1
                         FOR NEW.char_end - NEW.char_start) <> NEW.quoted_text THEN
                RAISE EXCEPTION
                    'span [%,%) does not quote the resume text (invariant I2)',
                    NEW.char_start, NEW.char_end;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER resume_extractions_span_must_quote
        BEFORE INSERT OR UPDATE ON resume_extractions
        FOR EACH ROW EXECUTE FUNCTION nightshift_resume_span_must_quote_the_text();
        """
    )
```

and the mirror in `downgrade()`:

```python
    op.execute("DROP TRIGGER IF EXISTS resume_extractions_span_must_quote ON resume_extractions;")
    op.execute("DROP FUNCTION IF EXISTS nightshift_resume_span_must_quote_the_text();")
```

Postgres's `substring(... FROM n FOR count)` is 1-indexed; the spans are 0-indexed Python slices, which is why the offset is `NEW.char_start + 1`. Get this wrong by one and every honest proposal is refused, so step 8's positive test matters as much as the negative ones.

- [ ] **Step 7: Apply it both directions**

```bash
cd services/api && alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check
```

Expected: three clean runs and `No new upgrade operations detected.` A drift report here usually means an index declared in the migration but not on the model — M2a hit exactly that.

- [ ] **Step 8: Run the tests until green**

```bash
cd services/api && python -m pytest tests/test_profile_models.py -q
```

Expected: 9 passed, 0 skipped.

- [ ] **Step 9: Mutation-check the trigger and the constraint**

1. `DROP TRIGGER resume_extractions_span_must_quote ON resume_extractions;` in psql, run the suite. **Expected: exactly 2 fail** (`must_quote_the_resume_text`, `runs_past_the_text`). Re-apply with `alembic downgrade -1 && alembic upgrade head`.
2. Change `ck_user_skills_confirmed_only` to `CHECK (true)` in the database. **Expected: `test_a_confirmed_skill_cannot_be_marked_pending` fails.** Restore.

Record both counts in the commit message. A guard nobody has watched fail is not yet evidence.

- [ ] **Step 10: Commit**

```bash
make check
git add services/api/nightshift/db/base.py services/api/nightshift/db/models.py \
  services/api/migrations/versions/20260803_2100_profile_and_resumes.py \
  services/api/tests/test_profile_models.py
git commit -m "feat(profile): add resumes, proposals, and the span-quoting trigger"
```

---

### Task 5: The write layer — the one module that may confirm a fact

Everything that touches `users`' profile columns, `user_skills` or `user_projects` lives here. The guard that says so is a source-level test, and it is the load-bearing test of the whole milestone.

**Files:**
- Create: `services/api/nightshift/domain/profile.py`
- Create: `services/api/tests/test_profile.py`
- Create: `services/api/tests/test_nothing_infers.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `async create_resume(session, *, user_id, name, source_kind, original_filename, text, now) -> tuple[Resume, bool]` — the bool is "newly created"; re-uploading identical text returns the existing row.
  - `async propose_from_resume(session, *, resume, vocabulary=None) -> list[ResumeExtraction]`
  - `async confirm_extractions(session, *, user_id, resume_id, decisions: Mapping[UUID, Decision], now) -> ConfirmationResult`
  - `async update_profile(session, *, user_id, patch: ProfilePatch) -> User`
  - `async add_skill(session, *, user_id, name, proficiency_level, now) -> UserSkill`
  - `async remove_skill(session, *, user_id, skill_id) -> bool`
  - `async add_project(session, *, user_id, name, summary, evidence, ...) -> UserProject`
  - `async remove_project(session, *, user_id, project_id) -> bool`
  - `Decision = Literal["confirm", "reject"]`; dataclasses `ProfilePatch`, `ConfirmationResult(confirmed, rejected, skipped, skills_added, projects_added, profile_fields_set: tuple[str, ...])`.

- [ ] **Step 1: Write the failing tests**

`services/api/tests/test_profile.py` — the behaviour, against a real database:

```python
"""Promotion across the boundary, and everything that must not cross it."""
```

Cover, one test each:

1. `test_pasting_a_resume_stores_the_text_and_proposes_nothing_confirmed` — after `create_resume` + `propose_from_resume`, `user_skills` is empty, `users.graduation_year` is `NULL`, and the proposals are all `pending`. **This is invariant I2 stated as a test**, and it is the one to write first.
2. `test_confirming_a_skill_creates_exactly_that_skill` — confirm one proposal; assert the `user_skills` row, its `source_reference` (`resume:<uuid>#<start>-<end>`), and that no other proposal was promoted.
3. `test_rejecting_a_proposal_writes_nothing_but_the_decision` — status `rejected`, `decided_at` set, no confirmed row anywhere.
4. `test_confirming_a_graduation_sets_a_year_and_a_month_and_no_day` — `graduation_year == 2027`, `graduation_month == 5`.
5. `test_confirming_twice_is_idempotent` — second call reports `skipped=1` and changes nothing.
6. `test_re_uploading_the_same_resume_returns_the_same_row` — same text → same `Resume.id`, `created=False`, and proposals are not duplicated.
7. `test_a_different_resume_for_the_same_user_is_a_new_row` — one character changed → new row, new proposals.
8. `test_confirming_a_project_stores_its_bullets_as_evidence`.
9. `test_a_proposal_from_another_users_resume_cannot_be_confirmed` — build a second user, attempt cross-user confirm, expect the count of confirmed rows to be zero and the call to raise `ExtractionNotFoundError`. (A3: every query filters on `user_id`, and this is the test that proves the filter is real rather than decorative.)
10. `test_deleting_a_resume_leaves_confirmed_skills_alone` — mirrors the model test at the domain level.
11. `test_manual_skill_entry_does_not_need_a_resume` — `add_skill` with `source_type=manual` works with no resume at all, because §6.2's manual path is the fallback whenever extraction proves nothing.

`services/api/tests/test_nothing_infers.py` — the structural guard, modelled on `test_nothing_applies.py`:

```python
"""Invariant I2, asserted structurally rather than promised in a docstring.

`domain/profile.py` is the only module that may write a confirmed fact. The
claim is worth a test because it is the kind of thing that stays true until one
convenient afternoon — which is the same sentence `test_nothing_applies.py`
opens with, for the same reason.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "nightshift"
WRITER = ROOT / "domain" / "profile.py"

#: The columns that hold a confirmed claim about a person.
PROFILE_COLUMNS = (
    "graduation_year",
    "graduation_month",
    "degree",
    "school",
    "work_authorization",
    "home_location_text",
    "remote_preference",
    "minimum_salary",
    "preferred_roles",
    "preferred_locations",
)


def test_only_the_confirm_handler_writes_a_profile_column() -> None:
    # `=` but not `==`: `User.degree == value` is a filter, not a write. The
    # same subtlety bit M2b's stage guard, which matched a comparison and
    # hid a real bug.
    patterns = [re.compile(rf"\.{column}\s*=(?!=)") for column in PROFILE_COLUMNS]
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*.py")
        if path != WRITER and any(pattern.search(path.read_text()) for pattern in patterns)
    )
    assert offenders == [], f"these write a confirmed profile fact: {offenders}"


def test_only_the_confirm_handler_constructs_a_confirmed_row() -> None:
    constructor = re.compile(r"\b(UserSkill|UserProject)\s*\(")
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*.py")
        if path != WRITER and path != ROOT / "db" / "models.py" and constructor.search(path.read_text())
    )
    assert offenders == [], f"these construct a confirmed fact: {offenders}"


def test_the_extractor_is_not_imported_by_the_writer_of_confirmed_rows_alone() -> None:
    """`profile.py` may call the extractor; the extractor may not call back."""
    extractor = (ROOT / "domain" / "resume_extraction.py").read_text()
    assert "profile" not in extractor
```

- [ ] **Step 2: Run them and watch them fail**

```bash
cd services/api && python -m pytest tests/test_profile.py tests/test_nothing_infers.py -q
```

Expected: import error on `nightshift.domain.profile`.

- [ ] **Step 3: Write `domain/profile.py`**

Structure it as: exceptions, `ProfilePatch` / `ConfirmationResult` dataclasses, resume creation (hash + get-or-create), proposal writing, `confirm_extractions` with one `_promote_*` function per kind, then the manual entry points. Key decisions to implement exactly:

- `content_hash` is `hashlib.sha256(parsed_text.encode("utf-8")).hexdigest()` — the hash is over the *normalised text*, not the file, so a PDF and a paste of the same content are one resume.
- `propose_from_resume` is a no-op when the resume already has extractions. Re-proposing would strand the decisions already made against it.
- `confirm_extractions` loads only rows matching **both** `user_id` and `resume_id`, and raises `ExtractionNotFoundError` for any id it did not load. A silent skip here would make a cross-user confirm look successful.
- A proposal not in `pending` is counted in `skipped` and left alone.
- Promotion by kind: `skill` → upsert `UserSkill` on `(user_id, normalized_name)`; `graduation` → `graduation_year` / `graduation_month`; `degree` → `degree`; `school` → `school`; `project` → upsert `UserProject` on `(user_id, name)`.
- `source_reference` is `f"resume:{resume_id}#{char_start}-{char_end}"` so the evidence is followable from the row alone.
- Every promotion sets `source_type=SkillSourceType.RESUME`; `add_skill` sets `MANUAL`.

- [ ] **Step 4: Run the tests until green**

```bash
cd services/api && python -m pytest tests/test_profile.py tests/test_nothing_infers.py -q
```

Expected: 14 passed, 0 skipped.

- [ ] **Step 5: Mutation-check the guard itself**

The structural test is the milestone's most important and the easiest to write vacuously:

1. In `services/api/nightshift/api/routes/jobs.py`, temporarily add `user.degree = "BS"` inside any handler. **Expected: `test_only_the_confirm_handler_writes_a_profile_column` fails and names `api/routes/jobs.py`.** Revert.
2. Temporarily add `UserSkill(user_id=user_id, name="x")` to the same handler. **Expected: `test_only_the_confirm_handler_constructs_a_confirmed_row` fails.** Revert.
3. In `confirm_extractions`, remove the `user_id` filter from the load. **Expected: `test_a_proposal_from_another_users_resume_cannot_be_confirmed` fails.** Revert.

If mutation 1 passes, the regex is wrong — the most likely cause is matching only `self.` forms.

- [ ] **Step 6: Commit**

```bash
make check
git add services/api/nightshift/domain/profile.py services/api/tests/test_profile.py \
  services/api/tests/test_nothing_infers.py
git commit -m "feat(profile): promote a proposal only through the one confirm handler"
```

---

### Task 6: The routes

Routes validate and delegate (CLAUDE.md §3). Nothing here decides anything.

**Files:**
- Create: `services/api/nightshift/api/routes/profile.py`
- Create: `services/api/nightshift/api/routes/resumes.py`
- Modify: `services/api/nightshift/api/schemas.py`
- Modify: `services/api/nightshift/api/main.py` (register both routers)
- Modify: `services/api/nightshift/api/routes/applications.py` (remove the "Selected resume" deferred entry; accept `selected_resume_id` in `ApplicationPatchIn`)
- Create: `services/api/tests/test_profile_routes.py`

**Interfaces:**
- Consumes: Task 5's functions.
- Produces: `GET /profile`, `PATCH /profile`, `POST /profile/skills`, `DELETE /profile/skills/{skill_id}`, `POST /profile/projects`, `DELETE /profile/projects/{project_id}`, `POST /resumes/paste`, `POST /resumes/upload`, `GET /resumes`, `GET /resumes/{resume_id}`, `PATCH /resumes/{resume_id}`, `DELETE /resumes/{resume_id}`, `POST /resumes/{resume_id}/confirm`.

- [ ] **Step 1: Write the failing route tests**

`services/api/tests/test_profile_routes.py`, following `test_application_routes.py`'s client fixture. One test each:

1. `test_the_profile_starts_empty_and_says_what_is_not_confirmed` — `GET /profile` returns nulls, empty skill and project lists, and a non-empty `deferred_fields`.
2. `test_pasting_a_resume_returns_proposals_and_confirms_nothing` — `POST /resumes/paste` with the fixture text; response has proposals with spans; a following `GET /profile` is still empty.
3. `test_every_proposal_in_the_response_quotes_the_parsed_text` — slice `parsed_text` by each span and compare. **The API's own copy of the trigger's promise**, so a serialisation bug that shifts an offset is caught at the boundary the browser reads.
4. `test_uploading_a_pdf_returns_the_same_facts_as_pasting_it` — multipart upload of the fixture PDF.
5. `test_uploading_a_docx_is_refused_with_a_message_naming_the_format` — 415 with `.docx` in the detail.
6. `test_uploading_a_scan_is_refused_and_offers_paste` — 422 with "paste" in the detail.
7. `test_confirming_promotes_only_what_was_confirmed` — confirm one skill, reject one; `GET /profile` shows exactly one skill.
8. `test_confirming_an_unknown_extraction_is_404_and_promotes_nothing`.
9. `test_a_resume_that_proves_nothing_says_so` — paste `prose_only.txt`; response has zero proposals and the API's `nothing_proven` flag is true.
10. `test_deleting_a_resume_keeps_the_skills_it_produced`.
11. `test_an_application_can_select_a_resume` — `PATCH /applications/{id}` with `selected_resume_id`, and the detail response echoes it.
12. `test_the_deferred_list_no_longer_names_the_resume` — asserts "Selected resume" has left `DEFERRED_FIELDS`, so the UI cannot keep claiming a shipped feature is missing.

- [ ] **Step 2: Run them and watch them fail**

```bash
cd services/api && python -m pytest tests/test_profile_routes.py -q
```

Expected: 404s and import errors.

- [ ] **Step 3: Write the schemas**

In `services/api/nightshift/api/schemas.py`, add `ProfileOut`, `ProfilePatchIn`, `SkillIn`, `SkillOut`, `ProjectIn`, `ProjectOut`, `ResumeOut`, `ResumeDetailOut` (carrying `parsed_text`, `extractions`, `nothing_proven: bool`), `ExtractionOut` (`id`, `kind`, `value`, `char_start`, `char_end`, `quoted_text`, `status`), `ConfirmIn` (`decisions: list[ExtractionDecisionIn]`), and `ConfirmationOut`. Add a `DeferredProfileFieldOut` list naming what M2c does not do, in the same shape the applications route already uses:

```python
DEFERRED_PROFILE_FIELDS: tuple[DeferredProfileFieldOut, ...] = (
    DeferredProfileFieldOut(
        name="Skill proficiency from a resume",
        blocked_on="never",
        reason="a resume cannot show how well someone knows a thing, so the "
        "level is yours to set and nothing infers it (I2)",
    ),
    DeferredProfileFieldOut(
        name="Work authorization from a resume",
        blocked_on="never",
        reason="a claim about legal status is confirmed in a form, never read "
        "off a page — the extractor has no rule that could produce one",
    ),
    DeferredProfileFieldOut(
        name="Skill taxonomy and aliases",
        blocked_on="M3",
        reason="M2c matches a starter vocabulary in data/skills.yaml; the "
        "taxonomy proper, with its evidence graph, is M3's",
    ),
    DeferredProfileFieldOut(
        name=".docx upload",
        blocked_on="unscheduled",
        reason="one parser at a time in the slice with the most invariant "
        "risk; paste the text instead",
    ),
)
```

- [ ] **Step 4: Write the routers**

`api/routes/resumes.py` handles the two intake shapes as two routes rather than one content-type-sniffing handler. Both end in the same three calls — `read` (or take the paste), `create_resume`, `propose_from_resume` — so there is one code path to be wrong in:

```python
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user_id: CurrentUserId,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
) -> ResumeDetailOut:
    data = await file.read()
    try:
        text = read_resume_bytes(data=data, filename=file.filename or "")
    except UnsupportedResumeFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=exc.user_message
        ) from exc
    except ResumeTextError as exc:
        # 422, not 500: the file is the problem and the message says how to
        # get past it. `command-center.md` §6.2 — failure is stated, never filled.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.user_message
        ) from exc
    ...
```

`DELETE /resumes/{id}` returns 204 and its docstring states that confirmed facts survive, because that is a product decision a reader will otherwise assume the other way.

- [ ] **Step 5: Register the routers and update the applications route**

In `api/main.py`, include both. In `api/routes/applications.py`, delete the `"Selected resume"` entry from `DEFERRED_FIELDS`, add `selected_resume_id` to `ApplicationPatchIn`, and let `update_details` carry it — it already writes a `detail_updated` event, so selecting a resume gets history for free.

- [ ] **Step 6: Run the tests until green**

```bash
cd services/api && python -m pytest tests/test_profile_routes.py -q
```

Expected: 12 passed, 0 skipped.

- [ ] **Step 7: Commit**

```bash
make check
git add services/api/nightshift/api services/api/tests/test_profile_routes.py
git commit -m "feat(api): add profile and resume routes, and select a resume on an application"
```

---

### Task 7: Web schemas and the client

**Files:**
- Modify: `apps/web/src/lib/schemas.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/lib/schemas.test.ts`

**Interfaces:**
- Produces: `profileSchema`, `resumeSchema`, `resumeDetailSchema`, `extractionSchema`, `confirmationSchema` and their inferred types; client functions `fetchProfile`, `patchProfile`, `addSkill`, `removeSkill`, `addProject`, `removeProject`, `listResumes`, `pasteResume`, `uploadResume`, `fetchResume`, `confirmExtractions`, `deleteResume`.

- [ ] **Step 1: Write the failing schema tests**

The one that matters mirrors the database trigger on the client side:

```typescript
it('refuses a proposal whose quoted text does not match its span', () => {
  const proposal = {
    id: '0f3d...',
    kind: 'skill',
    value: { name: 'Python' },
    char_start: 8,
    char_end: 14,
    quoted_text: 'Rust',
    status: 'pending',
  };
  expect(() => extractionSchema.parse(proposal)).toThrow();
});
```

`extractionSchema` uses `superRefine` to assert `char_end > char_start` and `quoted_text.length === char_end - char_start`. It cannot check the text itself — the resume text lives on the parent — so `resumeDetailSchema` adds a second `superRefine` that slices `parsed_text` by every span and compares. Write a test for that too, with a proposal whose span points at the wrong words.

**Watch for the M2b trap:** three Zod tests there passed before the schema existed, because `undefined.parse()` throws and the test only asserted "throws". Every negative test here must also have a positive twin that parses successfully, or it proves nothing.

- [ ] **Step 2: Run, fail, implement, run**

```bash
cd apps/web && npm run test -- schemas
```

- [ ] **Step 3: Add the client functions**

`uploadResume` is the only one that does not send JSON:

```typescript
export async function uploadResume(file: File): Promise<ResumeDetail> {
  const body = new FormData();
  body.append('file', file);
  // No Content-Type header: the browser sets the multipart boundary, and
  // setting it by hand produces a request the server cannot parse.
  return parseResponse(
    await fetch(`${API_BASE_URL}/resumes/upload`, { method: 'POST', body }),
    resumeDetailSchema,
  );
}
```

- [ ] **Step 4: Commit**

```bash
make check
git add apps/web/src/lib
git commit -m "feat(web): add profile and resume schemas and client calls"
```

---

### Task 8: The profile page

**Files:**
- Create: `apps/web/src/components/ProfileForm.tsx`
- Create: `apps/web/src/components/ProfileForm.test.tsx`
- Create: `apps/web/src/components/SkillList.tsx`
- Create: `apps/web/src/components/SkillList.test.tsx`
- Create: `apps/web/src/components/ResumeUpload.tsx`
- Create: `apps/web/src/components/ResumeUpload.test.tsx`
- Create: `apps/web/src/app/operate/profile/page.tsx`
- Modify: `apps/web/src/app/operate/page.tsx` (link to it)

- [ ] **Step 1: Write the failing component tests**

Cover: the form renders every profile field with its current value; an empty profile renders "not set" rather than a blank input with no label; the skill list shows each skill's source (`from your resume` / `added by you`) and, for a resume skill, the quoted words it came from; `ResumeUpload` offers paste and file side by side and **names `.docx` as unsupported before the user tries it**; a failed upload renders the API's message and keeps the paste box available.

- [ ] **Step 2: Implement the components, then the page**

Keep the page thin — data in, components out. Domain logic never lives in a component (CLAUDE.md §3).

The profile page also renders `deferred_fields` from the API, the same way the filter panel and the application page do. This is the I7 surface for M2c: what the product does *not* infer is stated on the page where somebody would expect it to.

- [ ] **Step 3: Add the colour assertions**

Any new token in `colour-contrast.test.ts`, per CLAUDE.md §7. If the highlight colours are introduced here rather than in Task 9, they need their assertions here.

- [ ] **Step 4: Commit**

```bash
make check
git add apps/web/src/components apps/web/src/app/operate
git commit -m "feat(web): add the profile page, the skill list and the resume upload"
```

---

### Task 9: The confirmation screen

The screen the whole slice exists for. Two panes: the proposals, and the resume text with their spans highlighted.

**Files:**
- Create: `apps/web/src/components/HighlightedText.tsx`
- Create: `apps/web/src/components/HighlightedText.test.tsx`
- Create: `apps/web/src/components/ExtractionReview.tsx`
- Create: `apps/web/src/components/ExtractionReview.test.tsx`
- Create: `apps/web/src/app/operate/resumes/[id]/page.tsx`

- [ ] **Step 1: Write `HighlightedText`'s tests first — it is the subtle one**

Spans overlap by design: a project's span contains the skills inside it. The component splits the text at every span boundary and styles each segment by what covers it.

The strongest test is a property, and it must run against overlapping input:

```typescript
it('renders every character of the text exactly once, even when spans overlap', () => {
  const text = 'Transit Delay Tracker - Python, PostgreSQL';
  render(
    <HighlightedText
      text={text}
      spans={[
        { id: 'project', start: 0, end: 41 },
        { id: 'python', start: 24, end: 30 },
        { id: 'postgres', start: 32, end: 42 },
      ]}
      activeId="python"
    />,
  );
  expect(screen.getByTestId('highlighted-text').textContent).toBe(text);
});
```

Also test: a span at position 0; a span ending at the last character; adjacent spans with no gap; an empty span list rendering the plain text; the active span carrying a distinct class from the inactive ones.

- [ ] **Step 2: Implement `HighlightedText`**

Collect all boundaries, sort them, walk the segments, and for each segment find the covering spans. No `dangerouslySetInnerHTML` anywhere — the resume text is user data and goes in as text nodes.

- [ ] **Step 3: `ExtractionReview` and the page**

Behaviour to test:

- every proposal row shows its kind, its proposed value, and the words it came from;
- clicking a row makes it the active span and the text pane scrolls to it;
- **nothing is pre-confirmed** — the confirm buttons start unpressed and the page states that nothing has been saved to the profile yet. Assert this; it is invariant I2 in the browser.
- confirming sends only the chosen ids;
- a resume with zero proposals renders "Nothing could be proven from this file" and a link to the manual form, not an empty list (§6.2, and I7).

- [ ] **Step 4: Commit**

```bash
make check
git add apps/web/src/components apps/web/src/app/operate/resumes
git commit -m "feat(web): add the confirmation screen, highlighting the words each claim came from"
```

---

### Task 10: The loop, end to end — browser test and `verify.py`

**Files:**
- Create: `apps/web/e2e-seeded/profile.spec.ts`
- Modify: `scripts/verify.py`

- [ ] **Step 1: Write the seeded browser test**

`apps/web/e2e-seeded/profile.spec.ts`. It must **normalise what it finds on entry** rather than trusting its own tidy exit — M2b's pipeline test could not run twice for exactly that reason, and this one creates rows too.

The walk:

1. Open `/operate/profile`. Delete any resume left by a previous run.
2. Paste the fixture resume text. Land on the confirmation screen.
3. Assert proposals are listed, each showing the words it came from.
4. **Assert the profile still shows no confirmed skills** — go back and check. This is the criterion, in a browser.
5. Confirm one skill and the graduation date; reject one skill.
6. Assert the profile now shows exactly that skill and that graduation, the rejected one is absent, and the skill names the resume as its source.
7. Reload; assert it persisted.
8. Paste the prose-only fixture; assert "Nothing could be proven" and that the profile is unchanged.
9. Delete the resumes it created; assert the confirmed skill survives, then remove it so the run is repeatable.

- [ ] **Step 2: Add a `verify.py` check**

`check_profile_confirmation`, in the style of the existing checks: paste a resume through the API, assert proposals came back with spans that quote the text, assert the profile is unchanged, confirm one, assert it landed, then clean up both the resume and the skill. State in the docstring what it leaves behind, if anything — `check_application_tracking` set that precedent.

- [ ] **Step 3: Run the three commands**

```bash
make check
make acceptance
make test-e2e
```

Read the counts out of the output rather than inferring them. Run `make acceptance` **three times back to back** — that is the idempotency evidence, and it is how M2b caught a test that could not run twice.

- [ ] **Step 4: Commit**

```bash
git add apps/web/e2e-seeded/profile.spec.ts scripts/verify.py
git commit -m "test(profile): walk paste, review, confirm and reject in a browser"
```

---

### Task 11: ADR, review, PROGRESS

- [ ] **Step 1: Write `docs/adr/0013-resume-facts-are-proposals-with-spans.md`**

Record three decisions and the reasoning behind each: the two-table split with one writer; the span-quoting trigger (why a check constraint could not do it, and the 1-indexing detail); and **`graduation_year` + `graduation_month` instead of §6.1's `graduation_date`**, on the same grounds as AMENDMENTS A2 — a resume says a month, and a DATE column would require inventing a day. Name the two dependencies and their $0 cost (A9).

- [ ] **Step 2: Write `docs/reviews/milestone-2c-review.md`**

Per CLAUDE.md §5, actively look for: hallucinated certainty, silent data loss, wrong merges, tests that assert nothing. Specific to this slice, check for:

- a proposal that survives a resume edit and now quotes the wrong words;
- a confirmed skill whose `source_reference` points at a deleted resume;
- an upload path that logs the resume text (it is the most personal data in the project — §13);
- whether `make acceptance` leaves rows behind, and whether that is stated;
- whether any test would still pass with the extractor returning `[]`.

- [ ] **Step 3: Update `docs/PROGRESS.md`**

Walk M2's acceptance criteria and record concrete evidence for criterion 4 — *no parsed resume fact is stored as confirmed without a user action* — naming the test, the trigger, the structural guard, and the mutation results that showed each able to fail. Record what M2c found that this plan did not predict; every milestone so far has found six or more defects in code that reported success, and writing them down is how the next plan gets better.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin m2c-profile-and-resume
gh pr create --title "M2c — profile and resume: proposals with spans" --body "..."
```

Then check the run, read the job counts out of the logs, and verify `git diff <last-code-commit>..HEAD --stat` lists nothing outside `docs/` before merging.

---

## Self-review of this plan

**Spec coverage.** `command-center.md` §6.1's four proposal kinds → Task 3 (skill, graduation, degree/school, project). §6.2's two failure rules → Task 1 (fail whole) and Tasks 6/9 (nothing proven). §6.3's synthetic fixtures → Task 1. §2.2's two-table split → Tasks 4–5. §2.3's `users` columns → Task 4. §8's testing table: separate tables ✓ (Task 4), structural write test ✓ (Task 5), extraction determinism ✓ (Task 3), a proposal becoming confirmed without a click ✓ (Tasks 5, 9, 10). PRODUCT-SPEC §6.1–6.4 fields are all in Task 4 except the three named in "deliberately not built" with reasons.

**Known gap, deliberate.** §12.1's guided first-run wizard is not built. M2c ships the profile page and the confirmation screen; sequencing them into a ten-step first run needs the daily queue and the match list that steps 9–10 of §12.1 refer to. Record it in PROGRESS as deferred to M2d rather than leaving it unstated.

**Type consistency.** `ResumeFormat` (Task 1) and `ResumeSourceKind` (Task 4) share their three values and Task 4 tests that they agree. `ProposalKind` (Task 3) and `ExtractionKind` (Task 4) share their five values. `Proposal.as_dict()` (Task 3) is what the golden file and Task 5's row writer both consume. `extractionSchema` (Task 7) mirrors `ExtractionOut` (Task 6).
