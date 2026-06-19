#!/usr/bin/env python3
"""Dry-consume an OKF-like compiled inspection pack without runtime writes."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPILED_ROOT = INVENTORY_ROOT / "extractions" / "okf_rubric_pilot_v0"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "extractions" / "okf_dry_consumer_v0"
SENTINEL_NAME = ".okf_dry_consumer_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "okf_dry_consumer_v0")
RUNTIME_GUARD = {
    "release_stage": "dry_consumer_receipt",
    "runtime_consumable": False,
    "installed_runtime_supply": False,
    "canonical_write_allowed": False,
    "learner_truth_write_allowed": False,
    "gbrain_write_allowed": False,
    "production_registry_write_allowed": False,
    "official_score_allowed": False,
}


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


def resolve_soft(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_output_root(path: Path) -> None:
    resolved = resolve_soft(path)
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        (INVENTORY_ROOT / "extractions").resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = load_json(sentinel_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_okf_dry_consumer.py"
        or sentinel.get("kind") != "okf_dry_consumer"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {"receipt.json", "receipt.md", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "okf_dry_consumer",
        "generated_by": "build_okf_dry_consumer.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_non_runtime_guard(payload: dict[str, Any], label: str) -> None:
    guard = payload.get("runtime_guard")
    if not isinstance(guard, dict):
        raise ValueError(f"{label} must include runtime_guard")
    for key in [
        "runtime_consumable",
        "installed_runtime_supply",
        "canonical_write_allowed",
        "learner_truth_write_allowed",
        "gbrain_write_allowed",
        "production_registry_write_allowed",
        "official_score_allowed",
    ]:
        if guard.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def load_compiled_pack(compiled_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not compiled_root.exists() or not compiled_root.is_dir():
        raise ValueError(f"compiled root does not exist: {display_path(compiled_root)}")
    manifest = load_json(compiled_root / "manifest.json")
    context_pack = load_json(compiled_root / "question_context_pack.json")
    point_index = load_json(compiled_root / "scoring_point_index.json")
    require_non_runtime_guard(manifest, "okf manifest")
    require_non_runtime_guard(context_pack, "question context pack")
    require_non_runtime_guard(point_index, "scoring point index")
    return manifest, context_pack, point_index


def validate_counts(manifest: dict[str, Any], context_pack: dict[str, Any], point_index: dict[str, Any]) -> dict[str, int]:
    manifest_counts = manifest.get("counts") or {}
    rubrics = context_pack.get("rubrics") or []
    points = context_pack.get("scoring_points") or []
    points_by_id = point_index.get("points_by_id") or {}
    if int(manifest_counts.get("cases") or 0) != 1:
        raise ValueError("case count mismatch")
    if int(manifest_counts.get("rubrics") or 0) != len(rubrics):
        raise ValueError("rubric count mismatch")
    if int(manifest_counts.get("scoring_points") or 0) != len(points):
        raise ValueError("scoring point count mismatch")
    if int(manifest_counts.get("scoring_points") or 0) != len(points_by_id):
        raise ValueError("scoring point count mismatch")
    return {
        "cases": int(manifest_counts["cases"]),
        "rubrics": len(rubrics),
        "scoring_points": len(points),
    }


def make_receipt(
    *,
    compiled_root: Path,
    manifest: dict[str, Any],
    context_pack: dict[str, Any],
    point_index: dict[str, Any],
    counts: dict[str, int],
    generated_at: str,
) -> dict[str, Any]:
    case = context_pack.get("case") or {}
    point_ids = sorted((point_index.get("points_by_id") or {}).keys())
    return {
        "schema": "luban_okf_dry_consumer_receipt.v0",
        "generated_at": generated_at,
        "status": "dry_consumed_non_runtime",
        "compiled_root": display_path(compiled_root),
        "runtime_guard": RUNTIME_GUARD,
        "counts": counts,
        "source_manifest": {
            "source_path": display_path(compiled_root / "manifest.json"),
            "authority": manifest.get("authority"),
            "official_score_allowed": manifest.get("official_score_allowed"),
        },
        "sample": {
            "case_id": case.get("id"),
            "rubric_ids": [rubric.get("rubric_id") for rubric in (context_pack.get("rubrics") or [])[:5]],
            "scoring_point_ids": point_ids[:8],
        },
        "forbidden_writes": [
            "runtime_supply",
            "canonical_truth",
            "LearnerState",
            "GBrain",
            "production_registry",
            "official_score",
        ],
    }


def write_markdown_receipt(path: Path, receipt: dict[str, Any]) -> None:
    lines = [
        "# OKF dry consumer receipt v0",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Cases read: `{receipt['counts']['cases']}`",
        f"- Rubrics read: `{receipt['counts']['rubrics']}`",
        f"- Scoring points read: `{receipt['counts']['scoring_points']}`",
        f"- Runtime consumable: `{receipt['runtime_guard']['runtime_consumable']}`",
        f"- Official score allowed: `{receipt['runtime_guard']['official_score_allowed']}`",
        "",
        "This receipt proves the compiled inspection pack can be read without writing runtime or canonical truth.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def consume_candidate_pack(
    compiled_root: Path = DEFAULT_COMPILED_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest, context_pack, point_index = load_compiled_pack(compiled_root)
    counts = validate_counts(manifest, context_pack, point_index)
    receipt = make_receipt(
        compiled_root=compiled_root,
        manifest=manifest,
        context_pack=context_pack,
        point_index=point_index,
        counts=counts,
        generated_at=generated_at,
    )

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown_receipt(output_root / "receipt.md", receipt)
    return {
        "output_root": display_path(output_root),
        "receipt": receipt,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiled-root", type=Path, default=DEFAULT_COMPILED_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = consume_candidate_pack(
        compiled_root=args.compiled_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
