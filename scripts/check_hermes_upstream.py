from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INVENTORY = Path("docs/plan/artifacts/hermes-edu-skills-inventory.json")
DEFAULT_SOURCE = Path(os.getenv("HERMES_EDU_SOURCE", "~/.cache/deeptutor/hermes-edu-skills")).expanduser()


@dataclass(frozen=True)
class VersionCheckResult:
    status: str
    inventory_version: str
    upstream_version: str
    message: str


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _version_from_inventory(path: Path) -> str:
    version = _read_json(path).get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"Missing inventory version: {path}")
    return version.strip()


def _version_from_source(source: Path) -> str:
    if source.is_dir():
        candidates = [source / "package.json", source / "catalog.json"]
    else:
        candidates = [source]

    for candidate in candidates:
        if not candidate.exists():
            continue
        payload = _read_json(candidate)
        version = payload.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()

    raise FileNotFoundError(f"No package.json or catalog.json with version found under {source}")


def check_versions(*, inventory_path: Path = DEFAULT_INVENTORY, source_path: Path = DEFAULT_SOURCE) -> VersionCheckResult:
    inventory_version = _version_from_inventory(inventory_path)
    upstream_version = _version_from_source(source_path)

    if inventory_version == upstream_version:
        return VersionCheckResult(
            status="ok",
            inventory_version=inventory_version,
            upstream_version=upstream_version,
            message=f"Hermes inventory pinned to upstream version {inventory_version}.",
        )

    return VersionCheckResult(
        status="drift",
        inventory_version=inventory_version,
        upstream_version=upstream_version,
        message=(
            "Hermes upstream drift detected: "
            f"inventory={inventory_version}, upstream={upstream_version}. "
            "Re-run Phase 0 inventory review before absorbing new skills."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check hermes-edu-skills upstream version drift.")
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY), help="DeepTutor Hermes inventory JSON.")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="hermes-edu-skills checkout, package.json, or catalog.json. Defaults to HERMES_EDU_SOURCE.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Return non-zero when upstream version differs from the pinned inventory version.",
    )
    args = parser.parse_args(argv)

    try:
        result = check_versions(inventory_path=Path(args.inventory), source_path=Path(args.source).expanduser())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR hermes upstream check failed: {exc}")
        return 2

    prefix = "INFO" if result.status == "ok" else "WARN"
    print(f"{prefix} hermes upstream {result.status}: {result.message}")
    if result.status == "drift" and args.fail_on_drift:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
