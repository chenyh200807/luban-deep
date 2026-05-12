"""Document text extraction for uploaded bytes and local files."""

from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import re
from typing import Any
import zipfile
from xml.etree import ElementTree

from deeptutor.services.rag.components.routing import FileTypeRouter

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

TEXT_LIKE_EXTENSIONS: frozenset[str] = frozenset(FileTypeRouter.TEXT_EXTENSIONS)
OFFICE_EXTENSIONS: frozenset[str] = frozenset(FileTypeRouter.PARSER_EXTENSIONS) | {".docx"}
SUPPORTED_DOC_EXTENSIONS: frozenset[str] = OFFICE_EXTENSIONS | TEXT_LIKE_EXTENSIONS

MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS_PER_DOC = 200_000


class DocumentExtractionError(Exception):
    def __init__(self, message: str, filename: str = "") -> None:
        super().__init__(message)
        self.filename = filename


class UnsupportedDocumentError(DocumentExtractionError):
    pass


class CorruptDocumentError(DocumentExtractionError):
    pass


class EmptyDocumentError(DocumentExtractionError):
    pass


class DocumentTooLargeError(DocumentExtractionError):
    pass


def _ext(filename: str) -> str:
    return PurePosixPath(filename or "").suffix.lower()


def is_document_extension(filename: str) -> bool:
    return _ext(filename) in SUPPORTED_DOC_EXTENSIONS


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"... (truncated, {len(text)} chars total)"


def extract_text_from_bytes(
    filename: str,
    data: bytes,
    *,
    max_bytes: int | None = MAX_DOC_BYTES,
    max_chars: int | None = MAX_EXTRACTED_CHARS_PER_DOC,
) -> str:
    if not data:
        raise EmptyDocumentError(f"{filename} is empty", filename=filename)
    if max_bytes is not None and len(data) > max_bytes:
        raise DocumentTooLargeError(
            f"{filename} exceeds the {max_bytes // (1024 * 1024)} MB per-file limit",
            filename=filename,
        )

    ext = _ext(filename)
    if ext not in SUPPORTED_DOC_EXTENSIONS:
        raise UnsupportedDocumentError(
            f"{filename} has unsupported extension '{ext}'",
            filename=filename,
        )

    if ext == ".pdf":
        text = _extract_pdf(data, filename)
    elif ext == ".docx":
        text = _extract_docx_ooxml(data, filename)
    else:
        text = _extract_text_like(data)

    if not text.strip():
        raise EmptyDocumentError(f"{filename}: no extractable text", filename=filename)
    return _truncate(text, max_chars) if max_chars is not None else text


def extract_text_from_path(
    file_path: str | Path,
    *,
    max_bytes: int | None = MAX_DOC_BYTES,
    max_chars: int | None = MAX_EXTRACTED_CHARS_PER_DOC,
) -> str:
    path = Path(file_path)
    return extract_text_from_bytes(
        path.name,
        path.read_bytes(),
        max_bytes=max_bytes,
        max_chars=max_chars,
    )


def _extract_pdf(data: bytes, filename: str) -> str:
    if fitz is None:
        raise CorruptDocumentError(
            f"{filename}: no PDF reader available",
            filename=filename,
        )
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.is_encrypted and not doc.authenticate(""):
                raise CorruptDocumentError(
                    f"{filename} is encrypted and cannot be read",
                    filename=filename,
                )
            return "\n\n".join(
                f"--- Page {i} ---\n{page.get_text() or ''}" for i, page in enumerate(doc, 1)
            )
    except CorruptDocumentError:
        raise
    except Exception as exc:
        raise CorruptDocumentError(
            f"{filename}: failed to read PDF ({exc})",
            filename=filename,
        ) from exc


def _extract_docx_ooxml(data: bytes, filename: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except Exception as exc:
        raise CorruptDocumentError(
            f"{filename} does not look like a valid docx file",
            filename=filename,
        ) from exc

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise CorruptDocumentError(
            f"{filename}: failed to parse docx XML",
            filename=filename,
        ) from exc

    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(
            node.text or ""
            for node in paragraph.iter(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
            )
        )
        if text.strip():
            paragraphs.append(text)
    if paragraphs:
        return "\n\n".join(paragraphs)

    # Some minimal OOXML fixtures omit namespaces; keep a small fallback.
    text_chunks = re.findall(rb"<w:t[^>]*>(.*?)</w:t>", xml_bytes, flags=re.DOTALL)
    return "\n".join(chunk.decode("utf-8", errors="replace") for chunk in text_chunks)


def _extract_text_like(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "latin-1", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_documents_from_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract text from attachment-like records containing filename and bytes/base64 data."""
    extracted: list[dict[str, str]] = []
    for record in records:
        filename = str(record.get("filename") or record.get("name") or "")
        raw = record.get("bytes")
        if raw is None:
            raw = record.get("data")
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not isinstance(raw, bytes) or not is_document_extension(filename):
            continue
        extracted.append({"filename": filename, "text": extract_text_from_bytes(filename, raw)})
    return extracted
