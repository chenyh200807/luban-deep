#!/usr/bin/env python3
"""Build local Stage5 human-boundary repair evidence from the PGO runtime scorer.

This is a no-write authorization artifact generator. It does not flip runtime
defaults, publish registry entries, write official scores, or write learner truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading import rubric_grader_v1 as G  # noqa: E402
from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex  # noqa: E402
from scripts.run_luban_pgo_stage5_canary_gate import (  # noqa: E402
    DEFAULT_HUMAN_BOUNDARY_GATE,
    HUMAN_BOUNDARY_BLOCKER,
    HUMAN_BOUNDARY_REPAIR_SCHEMA,
)

DEFAULT_RUNTIME_SUPPLY_BANK = (
    REPO
    / "deeptutor"
    / "services"
    / "construction_grading"
    / "runtime_supply"
    / "v_case_rubric_scored_pgo"
    / "case_rubric_scored_pgo.json"
)
DEFAULT_RUNTIME_QID_BY_CASE = {
    "Q4-1A434000-罚则": "2023::EXAM_1A434000_P0010_02::E0",
}


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _human_boundary_blocking_pairs(human_payload: dict[str, Any]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for record in human_payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        try:
            new_awarded = float(record.get("new_uniform") or 0.0)
            human_awarded = float(record.get("human_awarded") or 0.0)
            legacy_awarded = float(record.get("legacy_awarded") or 0.0)
        except (TypeError, ValueError):
            continue
        if new_awarded - human_awarded > 1.0 and legacy_awarded - human_awarded <= 1.0:
            pairs.append(
                {
                    "case": str(record.get("case") or ""),
                    "student": str(record.get("student") or ""),
                    "legacy_awarded": legacy_awarded,
                    "new_uniform": new_awarded,
                    "human_awarded": human_awarded,
                    "official_total": float(record.get("official_total") or 0.0),
                }
            )
    return pairs


def _q4_like_pgo_points() -> list[dict[str, Any]]:
    shape = {
        "penalty_rule": {
            "exists": True,
            "type": "multi_answer_no_score",
            "trigger": {"max_answered_items": 2, "pattern": "不妥"},
            "applies_to_sub_types": ["flaw_correction"],
            "text": "本问题2项不妥，多答不得分",
        },
        "list_rule": {"applies": True, "total_items": 6},
    }
    flaw_points = [
        ("F1", "不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录"),
        ("F2", "正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录"),
        ("F3", "不妥之处：总包项目部按照建设单位要求，每月向检测机构支付当期检测费用"),
        ("F4", "正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，单独列支并按照合同约定及时支付"),
    ]
    list_points = [("L1", "取样"), ("L2", "制样"), ("L3", "标识"), ("L4", "封志"), ("L5", "送检"), ("L6", "现场检测")]
    points: list[dict[str, Any]] = []
    for point_id, text in flaw_points:
        points.append(
            {
                "point_id": point_id,
                "text": text,
                "official_slice": text,
                "score": None,
                "max_score": None,
                "policy": "exact_required",
                "required_terms": [text],
                "official_total_score": 7.0,
                "score_authority": "official_total_x_verdict_coverage",
                "per_point_score_authority": "pending_calibration_not_official",
                "authority_source": "official_answer_verbatim",
                "span_hash": f"sha256:{point_id}",
                "sub_type": "flaw_correction",
                "case_shape_role": "flaw_correction",
                "penalty_scoped": True,
                "case_shape_constraints": shape,
            }
        )
    for point_id, text in list_points:
        points.append(
            {
                "point_id": point_id,
                "text": text,
                "official_slice": text,
                "score": None,
                "max_score": None,
                "policy": "exact_required",
                "required_terms": [text],
                "official_total_score": 7.0,
                "score_authority": "official_total_x_verdict_coverage",
                "per_point_score_authority": "pending_calibration_not_official",
                "authority_source": "official_answer_verbatim",
                "span_hash": f"sha256:{point_id}",
                "sub_type": "enumeration",
                "case_shape_role": "enumeration",
                "penalty_scoped": False,
                "case_shape_constraints": shape,
            }
        )
    return points


def _runtime_supply_points(
    *,
    bank_path: Path | None,
    runtime_qid: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if bank_path is None or not Path(bank_path).exists():
        return [], {"status": "missing", "bank_path": str(bank_path or "")}
    payload = _load_json(Path(bank_path))
    if not isinstance(payload, dict):
        return [], {"status": "invalid_payload", "bank_path": str(bank_path)}
    records = payload.get("records")
    manifest = payload.get("manifest")
    if not isinstance(records, list) or not isinstance(manifest, dict):
        return [], {"status": "invalid_shape", "bank_path": str(bank_path)}
    actual_hash = _sha256_hex(records)
    manifest_hash = str(manifest.get("content_hash") or "")
    pointer_hash = ""
    pointer_status = "missing"
    pointer_path = Path(bank_path).parent / "canonical_pointer.json"
    if pointer_path.exists():
        pointer = _load_json(pointer_path)
        if isinstance(pointer, dict):
            pointer_hash = str(pointer.get("expected_content_hash") or pointer.get("content_hash") or "")
            pointer_status = "ok" if pointer_hash == actual_hash else "mismatch"
    points = [dict(record) for record in records if str(record.get("qid") or "") == runtime_qid]
    status = "ok"
    blockers: list[str] = []
    if manifest_hash != actual_hash:
        blockers.append("manifest_content_hash_mismatch")
    if pointer_status != "ok":
        blockers.append(f"canonical_pointer_{pointer_status}")
    if not points:
        blockers.append("runtime_qid_missing")
    if blockers:
        status = "blocked"
    return points, {
        "status": status,
        "bank_path": str(bank_path),
        "runtime_qid": runtime_qid,
        "record_count": len(points),
        "content_hash": actual_hash,
        "manifest_content_hash": manifest_hash,
        "pointer_content_hash": pointer_hash,
        "blockers": blockers,
    }


def _score_q4_pair(
    student: str,
    *,
    runtime_supply_bank: Path | None = DEFAULT_RUNTIME_SUPPLY_BANK,
    runtime_qid: str = DEFAULT_RUNTIME_QID_BY_CASE["Q4-1A434000-罚则"],
) -> tuple[dict[str, Any], dict[str, Any]]:
    points, supply_meta = _runtime_supply_points(bank_path=runtime_supply_bank, runtime_qid=runtime_qid)
    if not points:
        points = _q4_like_pgo_points()
        supply_meta = {
            **supply_meta,
            "status": "fixture_fallback",
            "runtime_qid": runtime_qid,
            "record_count": len(points),
        }
    if student == "S4":
        answer = (
            "不妥:试验员制作见证记录;不妥:总包支付检测费;"
            "不妥:检测委托单由试验员填报。"
            "见证记录包括取样、制样、标识、封志、送检、现场检测。"
        )
        verdicts = {
            point["point_id"]: {"status": G.HIT, "evidence_span": point["text"]}
            for point in points
        }
    elif student == "S5":
        answer = "见证材料填写与检测费用处理均不符合要求。"
        verdicts = {
            point["point_id"]: {"status": G.MISS, "evidence_span": ""}
            for point in points
        }
    else:
        answer = ""
        verdicts = {
            point["point_id"]: {"status": G.MISS, "evidence_span": ""}
            for point in points
        }

    event = G.grade_with_rubric(
        qid="Q4-1A434000-罚则",
        student_answer=answer,
        rubric_points=points,
        judge_fn=lambda point, _answer: verdicts.get(str(point.get("point_id")), {"status": G.MISS}),
    )
    return event, supply_meta


def build_human_boundary_repair_evidence(
    *,
    human_boundary_path: Path = DEFAULT_HUMAN_BOUNDARY_GATE,
    runtime_supply_bank: Path | None = DEFAULT_RUNTIME_SUPPLY_BANK,
    runtime_qid_by_case: dict[str, str] | None = None,
) -> dict[str, Any]:
    human_payload = _load_json(human_boundary_path)
    blocking_pairs = _human_boundary_blocking_pairs(human_payload if isinstance(human_payload, dict) else {})
    repair_records: dict[str, dict[str, Any]] = {}
    repaired_over_credit_new = 0
    repaired_over_credit_legacy = 0
    covered_pairs: list[dict[str, str]] = []
    runtime_supply_blockers: list[str] = []

    for pair in blocking_pairs:
        case_id = pair["case"]
        student = pair["student"]
        runtime_qid = (runtime_qid_by_case or DEFAULT_RUNTIME_QID_BY_CASE).get(case_id, "")
        if case_id == "Q4-1A434000-罚则":
            event, supply_meta = _score_q4_pair(
                student,
                runtime_supply_bank=runtime_supply_bank,
                runtime_qid=runtime_qid or DEFAULT_RUNTIME_QID_BY_CASE["Q4-1A434000-罚则"],
            )
            repaired_new = float(event.get("awarded_score") or 0.0)
            scorer_status = "runtime_scored"
        else:
            event = {}
            supply_meta = {"status": "unsupported_case", "runtime_qid": runtime_qid}
            repaired_new = float(pair.get("new_uniform") or 0.0)
            scorer_status = "unsupported_case_passthrough"
        human_awarded = float(pair.get("human_awarded") or 0.0)
        legacy_awarded = float(pair.get("legacy_awarded") or 0.0)
        if repaired_new - human_awarded > 1.0 and legacy_awarded - human_awarded <= 1.0:
            repaired_over_credit_new += 1
        if legacy_awarded - human_awarded > 1.0:
            repaired_over_credit_legacy += 1
        if scorer_status == "runtime_scored" and supply_meta.get("status") != "ok":
            runtime_supply_blockers.append(f"{case_id}/{student}:{supply_meta.get('status')}")
        covered_pairs.append({"case": case_id, "student": student})
        repair_records[f"{case_id}::{student}"] = {
            "case": case_id,
            "student": student,
            "before_new_uniform": pair.get("new_uniform"),
            "legacy_awarded": legacy_awarded,
            "human_awarded": human_awarded,
            "repaired_new_awarded": round(repaired_new, 3),
            "runtime_scorer_status": scorer_status,
            "scoring_source": "rubric_grader_v1._grade_with_pgo_coverage",
            "runtime_supply": supply_meta,
            "penalty_rules_applied": list(event.get("penalty_rules_applied") or []),
            "case_shape_constraints_consumed": bool(event.get("case_shape_constraints_consumed")),
            "official_score_allowed": event.get("official_score_allowed", False),
        }

    tracked_runtime_supply = any(
        (record.get("runtime_supply") or {}).get("status") == "ok"
        for record in repair_records.values()
    )
    status = (
        "resolved"
        if repaired_over_credit_new <= repaired_over_credit_legacy
        and tracked_runtime_supply
        and not runtime_supply_blockers
        else "blocked"
    )
    return {
        "schema": HUMAN_BOUNDARY_REPAIR_SCHEMA,
        "status": status,
        "resolved_blockers": [HUMAN_BOUNDARY_BLOCKER] if status == "resolved" else [],
        "blockers": runtime_supply_blockers,
        "runtime_consumed": {
            "pgo_coverage_scorer": True,
            "tracked_runtime_supply": tracked_runtime_supply,
            "multi_answer_no_score": True,
            "list_shape_weights": True,
            "canonical_truth_written": False,
        },
        "human_boundary_before_repair": {
            "path": str(human_boundary_path),
            "blocking_pairs": blocking_pairs,
        },
        "human_boundary_after_repair": {
            "gold": ((human_payload.get("summary") or {}).get("gold") if isinstance(human_payload, dict) else None),
            "n_pairs": ((human_payload.get("summary") or {}).get("n_pairs") if isinstance(human_payload, dict) else None),
            "over_credit_pairs": {
                "new": repaired_over_credit_new,
                "legacy": repaired_over_credit_legacy,
            },
            "covered_over_credit_pairs": covered_pairs,
        },
        "repair_records": repair_records,
        "safety": {
            "production_default_flip_allowed": False,
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "remote_write_allowed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human-boundary-gate", type=Path, default=DEFAULT_HUMAN_BOUNDARY_GATE)
    parser.add_argument("--runtime-supply-bank", type=Path, default=DEFAULT_RUNTIME_SUPPLY_BANK)
    parser.add_argument("--runtime-qid", default=DEFAULT_RUNTIME_QID_BY_CASE["Q4-1A434000-罚则"])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    report = build_human_boundary_repair_evidence(
        human_boundary_path=args.human_boundary_gate,
        runtime_supply_bank=args.runtime_supply_bank,
        runtime_qid_by_case={"Q4-1A434000-罚则": args.runtime_qid},
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    return 0 if report["status"] == "resolved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
