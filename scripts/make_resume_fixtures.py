"""Generate the committed synthetic resume PDFs from the committed .txt.

Run by hand; the outputs are committed. Everything here is byte-deterministic
except ``encrypted.pdf``: PDF encryption seeds a random file ID, so re-running
changes that one file and only that one. Nothing else uses a timestamp, a UUID
or a random value.

    python scripts/make_resume_fixtures.py

The people in these files are invented. Real resumes are never committed and
are never written to disk by this project at all — an upload is read in memory
and discarded once its text has been extracted.
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
            b"<< /Length "
            + str(len(content)).encode()
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
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
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
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
