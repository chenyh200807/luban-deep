#!/usr/bin/env python3
"""Compare the current OKF source-layer pilot with the rubric target."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_RUBRIC = INVENTORY_ROOT / "extractions" / "case_rubric_canonical.json"
DEFAULT_JSON_LEDGER_MANIFEST = INVENTORY_ROOT / "extractions" / "json_source_ledger_v0" / "manifest.json"
DEFAULT_OKF_MANIFEST = INVENTORY_ROOT / "extractions" / "okf_rubric_pilot_v0" / "manifest.json"
DEFAULT_DRY_CONSUMER_RECEIPT = INVENTORY_ROOT / "extractions" / "okf_dry_consumer_v0" / "receipt.json"
DEFAULT_SOURCE_ALIGNMENT_REPORT = INVENTORY_ROOT / "extractions" / "okf_source_alignment_v0" / "report.json"
DEFAULT_CANDIDATE_SCOPE_MANIFEST = INVENTORY_ROOT / "extractions" / "okf_candidate_scope_v0" / "manifest.json"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "extractions" / "okf_landing_gap_v0"
SENTINEL_NAME = ".okf_landing_gap_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "okf_landing_gap_v0")
RUNTIME_GUARD = {
    "release_stage": "source_layer_gap_report",
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
        sentinel.get("generated_by") != "build_okf_landing_gap.py"
        or sentinel.get("kind") != "okf_landing_gap"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {"report.json", "report.md", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "okf_landing_gap",
        "generated_by": "build_okf_landing_gap.py",
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
    required_false = [
        "runtime_consumable",
        "installed_runtime_supply",
        "canonical_write_allowed",
        "learner_truth_write_allowed",
        "gbrain_write_allowed",
        "production_registry_write_allowed",
        "official_score_allowed",
    ]
    for key in required_false:
        if guard.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def summarize_canonical_rubric(path: Path) -> dict[str, Any]:
    data = load_json(path)
    rubric = data.get("rubric")
    if not isinstance(rubric, dict):
        raise ValueError("canonical rubric must include rubric object")
    by_year = []
    point_total = 0
    rubric_total = 0
    case_total = 0
    for year, cases in sorted(rubric.items()):
        if not isinstance(cases, dict):
            continue
        year_cases = len(cases)
        year_points = 0
        year_rubrics = 0
        for case in cases.values():
            if not isinstance(case, dict):
                continue
            year_rubrics += len(case)
            for sub_q in case.values():
                if isinstance(sub_q, dict) and isinstance(sub_q.get("points"), list):
                    year_points += len(sub_q["points"])
        by_year.append({
            "year": str(year),
            "cases": year_cases,
            "rubrics": year_rubrics,
            "scoring_points": year_points,
        })
        case_total += year_cases
        rubric_total += year_rubrics
        point_total += year_points
    return {
        "source_path": display_path(path),
        "cases": case_total,
        "rubrics": rubric_total,
        "scoring_points": point_total,
        "by_year": by_year,
    }


def summarize_ledger(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    require_non_runtime_guard(manifest, "json source ledger manifest")
    counts = manifest.get("counts") or {}
    buckets = counts.get("buckets") or {}
    return {
        "source_path": display_path(path),
        "json_sources": int(counts.get("json_sources") or 0),
        "buckets": buckets,
        "authority_status": manifest.get("authority_status"),
    }


def summarize_okf(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    require_non_runtime_guard(manifest, "okf manifest")
    counts = manifest.get("counts") or {}
    return {
        "source_path": display_path(path),
        "cases": int(counts.get("cases") or 0),
        "rubrics": int(counts.get("rubrics") or 0),
        "scoring_points": int(counts.get("scoring_points") or 0),
        "authority": manifest.get("authority"),
        "official_score_allowed": manifest.get("official_score_allowed"),
    }


def summarize_dry_consumer(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "source_path": display_path(path),
            "exists": False,
            "status": "missing",
        }
    receipt = load_json(path)
    require_non_runtime_guard(receipt, "okf dry consumer receipt")
    return {
        "source_path": display_path(path),
        "exists": True,
        "status": receipt.get("status"),
        "counts": receipt.get("counts") or {},
    }


def summarize_source_alignment(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "source_path": display_path(path),
            "exists": False,
            "status": "missing",
        }
    report = load_json(path)
    require_non_runtime_guard(report, "okf source alignment report")
    return {
        "source_path": display_path(path),
        "exists": True,
        "status": report.get("status"),
        "counts": report.get("counts") or {},
    }


def summarize_candidate_scope(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "source_path": display_path(path),
            "exists": False,
            "status": "missing",
            "cases": 0,
            "rubrics": 0,
            "scoring_points": 0,
        }
    manifest = load_json(path)
    require_non_runtime_guard(manifest, "okf candidate scope manifest")
    counts = manifest.get("counts") or {}
    return {
        "source_path": display_path(path),
        "exists": True,
        "status": manifest.get("status"),
        "cases": int(counts.get("cases") or 0),
        "rubrics": int(counts.get("rubrics") or 0),
        "scoring_points": int(counts.get("scoring_points") or 0),
    }


def make_gap(target: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return {
        "remaining_cases": max(0, int(target["cases"]) - int(current["cases"])),
        "remaining_rubrics": max(0, int(target["rubrics"]) - int(current["rubrics"])),
        "remaining_scoring_points": max(0, int(target["scoring_points"]) - int(current["scoring_points"])),
    }


def next_actions(
    gap: dict[str, Any],
    *,
    dry_consumer: dict[str, Any],
    source_alignment: dict[str, Any],
    candidate_scope: dict[str, Any],
) -> list[dict[str, Any]]:
    dry_consumer_completed = (
        dry_consumer.get("exists") is True
        and dry_consumer.get("status") == "dry_consumed_non_runtime"
    )
    source_alignment_completed = (
        source_alignment.get("exists") is True
        and source_alignment.get("status") == "case_source_alignment_ready"
    )
    candidate_scope_completed = (
        candidate_scope.get("exists") is True
        and candidate_scope.get("status") == "source_layer_candidate_complete"
        and gap["remaining_scoring_points"] == 0
    )
    actions = [
        {
            "id": "okf_dry_consumer",
            "status": "completed" if dry_consumer_completed else "required",
            "reason": (
                "compiled inspection artifacts were read without runtime/canonical writes"
                if dry_consumer_completed
                else "prove compiled inspection artifacts can be read without runtime/canonical writes"
            ),
        },
        {
            "id": "ledger_to_okf_source_alignment",
            "status": "completed" if source_alignment_completed else "required",
            "reason": (
                "exam_cleaned_json and rubric candidate cases are source-aligned"
                if source_alignment_completed
                else "align exam_cleaned_json and rubric candidate sources before expanding cases"
            ),
        },
    ]
    actions.append({
        "id": "expand_okf_candidate_scope",
        "status": "completed" if candidate_scope_completed else "blocked_until_alignment",
        "reason": (
            "source-layer candidate scope covers the canonical rubric target"
            if candidate_scope_completed
            else "remaining scoring points exist, but expansion should use reviewed JSON source alignment first"
        ),
    })
    return actions


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# OKF landing gap v0",
        "",
        f"- Status: `{report['status']}`",
        f"- Target cases: `{report['target']['canonical_rubric']['cases']}`",
        f"- Target scoring points: `{report['target']['canonical_rubric']['scoring_points']}`",
        f"- Current OKF cases: `{report['current']['okf_pilot']['cases']}`",
        f"- Current OKF scoring points: `{report['current']['okf_pilot']['scoring_points']}`",
        f"- Remaining cases: `{report['gap']['remaining_cases']}`",
        f"- Remaining scoring points: `{report['gap']['remaining_scoring_points']}`",
        "",
        "## Guardrail",
        "",
        "- This report is a source-layer gap report, not runtime supply.",
        "- It cannot write official score, canonical truth, LearnerState, GBrain, or production registry.",
        "",
        "## Next actions",
        "",
    ]
    for action in report["next_actions"]:
        lines.append(f"- `{action['id']}`: {action['status']} — {action['reason']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_gap_report(
    canonical_rubric_path: Path = DEFAULT_CANONICAL_RUBRIC,
    json_ledger_manifest_path: Path = DEFAULT_JSON_LEDGER_MANIFEST,
    okf_manifest_path: Path = DEFAULT_OKF_MANIFEST,
    dry_consumer_receipt_path: Path = DEFAULT_DRY_CONSUMER_RECEIPT,
    source_alignment_report_path: Path = DEFAULT_SOURCE_ALIGNMENT_REPORT,
    candidate_scope_manifest_path: Path = DEFAULT_CANDIDATE_SCOPE_MANIFEST,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    target = summarize_canonical_rubric(canonical_rubric_path)
    ledger = summarize_ledger(json_ledger_manifest_path)
    okf = summarize_okf(okf_manifest_path)
    dry_consumer = summarize_dry_consumer(dry_consumer_receipt_path)
    source_alignment = summarize_source_alignment(source_alignment_report_path)
    candidate_scope = summarize_candidate_scope(candidate_scope_manifest_path)
    current_for_gap = candidate_scope if candidate_scope.get("exists") else okf
    gap = make_gap(target, current_for_gap)
    status = "source_layer_gap_open" if Counter(gap).total() > 0 else "source_layer_target_matched"
    report = {
        "schema": "luban_okf_landing_gap_report.v0",
        "generated_at": generated_at,
        "status": status,
        "runtime_guard": RUNTIME_GUARD,
        "target": {
            "canonical_rubric": target,
        },
        "current": {
            "json_source_ledger": ledger,
            "okf_pilot": okf,
            "okf_dry_consumer": dry_consumer,
            "okf_source_alignment": source_alignment,
            "okf_candidate_scope": candidate_scope,
        },
        "gap": gap,
        "next_actions": next_actions(
            gap,
            dry_consumer=dry_consumer,
            source_alignment=source_alignment,
            candidate_scope=candidate_scope,
        ),
    }

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown_report(output_root / "report.md", report)
    return {
        "output_root": display_path(output_root),
        "report": report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-rubric", type=Path, default=DEFAULT_CANONICAL_RUBRIC)
    parser.add_argument("--json-ledger-manifest", type=Path, default=DEFAULT_JSON_LEDGER_MANIFEST)
    parser.add_argument("--okf-manifest", type=Path, default=DEFAULT_OKF_MANIFEST)
    parser.add_argument("--dry-consumer-receipt", type=Path, default=DEFAULT_DRY_CONSUMER_RECEIPT)
    parser.add_argument("--source-alignment-report", type=Path, default=DEFAULT_SOURCE_ALIGNMENT_REPORT)
    parser.add_argument("--candidate-scope-manifest", type=Path, default=DEFAULT_CANDIDATE_SCOPE_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_gap_report(
        canonical_rubric_path=args.canonical_rubric,
        json_ledger_manifest_path=args.json_ledger_manifest,
        okf_manifest_path=args.okf_manifest,
        dry_consumer_receipt_path=args.dry_consumer_receipt,
        source_alignment_report_path=args.source_alignment_report,
        candidate_scope_manifest_path=args.candidate_scope_manifest,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
