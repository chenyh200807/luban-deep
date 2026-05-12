"""Document text extraction for chat attachments."""

from __future__ import annotations

import base64
from collections.abc import Iterable
import io
import logging
from pathlib import Path, PurePosixPath
import re
from typing import Any
import xml.etree.ElementTree as ElementTree
import zipfile

from deeptutor.services.rag.components.routing import FileTypeRouter

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

logger = logging.getLogger(__name__)

TEXT_LIKE_EXTENSIONS: frozenset[str] = frozenset(FileTypeRouter.TEXT_EXTENSIONS)
OFFICE_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".xlsx", ".pptx"})
SUPPORTED_DOC_EXTENSIONS: frozenset[str] = TEXT_LIKE_EXTENSIONS | OFFICE_EXTENSIONS

MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_TOTAL_DOC_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARS_PER_DOC = 200_000
MAX_EXTRACTED_CHARS_TOTAL = 150_000


class DocumentExtractionError(Exception):
    """Base class for user-readable extraction failures."""

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


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "latin-1", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


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
            f"{filename} has unsupported extension '{ext}'", filename=filename
        )

    if ext == ".pdf":
        text = _extract_pdf(data, filename)
    elif ext == ".docx":
        text = _extract_docx_ooxml(data, filename)
    elif ext == ".xlsx":
        text = _extract_xlsx_ooxml(data, filename)
    elif ext == ".pptx":
        text = _extract_pptx_ooxml(data, filename)
    else:
        text = _decode_text(data)

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
    if not data.startswith(b"%PDF-"):
        raise CorruptDocumentError(f"{filename} does not look like a PDF", filename=filename)
    if fitz is None:
        raise CorruptDocumentError(
            f"{filename}: no PDF reader available (install PyMuPDF)",
            filename=filename,
        )
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.is_encrypted and not doc.authenticate(""):
                raise CorruptDocumentError(
                    f"{filename} is encrypted and cannot be read", filename=filename
                )
            return "\n\n".join(
                f"--- Page {i} ---\n{page.get_text() or ''}"
                for i, page in enumerate(doc, 1)
            )
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise CorruptDocumentError(
            f"{filename}: failed to read PDF ({exc})", filename=filename
        ) from exc


def _open_ooxml(data: bytes, filename: str) -> zipfile.ZipFile:
    if not data.startswith(b"PK\x03\x04"):
        raise CorruptDocumentError(
            f"{filename} does not look like a valid Office file", filename=filename
        )
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError(
            f"{filename}: failed to open Office ZIP package ({exc})", filename=filename
        ) from exc


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_xml_member(zf: zipfile.ZipFile, member: str, filename: str) -> Any | None:
    try:
        raw = zf.read(member)
    except KeyError:
        return None
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise CorruptDocumentError(
            f"{filename}: failed to parse {member} ({exc})", filename=filename
        ) from exc


def _collect_ooxml_text(node: Any) -> str:
    parts: list[str] = []
    for child in node.iter():
        name = _local_name(child.tag)
        if name == "t" and child.text:
            parts.append(child.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _extract_paragraph_text(root: Any) -> list[str]:
    paragraphs: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) == "p":
            text = _collect_ooxml_text(node)
            if text:
                paragraphs.append(text)
    if paragraphs:
        return paragraphs
    text = _collect_ooxml_text(root)
    return [text] if text else []


def _extract_docx_ooxml(data: bytes, filename: str) -> str:
    with _open_ooxml(data, filename) as zf:
        members = ["word/document.xml"]
        members.extend(
            sorted(
                name
                for name in zf.namelist()
                if re.match(r"word/(header|footer|footnotes|endnotes|comments)\d*\.xml$", name)
            )
        )
        chunks: list[str] = []
        for member in members:
            root = _parse_xml_member(zf, member, filename)
            if root is not None:
                chunks.extend(_extract_paragraph_text(root))
        return "\n\n".join(chunks)


def _extract_xlsx_ooxml(data: bytes, filename: str) -> str:
    with _open_ooxml(data, filename) as zf:
        sheet_members = sorted(
            name for name in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name)
        )
        sheets: list[str] = []
        for index, member in enumerate(sheet_members, 1):
            root = _parse_xml_member(zf, member, filename)
            if root is None:
                continue
            rows: list[str] = []
            for row in root.iter():
                if _local_name(row.tag) != "row":
                    continue
                cells = [
                    _collect_ooxml_text(cell)
                    for cell in row
                    if _local_name(cell.tag) in {"c", "is"}
                ]
                row_text = "\t".join(cell for cell in cells if cell)
                if row_text:
                    rows.append(row_text)
            if rows:
                sheets.append(f"--- Sheet {index} ---\n" + "\n".join(rows))
        return "\n\n".join(sheets)


def _extract_pptx_ooxml(data: bytes, filename: str) -> str:
    with _open_ooxml(data, filename) as zf:
        slide_members = sorted(
            name for name in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)
        )
        slides: list[str] = []
        for index, member in enumerate(slide_members, 1):
            root = _parse_xml_member(zf, member, filename)
            if root is None:
                continue
            paragraphs = _extract_paragraph_text(root)
            if paragraphs:
                slides.append(f"--- Slide {index} ---\n" + "\n".join(paragraphs))
        return "\n\n".join(slides)


def extract_documents_from_records(
    records: Iterable[dict],
) -> tuple[list[str], list[dict]]:
    doc_texts: list[str] = []
    updated: list[dict] = []
    total_bytes = 0
    total_chars = 0
    over_quota = False

    for raw in records:
        record = dict(raw)
        filename = str(record.get("filename") or "")
        if not is_document_extension(filename):
            updated.append(record)
            continue

        b64 = record.get("base64") or ""
        if not b64:
            updated.append(record)
            continue

        if over_quota:
            doc_texts.append(f"[File: {filename} - skipped: total attachment quota exceeded]")
            record["base64"] = ""
            record["extracted_chars"] = 0
            updated.append(record)
            continue

        try:
            data = base64.b64decode(b64, validate=False)
        except Exception as exc:
            doc_texts.append(f"[File: {filename} - could not be read: invalid base64 ({exc})]")
            record["base64"] = ""
            record["extracted_chars"] = 0
            updated.append(record)
            continue

        if total_bytes + len(data) > MAX_TOTAL_DOC_BYTES:
            over_quota = True
            doc_texts.append(f"[File: {filename} - skipped: total attachment quota exceeded]")
            record["base64"] = ""
            record["extracted_chars"] = 0
            updated.append(record)
            continue
        total_bytes += len(data)

        try:
            text = extract_text_from_bytes(filename, data)
        except DocumentExtractionError as exc:
            logger.info("Document extraction failed for %s: %s", filename, exc)
            doc_texts.append(f"[File: {filename} - could not be read: {exc}]")
            record["base64"] = ""
            record["extracted_chars"] = 0
            updated.append(record)
            continue

        remaining_budget = MAX_EXTRACTED_CHARS_TOTAL - total_chars
        if remaining_budget <= 0:
            doc_texts.append(f"[File: {filename} - skipped: total extracted-text quota exceeded]")
            record["base64"] = ""
            record["extracted_chars"] = 0
            updated.append(record)
            continue
        if len(text) > remaining_budget:
            text = text[:remaining_budget] + f"... (truncated, {len(text)} chars total; turn quota hit)"

        total_chars += len(text)
        doc_texts.append(f"[File: {filename}]\n{text}")
        record["base64"] = ""
        record["extracted_chars"] = len(text)
        record["extracted_text"] = text
        updated.append(record)

    return doc_texts, updated
