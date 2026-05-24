from __future__ import annotations

import json
from pathlib import Path

from .pii_guard import assert_no_pii
from .source_inventory import classify_source, stable_source_id


def load_source_payload(path: Path, source_root: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert_no_pii(text[:256_000])
    payload = json.loads(text)
    rel = path.relative_to(source_root).as_posix()
    source_class = classify_source(path, source_root)
    return {
        "stable_source_id": stable_source_id(source_class, rel),
        "source_path": rel,
        "source_class": source_class,
        "payload": payload,
    }


def iter_payload_records(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("records", "nodes", "content_blocks", "chunks", "questions", "exercises", "pages", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []

