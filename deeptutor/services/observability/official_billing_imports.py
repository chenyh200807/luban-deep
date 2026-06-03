"""Provider-neutral official billing import manifest store."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from deeptutor.services.path_service import PathService


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _load_manifest(raw: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True, slots=True)
class OfficialBillingImportRecord:
    import_id: int
    provider_name: str
    billing_cycle: str
    source_file_sha256: str
    schema_hash: str
    source_file_name: str
    imported_at: float
    manifest: dict[str, Any]
    inserted: bool = False


class OfficialBillingImportStore:
    def __init__(self, db_path: Path | None = None) -> None:
        path_service = PathService.get_instance()
        self._db_path = (db_path or (path_service.get_user_root() / "official_billing_imports.db")).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS official_billing_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_name TEXT NOT NULL,
                    billing_cycle TEXT NOT NULL,
                    source_file_sha256 TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    source_file_name TEXT NOT NULL,
                    imported_at REAL NOT NULL,
                    manifest_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(provider_name, billing_cycle, source_file_sha256)
                )
                """
            )
            conn.commit()

    @staticmethod
    def _record_from_row(row: sqlite3.Row, *, inserted: bool = False) -> OfficialBillingImportRecord:
        return OfficialBillingImportRecord(
            import_id=int(row["id"]),
            provider_name=str(row["provider_name"]),
            billing_cycle=str(row["billing_cycle"]),
            source_file_sha256=str(row["source_file_sha256"]),
            schema_hash=str(row["schema_hash"]),
            source_file_name=str(row["source_file_name"]),
            imported_at=float(row["imported_at"]),
            manifest=_load_manifest(row["manifest_json"]),
            inserted=inserted,
        )

    def record_import(
        self,
        *,
        provider_name: str,
        billing_cycle: str,
        source_file_sha256: str,
        schema_hash: str,
        source_file_name: str,
        manifest: dict[str, Any] | None = None,
        imported_at: float | None = None,
    ) -> OfficialBillingImportRecord:
        provider = _as_str(provider_name)
        cycle = _as_str(billing_cycle)
        source_hash = _as_str(source_file_sha256)
        if not provider or not cycle or not source_hash:
            raise ValueError("provider_name, billing_cycle, and source_file_sha256 are required")
        manifest_json = json.dumps(manifest or {}, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO official_billing_imports (
                    provider_name, billing_cycle, source_file_sha256,
                    schema_hash, source_file_name, imported_at, manifest_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    cycle,
                    source_hash,
                    _as_str(schema_hash),
                    _as_str(source_file_name),
                    float(imported_at if imported_at is not None else time.time()),
                    manifest_json,
                ),
            )
            inserted = cursor.rowcount == 1
            row = conn.execute(
                """
                SELECT *
                FROM official_billing_imports
                WHERE provider_name = ?
                  AND billing_cycle = ?
                  AND source_file_sha256 = ?
                """,
                (provider, cycle, source_hash),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("official billing import insert did not produce a canonical row")
        return self._record_from_row(row, inserted=inserted)

    def list_imports(
        self,
        *,
        provider_name: str | None = None,
        billing_cycle: str | None = None,
    ) -> list[OfficialBillingImportRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if _as_str(provider_name):
            clauses.append("provider_name = ?")
            params.append(_as_str(provider_name))
        if _as_str(billing_cycle):
            clauses.append("billing_cycle = ?")
            params.append(_as_str(billing_cycle))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM official_billing_imports
                {where_sql}
                ORDER BY imported_at DESC, id DESC
                """,
                params,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]


__all__ = ["OfficialBillingImportRecord", "OfficialBillingImportStore"]
