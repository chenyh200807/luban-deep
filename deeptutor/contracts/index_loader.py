from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


_PACKAGE_DIR = Path(__file__).resolve().parent
_PACKAGE_INDEX_PATH = _PACKAGE_DIR / "index.yaml"
_REPO_INDEX_PATH = _PACKAGE_DIR.parent.parent / "contracts" / "index.yaml"


def get_contract_index_candidates() -> tuple[Path, ...]:
    env_override = os.getenv("DEEPTUTOR_CONTRACT_INDEX_PATH", "").strip()
    candidates: list[Path] = []
    if env_override:
        candidates.append(Path(env_override).expanduser())
    candidates.extend([_REPO_INDEX_PATH, _PACKAGE_INDEX_PATH])

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def get_contract_index_path() -> Path:
    for candidate in get_contract_index_candidates():
        if candidate.exists():
            return candidate
    return get_contract_index_candidates()[0]


def load_contract_index() -> dict[str, Any]:
    payload = yaml.safe_load(get_contract_index_path().read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("contracts/index.yaml must contain an object at the top level")
    return payload


def export_contract_index() -> dict[str, Any]:
    payload = load_contract_index()
    return dict(payload)


__all__ = [
    "export_contract_index",
    "get_contract_index_candidates",
    "get_contract_index_path",
    "load_contract_index",
]
