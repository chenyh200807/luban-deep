#!/usr/bin/env python3
"""Compile M34 source/path conflict work orders into a repair overlay candidate.

This compiler does not mint truth. It only converts strong, reproducible source/path
pollution evidence into a teaching-tier fail-open overlay for general compiled context.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/general_knowledge_dividend_m34_20260609/"
    / "compiler_source_work_orders_m34.jsonl"
)
DEFAULT_SUPPLY_DIR = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge"
)
DEFAULT_BUNDLE = DEFAULT_SUPPLY_DIR / "canonical_unified_knowledge.json"
DEFAULT_EXISTING_OVERLAY = DEFAULT_SUPPLY_DIR / "source_alignment_repairs.json"
DEFAULT_OUTPUT_DIR = (
    REPO
    / "artifacts/luban_grading_artifacts/m34_source_alignment_repair_compile_20260611"
)

SCHEMA = "luban_canonical_unified_knowledge_source_alignment_repairs.v1"
NAMESPACE = "canonical_unified_knowledge.source_alignment_repairs"
SOURCE_NAMESPACE = "canonical_unified_knowledge"
TEACHING_TIER = "teaching_context_not_answer_key"


def default_protected_hit_questions() -> set[str]:
    """Reuse the M34 calibration hit lane as a protection set.

    These questions are not release truth; they are local runtime calibration positives.
    A source/path work order generated from them is not safe to auto-compile into a
    detach repair, because doing so can convert a recall-positive case into fail-open.
    """
    try:
        from scripts.run_luban_m34_general_knowledge_dividend_slice import CALIBRATION_CASES
    except Exception:  # noqa: BLE001
        return set()
    return {
        str(case.get("question") or "").strip()
        for case in CALIBRATION_CASES
        if str(case.get("expected") or "") == "hit" and str(case.get("question") or "").strip()
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = str(value or "").strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _is_valid_existing_overlay(overlay: dict[str, Any], bundle_hash: str) -> bool:
    manifest = overlay.get("manifest") or {}
    try:
        production_write_count = int(manifest.get("production_write_count") or 0)
    except (TypeError, ValueError):
        return False
    return (
        manifest.get("schema") == SCHEMA
        and manifest.get("namespace") == NAMESPACE
        and manifest.get("tier") == TEACHING_TIER
        and manifest.get("official_score_allowed") is False
        and manifest.get("llm_may_decide_correctness") is False
        and manifest.get("canonical_truth_written") is False
        and production_write_count == 0
        and manifest.get("source_bundle_namespace") == SOURCE_NAMESPACE
        and manifest.get("source_bundle_content_hash") == bundle_hash
    )


def normalize_existing_overlay(existing_overlay: dict[str, Any] | None, bundle_hash: str) -> dict[str, Any]:
    if existing_overlay and _is_valid_existing_overlay(existing_overlay, bundle_hash):
        return existing_overlay
    return {
        "manifest": {
            "schema": SCHEMA,
            "namespace": NAMESPACE,
            "status": "empty_baseline",
            "tier": TEACHING_TIER,
            "official_score_allowed": False,
            "llm_may_decide_correctness": False,
            "canonical_truth_written": False,
            "production_write_count": 0,
            "source_bundle_namespace": SOURCE_NAMESPACE,
            "source_bundle_content_hash": bundle_hash,
            "repair_count": 0,
        },
        "repairs": [],
    }


def _repair_key(repair: dict[str, Any]) -> tuple[str, str]:
    return (
        str(repair.get("node_code") or "").strip(),
        str(repair.get("action") or "").strip(),
    )


def _has_descendants(node_code: str, bundle_nodes: dict[str, Any]) -> bool:
    node = str(node_code or "").strip()
    return bool(node and any(str(code).startswith(node + "-") for code in bundle_nodes))


def _is_strong_source_conflict(
    row: dict[str, Any],
    bundle_nodes: dict[str, Any],
    protected_hit_questions: set[str],
) -> bool:
    evidence = {str(item).strip() for item in row.get("negative_evidence") or []}
    try:
        production_write_count = int(row.get("production_write_count") or 0)
    except (TypeError, ValueError):
        return False
    node_code = str(row.get("candidate_node_code") or "").strip()
    return (
        row.get("work_order_type") == "source_path_conflict"
        and bool(node_code)
        and str(row.get("question") or "").strip() not in protected_hit_questions
        and "primary_path_mismatch" in evidence
        and "source_path_conflict" in evidence
        and not _has_descendants(node_code, bundle_nodes)
        and row.get("canonical_truth_written") is False
        and production_write_count == 0
    )


def _repair_from_work_order(row: dict[str, Any]) -> dict[str, Any]:
    question = str(row.get("question") or "").strip()
    reason = (
        "M34 compiler work order found source/path pollution: "
        "candidate source text matched the query terms while canonical path terms did not. "
        "No governed re-anchor is minted here, so runtime fails open to existing TutorBot RAG."
    )
    return {
        "node_code": str(row.get("candidate_node_code") or "").strip(),
        "name_path": str(row.get("candidate_leaf_name_path") or "").strip(),
        "action": "detach_node_from_general_compiled_context",
        "reason": reason,
        "evidence_queries": [question] if question else [],
        "reanchor_to_node_code": None,
        "runtime_action": "fail_open_to_existing_tutorbot_rag",
    }


def build_source_alignment_repairs(
    work_orders: list[dict[str, Any]],
    *,
    bundle: dict[str, Any],
    existing_overlay: dict[str, Any] | None,
    generated_from: str,
    protected_hit_questions: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle_hash = str(((bundle.get("manifest") or {}).get("content_hash") or "")).strip()
    if not bundle_hash:
        raise ValueError("bundle manifest.content_hash is required")

    repairs_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    existing_repair_count = 0
    existing_overlay_used = False
    existing_overlay = normalize_existing_overlay(existing_overlay, bundle_hash)
    if existing_overlay.get("repairs"):
        existing_overlay_used = True
        for repair in existing_overlay.get("repairs") or []:
            if not isinstance(repair, dict):
                continue
            key = _repair_key(repair)
            if key[0] and key[1]:
                repairs_by_key[key] = {
                    **repair,
                    "evidence_queries": _stable_unique(list(repair.get("evidence_queries") or [])),
                }
                existing_repair_count += 1

    bundle_nodes = bundle.get("nodes") or {}
    protected_hit_questions = protected_hit_questions or set()
    strong_rows = [
        row
        for row in work_orders
        if _is_strong_source_conflict(row, bundle_nodes, protected_hit_questions)
    ]
    deferred_rows = [row for row in work_orders if row not in strong_rows]
    new_repair_count = 0
    for row in strong_rows:
        repair = _repair_from_work_order(row)
        key = _repair_key(repair)
        current = repairs_by_key.get(key)
        if current is None:
            repairs_by_key[key] = repair
            new_repair_count += 1
            continue
        current["evidence_queries"] = _stable_unique(
            list(current.get("evidence_queries") or []) + repair["evidence_queries"]
        )

    repairs = sorted(
        repairs_by_key.values(),
        key=lambda item: (str(item.get("node_code") or ""), str(item.get("action") or "")),
    )
    overlay = {
        "manifest": {
            "schema": SCHEMA,
            "namespace": NAMESPACE,
            "status": "release_candidate",
            "tier": TEACHING_TIER,
            "official_score_allowed": False,
            "llm_may_decide_correctness": False,
            "canonical_truth_written": False,
            "production_write_count": 0,
            "source_bundle_namespace": SOURCE_NAMESPACE,
            "source_bundle_content_hash": bundle_hash,
            "repair_count": len(repairs),
            "generated_from": generated_from,
            "compiler_policy": "strong_source_path_conflict_only_v1",
        },
        "repairs": repairs,
    }
    report = {
        "status": "compiled_candidate",
        "input_work_order_count": len(work_orders),
        "strong_source_conflict_work_order_count": len(strong_rows),
        "deferred_review_count": len(deferred_rows),
        "deferred_broad_parent_count": sum(
            1
            for row in deferred_rows
            if _has_descendants(str(row.get("candidate_node_code") or ""), bundle_nodes)
        ),
        "deferred_protected_hit_count": sum(
            1
            for row in deferred_rows
            if str(row.get("question") or "").strip() in protected_hit_questions
        ),
        "existing_overlay_used": existing_overlay_used,
        "existing_repair_count": existing_repair_count,
        "new_repair_count": new_repair_count,
        "merged_repair_count": len(repairs),
        "deferred_review_node_codes": sorted(
            {
                str(row.get("candidate_node_code") or "").strip()
                for row in deferred_rows
                if str(row.get("candidate_node_code") or "").strip()
            }
        ),
        "safety": {
            "official_score_allowed": False,
            "canonical_truth_written": False,
            "production_write_count": 0,
            "installed_runtime_supply": False,
            "release_truth_claimed": False,
        },
    }
    return overlay, report


def write_candidate_outputs(
    *,
    overlay: dict[str, Any],
    report: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / "source_alignment_repairs_candidate.json"
    report_path = output_dir / "compile_report.json"
    overlay_path.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return overlay_path, report_path


def evaluate_candidate_calibration(bundle_path: Path, overlay: dict[str, Any]) -> dict[str, Any]:
    """Evaluate candidate overlay against M34 calibration in an isolated temp supply."""
    try:
        from deeptutor.services.construction_grading import canonical_knowledge_runtime as CK
        runner_path = REPO / "scripts/run_luban_m34_general_knowledge_dividend_slice.py"
        spec = importlib.util.spec_from_file_location("m34_general_knowledge_dividend_slice", runner_path)
        if spec is None or spec.loader is None:
            raise ModuleNotFoundError(str(runner_path))
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        HIT_RATE_THRESHOLD = runner.HIT_RATE_THRESHOLD
        _evaluate_on_syllabus = runner._evaluate_on_syllabus
        _evaluate_calibration_cases = runner._evaluate_calibration_cases
    except Exception as exc:  # noqa: BLE001
        return {"status": "not_exercised", "reason": f"import_failed:{type(exc).__name__}"}

    original_supply_dir = CK._SUPPLY_DIR
    original_graph_dir = CK._GRAPH_DIR
    try:
        with tempfile.TemporaryDirectory(prefix="m34_repair_eval_") as raw_tmp:
            tmp = Path(raw_tmp)
            shutil.copyfile(bundle_path, tmp / "canonical_unified_knowledge.json")
            (tmp / "source_alignment_repairs.json").write_text(
                json.dumps(overlay, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            CK._SUPPLY_DIR = tmp
            CK._GRAPH_DIR = tmp / "no_graph"
            CK._load.cache_clear()
            CK._load_graph.cache_clear()
            CK._load_source_alignment_repairs.cache_clear()
            on_rows = _evaluate_on_syllabus()
            rows = _evaluate_calibration_cases()
    finally:
        CK._SUPPLY_DIR = original_supply_dir
        CK._GRAPH_DIR = original_graph_dir
        CK._load.cache_clear()
        CK._load_graph.cache_clear()
        CK._load_source_alignment_repairs.cache_clear()

    on_hits = sum(1 for row in on_rows if row.get("hit"))
    pass_count = sum(1 for row in rows if row.get("passed"))
    hit_rate = on_hits / len(on_rows) if on_rows else 0.0
    pass_rate = pass_count / len(rows) if rows else 0.0
    return {
        "status": "evaluated",
        "hit_total": len(on_rows),
        "hit_passed": on_hits,
        "teaching_context_hit_rate": hit_rate,
        "hit_rate_threshold": HIT_RATE_THRESHOLD,
        "calibration_total": len(rows),
        "calibration_passed": pass_count,
        "calibration_pass_rate": pass_rate,
        "failed_cases": [
            {
                "question": row.get("question"),
                "expected": row.get("expected"),
                "hit": row.get("hit"),
                "path_ok": row.get("path_ok"),
            }
            for row in rows
            if not row.get("passed")
        ],
    }


def _calibration_is_non_regressing(candidate: dict[str, Any], baseline: dict[str, Any] | None) -> bool:
    if candidate.get("status") != "evaluated":
        return False
    threshold = float(candidate.get("hit_rate_threshold") or 0.0)
    candidate_hit_rate = float(candidate.get("teaching_context_hit_rate") or 0.0)
    candidate_pass_rate = float(candidate.get("calibration_pass_rate") or 0.0)
    if candidate_hit_rate < threshold:
        return False
    if baseline and baseline.get("status") == "evaluated":
        baseline_failures = {
            (str(row.get("question") or ""), str(row.get("expected") or ""))
            for row in baseline.get("failed_cases") or []
            if isinstance(row, dict)
        }
        candidate_failures = {
            (str(row.get("question") or ""), str(row.get("expected") or ""))
            for row in candidate.get("failed_cases") or []
            if isinstance(row, dict)
        }
        if not candidate_failures.issubset(baseline_failures):
            return False
        return (
            candidate_hit_rate >= float(baseline.get("teaching_context_hit_rate") or 0.0)
            and candidate_pass_rate >= float(baseline.get("calibration_pass_rate") or 0.0)
        )
    return True


def select_calibration_safe_subset(
    *,
    bundle_path: Path,
    candidate_overlay: dict[str, Any],
    existing_overlay: dict[str, Any],
    baseline_calibration: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Greedily keep only new repairs that do not regress M34 calibration."""
    existing_keys = {_repair_key(repair) for repair in existing_overlay.get("repairs") or []}
    selected_repairs = [dict(repair) for repair in existing_overlay.get("repairs") or []]
    rejected: list[dict[str, str]] = []
    selected_new_count = 0

    for repair in candidate_overlay.get("repairs") or []:
        key = _repair_key(repair)
        if not key[0] or key in existing_keys:
            continue
        trial_repairs = selected_repairs + [repair]
        trial_overlay = {
            **candidate_overlay,
            "manifest": {**candidate_overlay["manifest"], "repair_count": len(trial_repairs)},
            "repairs": trial_repairs,
        }
        trial_calibration = evaluate_candidate_calibration(bundle_path, trial_overlay)
        if _calibration_is_non_regressing(trial_calibration, baseline_calibration):
            selected_repairs = trial_repairs
            selected_new_count += 1
            continue
        rejected.append(
            {
                "node_code": str(repair.get("node_code") or ""),
                "name_path": str(repair.get("name_path") or ""),
                "reason": "candidate_calibration_regression",
            }
        )

    selected_overlay = {
        **candidate_overlay,
        "manifest": {
            **candidate_overlay["manifest"],
            "repair_count": len(selected_repairs),
            "compiler_policy": "calibration_safe_source_path_conflict_subset_v1",
        },
        "repairs": selected_repairs,
    }
    selected_calibration = evaluate_candidate_calibration(bundle_path, selected_overlay)
    report = {
        "selected_new_repair_count": selected_new_count,
        "rejected_new_repair_count": len(rejected),
        "rejected_repairs": rejected,
        "selected_calibration": selected_calibration,
        "installable": _calibration_is_non_regressing(selected_calibration, baseline_calibration),
    }
    return selected_overlay, report


