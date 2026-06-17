#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.irr_scoring import score_point_label_agreement  # noqa: E402


DEFAULT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts/luban_no_human_v1_5/spotcheck_20260601"
PACKET_COLUMNS = [
    "case_id",
    "student_id",
    "point_id",
    "stratum",
    "max_score",
    "point_label",
    "student_answer_excerpt",
    "textbook_provenance",
    "human_hit",
    "human_score",
    "human_note",
]
DEFAULT_LIMITS = {
    "paraphrase": 10,
    "ex_class_b": 10,
    "genuinely_absent": 4,
    "current_class_b": 10,
    "corrected_repaired": 10,
    "stable_deterministic": 3,
}
SUSPECT_STRATA = ("paraphrase", "ex_class_b")
FILLING_INSTRUCTION = (
    "踩字口径: 命中=学生写出教材原文那几个字; 近义/同义/口号/大白话不算; "
    "列举型按写对的原文术语个数给分。对照 textbook_provenance 的原文判,别凭印象。"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _repair_categories(point: dict[str, Any]) -> set[str]:
    squeeze = point.get("term_squeeze_v1_5") if isinstance(point.get("term_squeeze_v1_5"), dict) else {}
    return {str(row.get("category") or "") for row in squeeze.get("repairs") or [] if row.get("category")}


def _repair_terms(point: dict[str, Any], category: str) -> list[str]:
    squeeze = point.get("term_squeeze_v1_5") if isinstance(point.get("term_squeeze_v1_5"), dict) else {}
    return [
        str(row.get("original_term") or row.get("term") or "").strip()
        for row in squeeze.get("repairs") or []
        if str(row.get("category") or "") == category and str(row.get("original_term") or row.get("term") or "").strip()
    ]


def _provenance_excerpt(point: dict[str, Any]) -> str:
    provenance = point.get("textbook_provenance") if isinstance(point.get("textbook_provenance"), dict) else {}
    snippets: list[str] = []
    for term_row in provenance.get("terms") or []:
        term = str(term_row.get("term") or "").strip()
        for anchor in term_row.get("anchors") or []:
            source = str(anchor.get("source_path") or "").strip()
            span = str(anchor.get("span_text") or "").strip().replace("\n", " ")
            if source or span:
                snippets.append(f"{term} | {source} | {span}")
    if snippets:
        return " || ".join(snippets[:3])
    absent = _repair_terms(point, "genuinely_absent")
    return "未锚定: " + "、".join(absent) if absent else ""


def _answer_excerpt(answer: str, label: dict[str, Any], point: dict[str, Any], *, window: int = 90) -> str:
    clean_answer = str(answer or "").replace("\n", " ").strip()
    if len(clean_answer) <= 1200:
        return clean_answer
    terms = [str(term) for term in label.get("matched_terms") or [] if str(term).strip()]
    terms.extend(str(term) for term in point.get("required_terms_v1_5") or [] if str(term).strip())
    for term in terms:
        index = clean_answer.find(term)
        if index >= 0:
            start = max(0, index - window)
            end = min(len(clean_answer), index + len(term) + window)
            return clean_answer[start:end].strip()
    return clean_answer[:1200].strip()


def _all_candidate_rows(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in fixture.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        points = {str(point.get("point_id") or ""): point for point in case.get("gold_scoring_points") or []}
        for sample in case.get("eval_samples") or []:
            student_id = str(sample.get("student_id") or "")
            answer = str(sample.get("answer_text") or "")
            for label in sample.get("no_human_v1_5_labels") or []:
                point_id = str(label.get("point_id") or "")
                point = points.get(point_id) or {}
                categories = _repair_categories(point)
                rows.append(
                    {
                        "case_id": case_id,
                        "student_id": student_id,
                        "point_id": point_id,
                        "max_score": float(point.get("max_score") or label.get("max_score") or 0),
                        "point_label": str(point.get("label") or ""),
                        "student_answer_excerpt": _answer_excerpt(answer, label, point),
                        "textbook_provenance": _provenance_excerpt(point),
                        "pipeline_hit": str(label.get("hit") or ""),
                        "pipeline_score": round(float(label.get("score") or 0), 4),
                        "resolution_class": str(label.get("resolution_class") or ""),
                        "is_deterministic": bool(label.get("is_deterministic")),
                        "independent_triage_applied": bool(label.get("independent_triage_applied")),
                        "repair_categories": sorted(categories),
                        "fallback_repair": str((point.get("term_squeeze_v1_5") or {}).get("fallback_repair") or ""),
                    }
                )
    return sorted(rows, key=lambda row: (row["case_id"], row["student_id"], row["point_id"]))


def _matches_stratum(row: dict[str, Any], stratum: str) -> bool:
    categories = set(row.get("repair_categories") or [])
    if stratum == "paraphrase":
        return "rubric_is_paraphrase" in categories
    if stratum == "ex_class_b":
        return bool(row.get("independent_triage_applied"))
    if stratum == "genuinely_absent":
        return "genuinely_absent" in categories and str(row.get("pipeline_hit")) == "miss"
    if stratum == "current_class_b":
        return str(row.get("resolution_class")) == "B"
    if stratum == "corrected_repaired":
        return bool(categories or row.get("fallback_repair")) and bool(row.get("is_deterministic"))
    if stratum == "stable_deterministic":
        return (
            bool(row.get("is_deterministic"))
            and str(row.get("pipeline_hit")) == "hit"
            and not row.get("independent_triage_applied")
            and not categories
        )
    raise ValueError(f"unknown stratum: {stratum}")


def select_spotcheck_rows(fixture: dict[str, Any], *, limits: dict[str, int] | None = None) -> list[dict[str, Any]]:
    limits = limits or DEFAULT_LIMITS
    all_rows = _all_candidate_rows(fixture)
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, str, str]] = set()
    for stratum in (
        "paraphrase",
        "ex_class_b",
        "genuinely_absent",
        "current_class_b",
        "corrected_repaired",
        "stable_deterministic",
    ):
        count = int(limits.get(stratum, 0))
        taken = 0
        for row in all_rows:
            key = (str(row["case_id"]), str(row["student_id"]), str(row["point_id"]))
            if key in used or not _matches_stratum(row, stratum):
                continue
            selected.append({**row, "stratum": stratum})
            used.add(key)
            taken += 1
            if taken >= count:
                break
    return selected


