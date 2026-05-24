from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .metadata import with_compiler_metadata
from .pii_guard import assert_no_pii
from .platform import actually_open_and_read, detect_dataless


KNOWN_CONTAINER_KEYS = (
    "records",
    "nodes",
    "content_blocks",
    "chunks",
    "questions",
    "exercises",
    "pages",
    "items",
    "data",
)


def classify_source(path: Path, source_root: Path) -> str:
    rel = path.relative_to(source_root).as_posix()
    top = rel.split("/", 1)[0]
    if top == "标准文件":
        return "standard"
    if top == "题库":
        return "question"
    if top == "讲义":
        return "lecture_page" if "/pages/" in rel or path.name.startswith("page_") else "lecture_bundle"
    if top == "2026教材":
        return "book"
    if top == "taxonomy":
        return "taxonomy"
    if top == "scripts":
        return "script"
    return "other"


def compile_eligibility(source_class: str, *, readable: bool, dataless: bool, pii_blocked: bool) -> str:
    if pii_blocked:
        return "blocked_pii"
    if dataless or not readable:
        return "blocked_dataless"
    if source_class == "lecture_page":
        return "redundant_skipped"
    if source_class in {"script", "other"}:
        return "unsupported_skipped"
    return "primary"


def _record_count(payload: Any) -> tuple[int | None, str | None]:
    if isinstance(payload, list):
        return len(payload), None
    if isinstance(payload, dict):
        for key in KNOWN_CONTAINER_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return len(value), None
            if isinstance(value, dict):
                return len(value), None
        if payload and all(isinstance(value, dict) for value in payload.values()):
            return None, "unknown_record_shape"
        return 1, None
    return None, "unknown_record_shape"


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def stable_source_id(source_class: str, source_path: str) -> str:
    seed = f"2026|{source_class}|{source_path}"
    return "src_2026_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def build_source_inventory(
    source_root: Path,
    *,
    run_id: str,
    compiled_at: str,
    require_platform: str = "darwin",
    allow_dataless_scan_disabled: bool = False,
    only_class: str | None = None,
    limit: int | None = None,
    platform_name: str | None = None,
) -> list[dict]:
    source_root = source_root.resolve()
    platform_value = platform_name or require_platform
    records: list[dict] = []
    for path in sorted(source_root.rglob("*.json")):
        source_class = classify_source(path, source_root)
        if only_class and source_class != only_class:
            continue
        if limit is not None and len(records) >= limit:
            break
        rel = path.relative_to(source_root).as_posix()
        dataless = detect_dataless(
            path,
            platform_name=platform_value,
            allow_disabled=allow_dataless_scan_disabled,
        )
        read_probe_ok = False
        read_probe_bytes = 0
        readable = False
        record_count: int | None = None
        record_count_error: str | None = None
        pii_blocked = False
        if not dataless:
            try:
                read_probe_ok, read_probe_bytes = actually_open_and_read(path)
                text = path.read_text(encoding="utf-8")
                assert_no_pii(text[:256_000])
                payload = json.loads(text)
                record_count, record_count_error = _record_count(payload)
                readable = read_probe_ok
            except ValueError as exc:
                if "PII" in str(exc):
                    pii_blocked = True
                record_count_error = str(exc)
            except Exception as exc:  # noqa: BLE001 - artifact must explain parse/read failures.
                record_count_error = type(exc).__name__

        stat = path.stat()
        payload = {
            "stable_source_id": stable_source_id(source_class, rel),
            "source_path": rel,
            "source_class": source_class,
            "compile_eligibility": compile_eligibility(
                source_class,
                readable=readable,
                dataless=dataless,
                pii_blocked=pii_blocked,
            ),
            "readable": readable,
            "dataless": dataless,
            "bytes": stat.st_size,
            "sha256": None if dataless else _sha256(path),
            "record_count": record_count,
            "record_count_error": record_count_error,
            "read_probe_bytes": read_probe_bytes,
            "dataless_scan_disabled": allow_dataless_scan_disabled and platform_value != "darwin",
            "download_owner": "yehongchen",
            "last_download_verified_at": "2026-05-24",
            "dataless_remediation_note": None if not dataless else "Download local bytes before writeback gates.",
        }
        records.append(
            with_compiler_metadata(
                payload,
                run_id=run_id,
                source_path=rel,
                compiled_at=compiled_at,
            )
        )
    return records


def summarize_inventory(records: list[dict]) -> dict[str, int]:
    summary = {
        "json_files": len(records),
        "readable": sum(1 for record in records if record["readable"]),
        "dataless": sum(1 for record in records if record["dataless"]),
        "blocked_dataless": sum(1 for record in records if record["compile_eligibility"] == "blocked_dataless"),
        "redundant_skipped": sum(1 for record in records if record["compile_eligibility"] == "redundant_skipped"),
    }
    for record in records:
        key = f"class_{record['source_class']}"
        summary[key] = summary.get(key, 0) + 1
    return summary
