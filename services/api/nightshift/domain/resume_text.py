"""Turning what a person handed us into the text the extractor reads.

Three inputs and one output. A paste is text already; a ``.txt`` is bytes to
decode; a PDF is bytes for ``pypdf``. Anything else is refused **by name**, with
paste offered as the way around it — a format we cannot read is a fact worth
stating, not a silent no-op.

**Failure is whole** (``command-center.md`` §6.2). There is no partial parse and
no salvaged first page. A resume half-read is a resume whose missing half looks
exactly like a qualification the person does not have, which is invariant I2
failing quietly instead of loudly.

Nothing here touches the database, and nothing here decides what any of the text
*means*. That is ``resume_extraction.py``, which cannot import the ORM either.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import PurePosixPath
from typing import Literal, get_args

from pypdf import PdfReader
from pypdf.errors import PyPdfError

#: 2 MB. A text resume is a few kilobytes; a PDF carrying a photograph is a few
#: hundred. Past this it is not a resume, and parsing it first to find that out
#: is work done on a caller's say-so.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

#: A resume is one or two pages. Twenty is generous and bounds the work a single
#: request can ask for.
MAX_PDF_PAGES = 20

ResumeFormat = Literal["paste", "txt", "pdf"]

#: The values of ``ResumeFormat``, for the test that keeps the database enum and
#: this module from drifting apart.
RESUME_FORMATS: tuple[str, ...] = get_args(ResumeFormat)

#: Extensions people actually try, each answered by name rather than by a
#: generic refusal. Being told "we do not read .pages, paste instead" is a
#: better experience than "unsupported file".
_NAMED_UNSUPPORTED = (
    ".docx",
    ".doc",
    ".rtf",
    ".odt",
    ".pages",
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
)


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

    Every character offset stored in ``resume_extractions`` indexes into the
    output of this function, so normalisation may never run twice with different
    results — ``test_normalisation_is_idempotent`` is what holds that.

    NFKC is not cosmetic here: a PDF renders "config" with an fi-ligature, and
    without folding it the string never matches a vocabulary term.
    """
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Control characters other than tab and newline carry no meaning in a resume
    # and would make a span count characters a reader cannot see.
    text = "".join(char for char in text if char in "\n\t" or unicodedata.category(char)[0] != "C")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_for_filename(filename: str) -> ResumeFormat:
    """Decide the reader from the extension, or refuse by name."""
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
            f"That file is {len(data) // 1024} KB and the limit is {MAX_UPLOAD_BYTES // 1024} KB."
        )
    resume_format = format_for_filename(filename)
    if resume_format == "pdf":
        return _read_pdf(data)

    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Deliberately not `errors="replace"`. Replacing turns a person's name
        # into U+FFFD and reports success, which is the failure mode this whole
        # slice exists to avoid.
        raise ResumeTextError(
            "This file is not valid UTF-8 text. Paste the text of your resume instead."
        ) from exc
    text = normalize_text(decoded)
    if not text:
        raise ResumeTextError("That file is empty.")
    return text