def build_spotcheck_packet(
    fixture: dict[str, Any],
    *,
    packet_path: Path,
    keys_path: Path,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    rows = select_spotcheck_rows(fixture, limits=limits)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    with packet_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in PACKET_COLUMNS})
    keys = {
        "claim_boundary": "No-human v1.5 spotcheck keys. Open only after PO completes blind labels.",
        "items": [
            {
                "case_id": row["case_id"],
                "student_id": row["student_id"],
                "sample_id": row["student_id"],
                "point_id": row["point_id"],
                "stratum": row["stratum"],
                "pipeline_hit": row["pipeline_hit"],
                "pipeline_score": row["pipeline_score"],
                "resolution_class": row["resolution_class"],
                "is_deterministic": row["is_deterministic"],
                "independent_triage_applied": row["independent_triage_applied"],
                "repair_categories": row["repair_categories"],
                "fallback_repair": row["fallback_repair"],
            }
            for row in rows
        ],
    }
    _write_json(keys_path, keys)
    stratum_counts: dict[str, int] = {}
    for row in rows:
        stratum = str(row["stratum"])
        stratum_counts[stratum] = stratum_counts.get(stratum, 0) + 1
    return {
        "packet_path": str(packet_path),
        "keys_path": str(keys_path),
        "row_count": len(rows),
        "stratum_counts": dict(sorted(stratum_counts.items())),
        "instruction": FILLING_INSTRUCTION,
    }


def _read_packet_rows(packet_path: Path) -> list[dict[str, Any]]:
    with packet_path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _human_rows(packet_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in packet_rows:
        hit = str(row.get("human_hit") or "").strip()
        score = str(row.get("human_score") or "").strip()
        if not hit and not score:
            continue
        rows.append(
            {
                "case_id": row.get("case_id"),
                "sample_id": row.get("student_id"),
                "point_id": row.get("point_id"),
                "hit": hit,
                "score": float(score or 0),
                "stratum": row.get("stratum"),
                "human_note": row.get("human_note") or "",
            }
        )
    return rows


def _pipeline_rows(keys: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": row.get("case_id"),
            "sample_id": row.get("sample_id") or row.get("student_id"),
            "point_id": row.get("point_id"),
            "hit": row.get("pipeline_hit"),
            "score": float(row.get("pipeline_score") or 0),
            "stratum": row.get("stratum"),
        }
        for row in keys.get("items") or []
    ]


