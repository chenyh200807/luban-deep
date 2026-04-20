"""Release lineage helpers for observability and release gating."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import subprocess


_UNKNOWN_GIT_SHA = "unknown"
_UNKNOWN_ENV = "unknown"
_UNSET_PROMPT_VERSION = "unset"
_EMPTY_FF_SNAPSHOT = "none"


@dataclass(frozen=True, slots=True)
class ReleaseLineage:
    release_id: str
    service_version: str
    git_sha: str
    deployment_environment: str
    prompt_version: str
    ff_snapshot_hash: str

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


_cached_release_lineage: ReleaseLineage | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _env_value(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return ""


def _resolve_service_version() -> str:
    overridden = _env_value("DEEPTUTOR_SERVICE_VERSION", "SERVICE_VERSION")
    if overridden:
        return overridden
    try:
        return importlib_metadata.version("deeptutor")
    except importlib_metadata.PackageNotFoundError:
        return "1.0.0"


def _resolve_git_sha() -> str:
    overridden = _env_value("DEEPTUTOR_GIT_SHA", "GIT_SHA", "COMMIT_SHA")
    if overridden:
        return overridden
    repo_root = _repo_root()
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=12", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return _UNKNOWN_GIT_SHA
    resolved = str(completed.stdout or "").strip()
    return resolved or _UNKNOWN_GIT_SHA


def _resolve_environment() -> str:
    return _env_value("DEEPTUTOR_ENV", "APP_ENV", "ENVIRONMENT", "ENV") or _UNKNOWN_ENV


def _resolve_prompt_version() -> str:
    return _env_value(
        "DEEPTUTOR_PROMPT_VERSION",
        "PROMPT_VERSION",
        "NEXT_PUBLIC_PROMPT_VERSION",
    ) or _UNSET_PROMPT_VERSION


def _should_capture_flag(key: str) -> bool:
    if key.startswith("FF_"):
        return True
    if not key.startswith("DEEPTUTOR_"):
        return False
    return key.endswith("_ENABLED") or key.endswith("_MODE") or "_SHADOW_" in key or key.endswith("_STRICT")


def _normalize_flag_value(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return "true"
    if lowered in {"0", "false", "no", "off"}:
        return "false"
    return str(value or "").strip()


def _resolve_ff_snapshot_hash() -> str:
    explicit = _env_value("DEEPTUTOR_FF_SNAPSHOT_HASH", "FF_SNAPSHOT_HASH")
    if explicit:
        return explicit

    snapshot = {
        key: _normalize_flag_value(value)
        for key, value in sorted(os.environ.items(), key=lambda item: item[0])
        if _should_capture_flag(key)
    }
    if not snapshot:
        return _EMPTY_FF_SNAPSHOT

    digest = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest[:12]


def _build_release_lineage() -> ReleaseLineage:
    service_version = _resolve_service_version()
    git_sha = _resolve_git_sha()
    deployment_environment = _resolve_environment()
    prompt_version = _resolve_prompt_version()
    ff_snapshot_hash = _resolve_ff_snapshot_hash()
    release_id = _env_value("DEEPTUTOR_RELEASE_ID", "RELEASE_ID")
    if not release_id:
        release_id = f"{service_version}+{git_sha}+{deployment_environment}"
    return ReleaseLineage(
        release_id=release_id,
        service_version=service_version,
        git_sha=git_sha,
        deployment_environment=deployment_environment,
        prompt_version=prompt_version,
        ff_snapshot_hash=ff_snapshot_hash,
    )


def get_release_lineage() -> ReleaseLineage:
    global _cached_release_lineage
    if _cached_release_lineage is None:
        _cached_release_lineage = _build_release_lineage()
    return _cached_release_lineage


def get_release_lineage_metadata() -> dict[str, str]:
    return get_release_lineage().to_dict()


def get_release_lineage_snapshot() -> dict[str, str]:
    return get_release_lineage_metadata()


def reset_release_lineage_cache() -> None:
    global _cached_release_lineage
    _cached_release_lineage = None


__all__ = [
    "ReleaseLineage",
    "get_release_lineage",
    "get_release_lineage_metadata",
    "get_release_lineage_snapshot",
    "reset_release_lineage_cache",
]
