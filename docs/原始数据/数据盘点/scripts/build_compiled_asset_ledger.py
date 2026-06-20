#!/usr/bin/env python3
"""Build an AI-readable ledger for compiled artifacts and runtime supply."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
DEFAULT_RUNTIME_SUPPLY_ROOT = REPO_ROOT / "deeptutor" / "services" / "construction_grading" / "runtime_supply"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "compiled_asset_ledger_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "compiled_asset_ledger_v1")
SENTINEL_NAME = ".compiled_asset_ledger_generated.json"
SNAPSHOT_DIR_NAME = "manifest_snapshots"
SNAPSHOT_MAX_BYTES = 512 * 1024

EXCLUDED_PARTS = {".git", "__pycache__", "node_modules", ".pytest_cache"}
EXCLUDED_FILES = {".DS_Store"}
MANIFEST_NAME_RE = re.compile(r"(manifest|summary|report|canonical_pointer|pointer|quality_report|registry|ledger)", re.I)

RUNTIME_GUARD = {
    "release_stage": "compiled_asset_inventory_only",
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


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def extension(path: Path) -> str:
    return path.suffix.lower() or "[no_ext]"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_output_root(path: Path) -> None:
    resolved = resolve_soft(path)
    controlled_roots = {
        EXTRACTIONS_ROOT.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        EXTRACTIONS_ROOT.resolve(),
        DEFAULT_ARTIFACTS_ROOT.resolve(),
        DEFAULT_RUNTIME_SUPPLY_ROOT.resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_compiled_asset_ledger.py"
        or sentinel.get("kind") != "compiled_asset_ledger"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed_files = {"manifest.json", "asset_groups.json", "files.jsonl", "manifest_refs.jsonl", "summary.md", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name == SNAPSHOT_DIR_NAME and child.is_dir():
            continue
        if child.name not in allowed_files or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "compiled_asset_ledger",
        "generated_by": "build_compiled_asset_ledger.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if set(path.relative_to(root).parts) & EXCLUDED_PARTS:
            continue
        files.append(path)
    return sorted(files)


def artifact_group_for(path: Path, artifacts_root: Path, runtime_supply_root: Path) -> str:
    if is_relative_to(path, runtime_supply_root):
        return "runtime_supply"
    if is_relative_to(path, artifacts_root):
        rel_parts = path.relative_to(artifacts_root).parts
        if len(rel_parts) == 1:
            return "artifacts/[root_files]"
        return f"artifacts/{rel_parts[0]}" if rel_parts else "artifacts"
    return "external"


def group_kind(group: str) -> str:
    if group == "runtime_supply":
        return "runtime_supply_mixed_published_and_candidate"
    mapping = {
        "artifacts/knowledge_compiler": "knowledge_compiler_workbench",
        "artifacts/luban_grading_artifacts": "grading_compiler_shadow_workbench",
        "artifacts/luban_case_family_assets": "case_family_multimedia_assets",
        "artifacts/luban_consensus_gold": "consensus_gold_shadow_review",
        "artifacts/luban_agentic_grading_harness": "agentic_grading_harness",
        "artifacts/luban_case_grading_three_arms": "case_grading_ab_workbench",
        "artifacts/assessment_testset": "assessment_testset",
        "artifacts/assessment_flywheel": "assessment_flywheel",
    }
    return mapping.get(group, "artifact_auxiliary_or_report")


def authority_status_for(group: str) -> str:
    if group == "runtime_supply":
        return "runtime_supply_inventory_mixed_publication_status"
    if group.startswith("artifacts/"):
        return "artifact_workbench_or_candidate_inventory"
    return "compiled_asset_inventory"


def is_manifest_like(path: Path) -> bool:
    if extension(path) not in {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}:
        return False
    return bool(MANIFEST_NAME_RE.search(path.name))


def snapshot_name(source_path: str, path: Path) -> str:
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:16]
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", path.name)
    return f"{digest}__{safe_name}"


def build_file_records(artifacts_root: Path, runtime_supply_root: Path) -> list[dict[str, Any]]:
    files = iter_files(artifacts_root) + iter_files(runtime_supply_root)
    records = []
    for path in sorted(files):
        source_path = display_path(path)
        group = artifact_group_for(path, artifacts_root, runtime_supply_root)
        stat = path.stat()
        records.append(
            {
                "schema": "luban_compiled_asset_file_record.v1",
                "source_path": source_path,
                "asset_group": group,
                "group_kind": group_kind(group),
                "authority_status": authority_status_for(group),
                "extension": extension(path),
                "bytes": stat.st_size,
                "sha256": sha256_file(path),
                "manifest_like": is_manifest_like(path),
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return records


def build_group_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["asset_group"], []).append(record)
    rows = []
    for group, group_records in sorted(grouped.items()):
        ext = Counter(record["extension"] for record in group_records)
        rows.append(
            {
                "asset_group": group,
                "group_kind": group_kind(group),
                "authority_status": authority_status_for(group),
                "files": len(group_records),
                "bytes": sum(record["bytes"] for record in group_records),
                "extensions": dict(ext.most_common()),
                "manifest_like_files": sum(1 for record in group_records if record["manifest_like"]),
                "largest_files": [
                    {"path": record["source_path"], "bytes": record["bytes"]}
                    for record in sorted(group_records, key=lambda item: item["bytes"], reverse=True)[:8]
                ],
            }
        )
    return rows


def write_manifest_snapshots(output_root: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot_root = output_root / SNAPSHOT_DIR_NAME
    snapshot_root.mkdir(parents=True, exist_ok=True)
    refs = []
    for record in records:
        if not record["manifest_like"] or record["bytes"] > SNAPSHOT_MAX_BYTES:
            continue
        source = REPO_ROOT / record["source_path"]
        if not source.exists():
            continue
        snapshot_rel = Path(SNAPSHOT_DIR_NAME) / snapshot_name(record["source_path"], source)
        target = output_root / snapshot_rel
        target.write_bytes(source.read_bytes())
        refs.append(
            {
                "schema": "luban_compiled_asset_manifest_ref.v1",
                "source_path": record["source_path"],
                "asset_group": record["asset_group"],
                "bytes": record["bytes"],
                "sha256": record["sha256"],
                "snapshot_path": snapshot_rel.as_posix(),
                "authority_status": record["authority_status"],
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return refs


def render_summary(manifest: dict[str, Any], groups: list[dict[str, Any]]) -> str:
    counts = manifest["counts"]
    lines = [
        "# Compiled Asset Ledger v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Authority: compiled asset inventory only; not runtime install, not official score authority.",
        f"- Files indexed: **{counts['files']:,}**",
        f"- Total bytes: **{counts['total_bytes']:,}**",
        f"- Asset groups: **{counts['asset_groups']:,}**",
        f"- Manifest-like refs copied: **{counts['manifest_refs_copied']:,}**",
        "",
        "## Asset Groups",
        "",
        "| Group | Kind | Files | Bytes | Authority |",
        "|---|---|---:|---:|---|",
    ]
    for row in groups:
        lines.append(
            f"| `{row['asset_group']}` | `{row['group_kind']}` | {row['files']:,} | {row['bytes']:,} | `{row['authority_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Source payloads remain in their original artifact/runtime directories; this ledger copies only indexes and small manifest-like snapshots.",
            "- `artifacts/*` entries are workbench/candidate/shadow unless separately signed and published through runtime supply.",
            "- `runtime_supply` contains mixed published/release-candidate assets; consumers must read each canonical pointer/status before use.",
            "- No record in this ledger may write LearnerState, GBrain, production registry, or official score authority.",
            "",
        ]
    )
    return "\n".join(lines)


def build_compiled_asset_ledger(
    artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT,
    runtime_supply_root: Path = DEFAULT_RUNTIME_SUPPLY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not artifacts_root.exists() or not artifacts_root.is_dir():
        raise ValueError(f"artifacts root does not exist: {display_path(artifacts_root)}")
    if not runtime_supply_root.exists() or not runtime_supply_root.is_dir():
        raise ValueError(f"runtime supply root does not exist: {display_path(runtime_supply_root)}")
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records = build_file_records(artifacts_root, runtime_supply_root)
    if not records:
        raise ValueError("no compiled asset files found")
    groups = build_group_rows(records)
    ext = Counter(record["extension"] for record in records)

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    manifest_refs = write_manifest_snapshots(output_root, records)
    manifest = {
        "schema": "luban_compiled_asset_ledger_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "compiled_asset_inventory_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_roots": {
            "artifacts": display_path(artifacts_root),
            "runtime_supply": display_path(runtime_supply_root),
        },
        "copy_policy": {
            "payloads_copied": False,
            "manifest_like_snapshots_copied": True,
            "snapshot_max_bytes": SNAPSHOT_MAX_BYTES,
            "reason": "avoid duplicating large workbench payloads; preserve original artifact paths as authority",
        },
        "artifact_refs": {
            "asset_groups": "asset_groups.json",
            "files": "files.jsonl",
            "manifest_refs": "manifest_refs.jsonl",
            "summary": "summary.md",
            "manifest_snapshots": f"{SNAPSHOT_DIR_NAME}/",
        },
        "counts": {
            "files": len(records),
            "total_bytes": sum(record["bytes"] for record in records),
            "asset_groups": len(groups),
            "manifest_like_files": sum(1 for record in records if record["manifest_like"]),
            "manifest_refs_copied": len(manifest_refs),
            "by_extension": dict(ext.most_common()),
        },
        "guardrails": [
            "compiled asset ledger only",
            "artifact workbench != runtime truth",
            "runtime supply publication status must be checked per canonical pointer",
            "no official score claim",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "asset_groups.json").write_text(
        json.dumps({"schema": "luban_compiled_asset_groups.v1", "asset_groups": groups}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "files.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (output_root / "manifest_refs.jsonl").open("w", encoding="utf-8") as f:
        for ref in manifest_refs:
            f.write(json.dumps(ref, ensure_ascii=False) + "\n")
    (output_root / "summary.md").write_text(render_summary(manifest, groups), encoding="utf-8")
    return {"manifest": manifest, "asset_groups": groups, "records": records, "manifest_refs": manifest_refs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    parser.add_argument("--runtime-supply-root", type=Path, default=DEFAULT_RUNTIME_SUPPLY_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_compiled_asset_ledger(
        artifacts_root=args.artifacts_root,
        runtime_supply_root=args.runtime_supply_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    manifest = result["manifest"]
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "asset_groups": display_path(args.output_root / "asset_groups.json"),
                "files": display_path(args.output_root / "files.jsonl"),
                "manifest_refs": display_path(args.output_root / "manifest_refs.jsonl"),
                "summary": display_path(args.output_root / "summary.md"),
                "counts": manifest["counts"],
                "runtime_consumable": manifest["runtime_guard"]["runtime_consumable"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
