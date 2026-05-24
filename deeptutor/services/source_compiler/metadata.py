from __future__ import annotations

from datetime import UTC, datetime


COMPILER_VERSION = "2026-source-compiler-v0.2"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def with_compiler_metadata(
    payload: dict,
    *,
    run_id: str,
    source_path: str,
    compiled_at: str,
) -> dict:
    enriched = dict(payload)
    enriched.update(
        {
            "compiler_version": COMPILER_VERSION,
            "compiled_at": compiled_at,
            "run_id": run_id,
            "source_path": source_path,
        }
    )
    return enriched

