#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_luban_no_human_v1_5_golden import (  # noqa: E402
    _anchor_normalized,
    _is_short_common_single_term,
)

DEFAULT_GOLDEN = ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json"
DEFAULT_AGENTIC_DIR = (
    ROOT / "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602"
)
DEFAULT_RESIDUAL_AUDIT = DEFAULT_AGENTIC_DIR / "dual_residual_audit_20260603.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/luban_typed_policy/po_slice_20260601_typed_policy_20260603"

SCHEMA_VERSION = "luban_typed_policy.v0.1"
POLICY_TYPES = [
    "exact_required",
    "semantic_allowed",
    "list_rule",
    "calculation",
    "figure_label",
    "penalty_rule",
    "high_risk_review",
]
NON_SCORING_TERMS = {
    "折算",
    "命中",
    "满分",
    "扣分",
    "得分",
    "近义",
    "不算",
    "关键词",
    "标准术语",
}
NON_SCORING_KEYS = {_anchor_normalized(term) for term in NON_SCORING_TERMS}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_terms(terms: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms or []:
        value = str(term or "").strip()
        if not value:
            continue
        key = _anchor_normalized(value)
        if not key or key in seen or key in NON_SCORING_KEYS:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_penalty_points(rule: str) -> list[str]:
    points: list[str] = []
    for match in re.finditer(r"P\d+", rule or "", flags=re.IGNORECASE):
        point = match.group(0).upper()
        if point not in points:
            points.append(point)
    return points


def _extract_non_implicated_penalty_points(rule: str) -> set[str]:
    excluded: set[str] = set()
    for segment in re.findall(r"不牵连[^。；;]*", rule or ""):
        excluded.update(point.upper() for point in re.findall(r"P\d+", segment, flags=re.IGNORECASE))
    return excluded


def _point_is_penalty_subject(case_penalty_rule: str, point_id: str) -> bool:
    if not case_penalty_rule:
        return False
    if point_id.upper() in _extract_non_implicated_penalty_points(case_penalty_rule):
        return False
    penalty_points = _extract_penalty_points(case_penalty_rule)
    if penalty_points:
        excluded = _extract_non_implicated_penalty_points(case_penalty_rule)
        return point_id.upper() in [point for point in penalty_points if point not in excluded]
    return "多答不得分" in case_penalty_rule and point_id.upper() in {"P1", "P2"}


def _verified_term_count(point: dict[str, Any]) -> int:
    count = 0
    for meta in (point.get("term_anchor_map") or {}).values():
        if meta.get("verified") and meta.get("anchor_source") == "textbook":
            count += 1
    return count


def _has_short_common_single_anchor(terms: list[str]) -> bool:
    return len(terms) == 1 and _is_short_common_single_term(terms[0])


def _residual_index(residual_audit: dict[str, Any] | None) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if not residual_audit:
        return index
    for row in residual_audit.get("residuals") or []:
        index[(str(row.get("case_id")), str(row.get("point_id")))].append(row)
    return index


def _base_policy_for_text_point(point: dict[str, Any]) -> str:
    label = str(point.get("label") or "")
    basis = str(point.get("official_basis") or "")
    terms = _clean_terms(point.get("required_terms_v1_5") or [])
    strict_markers = [
        "必须写出",
        "规范术语",
        "原文",
        "近义不算",
        "不得分",
        "不算",
        "应为",
        "不得",
        "严禁",
        "必须",
    ]
    if terms and any(marker in label or marker in basis for marker in strict_markers):
        return "exact_required"
    if terms and point.get("anchor_source") == "textbook":
        return "exact_required"
    return "semantic_allowed"


def infer_policy_type(
    *,
    case: dict[str, Any],
    point: dict[str, Any],
    residuals: list[dict[str, Any]] | None = None,
) -> tuple[str, str | None, list[str]]:
    reasons: list[str] = []
    point_id = str(point.get("point_id") or "")
    point_type = str(point.get("point_type") or "")
    anchor_source = str(point.get("anchor_source") or "")
    case_penalty_rule = str(case.get("penalty_rule") or "")

    if _point_is_penalty_subject(case_penalty_rule, point_id) or point.get("penalty_rule"):
        base = _base_policy_for_text_point(point)
        reasons.append("case_or_point_penalty_rule_applies")
        return "penalty_rule", base, reasons

    if point_type == "calculation" or anchor_source == "calculation":
        reasons.append("point_type_or_anchor_source_is_calculation")
        return "calculation", None, reasons

    if point_type == "figure_label" or anchor_source == "exam_figure":
        reasons.append("point_type_or_anchor_source_is_figure_label")
        return "figure_label", None, reasons

    if point.get("list_rule"):
        reasons.append("list_rule_present")
        return "list_rule", None, reasons

    if point_type == "non_textbook" or anchor_source in {"non_textbook", "official_answer_weak"}:
        reasons.append("source_not_textbook_verified")
        return "high_risk_review", None, reasons

    if residuals:
        residual_types = {str(row.get("residual_type") or "") for row in residuals}
        if "exact_required" in residual_types:
            reasons.append("dual_residual_identified_exact_required_boundary")
            return "exact_required", None, reasons

    base = _base_policy_for_text_point(point)
    reasons.append(f"text_point_base_policy_{base}")
    return base, None, reasons


def build_typed_policies(
    golden_fixture: dict[str, Any],
    residual_audit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    residuals_by_point = _residual_index(residual_audit)
    policies: list[dict[str, Any]] = []

    for case in golden_fixture.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        question_node = str(case.get("question_node") or "")
        case_penalty_rule = str(case.get("penalty_rule") or "")
        for point in case.get("gold_scoring_points") or []:
            point_id = str(point.get("point_id") or "")
            residuals = residuals_by_point.get((case_id, point_id), [])
            required_terms = _clean_terms(point.get("required_terms_v1_5") or [])
            policy_type, base_policy, reasons = infer_policy_type(case=case, point=point, residuals=residuals)
            point_type = str(point.get("point_type") or "")
            anchor_source = str(point.get("anchor_source") or "")
            max_score = float(point.get("max_score") or 0)

            policy: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "case_id": case_id,
                "question_node": question_node,
                "point_id": point_id,
                "policy_id": f"{case_id}::{point_id}::{SCHEMA_VERSION}",
                "label": point.get("label") or "",
                "official_basis": point.get("official_basis") or "",
                "max_score": max_score,
                "source_point_type": point_type,
                "anchor_source": anchor_source,
                "policy_type": policy_type,
                "base_policy": base_policy,
                "policy_reason": reasons,
                "required_terms": required_terms,
                "required_terms_source": "required_terms_v1_5_candidate",
                "verified_textbook_term_count": _verified_term_count(point),
                "term_anchor_map": point.get("term_anchor_map") or {},
                "list_spec": None,
                "numeric_spec": None,
                "figure_spec": None,
                "penalty_spec": None,
                "evidence_policy": {
                    "needs_student_answer_span": policy_type not in {"calculation"},
                    "source_authority": anchor_source or point_type or "unknown",
                    "chunk_id": point.get("chunk_id") or "",
                    "textbook_quote": point.get("textbook_quote") or "",
                },
                "residual_signals": [
                    {
                        "student_id": row.get("student_id"),
                        "residual_type": row.get("residual_type"),
                        "direction": row.get("direction"),
                        "handling_strategy": row.get("handling_strategy"),
                        "human_note": row.get("human_note"),
                    }
                    for row in residuals
                ],
                "auto_certify": False,
                "policy_readiness": "ready_for_llm_adjudication",
                "safety_notes": [
                    "directional_shadow_only",
                    "not_runtime_guardrail",
                    "required_terms_are_candidates_not_global_hard_gate",
                ],
            }

            if policy_type == "list_rule":
                policy["list_spec"] = {
                    "rule_text": point.get("list_rule") or "",
                    "terms": required_terms,
                    "denominator": len(required_terms),
                    "score_formula": "candidate_k_over_n_times_max_score",
                    "readiness_note": "candidate_only_until_denominator_curated",
                }
            elif policy_type == "calculation":
                expected_terms = _clean_terms(point.get("calculation_expected_terms_v1_5") or [])
                policy["numeric_spec"] = {
                    "expected_terms": expected_terms,
                    "validator_status": "candidate_not_implemented",
                    "tolerance_policy": "unset",
                    "readiness_note": "needs_numeric_expression_extraction_before_auto_certify",
                }
                policy["policy_readiness"] = "needs_numeric_validator_spec"
            elif policy_type == "figure_label":
                policy["figure_spec"] = {
                    "authority": "exam_figure_and_official_answer",
                    "readiness_note": "requires_question_figure_reference",
                }
            elif policy_type == "penalty_rule":
                rule_text = case_penalty_rule or str(point.get("penalty_rule") or "")
                excluded = _extract_non_implicated_penalty_points(rule_text)
                applies_to = [point_ref for point_ref in _extract_penalty_points(rule_text) if point_ref not in excluded]
                policy["penalty_spec"] = {
                    "rule_text": point.get("penalty_rule") or case_penalty_rule,
                    "applies_to_points": applies_to,
                    "base_policy": base_policy,
                    "trigger_status": "candidate_from_official_rule_text",
                }
                policy["policy_readiness"] = "needs_penalty_trigger_validator"
            elif policy_type == "high_risk_review":
                policy["policy_readiness"] = "needs_human_or_source_curation"
            elif policy_type == "exact_required" and not required_terms:
                policy["policy_readiness"] = "needs_required_terms_curation"

            if _has_short_common_single_anchor(required_terms):
                policy["policy_readiness"] = "needs_required_terms_curation"
                policy["safety_notes"].append("short_common_single_term_not_allowed_as_hard_gate")

            policy["validation"] = validate_typed_policy(policy)
            validation_issues = set(policy["validation"].get("issues") or [])
            if "list_rule_missing_denominator" in validation_issues:
                policy["policy_readiness"] = "needs_list_denominator_curation"
            policies.append(policy)

    return policies


def validate_typed_policy(policy: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    policy_type = policy.get("policy_type")
    terms = policy.get("required_terms") or []

    if policy_type == "exact_required" and not terms:
        issues.append("exact_required_missing_required_terms")
    if policy_type == "list_rule":
        list_spec = policy.get("list_spec") or {}
        if not list_spec.get("denominator"):
            issues.append("list_rule_missing_denominator")
    if policy_type == "calculation":
        numeric_spec = policy.get("numeric_spec") or {}
        if not numeric_spec.get("expected_terms"):
            issues.append("calculation_numeric_expression_unset")
    if policy_type == "penalty_rule":
        penalty_spec = policy.get("penalty_spec") or {}
        if not penalty_spec.get("rule_text"):
            issues.append("penalty_rule_missing_rule_text")
        if not penalty_spec.get("applies_to_points"):
            issues.append("penalty_rule_missing_applies_to_points")
    if _has_short_common_single_anchor([str(term) for term in terms]):
        issues.append("short_common_single_term_anchor")

    return {
        "valid": not any(
            issue
            in {
                "exact_required_missing_required_terms",
                "list_rule_missing_denominator",
                "penalty_rule_missing_rule_text",
                "penalty_rule_missing_applies_to_points",
                "short_common_single_term_anchor",
            }
            for issue in issues
        ),
        "issues": issues,
    }


def _summary(policies: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = Counter(str(p.get("policy_type")) for p in policies)
    by_readiness = Counter(str(p.get("policy_readiness")) for p in policies)
    validation_issues = Counter(
        issue for policy in policies for issue in (policy.get("validation") or {}).get("issues", [])
    )
    residual_points = sum(1 for p in policies if p.get("residual_signals"))
    return {
        "schema_version": SCHEMA_VERSION,
        "version_id": f"typed-policy-{_stable_hash(policies)}",
        "total_points": len(policies),
        "policy_type_counts": {policy_type: by_type.get(policy_type, 0) for policy_type in POLICY_TYPES},
        "policy_readiness_counts": dict(sorted(by_readiness.items())),
        "validation_issue_counts": dict(sorted(validation_issues.items())),
        "residual_signal_points": residual_points,
        "auto_certify_points": sum(1 for p in policies if p.get("auto_certify") is True),
        "hard_boundary": "directional_shadow_only_not_runtime",
    }


def _write_csv_policies(path: Path, policies: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "question_node",
        "point_id",
        "policy_type",
        "base_policy",
        "policy_readiness",
        "source_point_type",
        "anchor_source",
        "max_score",
        "required_terms",
        "verified_textbook_term_count",
        "validation_issues",
        "residual_types",
        "label",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for policy in policies:
            writer.writerow(
                {
                    "case_id": policy["case_id"],
                    "question_node": policy["question_node"],
                    "point_id": policy["point_id"],
                    "policy_type": policy["policy_type"],
                    "base_policy": policy.get("base_policy") or "",
                    "policy_readiness": policy["policy_readiness"],
                    "source_point_type": policy["source_point_type"],
                    "anchor_source": policy["anchor_source"],
                    "max_score": policy["max_score"],
                    "required_terms": " | ".join(policy.get("required_terms") or []),
                    "verified_textbook_term_count": policy.get("verified_textbook_term_count"),
                    "validation_issues": " | ".join((policy.get("validation") or {}).get("issues", [])),
                    "residual_types": " | ".join(
                        str(row.get("residual_type")) for row in policy.get("residual_signals") or []
                    ),
                    "label": policy.get("label") or "",
                }
            )


def _finding_markdown(summary: dict[str, Any], policies: list[dict[str, Any]]) -> str:
    lines = [
        "# Luban Typed Policy Candidate Finding 2026-06-03",
        "",
        "## Scope",
        "",
        "- Dataset: 20-case no-human v1.5 golden scoring points.",
        "- Purpose: compile point-level typed policy candidates for agentic grading protocol.",
        "- Boundary: directional/shadow only; not production runtime; not a CaseGradingSkillKernel change.",
        "- Guardrail lesson: current required_terms are candidates, not global hard gates; the previous hard-term POC regressed.",
        "",
        "## Summary",
        "",
        f"- version_id: `{summary['version_id']}`",
        f"- total_points: `{summary['total_points']}`",
        f"- auto_certify_points: `{summary['auto_certify_points']}`",
        f"- residual_signal_points: `{summary['residual_signal_points']}`",
        "",
        "### Policy Type Counts",
        "",
    ]
    for key, value in summary["policy_type_counts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "### Policy Readiness Counts", ""])
    for key, value in summary["policy_readiness_counts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "### Validation Issue Counts", ""])
    if summary["validation_issue_counts"]:
        for key, value in summary["validation_issue_counts"].items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `calculation` and `penalty_rule` are the first candidates for narrow deterministic validators, but they still need explicit validator specs before runtime use.",
            "- `list_rule` is useful as a scoring protocol candidate, but denominator terms must be curated before it can be a hard scorer.",
            "- `exact_required` identifies strict terminology points for LLM prompts and reviewer discipline; it is not a global substring gate.",
            "- `high_risk_review` captures non-textbook, official-answer-weak, or source-unclear points that should not be auto-certified.",
            "",
            "## Residual-Driven Backlog",
            "",
        ]
    )
    residual_policies = [p for p in policies if p.get("residual_signals")]
    for policy in residual_policies:
        residual_types = ", ".join(str(row.get("residual_type")) for row in policy["residual_signals"])
        lines.append(
            f"- {policy['case_id']} {policy['point_id']}: `{policy['policy_type']}` "
            f"readiness=`{policy['policy_readiness']}`, residuals=`{residual_types}`"
        )
    lines.extend(
        [
            "",
            "## Next Gate",
            "",
            "Use this artifact to build a prompt-level typed policy protocol and a DeepSeek shadow harness. Do not promote these policies to production guardrails until the policy-specific validator lifts against human labels.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_outputs(*, golden_path: Path, residual_audit_path: Path | None, output_dir: Path) -> dict[str, Path]:
    golden = _read_json(golden_path)
    residual = _read_json(residual_audit_path) if residual_audit_path and residual_audit_path.exists() else None
    policies = build_typed_policies(golden, residual)
    summary = _summary(policies)
    validation_issues = [
        {
            "case_id": policy["case_id"],
            "point_id": policy["point_id"],
            "policy_type": policy["policy_type"],
            "issues": (policy.get("validation") or {}).get("issues", []),
            "policy_readiness": policy["policy_readiness"],
        }
        for policy in policies
        if (policy.get("validation") or {}).get("issues")
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "policies_json": output_dir / "typed_policy_candidates.json",
        "policies_csv": output_dir / "typed_policy_candidates.csv",
        "summary": output_dir / "typed_policy_summary.json",
        "validation_issues": output_dir / "typed_policy_validation_issues.json",
        "finding": output_dir / "FINDING_typed_policy_candidates_20260603.md",
    }
    _write_json(paths["policies_json"], {"summary": summary, "policies": policies})
    _write_csv_policies(paths["policies_csv"], policies)
    _write_json(paths["summary"], summary)
    _write_json(paths["validation_issues"], validation_issues)
    paths["finding"].write_text(_finding_markdown(summary, policies), encoding="utf-8")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Luban typed scoring policy candidate artifacts.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--residual-audit", type=Path, default=DEFAULT_RESIDUAL_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    paths = build_outputs(
        golden_path=args.golden,
        residual_audit_path=args.residual_audit,
        output_dir=args.output_dir,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
