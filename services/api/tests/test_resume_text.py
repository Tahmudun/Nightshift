"""The text layer: three inputs, one output, and failure that is whole.

Nothing here knows what a resume *means*. These tests are about the boundary
between a file somebody handed us and the string every span in
``resume_extractions`` is measured against.
"""

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

    What must survive the round trip is the content the extractor reads.
    """
    text = read_resume_bytes(
        data=(FIXTURES / "nadia_okonkwo.pdf").read_bytes(), filename="nadia_okonkwo.pdf"
    )
    for phrase in ("NADIA OKONKWO", "EDUCATION", "Bachelor of Science", "May 2027", "Playwright"):
        assert phrase in text, f"the PDF path lost {phrase!r}"


def test_a_scanned_pdf_fails_whole_and_says_why() -> None:
    with pytest.raises(ResumeTextError) as caught:
        read_resume_bytes(data=(FIXTURES / "no_text_scan.pdf").read_bytes(), filename="scan.pdf")
    assert "paste" in caught.value.user_message.lower()


def test_a_corrupt_pdf_fails_whole() -> None:
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=(FIXTURES / "corrupt.pdf").read_bytes(), filename="corrupt.pdf")


def test_an_encrypted_pdf_fails_whole_and_names_the_reason() -> None:
    with pytest.raises(ResumeTextError) as caught:
        read_resume_bytes(data=(FIXTURES / "encrypted.pdf").read_bytes(), filename="encrypted.pdf")
    assert "password" in caught.value.user_message.lower()


def test_a_docx_is_refused_by_name_rather_than_mangled() -> None:
    with pytest.raises(UnsupportedResumeFormatError) as caught:
        read_resume_bytes(data=b"PK\x03\x04anything", filename="resume.docx")
    message = caught.value.user_message.lower()
    assert ".docx" in message and "paste" in message


def test_an_unknown_extension_is_refused_with_the_formats_we_do_read() -> None:
    with pytest.raises(UnsupportedResumeFormatError) as caught:
        read_resume_bytes(data=b"anything", filename="resume.xyz")
    message = caught.value.user_message.lower()
    assert "pdf" in message and "paste" in message


def test_an_oversized_upload_is_refused_before_it_is_parsed() -> None:
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=b"x" * (MAX_UPLOAD_BYTES + 1), filename="huge.txt")


def test_undecodable_bytes_fail_whole_rather_than_dropping_characters() -> None:
    """``errors="replace"`` would silently turn a name into U+FFFD. I2's spirit."""
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=b"\xff\xfe\x00valid?", filename="resume.txt")


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(ResumeTextError):
        read_resume_bytes(data=b"   \n\n  ", filename="empty.txt")


def test_normalisation_is_idempotent() -> None:
    """Every stored span indexes into this output, so it may not move."""
    once = normalize_text("Café\r\n\r\n\r\nRésumé  \nfiﬁ")
    assert normalize_text(once) == once


def test_normalisation_folds_ligatures_so_a_skill_can_be_matched() -> None:
    assert normalize_text("conﬁg") == "config"


def test_normalisation_removes_control_characters_a_reader_cannot_see() -> None:
    """A span counts characters. Counting invisible ones makes it point wrong."""
    assert normalize_text("Pyth\x00on\x07") == "Python"


def test_format_is_decided_by_extension_case_insensitively() -> None:
    assert format_for_filename("Resume.PDF") == "pdf"
    assert format_for_filename("resume.txt") == "txt"
