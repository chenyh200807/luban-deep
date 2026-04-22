from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE_DIR = PROJECT_ROOT / "tmp" / "observability" / "control_plane"
_ALLOWED_KINDS = {
    "om_runs",
    "arr_runs",
    "aae_composite_runs",
    "oa_runs",
    "release_gate_runs",
    "incident_ledger",
}


def _normalize_kind(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized not in _ALLOWED_KINDS:
        raise ValueError(f"Unsupported control plane kind: {kind!r}")
    return normalized


def unwrap_payload_document(
    document: dict[str, Any],
    *,
    expected_kind: str | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise TypeError("Observability document must be a JSON object")

    normalized_expected = _normalize_kind(expected_kind) if expected_kind else None
    record_kind = str(document.get("kind") or "").strip().lower()
    payload = document.get("payload")
    is_control_plane_record = (
        isinstance(payload, dict)
        and bool(record_kind)
        and "run_id" in document
        and "recorded_at" in document
    )
    if not is_control_plane_record:
        return document

    if normalized_expected and record_kind != normalized_expected:
        raise ValueError(
            f"Control plane payload kind mismatch: expected {normalized_expected!r}, got {record_kind!r}"
        )
    return payload


def load_payload_json(
    path: str | Path | None,
    *,
    expected_kind: str | None = None,
) -> dict[str, Any] | None:
    if not path:
        return None

    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(target)

    document = json.loads(target.read_text(encoding="utf-8"))
    return unwrap_payload_document(document, expected_kind=expected_kind)


class ObservabilityControlPlaneStore:
    """Best-effort observability control plane store with artifact fallback."""

    def __init__(self, *, base_dir: Path | None = None) -> None:
        configured_dir = str(os.getenv("DEEPTUTOR_OBSERVABILITY_STORE_DIR", "") or "").strip()
        self._base_dir = (
            Path(configured_dir).expanduser().resolve()
            if configured_dir
            else (base_dir or DEFAULT_STORE_DIR).expanduser().resolve()
        )
        self._lock = threading.Lock()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _kind_dir(self, kind: str) -> Path:
        normalized = _normalize_kind(kind)
        target = self._base_dir / normalized
        target.mkdir(parents=True, exist_ok=True)
        return target

    def write_run(
        self,
        *,
        kind: str,
        run_id: str,
        release_id: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        normalized_kind = _normalize_kind(kind)
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            raise ValueError("run_id is required")

        metadata = {
            "kind": normalized_kind,
            "run_id": normalized_run_id,
            "release_id": str(release_id or "").strip(),
            "recorded_at": int(time.time()),
        }
        record = {
            **metadata,
            "payload": payload,
        }

        kind_dir = self._kind_dir(normalized_kind)
        json_path = kind_dir / f"{normalized_run_id}.json"
        latest_path = kind_dir / "latest.json"
        history_path = kind_dir / "history.jsonl"

        with self._lock:
            json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            latest_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            with history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        return {
            "json_path": str(json_path),
            "latest_path": str(latest_path),
            "history_path": str(history_path),
        }

    def latest_run(self, kind: str) -> dict[str, Any] | None:
        kind_dir = self._kind_dir(kind)
        latest_path = kind_dir / "latest.json"
        if latest_path.exists():
            return json.loads(latest_path.read_text(encoding="utf-8"))

        candidates = sorted(
            kind_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            if candidate.name == "latest.json":
                continue
            return json.loads(candidate.read_text(encoding="utf-8"))
        return None

    def latest_payload(self, kind: str) -> dict[str, Any] | None:
        latest = self.latest_run(kind)
        return unwrap_payload_document(latest, expected_kind=kind) if latest else None

    def list_runs(self, kind: str, *, limit: int = 20) -> list[dict[str, Any]]:
        kind_dir = self._kind_dir(kind)
        history_path = kind_dir / "history.jsonl"
        if not history_path.exists():
            return []
        rows = history_path.read_text(encoding="utf-8").splitlines()
        results: list[dict[str, Any]] = []
        for line in reversed(rows):
            if not line.strip():
                continue
            results.append(json.loads(line))
            if len(results) >= limit:
                break
        return results


_control_plane_store = ObservabilityControlPlaneStore()


def get_control_plane_store() -> ObservabilityControlPlaneStore:
    return _control_plane_store


def reset_control_plane_store(*, base_dir: Path | None = None) -> None:
    global _control_plane_store
    _control_plane_store = ObservabilityControlPlaneStore(base_dir=base_dir)
