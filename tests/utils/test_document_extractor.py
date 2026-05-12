from __future__ import annotations

import io
import zipfile

import pytest

from deeptutor.utils.document_extractor import (
    EmptyDocumentError,
    UnsupportedDocumentError,
    extract_text_from_bytes,
    is_document_extension,
)


def _make_docx(paragraphs: list[str]) -> bytes:
    buffer = io.BytesIO()
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
        + "</w:body></w:document>"
    )
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def test_document_extractor_supports_kb_text_extensions() -> None:
    assert is_document_extension("notes.md")
    assert is_document_extension("config.yaml")
    assert is_document_extension("table.csv")
    assert not is_document_extension("photo.png")


def test_extract_text_from_docx_bytes() -> None:
    text = extract_text_from_bytes("lesson.docx", _make_docx(["一级建造师", "施工管理"]))

    assert "一级建造师" in text
    assert "施工管理" in text


def test_extract_text_from_text_like_bytes() -> None:
    text = extract_text_from_bytes("notes.md", "# 标题\n\n正文".encode("utf-8"))

    assert "# 标题" in text
    assert "正文" in text


def test_document_extractor_reports_clear_failures() -> None:
    with pytest.raises(EmptyDocumentError):
        extract_text_from_bytes("empty.txt", b"")
    with pytest.raises(UnsupportedDocumentError):
        extract_text_from_bytes("archive.zip", b"PK\x03\x04")
