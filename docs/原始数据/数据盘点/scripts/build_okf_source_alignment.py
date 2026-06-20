#!/usr/bin/env python3
"""Align canonical rubric cases with cleaned exam JSON case chunks."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_RUBRIC = INVENTORY_ROOT / "extractions" / "case_rubric_canonical.json"
DEFAULT_JSON_LEDGER_SOURCES = INVENTORY_ROOT / "extractions" / "json_source_ledger_v0" / "sources.jsonl"
DEFAULT_EXAM_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "题库"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "extractions" / "okf_source_alignment_v0"
SENTINEL_NAME = ".okf_source_alignment_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "okf_source_alignment_v0")
CHINESE_NUMBERS = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}
RUNTIME_GUARD = {
    "release_stage": "source_alignment",
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
        sentinel.get("generated_by") != "build_okf_source_alignment.py"
        or sentinel.get("kind") != "okf_source_alignment"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {"report.json", "report.md", "case_alignment.jsonl", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "okf_source_alignment",
        "generated_by": "build_okf_source_alignment.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_case_number(text: str) -> str | None:
    patterns = [
        r"案例(?:题)?[（(]?([一二三四五12345])[）)]?",
        r"第[（(]([一二三四五12345])[）)]题",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            token = match.group(1)
            return CHINESE_NUMBERS.get(token, token)
    return None


def target_cases(canonical_rubric_path: Path) -> list[dict[str, Any]]:
    data = load_json(canonical_rubric_path)
    rubric = data.get("rubric")
    if not isinstance(rubric, dict):
        raise ValueError("canonical rubric must include rubric object")
    rows: list[dict[str, Any]] = []
    for year, cases in sorted(rubric.items()):
        for case_no, sub_questions in sorted(cases.items(), key=lambda item: int(item[0])):
            points = 0
            for sub_q in sub_questions.values():
                if isinstance(sub_q, dict) and isinstance(sub_q.get("points"), list):
                    points += len(sub_q["points"])
            rows.append({
                "case_id": f"case_{year}_{case_no}",
                "year": str(year),
                "case_no": str(case_no),
                "sub_questions": sorted(str(key) for key in sub_questions.keys()),
                "rubrics": len(sub_questions),
                "scoring_points": points,
            })
    return rows


def load_exam_source_ledger(path: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("bucket") != "exam_cleaned_json":
                continue
            match = re.search(r"FINAL_CLEANED_EXAM_V(\d{4})\.json$", record.get("source_path", ""))
            if match:
                rows[match.group(1)] = record
    return rows


def exam_path_for_year(exam_root: Path, year: str) -> Path:
    matches = sorted(exam_root.glob(f"*{year}*建筑实务*/FINAL_CLEANED_EXAM_V{year}.json"))
    if not matches:
        raise ValueError(f"missing cleaned exam JSON for year={year}")
    if len(matches) > 1:
        raise ValueError(f"multiple cleaned exam JSON files for year={year}")
    return matches[0]


def has_case_study(chunk: dict[str, Any]) -> bool:
    return any(ex.get("type") == "case_study" for ex in (chunk.get("exercises") or []) if isinstance(ex, dict))


def is_answer_chunk(chunk: dict[str, Any]) -> bool:
    anchor = str((chunk.get("source_meta") or {}).get("original_anchor") or "")
    content = str(chunk.get("content_markdown") or "")
    return "答案" in anchor or "答案解析" in content[:80] or "参考答案" in content[:80]


def case_candidates(exam_path: Path) -> list[dict[str, Any]]:
    data = load_json(exam_path)
    candidates = []
    for index, chunk in enumerate(data.get("chunks") or []):
        if not isinstance(chunk, dict) or not has_case_study(chunk) or is_answer_chunk(chunk):
            continue
        source_meta = chunk.get("source_meta") or {}
        anchor = str(source_meta.get("original_anchor") or "")
        content = str(chunk.get("content_markdown") or "")
        exercises = [ex for ex in (chunk.get("exercises") or []) if isinstance(ex, dict) and ex.get("type") == "case_study"]
        candidates.append({
            "chunk_id": chunk.get("chunk_id"),
            "page": source_meta.get("page_num"),
            "anchor": anchor,
            "json_path": f"$.chunks[{index}]",
            "strong_case_no": parse_case_number(f"{anchor}\n{content[:120]}"),
            "exercise_count": len(exercises),
            "exercises": exercises,
        })
    return sorted(candidates, key=lambda item: (item["page"] or 10**9, item["chunk_id"] or ""))


def choose_case_chunks(exam_path: Path, case_numbers: list[str]) -> dict[str, dict[str, Any]]:
    candidates = case_candidates(exam_path)
    selected: dict[str, dict[str, Any]] = {}
    used_chunks: set[str] = set()
    for candidate in candidates:
        case_no = candidate.get("strong_case_no")
        chunk_id = str(candidate.get("chunk_id"))
        if case_no in case_numbers and case_no not in selected:
            selected[case_no] = candidate
            used_chunks.add(chunk_id)
    for case_no in case_numbers:
        if case_no in selected:
            continue
        for candidate in candidates:
            chunk_id = str(candidate.get("chunk_id"))
            if chunk_id not in used_chunks:
                selected[case_no] = candidate
                used_chunks.add(chunk_id)
                break
    return selected


def subquestion_alignment(target: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    exercises = chunk.get("exercises") or []
    sub_questions = target["sub_questions"]
    if len(exercises) != len(sub_questions):
        return {
            "status": "case_level_only",
            "target_sub_questions": sub_questions,
            "exercise_count": len(exercises),
        }
    pairs = []
    for sub_q, exercise in zip(sub_questions, exercises, strict=True):
        question_data = exercise.get("question_data") or {}
        pairs.append({
            "sub_q_no": sub_q,
            "exercise_score": question_data.get("score"),
            "predicted_node": exercise.get("predicted_node"),
        })
    return {
        "status": "ordinal_match",
        "pairs": pairs,
    }


def build_records(
    *,
    targets: list[dict[str, Any]],
    ledger_by_year: dict[str, dict[str, Any]],
    exam_root: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    targets_by_year: dict[str, list[dict[str, Any]]] = {}
    for target in targets:
        targets_by_year.setdefault(target["year"], []).append(target)

    for year, year_targets in sorted(targets_by_year.items()):
        ledger = ledger_by_year.get(year)
        if not ledger:
            raise ValueError(f"missing exam source ledger record for year={year}")
        exam_path = exam_path_for_year(exam_root, year)
        selected = choose_case_chunks(exam_path, [target["case_no"] for target in year_targets])
        for target in year_targets:
            chunk = selected.get(target["case_no"])
            if not chunk:
                raise ValueError(f"missing case chunk year={year} case={target['case_no']}")
            records.append({
                "schema": "luban_okf_case_source_alignment.v0",
                "case_id": target["case_id"],
                "year": year,
                "case_no": target["case_no"],
                "alignment_status": "case_chunk_found",
                "source_in_ledger": True,
                "runtime_guard": RUNTIME_GUARD,
                "target": {
                    "rubrics": target["rubrics"],
                    "scoring_points": target["scoring_points"],
                    "sub_questions": target["sub_questions"],
                },
                "exam_source": {
                    "source_id": ledger.get("source_id"),
                    "source_path": ledger.get("source_path"),
                    "bucket": ledger.get("bucket"),
                    "authority_status": ledger.get("authority_status"),
                    "file_sha256": (ledger.get("file") or {}).get("sha256"),
                },
                "question_chunk": {
                    "chunk_id": chunk.get("chunk_id"),
                    "page": chunk.get("page"),
                    "anchor": chunk.get("anchor"),
                    "json_path": chunk.get("json_path"),
                    "exercise_count": chunk.get("exercise_count"),
                },
                "subquestion_alignment": subquestion_alignment(target, chunk),
            })
    return records


def report_for(records: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    aligned = sum(1 for record in records if record["alignment_status"] == "case_chunk_found")
    ordinal = sum(1 for record in records if record["subquestion_alignment"]["status"] == "ordinal_match")
    status = "case_source_alignment_ready" if aligned == len(records) else "case_source_alignment_gap_open"
    return {
        "schema": "luban_okf_source_alignment_report.v0",
        "generated_at": generated_at,
        "status": status,
        "runtime_guard": RUNTIME_GUARD,
        "counts": {
            "target_cases": len(records),
            "aligned_cases": aligned,
            "ordinal_subquestion_matches": ordinal,
            "case_level_only": len(records) - ordinal,
        },
        "next_action": {
            "id": "expand_okf_candidate_scope",
            "status": "ready_for_source_layer_expansion" if status == "case_source_alignment_ready" else "blocked",
            "reason": "all canonical cases have cleaned exam JSON case chunks",
        },
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# OKF source alignment v0",
        "",
        f"- Status: `{report['status']}`",
        f"- Target cases: `{report['counts']['target_cases']}`",
        f"- Aligned cases: `{report['counts']['aligned_cases']}`",
        f"- Ordinal sub-question matches: `{report['counts']['ordinal_subquestion_matches']}`",
        f"- Case-level only: `{report['counts']['case_level_only']}`",
        f"- Runtime consumable: `{report['runtime_guard']['runtime_consumable']}`",
        "",
        "This is source-layer alignment only. It does not create runtime supply or official scores.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_source_alignment(
    canonical_rubric_path: Path = DEFAULT_CANONICAL_RUBRIC,
    json_ledger_sources_path: Path = DEFAULT_JSON_LEDGER_SOURCES,
    exam_root: Path = DEFAULT_EXAM_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    targets = target_cases(canonical_rubric_path)
    ledger_by_year = load_exam_source_ledger(json_ledger_sources_path)
    records = build_records(targets=targets, ledger_by_year=ledger_by_year, exam_root=exam_root)
    report = report_for(records, generated_at)

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown_report(output_root / "report.md", report)
    with (output_root / "case_alignment.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "output_root": display_path(output_root),
        "report": report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-rubric", type=Path, default=DEFAULT_CANONICAL_RUBRIC)
    parser.add_argument("--json-ledger-sources", type=Path, default=DEFAULT_JSON_LEDGER_SOURCES)
    parser.add_argument("--exam-root", type=Path, default=DEFAULT_EXAM_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_source_alignment(
        canonical_rubric_path=args.canonical_rubric,
        json_ledger_sources_path=args.json_ledger_sources,
        exam_root=args.exam_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
