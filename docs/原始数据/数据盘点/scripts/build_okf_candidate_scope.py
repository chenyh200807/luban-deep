#!/usr/bin/env python3
"""Build full OKF-like source-layer candidate artifacts from aligned cases."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_RUBRIC = INVENTORY_ROOT / "extractions" / "case_rubric_canonical.json"
DEFAULT_SOURCE_ALIGNMENT_ROOT = INVENTORY_ROOT / "extractions" / "okf_source_alignment_v0"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "extractions" / "okf_candidate_scope_v0"
SENTINEL_NAME = ".okf_candidate_scope_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "okf_candidate_scope_v0")
RUNTIME_GUARD = {
    "release_stage": "source_layer_candidate",
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
        sentinel.get("generated_by") != "build_okf_candidate_scope.py"
        or sentinel.get("kind") != "okf_candidate_scope"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {
        "manifest.json",
        "summary.md",
        "cases.jsonl",
        "rubrics.jsonl",
        "scoring_points.jsonl",
        "scoring_point_index.json",
        SENTINEL_NAME,
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
        "kind": "okf_candidate_scope",
        "generated_by": "build_okf_candidate_scope.py",
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


def make_case_id(year: str, case_no: str) -> str:
    return f"case_{year}_{case_no}"


def make_rubric_id(year: str, case_no: str, sub_q: str) -> str:
    return f"rubric_{year}_{case_no}_q{int(sub_q):02d}"


def make_scoring_point_id(year: str, case_no: str, sub_q: str, seq: int) -> str:
    return f"sp_{year}_{case_no}_q{int(sub_q):02d}_{int(seq):02d}"


def load_alignment(source_alignment_root: Path) -> dict[str, dict[str, Any]]:
    report = load_json(source_alignment_root / "report.json")
    if report.get("status") != "case_source_alignment_ready":
        raise ValueError("source alignment must be ready")
    require_non_runtime_guard(report, "source alignment report")
    rows: dict[str, dict[str, Any]] = {}
    with (source_alignment_root / "case_alignment.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            require_non_runtime_guard(record, f"source alignment record {record.get('case_id')}")
            rows[record["case_id"]] = record
    return rows


def split_acceptable_items(text: str, *, point_type: str, point_score: float) -> list[str]:
    if point_type != "列举" or point_score <= 1:
        return []
    candidate = text.split(":", 1)[1] if ":" in text else text
    candidate = candidate.replace("；", ";").replace("、", ";").replace("，", ";").replace(",", ";")
    items = [item.strip() for item in candidate.split(";") if item.strip()]
    return items if len(items) > 1 else []


def build_records(
    canonical_rubric_path: Path,
    alignment_by_case: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    data = load_json(canonical_rubric_path)
    meta = data.get("_meta") or {}
    if meta.get("NOT_official") is not True:
        raise ValueError("canonical rubric must preserve NOT_official=true")
    rubric_data = data.get("rubric")
    if not isinstance(rubric_data, dict):
        raise ValueError("canonical rubric must include rubric object")

    cases: list[dict[str, Any]] = []
    rubrics: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []
    for year, year_cases in sorted(rubric_data.items()):
        for case_no, case_rubrics in sorted(year_cases.items(), key=lambda item: int(item[0])):
            case_id = make_case_id(str(year), str(case_no))
            alignment = alignment_by_case.get(case_id)
            if not alignment:
                raise ValueError(f"missing source alignment for {case_id}")
            case_rubric_ids = []
            case_point_ids = []
            for sub_q, sub_q_data in sorted(case_rubrics.items(), key=lambda item: int(item[0])):
                rubric_id = make_rubric_id(str(year), str(case_no), str(sub_q))
                rubric_point_ids = []
                for point in sub_q_data.get("points") or []:
                    seq = int(point["seq"])
                    point_id = make_scoring_point_id(str(year), str(case_no), str(sub_q), seq)
                    text = str(point["text"])
                    point_score = float(point["score"])
                    point_type = str(point.get("type") or "unknown")
                    point_record = {
                        "schema": "luban_okf_candidate_scoring_point.v0",
                        "point_id": point_id,
                        "case_id": case_id,
                        "rubric_id": rubric_id,
                        "year": str(year),
                        "case_no": str(case_no),
                        "sub_question": str(sub_q),
                        "seq": seq,
                        "text": text,
                        "point_score": point_score,
                        "point_type": point_type,
                        "judge_rule": sub_q_data.get("judge_rule"),
                        "authority": meta.get("authority"),
                        "not_official": True,
                        "official_score_allowed": False,
                        "runtime_guard": RUNTIME_GUARD,
                        "source_ref": canonical_rubric_path.name,
                        "source_path": display_path(canonical_rubric_path),
                        "source_json_path": f'$.rubric["{year}"]["{case_no}"]["{sub_q}"].points[{seq - 1}]',
                        "exam_source": alignment["exam_source"],
                        "question_chunk": alignment["question_chunk"],
                    }
                    acceptable_items = split_acceptable_items(text, point_type=point_type, point_score=point_score)
                    if acceptable_items:
                        point_record["acceptable_items"] = acceptable_items
                        point_record["partial_credit_rule"] = "unknown_from_source"
                        point_record["max_per_group"] = point_score
                    points.append(point_record)
                    rubric_point_ids.append(point_id)
                    case_point_ids.append(point_id)
                rubrics.append({
                    "schema": "luban_okf_candidate_rubric.v0",
                    "rubric_id": rubric_id,
                    "case_id": case_id,
                    "year": str(year),
                    "case_no": str(case_no),
                    "sub_question": str(sub_q),
                    "sub_q_total_score": float(sub_q_data["sub_q_total_score"]),
                    "judge_rule": sub_q_data.get("judge_rule"),
                    "scoring_point_refs": rubric_point_ids,
                    "authority": meta.get("authority"),
                    "not_official": True,
                    "official_score_allowed": False,
                    "runtime_guard": RUNTIME_GUARD,
                    "source_path": display_path(canonical_rubric_path),
                    "source_json_path": f'$.rubric["{year}"]["{case_no}"]["{sub_q}"]',
                    "question_chunk": alignment["question_chunk"],
                    "subquestion_alignment": alignment["subquestion_alignment"],
                })
                case_rubric_ids.append(rubric_id)
            cases.append({
                "schema": "luban_okf_candidate_case.v0",
                "case_id": case_id,
                "year": str(year),
                "case_no": str(case_no),
                "rubric_refs": case_rubric_ids,
                "scoring_point_refs": case_point_ids,
                "authority": meta.get("authority"),
                "not_official": True,
                "official_score_allowed": False,
                "runtime_guard": RUNTIME_GUARD,
                "source_alignment_status": alignment["alignment_status"],
                "exam_source": alignment["exam_source"],
                "question_chunk": alignment["question_chunk"],
                "subquestion_alignment": alignment["subquestion_alignment"],
            })
    return cases, rubrics, points


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_summary(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# OKF candidate scope v0",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Cases: `{manifest['counts']['cases']}`",
        f"- Rubrics: `{manifest['counts']['rubrics']}`",
        f"- Scoring points: `{manifest['counts']['scoring_points']}`",
        f"- Runtime consumable: `{manifest['runtime_guard']['runtime_consumable']}`",
        f"- Official score allowed: `{manifest['runtime_guard']['official_score_allowed']}`",
        "",
        "This is a source-layer candidate scope, not signed runtime supply.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_candidate_scope(
    canonical_rubric_path: Path = DEFAULT_CANONICAL_RUBRIC,
    source_alignment_root: Path = DEFAULT_SOURCE_ALIGNMENT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    alignment_by_case = load_alignment(source_alignment_root)
    cases, rubrics, points = build_records(canonical_rubric_path, alignment_by_case)
    manifest = {
        "schema": "luban_okf_candidate_scope_manifest.v0",
        "generated_at": generated_at,
        "status": "source_layer_candidate_complete",
        "authority_status": "candidate_review",
        "runtime_guard": RUNTIME_GUARD,
        "source_paths": {
            "canonical_rubric": display_path(canonical_rubric_path),
            "source_alignment_root": display_path(source_alignment_root),
        },
        "artifact_refs": {
            "cases": "cases.jsonl",
            "rubrics": "rubrics.jsonl",
            "scoring_points": "scoring_points.jsonl",
            "scoring_point_index": "scoring_point_index.json",
        },
        "counts": {
            "cases": len(cases),
            "rubrics": len(rubrics),
            "scoring_points": len(points),
        },
        "guardrails": [
            "source-layer candidate only",
            "not signed runtime supply",
            "no official scoring claim",
            "no learner truth write",
        ],
    }
    point_index = {
        "schema": "luban_okf_candidate_scoring_point_index.v0",
        "generated_at": generated_at,
        "authority_status": "candidate_review",
        "runtime_guard": RUNTIME_GUARD,
        "points_by_id": {point["point_id"]: point for point in points},
    }

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_jsonl(output_root / "cases.jsonl", cases)
    write_jsonl(output_root / "rubrics.jsonl", rubrics)
    write_jsonl(output_root / "scoring_points.jsonl", points)
    (output_root / "scoring_point_index.json").write_text(
        json.dumps(point_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(output_root / "summary.md", manifest)
    return {
        "output_root": display_path(output_root),
        "manifest": manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-rubric", type=Path, default=DEFAULT_CANONICAL_RUBRIC)
    parser.add_argument("--source-alignment-root", type=Path, default=DEFAULT_SOURCE_ALIGNMENT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_candidate_scope(
        canonical_rubric_path=args.canonical_rubric,
        source_alignment_root=args.source_alignment_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