def _by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row.get("case_id")), str(row.get("sample_id")), str(row.get("point_id"))): row
        for row in rows
    }


def _breakdown(human: list[dict[str, Any]], pipeline: list[dict[str, Any]]) -> dict[str, Any]:
    human_map = _by_key(human)
    pipeline_map = _by_key(pipeline)
    strata = sorted({str(row.get("stratum") or "") for row in human + pipeline if row.get("stratum")})
    result: dict[str, Any] = {}
    for stratum in strata:
        h_rows = [row for row in human if row.get("stratum") == stratum]
        p_rows = [
            row
            for row in pipeline
            if row.get("stratum") == stratum and (str(row.get("case_id")), str(row.get("sample_id")), str(row.get("point_id"))) in human_map
        ]
        score = score_point_label_agreement(h_rows, p_rows)
        count = int(score["point_count"])
        disagreements = int(score["pre_adjudication_disagreement_count"])
        result[stratum] = {
            **score,
            "disagreement_rate": round(disagreements / count, 4) if count else 0.0,
        }
    return result


def _decision(by_stratum: dict[str, Any]) -> dict[str, Any]:
    suspect_rates = [float((by_stratum.get(stratum) or {}).get("disagreement_rate") or 0) for stratum in SUSPECT_STRATA]
    genuine = by_stratum.get("genuinely_absent") or {}
    genuine_flip = bool(genuine.get("pre_adjudication_disagreement_count"))
    if all(rate <= 0.10 for rate in suspect_rates) and not genuine_flip:
        return {
            "status": "spotcheck_confirmed_strong_go",
            "message": "Suspect strata disagreement <=10% and genuinely_absent has no flip; no-human v1.5 survives this PO spotcheck.",
        }
    if any(rate > 0.15 for rate in suspect_rates) or genuine_flip:
        return {
            "status": "expand_or_rework_suspect_stratum",
            "message": "A suspect stratum exceeded 15% disagreement or genuinely_absent flipped; do not trust the 94.85% headline without layer-specific rework.",
        }
    return {
        "status": "expand_suspect_stratum",
        "message": "A suspect stratum sits between 10% and 15% disagreement; expand that stratum before deciding.",
    }


def score_spotcheck_packet(packet_path: Path, keys_path: Path) -> dict[str, Any]:
    packet_rows = _read_packet_rows(Path(packet_path))
    keys = _read_json(Path(keys_path))
    human = _human_rows(packet_rows)
    pipeline = _pipeline_rows(keys)
    overall = score_point_label_agreement(human, pipeline)
    by_stratum = _breakdown(human, pipeline)
    return {
        "packet_path": str(packet_path),
        "keys_path": str(keys_path),
        "overall": overall,
        "by_stratum": by_stratum,
        "decision": _decision(by_stratum),
    }


def _cmd_build(args: argparse.Namespace) -> int:
    fixture = _read_json(Path(args.fixture))
    output_dir = Path(args.output_dir)
    summary = build_spotcheck_packet(
        fixture,
        packet_path=output_dir / "PO_spotcheck_packet.csv",
        keys_path=output_dir / "PO_spotcheck_keys.json",
    )
    (output_dir / "PO_spotcheck_instruction.txt").write_text(FILLING_INSTRUCTION + "\n", encoding="utf-8")
    _write_json(output_dir / "PO_spotcheck_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    result = score_spotcheck_packet(Path(args.packet), Path(args.keys))
    if args.output:
        _write_json(Path(args.output), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and score Luban no-human v1.5 PO spotcheck packets.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build blind PO packet and hidden key file.")
    build.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    build.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    build.set_defaults(func=_cmd_build)
    score = sub.add_parser("score", help="Score a PO-filled packet against hidden pipeline keys.")
    score.add_argument("--packet", required=True)
    score.add_argument("--keys", required=True)
    score.add_argument("--output")
    score.set_defaults(func=_cmd_score)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
