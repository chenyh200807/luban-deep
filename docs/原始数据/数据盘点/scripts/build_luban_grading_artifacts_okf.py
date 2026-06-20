#!/usr/bin/env python3
"""Build an AI-only OKF ledger for artifacts/luban_grading_artifacts."""

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
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "luban_grading_artifacts"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "luban_grading_artifacts_okf_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "luban_grading_artifacts_okf_v1")
SENTINEL_NAME = ".luban_grading_artifacts_okf_generated.json"
GENERATOR = "build_luban_grading_artifacts_okf.py"

EXCLUDED_PARTS = {".git", "__pycache__", "node_modules", ".pytest_cache"}
EXCLUDED_FILES = {".DS_Store"}
MANIFEST_LIKE_RE = re.compile(
    r"(manifest|summary|report|finding|audit|ledger|pointer|registry|verdict|coverage|quality|gate|candidate)",
    re.I,
)

RUNTIME_GUARD = {
    "release_stage": "ai_project_context_only",
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
        DEFAULT_ARTIFACT_ROOT.resolve(),
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
    sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    if (
        sentinel.get("generated_by") != GENERATOR
        or sentinel.get("kind") != "luban_grading_artifacts_okf"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {
        SENTINEL_NAME,
        "manifest.json",
        "artifact_runs.jsonl",
        "file_index.jsonl",
        "summary.md",
    }
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "luban_grading_artifacts_okf",
        "generated_by": GENERATOR,
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if set(path.relative_to(root).parts) & EXCLUDED_PARTS:
            continue
        files.append(path)
    return files


def classify_area(run_id: str) -> str:
    lower = run_id.lower()
    rules = [
        ("learning_brain", ("learning_brain", "learner_memory", "grading_to_brain", "outcome_loop")),
        ("runtime_shadow", ("runtime", "live_ab", "live_eval", "ws_", "wechat", "smoke", "default_flip", "production_runtime")),
        ("release_candidate", ("release", "promotion", "canonical", "published", "formal", "candidate", "registry")),
        ("gold_review", ("gold", "teacher_review", "consensus", "arbitration")),
        ("eval_benchmark", ("eval", "ab_", "bakeoff", "calibration", "benchmark", "matrix")),
        ("source_alignment", ("source", "anchor", "backfill", "taxonomy", "standard", "knowledge_graph", "compiler")),
        ("governance_audit", ("audit", "review", "gate", "governance", "scope", "finding")),
        ("skill_pack", ("lecture_answer_skill_pack", "skill_pack")),
    ]
    for area, tokens in rules:
        if any(token in lower for token in tokens):
            return area
    return "artifact_workbench"


def risk_level(run_id: str, area: str, extensions: Counter[str]) -> str:
    lower = run_id.lower()
    if area in {"runtime_shadow", "release_candidate", "learning_brain"}:
        return "high"
    if extensions.get(".db") or extensions.get(".db-wal") or extensions.get(".sql"):
        return "high"
    if any(token in lower for token in ("production", "canonical", "registry", "supabase", "learner", "gbrain")):
        return "high"
    if area in {"gold_review", "eval_benchmark", "source_alignment"}:
        return "medium"
    return "low"


def is_manifest_like(path: Path) -> bool:
    if extension(path) not in {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".csv"}:
        return False
    return bool(MANIFEST_LIKE_RE.search(path.name))


def jsonl_rows(path: Path) -> int | None:
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except UnicodeDecodeError:
        return None


def build_records(artifact_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs = [path for path in sorted(artifact_root.iterdir()) if path.is_dir()]
    run_records: list[dict[str, Any]] = []
    file_records: list[dict[str, Any]] = []
    for run in runs:
        files = iter_files(run)
        ext = Counter(extension(path) for path in files)
        area = classify_area(run.name)
        risk = risk_level(run.name, area, ext)
        jsonl_counts = {}
        for path in files:
            if extension(path) == ".jsonl":
                jsonl_counts[path.relative_to(run).as_posix()] = jsonl_rows(path)
        for path in files:
            stat = path.stat()
            file_records.append(
                {
                    "schema": "luban_grading_artifact_file_record.v1",
                    "run_id": run.name,
                    "area": area,
                    "risk_level": risk,
                    "source_path": display_path(path),
                    "relative_path": path.relative_to(run).as_posix(),
                    "extension": extension(path),
                    "bytes": stat.st_size,
                    "sha256": sha256_file(path),
                    "manifest_like": is_manifest_like(path),
                    "runtime_guard": RUNTIME_GUARD,
                }
            )
        run_records.append(
            {
                "schema": "luban_grading_artifact_run_record.v1",
                "run_id": run.name,
                "area": area,
                "risk_level": risk,
                "source_path": display_path(run),
                "files": len(files),
                "bytes": sum(path.stat().st_size for path in files),
                "extensions": dict(ext.most_common()),
                "manifest_like_files": sum(1 for path in files if is_manifest_like(path)),
                "jsonl_row_counts": dict(sorted(jsonl_counts.items())),
                "largest_files": [
                    {"path": path.relative_to(run).as_posix(), "bytes": path.stat().st_size}
                    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True)[:8]
                ],
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return run_records, sorted(file_records, key=lambda item: item["source_path"])


def render_summary(manifest: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    counts = manifest["counts"]
    lines = [
        "# Luban Grading Artifacts OKF v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Purpose: AI project understanding only; not production, not runtime supply, not official scoring authority.",
        f"- Runs indexed: **{counts['runs']}**",
        f"- Files indexed: **{counts['files']}**",
        f"- Total bytes: **{counts['total_bytes']:,}**",
        "",
        "## Area Counts",
        "",
    ]
    for area, count in (counts.get("by_area") or {}).items():
        lines.append(f"- `{area}`: {count}")
    lines.extend(["", "## Risk Counts", ""])
    for risk, count in (counts.get("by_risk_level") or {}).items():
        lines.append(f"- `{risk}`: {count}")
    lines.extend(["", "## Highest-Risk Sample", "", "| Run | Area | Files | Bytes |", "|---|---|---:|---:|"])
    high_risk = [run for run in runs if run["risk_level"] == "high"]
    for run in sorted(high_risk, key=lambda item: item["bytes"], reverse=True)[:20]:
        lines.append(f"| `{run['run_id']}` | `{run['area']}` | {run['files']} | {run['bytes']:,} |")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This ledger is for AI situational awareness only.",
            "- It deliberately does not promote canonical, gold, registry, runtime, or learner-state artifacts into truth.",
            "- Runtime use requires a separate signed runtime supply pointer and consumer proof outside OKF.",
            "- If a directory name says release/canonical/production, treat it as high-risk context until verified elsewhere.",
        ]
    )
    return "\n".join(lines)


def build_luban_grading_artifacts_okf(
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not artifact_root.exists() or not artifact_root.is_dir():
        raise ValueError(f"artifact root does not exist: {display_path(artifact_root)}")
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    runs, files = build_records(artifact_root)
    if not runs:
        raise ValueError("no luban grading artifact runs found")
    area_counts = Counter(run["area"] for run in runs)
    risk_counts = Counter(run["risk_level"] for run in runs)
    ext_counts = Counter(record["extension"] for record in files)

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    manifest = {
        "schema": "luban_grading_artifacts_okf_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "ai_project_context_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_roots": {
            "luban_grading_artifacts": display_path(artifact_root),
        },
        "copy_policy": {
            "payloads_copied": False,
            "reason": "OKF is a navigation and risk map for AI understanding, not a production artifact mirror",
        },
        "artifact_refs": {
            "artifact_runs": "artifact_runs.jsonl",
            "file_index": "file_index.jsonl",
            "summary": "summary.md",
        },
        "counts": {
            "runs": len(runs),
            "files": len(files),
            "total_bytes": sum(record["bytes"] for record in files),
            "manifest_like_files": sum(1 for record in files if record["manifest_like"]),
            "by_area": dict(area_counts.most_common()),
            "by_risk_level": dict(risk_counts.most_common()),
            "by_extension": dict(ext_counts.most_common()),
        },
        "guardrails": [
            "AI project understanding only",
            "not production",
            "not runtime supply",
            "not official scoring authority",
            "not canonical learner truth",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "artifact_runs.jsonl").open("w", encoding="utf-8") as handle:
        for run in runs:
            handle.write(json.dumps(run, ensure_ascii=False) + "\n")
    with (output_root / "file_index.jsonl").open("w", encoding="utf-8") as handle:
        for record in files:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output_root / "summary.md").write_text(render_summary(manifest, runs), encoding="utf-8")
    return {"manifest": manifest, "runs": runs, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    result = build_luban_grading_artifacts_okf(
        artifact_root=args.artifact_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "artifact_runs": display_path(args.output_root / "artifact_runs.jsonl"),
                "file_index": display_path(args.output_root / "file_index.jsonl"),
                "summary": display_path(args.output_root / "summary.md"),
                "counts": result["manifest"]["counts"],
                "runtime_consumable": result["manifest"]["runtime_guard"]["runtime_consumable"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
