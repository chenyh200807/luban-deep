from __future__ import annotations

import base64


def test_extract_documents_from_text_attachment_records() -> None:
    from deeptutor.utils.document_extractor import extract_documents_from_records

    encoded = base64.b64encode("hello from file".encode("utf-8")).decode("ascii")
    texts, records = extract_documents_from_records(
        [
            {
                "type": "file",
                "filename": "notes.txt",
                "mime_type": "text/plain",
                "base64": encoded,
            }
        ]
    )

    assert texts == ["[File: notes.txt]\nhello from file"]
    assert records[0]["base64"] == ""
    assert records[0]["extracted_text"] == "hello from file"
    assert records[0]["extracted_chars"] == len("hello from file")


def test_extract_documents_leaves_non_documents_unchanged() -> None:
    from deeptutor.utils.document_extractor import extract_documents_from_records

    record = {"type": "image", "filename": "photo.png", "base64": "abc"}
    texts, records = extract_documents_from_records([record])

    assert texts == []
    assert records == [record]