def install_runtime_supply(overlay_path: Path, supply_dir: Path) -> Path:
    target = supply_dir / "source_alignment_repairs.json"
    shutil.copyfile(overlay_path, target)
    return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-orders", type=Path, default=DEFAULT_WORK_ORDERS)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--existing-overlay", type=Path, default=DEFAULT_EXISTING_OVERLAY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--generated-from",
        default=str(DEFAULT_WORK_ORDERS.relative_to(REPO)),
    )
    parser.add_argument(
        "--install-runtime-supply",
        action="store_true",
        help="Install the candidate overlay into runtime_supply. Still release_candidate only.",
    )
    parser.add_argument(
        "--allow-calibration-regression",
        action="store_true",
        help="Allow install even if isolated M34 calibration says the candidate is not installable.",
    )
    parser.add_argument(
        "--select-calibration-safe-subset",
        action="store_true",
        help="Keep only new repairs that do not regress the existing M34 calibration baseline.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = _read_json(args.bundle)
    existing_overlay = _read_json(args.existing_overlay) if args.existing_overlay.exists() else None
    bundle_hash = str(((bundle.get("manifest") or {}).get("content_hash") or "")).strip()
    normalized_existing_overlay = normalize_existing_overlay(existing_overlay, bundle_hash)
    work_orders = _read_jsonl(args.work_orders)
    overlay, report = build_source_alignment_repairs(
        work_orders,
        bundle=bundle,
        existing_overlay=normalized_existing_overlay,
        generated_from=args.generated_from,
        protected_hit_questions=default_protected_hit_questions(),
    )
    baseline_calibration = (
        evaluate_candidate_calibration(args.bundle, normalized_existing_overlay)
        if normalized_existing_overlay
        else {"status": "not_exercised", "reason": "missing_existing_overlay"}
    )
    report["baseline_calibration"] = baseline_calibration
    calibration = evaluate_candidate_calibration(args.bundle, overlay)
    report["candidate_calibration"] = calibration
    report["candidate_installable"] = _calibration_is_non_regressing(calibration, baseline_calibration)
    if args.select_calibration_safe_subset and existing_overlay and baseline_calibration.get("status") == "evaluated":
        overlay, subset_report = select_calibration_safe_subset(
            bundle_path=args.bundle,
            candidate_overlay=overlay,
            existing_overlay=normalized_existing_overlay,
            baseline_calibration=baseline_calibration,
        )
        report["calibration_safe_subset"] = subset_report
        report["merged_repair_count"] = overlay["manifest"]["repair_count"]
        report["new_repair_count"] = subset_report["selected_new_repair_count"]
        calibration = subset_report["selected_calibration"]
        report["candidate_calibration"] = calibration
        report["candidate_installable"] = subset_report["installable"]
    if calibration.get("status") == "evaluated" and not report["candidate_installable"]:
        report["status"] = "compiled_candidate_not_installable"
        report["safety"]["install_blocker"] = "candidate_calibration_regression"
    overlay_path, report_path = write_candidate_outputs(
        overlay=overlay,
        report=report,
        output_dir=args.output_dir,
    )
    if args.install_runtime_supply:
        installable = calibration.get("status") == "evaluated" and report["candidate_installable"] is True
        if not installable and not args.allow_calibration_regression:
            report["status"] = "compiled_candidate_install_blocked"
            report["safety"]["install_blocker"] = (
                "candidate_calibration_not_installable"
                if calibration.get("status") == "evaluated"
                else "candidate_calibration_not_exercised"
            )
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return 2
        install_runtime_supply(overlay_path, args.bundle.parent)
        report["safety"]["installed_runtime_supply"] = True
        report["installed_runtime_supply_path"] = str(args.bundle.parent / "source_alignment_repairs.json")
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
