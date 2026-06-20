#!/usr/bin/env python3
"""Build an OKF-ready ledger for artifacts/knowledge_compiler."""

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
DEFAULT_COMPILER_ROOT = REPO_ROOT / "artifacts" / "knowledge_compiler" / "2026"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "knowledge_compiler_okf_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "knowledge_compiler_okf_v1")
SENTINEL_NAME = ".knowledge_compiler_okf_generated.json"
GENERATOR = "build_knowledge_compiler_okf.py"

EXCLUDED_PARTS = {".git", "__pycache__", "node_modules", ".pytest_cache"}
EXCLUDED_FILES = {".DS_Store"}
MANIFEST_LIKE_RE = re.compile(
    r"(manifest|summary|report|finding|quality|audit|proposal|calibration|pointer|registry|ledger)",
    re.I,
)

RUNTIME_GUARD = {
    "release_stage": "knowledge_compiler_okf_inventory_only",
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
        DEFAULT_COMPILER_ROOT.resolve(),
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
        or sentinel.get("kind") != "knowledge_compiler_okf"
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
        "compiler_runs.jsonl",
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
        "kind": "knowledge_compiler_okf",
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


def compiler_stage(run_name: str) -> str:
    lower = run_name.lower()
    if lower.startswith("pytest-"):
        return "fixture"
    if any(token in lower for token in ("release", "published", "signed")):
        return "release"
    return "candidate"


def run_kind(run_name: str) -> str:
    lower = run_name.lower()
    if lower.startswith("pytest-"):
        return "test_fixture"
    if lower.startswith("lecture_compile"):
        return "lecture_compile"
    if lower.startswith("mvp-answer-rubric"):
        return "answer_rubric_candidate"
    if lower.startswith("mvp-rubric-ab"):
        return "rubric_ab_eval"
    if lower.startswith("mvp-rubric-artifact"):
        return "rubric_artifact_candidate"
    if lower.startswith("scoring-point-assets"):
        return "scoring_point_candidate_assets"
    if lower.startswith("scoring-point-recall-calibration"):
        return "scoring_point_recall_calibration"
    return "compiler_workbench_run"


def is_manifest_like(path: Path) -> bool:
    if extension(path) not in {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}:
        return False
    return bool(MANIFEST_LIKE_RE.search(path.name))


def jsonl_rows(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def build_records(compiler_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs = [path for path in sorted(compiler_root.iterdir()) if path.is_dir()]
    file_records: list[dict[str, Any]] = []
    run_records: list[dict[str, Any]] = []
    for run in runs:
        files = iter_files(run)
        ext = Counter(extension(path) for path in files)
        stage = compiler_stage(run.name)
        kind = run_kind(run.name)
        jsonl_counts = {}
        for path in files:
            if extension(path) == ".jsonl":
                try:
                    jsonl_counts[path.relative_to(run).as_posix()] = jsonl_rows(path)
                except UnicodeDecodeError:
                    jsonl_counts[path.relative_to(run).as_posix()] = None
        for path in files:
            stat = path.stat()
            file_records.append(
                {
                    "schema": "luban_knowledge_compiler_file_record.v1",
                    "run_id": run.name,
                    "run_kind": kind,
                    "compiler_stage": stage,
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
                "schema": "luban_knowledge_compiler_run_record.v1",
                "run_id": run.name,
                "run_kind": kind,
                "compiler_stage": stage,
                "source_path": display_path(run),
                "files": len(files),
                "bytes": sum(path.stat().st_size for path in files),
                "extensions": dict(ext.most_common()),
                "manifest_like_files": sum(1 for path in files if is_manifest_like(path)),
                "jsonl_row_counts": dict(sorted(jsonl_counts.items())),
                "largest_files": [
                    {
                        "path": path.relative_to(run).as_posix(),
                        "bytes": path.stat().st_size,
                    }
                    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True)[:8]
                ],
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return run_records, sorted(file_records, key=lambda item: item["source_path"])


def render_summary(manifest: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    counts = manifest["counts"]
    lines = [
        "# Knowledge Compiler OKF v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Authority: compiler workbench inventory only; not runtime supply and not official scoring authority.",
        f"- Runs indexed: **{counts['runs']}**",
        f"- Files indexed: **{counts['files']}**",
        f"- Total bytes: **{counts['total_bytes']:,}**",
        "",
        "## Stage Counts",
        "",
    ]
    for stage, count in (counts.get("by_stage") or {}).items():
        lines.append(f"- `{stage}`: {count}")
    lines.extend(["", "## Compiler Runs", "", "| Run | Stage | Kind | Files | Bytes |", "|---|---|---|---:|---:|"])
    for run in runs:
        lines.append(
            f"| `{run['run_id']}` | `{run['compiler_stage']}` | `{run['run_kind']}` | "
            f"{run['files']} | {run['bytes']:,} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- `candidate` means useful compiler output that still needs source review or signing.",
            "- `release` means release-shaped naming only unless a separate runtime supply pointer signs it.",
            "- `fixture` means test/workbench data; never promote directly into production runtime supply.",
            "- This ledger copies no payloads. Source files remain in `artifacts/knowledge_compiler/2026`.",
        ]
    )
    return "\n".join(lines)


def build_knowledge_compiler_okf(
    compiler_root: Path = DEFAULT_COMPILER_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not compiler_root.exists() or not compiler_root.is_dir():
        raise ValueError(f"compiler root does not exist: {display_path(compiler_root)}")
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    runs, files = build_records(compiler_root)
    if not runs:
        raise ValueError("no knowledge compiler runs found")
    stage_counts = Counter(run["compiler_stage"] for run in runs)
    kind_counts = Counter(run["run_kind"] for run in runs)
    ext_counts = Counter(record["extension"] for record in files)

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    manifest = {
        "schema": "luban_knowledge_compiler_okf_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "knowledge_compiler_workbench_inventory_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_roots": {
            "knowledge_compiler": display_path(compiler_root),
        },
        "copy_policy": {
            "payloads_copied": False,
            "reason": "OKF cards route to compiler artifacts without duplicating workbench payloads",
        },
        "artifact_refs": {
            "compiler_runs": "compiler_runs.jsonl",
            "file_index": "file_index.jsonl",
            "summary": "summary.md",
        },
        "counts": {
            "runs": len(runs),
            "files": len(files),
            "total_bytes": sum(record["bytes"] for record in files),
            "manifest_like_files": sum(1 for record in files if record["manifest_like"]),
            "by_stage": dict(stage_counts.most_common()),
            "by_kind": dict(kind_counts.most_common()),
            "by_extension": dict(ext_counts.most_common()),
        },
        "guardrails": [
            "knowledge compiler workbench inventory only",
            "candidate artifacts are not signed release truth",
            "fixture artifacts are not production runtime supply",
            "no official score claim",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "compiler_runs.jsonl").open("w", encoding="utf-8") as handle:
        for run in runs:
            handle.write(json.dumps(run, ensure_ascii=False) + "\n")
    with (output_root / "file_index.jsonl").open("w", encoding="utf-8") as handle:
        for record in files:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output_root / "summary.md").write_text(render_summary(manifest, runs), encoding="utf-8")
    return {"manifest": manifest, "runs": runs, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-root", type=Path, default=DEFAULT_COMPILER_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_knowledge_compiler_okf(
        compiler_root=args.compiler_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "compiler_runs": display_path(args.output_root / "compiler_runs.jsonl"),
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
