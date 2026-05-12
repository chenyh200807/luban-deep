"""Flat per-embedding index versions for local knowledge bases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)

VERSION_PREFIX = "version-"
LEGACY_VERSION_DIRNAME = "index_versions"
LEGACY_STORAGE_DIRNAME = "llamaindex_storage"
META_FILENAME = "meta.json"

_VERSION_RE = re.compile(r"^version-(\d+)$")


@dataclass(frozen=True)
class EmbeddingSignature:
    """Stable identity of an embedding configuration."""

    binding: str
    model: str
    dimension: int
    base_url: str
    api_version: str

    def hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def kb_versions_dir(kb_dir: Path) -> Path:
    return kb_dir / LEGACY_VERSION_DIRNAME


def legacy_storage_dir(kb_dir: Path) -> Path:
    return kb_dir / LEGACY_STORAGE_DIRNAME


def _is_storage_ready(storage_dir: Path) -> bool:
    return storage_dir.is_dir() and any(
        child.name != META_FILENAME for child in storage_dir.iterdir()
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Failed to read version meta %s: %s", path, exc)
        return None


def _flat_version_number(path: Path) -> int:
    match = _VERSION_RE.match(path.name)
    return int(match.group(1)) if match else 0


def _flat_version_dirs(kb_dir: Path) -> list[Path]:
    if not kb_dir.is_dir():
        return []
    return sorted(
        (child for child in kb_dir.iterdir() if child.is_dir() and _VERSION_RE.match(child.name)),
        key=_flat_version_number,
    )


def _next_flat_version_dir(kb_dir: Path) -> Path:
    existing = [_flat_version_number(path) for path in _flat_version_dirs(kb_dir)]
    return kb_dir / f"{VERSION_PREFIX}{(max(existing) if existing else 0) + 1}"


def _entry_from_flat_version(version_dir: Path) -> dict[str, Any]:
    meta = _read_json(version_dir / META_FILENAME) or {}
    meta.setdefault("version", version_dir.name)
    meta.setdefault("signature", meta.get("signature") or version_dir.name)
    meta["ready"] = _is_storage_ready(version_dir)
    meta["storage_path"] = str(version_dir)
    meta["version_path"] = str(version_dir)
    meta["layout"] = "flat"
    return meta


def _entry_from_legacy_nested(kb_dir: Path, version_dir: Path) -> dict[str, Any]:
    storage = version_dir / LEGACY_STORAGE_DIRNAME
    meta = _read_json(version_dir / META_FILENAME) or {"signature": version_dir.name}
    meta.setdefault("version", version_dir.name)
    meta.setdefault("signature", version_dir.name)
    meta["ready"] = _is_storage_ready(storage)
    meta["storage_path"] = str(storage)
    meta["version_path"] = str(version_dir)
    meta["layout"] = "nested_legacy"
    meta["legacy"] = True
    meta["kb_path"] = str(kb_dir)
    return meta


def _entry_from_root_legacy(kb_dir: Path) -> dict[str, Any]:
    storage = legacy_storage_dir(kb_dir)
    return {
        "signature": "legacy",
        "version": "legacy",
        "ready": _is_storage_ready(storage),
        "storage_path": str(storage),
        "version_path": str(storage),
        "layout": "root_legacy",
        "legacy": True,
    }


def _sort_versions(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(entry: dict[str, Any]) -> tuple[str, int, int]:
        layout_priority = 2 if entry.get("layout") == "flat" else 1
        version_num = 0
        version_name = str(entry.get("version") or "")
        match = _VERSION_RE.match(version_name)
        if match:
            version_num = int(match.group(1))
        return (str(entry.get("created_at", "")), layout_priority, version_num)

    return sorted(versions, key=key, reverse=True)


def list_kb_versions(kb_dir: Path) -> list[dict[str, Any]]:
    """Return all index versions for a KB, newest first."""
    versions: list[dict[str, Any]] = []

    for version_dir in _flat_version_dirs(kb_dir):
        versions.append(_entry_from_flat_version(version_dir))

    legacy_versions_root = kb_versions_dir(kb_dir)
    if legacy_versions_root.is_dir():
        for child in sorted(legacy_versions_root.iterdir(), key=lambda path: path.name):
            if child.is_dir():
                versions.append(_entry_from_legacy_nested(kb_dir, child))

    root_legacy = legacy_storage_dir(kb_dir)
    if root_legacy.is_dir() and any(root_legacy.iterdir()):
        versions.append(_entry_from_root_legacy(kb_dir))

    return _sort_versions(versions)


def _find_flat_version_by_signature(
    kb_dir: Path, sig_hash: str, *, ready_only: bool
) -> dict[str, Any] | None:
    for entry in list_kb_versions(kb_dir):
        if entry.get("layout") != "flat":
            continue
        if entry.get("signature") != sig_hash:
            continue
        if ready_only and not entry.get("ready"):
            continue
        return entry
    return None


def _latest_ready_flat_version(kb_dir: Path) -> dict[str, Any] | None:
    for entry in list_kb_versions(kb_dir):
        if entry.get("layout") == "flat" and entry.get("ready"):
            return entry
    return None


def find_matching_version(
    kb_dir: Path, signature: EmbeddingSignature | None
) -> dict[str, Any] | None:
    if signature is None:
        return None
    target = signature.hash()
    matches = [
        entry
        for entry in list_kb_versions(kb_dir)
        if entry.get("signature") == target and entry.get("ready")
    ]
    if not matches:
        return None
    flat_matches = [entry for entry in matches if entry.get("layout") == "flat"]
    return flat_matches[0] if flat_matches else matches[0]


def version_dir_for_signature(kb_dir: Path, sig_hash: str) -> Path:
    entry = _find_flat_version_by_signature(kb_dir, sig_hash, ready_only=False)
    if entry:
        return Path(str(entry["version_path"]))
    return _next_flat_version_dir(kb_dir)


def resolve_storage_dir_for_write(
    kb_dir: Path, signature: EmbeddingSignature | None
) -> Path:
    if signature is None:
        target = _next_flat_version_dir(kb_dir)
    else:
        entry = _find_flat_version_by_signature(kb_dir, signature.hash(), ready_only=False)
        target = Path(str(entry["storage_path"])) if entry else _next_flat_version_dir(kb_dir)
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_storage_dir_for_rebuild(
    kb_dir: Path, signature: EmbeddingSignature | None
) -> Path:
    del signature
    target = _next_flat_version_dir(kb_dir)
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_storage_dir_for_read(
    kb_dir: Path, signature: EmbeddingSignature | None
) -> Path | None:
    if signature is not None:
        match = find_matching_version(kb_dir, signature)
        if match:
            return Path(str(match["storage_path"]))
    else:
        latest_flat = _latest_ready_flat_version(kb_dir)
        if latest_flat:
            return Path(str(latest_flat["storage_path"]))

    root_legacy = legacy_storage_dir(kb_dir)
    if _is_storage_ready(root_legacy):
        return root_legacy
    return None


def write_version_meta(
    kb_dir: Path,
    signature: EmbeddingSignature,
    storage_dir: Path | None = None,
) -> None:
    target = storage_dir or resolve_storage_dir_for_write(kb_dir, signature)
    target.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": target.name,
        "signature": signature.hash(),
        **asdict(signature),
        "layout": "flat" if target.parent == kb_dir else "nested_legacy",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    (target / META_FILENAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
