#!/usr/bin/env python3
"""Stage 5 canary gate for the KnowQL PGO runtime-supply slot.

Read-only gate: it verifies the PGO slot in a fresh Python process, checks that
canary cohorts are limited to qa_/operator_, and reports shadow delta,
over-credit, and score distribution. It does not flip production defaults and
does not restart a live worker.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.verify_luban_pgo_runtime_supply import (  # noqa: E402
    DEFAULT_SLOT_DIR,
    verify_pgo_runtime_supply,
)

DEFAULT_SCALED_DOUBLE_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
    / "scaled_gold/scaled_double_gate.json"
)
DEFAULT_HUMAN_BOUNDARY_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
    / "phase5_factory/legacy_arm_regression.json"
)
DEFAULT_HUMAN_BOUNDARY_REPAIR: Path | None = None
DEFAULT_COHORT_IDS = ("qa_stage5_pgo_canary", "operator_stage5_pgo_canary")
SCHEMA = "luban_pgo_stage5_canary_gate.v1"
ALLOWED_COHORT_PREFIXES = ("qa_", "operator_")
HUMAN_BOUNDARY_REPAIR_SCHEMA = "luban_pgo_stage5_human_boundary_repair.v1"
HUMAN_BOUNDARY_BLOCKER = "stage5_human_gold_over_credit_blocker"


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _round_float(value: float | int | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return _round_float(sum(values) / len(values))


def _distribution(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [float(record[field]) for record in records if record.get(field) is not None]
    full_score_count = 0
    for record in records:
        if record.get(field) is None or record.get("official_total") is None:
            continue
        if float(record[field]) >= float(record["official_total"]):
            full_score_count += 1

    return {
        "count": len(values),
        "mean": _mean(values),
        "median": _round_float(statistics.median(values)) if values else None,
        "min": _round_float(min(values)) if values else None,
        "max": _round_float(max(values)) if values else None,
        "zero_count": sum(1 for value in values if value == 0),
        "full_score_count": full_score_count,
    }


def _cohort_gate(cohort_ids: list[str]) -> dict[str, Any]:
    invalid = [
        cohort_id
        for cohort_id in cohort_ids
        if not any(cohort_id.startswith(prefix) for prefix in ALLOWED_COHORT_PREFIXES)
    ]
    return {
        "allowed": not invalid and bool(cohort_ids),
        "allowed_prefixes": list(ALLOWED_COHORT_PREFIXES),
        "cohort_ids": cohort_ids,
        "invalid_cohort_ids": invalid,
    }


def _fresh_process_verifier(slot_dir: Path) -> dict[str, Any]:
    code = (
        "import json\n"
        "from pathlib import Path\n"
        "from scripts.verify_luban_pgo_runtime_supply import verify_pgo_runtime_supply\n"
        f"print(json.dumps(verify_pgo_runtime_supply(Path({json.dumps(str(slot_dir))})), ensure_ascii=False))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {
            "status": "blocked",
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
        }
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "blocked",
            "returncode": result.returncode,
            "stderr": f"fresh_process_json_decode_error:{exc.__class__.__name__}",
            "stdout": result.stdout.strip(),
        }


def _fresh_process_runtime_loader(slot_dir: Path) -> dict[str, Any]:
    if Path(slot_dir).resolve() != DEFAULT_SLOT_DIR.resolve():
        return {
            "status": "skipped_non_default_slot_dir",
            "reason": "rubric_grader_v1 resolves slots from the repository runtime_supply directory",
        }

    code = (
        "import json\n"
        "from deeptutor.services.construction_grading import rubric_grader_v1 as G\n"
        "bank = G._rubric_bank()\n"
        "print(json.dumps({\n"
        "  'status': 'ok' if bank else 'blocked',\n"
        "  'slot': 'pgo',\n"
        "  'question_count': len(bank),\n"
        "  'scoring_point_count': sum(len(points) for points in bank.values()),\n"
        "}, ensure_ascii=False))\n"
    )
    env = os.environ.copy()
    env["LUBAN_CASE_RUBRIC_BANK_SLOT"] = "pgo"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {
            "status": "blocked",
            "slot": "pgo",
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
        }
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "blocked",
            "slot": "pgo",
            "returncode": result.returncode,
            "stderr": f"runtime_loader_json_decode_error:{exc.__class__.__name__}",
            "stdout": result.stdout.strip(),
        }


def _shadow_delta(records: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    deltas = [
        float(record["new"]) - float(record["legacy"])
        for record in records
        if record.get("new") is not None and record.get("legacy") is not None
    ]
    abs_deltas = [abs(delta) for delta in deltas]
    return {
        "sample_count": len(deltas),
        "mean_abs_new_legacy_delta": _mean(abs_deltas),
        "mean_signed_new_legacy_delta": _mean(deltas),
        "max_abs_new_legacy_delta": _round_float(max(abs_deltas)) if abs_deltas else None,
        "scaled_gate": {
            "n_pairs": summary.get("n_pairs"),
            "MAE_new": summary.get("MAE_new"),
            "MAE_legacy": summary.get("MAE_legacy"),
            "as_pct": summary.get("as_pct") or {},
            "gate_MAE_new_le_legacy": summary.get("gate_MAE_new_le_legacy"),
            "double_gate_pass": summary.get("double_gate_pass"),
            "honest_boundary": summary.get("honest_boundary"),
        },
    }


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
                    "new_uniform": new_awarded,
                    "legacy_awarded": legacy_awarded,
                    "human_awarded": human_awarded,
                    "delta_vs_human": round(new_awarded - human_awarded, 4),
                }
            )
    return pairs


def _human_boundary_repair_gate(
    *,
    repair_path: Path | None,
    human_payload: dict[str, Any],
    original_blocker: bool,
) -> dict[str, Any]:
    if not original_blocker:
        return {"status": "not_required", "blockers": [], "resolved": False}
    if repair_path is None:
        return {"status": "missing", "blockers": ["human_boundary_repair_missing"], "resolved": False}
    if not repair_path.exists():
        return {
            "status": "missing",
            "path": str(repair_path),
            "blockers": ["human_boundary_repair_missing"],
            "resolved": False,
        }
    repair = _load_json(repair_path)
    blockers: list[str] = []
    if repair.get("schema") != HUMAN_BOUNDARY_REPAIR_SCHEMA:
        blockers.append(f"human_boundary_repair_schema_mismatch:{repair.get('schema')}")
    if repair.get("status") != "resolved":
        blockers.append(f"human_boundary_repair_status_not_resolved:{repair.get('status')}")
    if HUMAN_BOUNDARY_BLOCKER not in list(repair.get("resolved_blockers") or []):
        blockers.append("human_boundary_repair_missing_resolved_blocker")
    after = repair.get("human_boundary_after_repair") if isinstance(repair.get("human_boundary_after_repair"), dict) else {}
    over_after = after.get("over_credit_pairs") if isinstance(after.get("over_credit_pairs"), dict) else {}
    try:
        new_after = int(over_after.get("new") or 0)
        legacy_after = int(over_after.get("legacy") or 0)
    except (TypeError, ValueError):
        new_after = 1
        legacy_after = 0
        blockers.append("human_boundary_repair_over_credit_pairs_invalid")
    if new_after > legacy_after:
        blockers.append("human_boundary_repair_new_over_credit_gt_legacy")
    blocking_pairs = _human_boundary_blocking_pairs(human_payload)
    covered = {
        (str(pair.get("case") or ""), str(pair.get("student") or ""))
        for pair in list(after.get("covered_over_credit_pairs") or [])
        if isinstance(pair, dict)
    }
    missing_pairs = [
        {"case": pair["case"], "student": pair["student"]}
        for pair in blocking_pairs
        if (pair["case"], pair["student"]) not in covered
    ]
    if missing_pairs:
        blockers.append("human_boundary_repair_missing_original_pair_coverage")
    safety = repair.get("safety") if isinstance(repair.get("safety"), dict) else {}
    for key in ("production_default_flip_allowed", "official_score_allowed", "canonical_write_allowed", "remote_write_allowed"):
        if safety.get(key) is not False:
            blockers.append(f"human_boundary_repair_{key}_not_false")
    return {
        "status": "resolved" if not blockers else "blocked",
        "path": str(repair_path),
        "schema": repair.get("schema"),
        "blockers": blockers,
        "resolved": not blockers,
        "after_over_credit_pairs": {"new": new_after, "legacy": legacy_after},
        "covered_original_pair_count": len(blocking_pairs) - len(missing_pairs),
        "original_blocking_pair_count": len(blocking_pairs),
        "missing_original_pairs": missing_pairs,
    }


def _over_credit(
    summary: dict[str, Any],
    human_boundary_path: Path,
    human_boundary_repair_path: Path | None = DEFAULT_HUMAN_BOUNDARY_REPAIR,
) -> dict[str, Any]:
    scaled_over_credit = summary.get("over_credit") or {}
    report = {
        "scaled_gate_new": scaled_over_credit.get("new"),
        "scaled_gate_legacy": scaled_over_credit.get("legacy"),
        "gate_overcredit_new_le_legacy": summary.get("gate_overcredit_new_le_legacy"),
    }
    if human_boundary_path.exists():
        human_payload = _load_json(human_boundary_path)
        human_summary = human_payload.get("summary") if isinstance(human_payload, dict) else {}
        human_over_credit = (human_summary or {}).get("over_credit_pairs") or {}
        original_blocker = (
            human_over_credit.get("new") is not None
            and human_over_credit.get("legacy") is not None
            and human_over_credit.get("new") > human_over_credit.get("legacy")
        )
        repair_gate = _human_boundary_repair_gate(
            repair_path=human_boundary_repair_path,
            human_payload=human_payload if isinstance(human_payload, dict) else {},
            original_blocker=bool(original_blocker),
        )
        report["human_boundary"] = {
            "path": str(human_boundary_path),
            "gold": (human_summary or {}).get("gold"),
            "new": human_over_credit.get("new"),
            "legacy": human_over_credit.get("legacy"),
            "original_broad_flip_blocker": bool(original_blocker),
            "broad_flip_blocker": bool(original_blocker) and repair_gate.get("resolved") is not True,
            "repair_status": repair_gate.get("status"),
            "repair_gate": repair_gate,
            "blocking_pairs": _human_boundary_blocking_pairs(human_payload if isinstance(human_payload, dict) else {}),
            "honest_boundary": (human_summary or {}).get("honest_boundary"),
        }
    else:
        report["human_boundary"] = {
            "available": False,
            "path": str(human_boundary_path),
            "repair_status": "not_applicable",
        }
    return report


def _score_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "new": _distribution(records, "new"),
        "legacy": _distribution(records, "legacy"),
        "gold": _distribution(records, "gold"),
    }


def build_canary_gate_report(
    *,
    slot_dir: Path = DEFAULT_SLOT_DIR,
    scaled_double_gate_path: Path = DEFAULT_SCALED_DOUBLE_GATE,
    cohort_ids: list[str] | None = None,
    human_boundary_path: Path = DEFAULT_HUMAN_BOUNDARY_GATE,
    human_boundary_repair_path: Path | None = DEFAULT_HUMAN_BOUNDARY_REPAIR,
) -> dict[str, Any]:
    slot_dir = Path(slot_dir)
    cohort_ids = list(cohort_ids or DEFAULT_COHORT_IDS)
    blockers: list[str] = []

    verifier_report = verify_pgo_runtime_supply(slot_dir)
    if verifier_report.get("status") != "ok":
        blockers.append("pgo_runtime_supply_verifier_failed")

    fresh_verifier = _fresh_process_verifier(slot_dir)
    if fresh_verifier.get("status") != "ok":
        blockers.append("worker_restart_fresh_process_verifier_failed")

    runtime_loader = _fresh_process_runtime_loader(slot_dir)
    if Path(slot_dir).resolve() == DEFAULT_SLOT_DIR.resolve() and runtime_loader.get("status") != "ok":
        blockers.append("worker_restart_slot_loader_failed")

    if scaled_double_gate_path.exists():
        scaled_gate = _load_json(scaled_double_gate_path)
    else:
        scaled_gate = {}
        blockers.append("scaled_double_gate_missing")
    summary = scaled_gate.get("summary") if isinstance(scaled_gate, dict) else {}
    records = scaled_gate.get("records") if isinstance(scaled_gate, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(records, list) or not records:
        records = []
        blockers.append("scaled_double_gate_no_records")

    if summary.get("double_gate_pass") is not True:
        blockers.append("shadow_double_gate_failed")
    if summary.get("gate_overcredit_new_le_legacy") is not True:
        blockers.append("scaled_over_credit_regression")

    cohort_report = _cohort_gate(cohort_ids)
    if not cohort_report["allowed"]:
        blockers.append("cohort_not_limited_to_qa_operator")

    over_credit_report = _over_credit(summary, human_boundary_path, human_boundary_repair_path)
    human_boundary = over_credit_report.get("human_boundary") if isinstance(over_credit_report.get("human_boundary"), dict) else {}
    if human_boundary.get("broad_flip_blocker") is True:
        blockers.append(HUMAN_BOUNDARY_BLOCKER)

    return {
        "schema": SCHEMA,
        "status": "qa_operator_canary_go" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "canary_scope": "qa_operator_only",
        "production_default_flip_allowed": False,
        "canonical_write_allowed": False,
        "remote_write_allowed": False,
        "actual_worker_restarted": False,
        "worker_restart_instruction": (
            "Live workers must be restarted after setting LUBAN_CASE_RUBRIC_BANK_SLOT=pgo; "
            "this gate verifies a fresh-process load only."
        ),
        "cohort_gate": cohort_report,
        "worker_restart_probe": {
            "fresh_process_verifier": fresh_verifier,
            "runtime_loader": runtime_loader,
        },
        "runtime_supply": verifier_report,
        "shadow_delta": _shadow_delta(records, summary),
        "over_credit": over_credit_report,
        "score_distribution": _score_distribution(records),
        "inputs": {
            "slot_dir": str(slot_dir),
            "scaled_double_gate_path": str(scaled_double_gate_path),
            "human_boundary_path": str(human_boundary_path),
            "human_boundary_repair_path": str(human_boundary_repair_path) if human_boundary_repair_path is not None else None,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-dir", type=Path, default=DEFAULT_SLOT_DIR)
    parser.add_argument("--scaled-double-gate", type=Path, default=DEFAULT_SCALED_DOUBLE_GATE)
    parser.add_argument("--human-boundary-gate", type=Path, default=DEFAULT_HUMAN_BOUNDARY_GATE)
    parser.add_argument("--human-boundary-repair", type=Path, default=DEFAULT_HUMAN_BOUNDARY_REPAIR)
    parser.add_argument("--cohort-id", action="append", dest="cohort_ids")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    report = build_canary_gate_report(
        slot_dir=args.slot_dir,
        scaled_double_gate_path=args.scaled_double_gate,
        cohort_ids=args.cohort_ids,
        human_boundary_path=args.human_boundary_gate,
        human_boundary_repair_path=args.human_boundary_repair,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    return 0 if report["status"] == "qa_operator_canary_go" else 1


if __name__ == "__main__":
    raise SystemExit(main())
