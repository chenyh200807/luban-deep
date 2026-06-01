#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.luban_no_human_v1_5 import (  # noqa: E402
    apply_resolution_merge_to_fixture,
    _anchored_subterms,
    _clean_required_term,
    _is_junk_required_term,
    anchor_required_terms,
    build_case_official_answer_corpus,
    build_human_escalation_queues,
    build_no_human_labels_for_case,
    build_textbook_anchor_corpus,
    merge_independent_resolution_labels,
    squeeze_required_terms,
    summarize_no_human_fixture,
)
from scripts.poc_luban_case_grading_three_arms import extract_required_terms  # noqa: E402


DEFAULT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts/luban_no_human_v1_5/20260601_textbook_anchored"
DEFAULT_PRIOR_REPORT = (
    PROJECT_ROOT
    / "artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_185157.json"
)
DEFAULT_AGENT_A_LABELS: Path | None = None
DEFAULT_AGENT_B_LABELS: Path | None = None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stable_unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        clean = _clean_required_term(term)
        compact = re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’]+", "", clean)
        if not compact or compact in seen or _is_junk_required_term(clean):
            continue
        seen.add(compact)
        result.append(clean)
    return result


def _split_outside_brackets(text: str, separators: set[str]) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in str(text or ""):
        if char in {"(", "（"}:
            depth += 1
        elif char in {")", "）"} and depth > 0:
            depth -= 1
        if char in separators and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _split_list_tail(value: str) -> list[str]:
    text = str(value or "")
    text = re.split(r"(?:近义不算|同义不算|不得分|按写对|每项|满分)", text, 1)[0]
    text = re.sub(r"[（(][^()（）]*(?:项列举|列举|口径|任选)[^()（）]*[)）]", "", text)
    pieces: list[str] = []
    enumerated = re.findall(r"(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(?\d+[）).、])\s*([^;；。]+)", text)
    if enumerated:
        pieces.extend(enumerated)
    else:
        pieces.extend(_split_outside_brackets(text, {"、", ",", "，", "/", "／", ";", "；"}))
    return _stable_unique_terms([piece for piece in pieces if 1 < len(str(piece).strip()) <= 40])


def _explicit_list_terms(point: dict[str, Any], corpus: list[dict[str, Any]]) -> list[str]:
    """Prefer the official list numerator/denominator over repaired free-text anchors."""

    texts = [
        str(point.get("label") or ""),
        str(point.get("list_rule") or ""),
        str(point.get("official_basis") or ""),
    ]
    candidates: list[str] = []
    for text in texts:
        for pattern in (
            r"(?:规范术语原文|标准术语原文|规范术语|标准术语|必须写出规范术语)[:：]\s*([^。；;]+)",
            r"应得分项为\d+项[:：]\s*([^。；;]+)",
            r"——\s*([^。；;]+)",
        ):
            for match in re.finditer(pattern, text):
                candidates.extend(_split_list_tail(match.group(1)))
        for match in re.finditer(r"[（(]([^()（）]{2,120})[)）]", text):
            inner = match.group(1)
            if re.search(r"项列举|近义|同义|不得分|每项|满分", inner):
                continue
            terms = _split_list_tail(inner)
            if len(terms) >= 2:
                candidates.extend(terms)
    anchored_terms: list[str] = []
    for term in _stable_unique_terms(candidates):
        anchored = anchor_required_terms([term], corpus).get("terms") or []
        if anchored and anchored[0].get("anchors"):
            anchored_terms.append(term)
    return _stable_unique_terms(anchored_terms)


def _required_terms_by_point(
    case: dict[str, Any],
    corpus: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]], dict[str, int]]:
    terms_by_point: dict[str, list[str]] = {}
    squeeze_by_point: dict[str, dict[str, Any]] = {}
    root_counts: dict[str, int] = {}
    for point in case.get("gold_scoring_points") or []:
        point_id = str(point.get("point_id") or "")
        raw_terms = extract_required_terms(point)
        squeezed = squeeze_required_terms(raw_terms, corpus)
        explicit_terms = _explicit_list_terms(point, corpus)
        if explicit_terms:
            squeezed = {
                **squeezed,
                "terms": explicit_terms,
                "list_rule_denominator_source": "explicit_official_list_terms",
            }
        if not squeezed["terms"]:
            fallback_text = "\n".join(
                str(point.get(field) or "") for field in ("label", "official_basis", "list_rule")
            )
            fallback_terms = _anchored_subterms(fallback_text, corpus)
            if fallback_terms:
                squeezed = {
                    **squeezed,
                    "terms": fallback_terms,
                    "fallback_repair": "label_subterms_anchored_to_official_sources",
                }
                root_counts["label_subterms_anchored_to_official_sources"] = (
                    root_counts.get("label_subterms_anchored_to_official_sources", 0) + 1
                )
        terms_by_point[point_id] = list(squeezed["terms"])
        squeeze_by_point[point_id] = {"raw_terms": raw_terms, **squeezed}
        for category, count in (squeezed.get("root_cause_counts") or {}).items():
            root_counts[str(category)] = root_counts.get(str(category), 0) + int(count)
    return terms_by_point, squeeze_by_point, dict(sorted(root_counts.items()))


def _ledger_score_map(sample: dict[str, Any], points_by_id: dict[str, dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    ledger = sample.get("ground_truth_ledger") if isinstance(sample.get("ground_truth_ledger"), dict) else {}
    for row in ledger.get("point_hits") or []:
        point_id = str(row.get("point_id") or "")
        status = str(row.get("hit") or "")
        max_score = float((points_by_id.get(point_id) or {}).get("max_score") or 0)
        result[point_id] = max_score if status == "hit" else (max_score / 2 if status == "partial" else 0.0)
    return result


def _point_score_from_result(row: dict[str, Any], point_ids: set[str]) -> dict[str, float]:
    scores = {point_id: 0.0 for point_id in point_ids}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    for item in result.get("rubric_items") or []:
        criterion = str(item.get("criterion") or "")
        if "::" in criterion:
            point_id = criterion.split("::", 1)[0]
            if point_id in scores:
                scores[point_id] += float(item.get("awarded_score") or 0)
    return {key: round(value, 4) for key, value in scores.items()}


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _compare_prior_report(prior_report_path: Path | None, fixture: dict[str, Any]) -> dict[str, Any]:
    if not prior_report_path or not prior_report_path.exists():
        return {"available": False, "reason": "missing_prior_report"}
    prior = _read_json(prior_report_path)
    labels: dict[tuple[str, str, str], float] = {}
    deterministic_points_by_sample: dict[tuple[str, str], set[str]] = {}
    ledger_scores: dict[tuple[str, str, str], float] = {}
    for case in fixture.get("cases") or []:
        points_by_id = {str(point.get("point_id") or ""): point for point in case.get("gold_scoring_points") or []}
        for sample in case.get("eval_samples") or []:
            key = (str(case.get("case_id")), str(sample.get("student_id")))
            deterministic_points_by_sample[key] = set()
            for label in sample.get("no_human_v1_5_labels") or []:
                if not label.get("is_deterministic"):
                    continue
                point_id = str(label.get("point_id"))
                deterministic_points_by_sample[key].add(point_id)
                labels[(key[0], key[1], point_id)] = float(label.get("score") or 0)
            for point_id, score in _ledger_score_map(sample, points_by_id).items():
                ledger_scores[(key[0], key[1], point_id)] = score
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in prior.get("rows") or []:
        arm = str(row.get("arm") or "")
        case_id = str(row.get("case_id") or "")
        sample_id = str(row.get("sample_id") or "")
        point_ids = deterministic_points_by_sample.get((case_id, sample_id), set())
        if not point_ids:
            continue
        pred_scores = _point_score_from_result(row, point_ids)
        gold_total = sum(labels.get((case_id, sample_id, point_id), 0.0) for point_id in point_ids)
        v0_total = sum(ledger_scores.get((case_id, sample_id, point_id), 0.0) for point_id in point_ids)
        pred_total = sum(pred_scores.values())
        grouped.setdefault(arm, []).append(
            {
                "case_id": case_id,
                "sample_id": sample_id,
                "deterministic_points": sorted(point_ids),
                "v1_5_gold_score": round(gold_total, 4),
                "v0_ledger_score": round(v0_total, 4),
                "pred_score_on_deterministic_subset": round(pred_total, 4),
                "abs_delta_v1_5": round(abs(pred_total - gold_total), 4),
                "abs_delta_v0": round(abs(pred_total - v0_total), 4),
            }
        )
    return {
        "available": True,
        "prior_report_path": str(prior_report_path),
        "summary": {
            arm: {
                "sample_count": len(rows),
                "mean_abs_score_delta_v1_5": _avg([float(row["abs_delta_v1_5"]) for row in rows]),
                "mean_abs_score_delta_v0_same_subset": _avg([float(row["abs_delta_v0"]) for row in rows]),
            }
            for arm, rows in sorted(grouped.items())
        },
        "rows": grouped,
    }


def _render_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    comparison = result.get("v0_vs_v1_5_comparison") or {}
    lines = [
        "# Luban No-Human v1.5 Textbook-Anchored Golden",
        "",
        "- status: `textbook_anchored_auditable_no_human_v1_5_shadow`",
        "- claim boundary: pure literal textbook-term points are auditable; residual points remain directional.",
        "- not human IRR; not production gate.",
        "",
        "## Fixture Summary",
        "",
        f"- cases: `{summary['cases']}`",
        f"- samples: `{summary['samples']}`",
        f"- point_labels: `{summary['point_labels']}`",
        f"- deterministic_point_labels: `{summary['deterministic_point_labels']}`",
        f"- deterministic_ratio: `{summary['deterministic_ratio']}`",
        f"- residual_counts: `{json.dumps(summary['residual_counts'], ensure_ascii=False)}`",
        f"- resolution_counts: `{json.dumps(summary['resolution_counts'], ensure_ascii=False)}`",
        f"- po_workload_ratio: `{summary['po_workload_ratio']}`",
        f"- external_expert_necessity_ratio: `{summary['external_expert_necessity_ratio']}`",
        f"- R7a_PO_self_decision_queue: `{result.get('human_escalation_queue_counts', {}).get('R7a_PO_self_decision')}`",
        f"- R7b_external_expert_last_resort_queue: `{result.get('human_escalation_queue_counts', {}).get('R7b_external_expert_last_resort')}`",
        f"- unanchored_root_cause_counts: `{json.dumps(result.get('unanchored_root_cause_counts') or {}, ensure_ascii=False)}`",
        f"- independent_triage_counts: `{json.dumps((result.get('independent_triage') or {}).get('counts') or {}, ensure_ascii=False)}`",
        "",
        "## v0 vs v1.5 Deterministic Subset",
        "",
    ]
    if comparison.get("available"):
        lines.extend(
            [
                "| arm | samples | mean abs delta v1.5 | mean abs delta v0 same subset |",
                "|---|---:|---:|---:|",
            ]
        )
        for arm, data in sorted((comparison.get("summary") or {}).items()):
            lines.append(
                f"| {arm} | {data['sample_count']} | {data['mean_abs_score_delta_v1_5']} | {data['mean_abs_score_delta_v0_same_subset']} |"
            )
    else:
        lines.append(f"- comparison unavailable: `{comparison.get('reason')}`")
    lines.extend(
        [
            "",
            "## Three Golden Layers",
            "",
            "| layer | anchor | can claim | cannot claim |",
            "|---|---|---|---|",
            "| v0 AI-ledger | AI construction ledger | directional grader-vs-construction-intent signal | accuracy / production gate |",
            "| no-human v1.5 | textbook / standard exact spans | auditable literal-term subset metrics | human IRR / production gate |",
            "| human v1 | double-blind expert IRR | production-gate evidence after reliability gate | unavailable until humans label |",
        ]
    )
    return "\n".join(lines) + "\n"


def build_no_human_v1_5_bundle(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_fixture_path: Path = DEFAULT_OUTPUT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    prior_report_path: Path | None = DEFAULT_PRIOR_REPORT,
    agent_a_labels_path: Path | None = DEFAULT_AGENT_A_LABELS,
    agent_b_labels_path: Path | None = DEFAULT_AGENT_B_LABELS,
) -> dict[str, Any]:
    source_root = Path(source_root).expanduser().resolve()
    fixture = _read_json(Path(fixture_path))
    corpus = build_textbook_anchor_corpus(source_root)
    previous_summary_path = output_dir / "no_human_v1_5_summary.json"
    previous_summary = _read_json(previous_summary_path).get("summary") if previous_summary_path.exists() else None
    output = dict(fixture)
    output["suite"] = "luban_case_grading_golden_no_human_v1_5"
    output["status"] = "textbook_anchored_auditable_no_human_v1_5_corrected_shadow"
    output["version"] = "no_human_v1_5_corrected_list_rule_r2"
    output["golden_layer"] = {
        "name": "textbook_anchored_auditable_no_human_v1_5",
        "source_root": str(source_root),
        "source_dirs": ["2026教材", "标准文件"],
        "claim_boundary": "Pure literal-term points are auditable; residual points are directional. Not human IRR and not production gate.",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "corpus_record_count": len(corpus),
    }
    cases: list[dict[str, Any]] = []
    all_agreements: list[dict[str, Any]] = []
    all_root_counts: dict[str, int] = {}
    for case in fixture.get("cases") or []:
        case_copy = dict(case)
        case_corpus = corpus + build_case_official_answer_corpus(case)
        terms_by_point, squeeze_by_point, root_counts = _required_terms_by_point(case, case_corpus)
        for category, count in root_counts.items():
            all_root_counts[category] = all_root_counts.get(category, 0) + int(count)
        labels = build_no_human_labels_for_case(case=case, corpus=case_corpus, required_terms_by_point=terms_by_point)
        all_agreements.append({"case_id": case.get("case_id"), **labels["agent_agreement"]})
        new_points = []
        for point in case.get("gold_scoring_points") or []:
            point_id = str(point.get("point_id") or "")
            new_points.append(
                {
                    **point,
                    "required_terms_v1_5": terms_by_point.get(point_id, []),
                    "term_squeeze_v1_5": squeeze_by_point.get(point_id, {}),
                    "textbook_provenance": labels["point_provenance"].get(point_id, {}),
                }
            )
        new_samples = []
        for sample in case.get("eval_samples") or []:
            sample_id = str(sample.get("student_id") or "")
            new_samples.append({**sample, "no_human_v1_5_labels": labels["labels_by_sample"].get(sample_id, [])})
        case_copy["gold_scoring_points"] = new_points
        case_copy["eval_samples"] = new_samples
        cases.append(case_copy)
    output["cases"] = cases
    output["no_human_v1_5_agreement"] = {
        "meaning": "process reproducibility between two isolated deterministic role implementations; not human IRR",
        "by_case": all_agreements,
    }
    human_escalation_queues = build_human_escalation_queues(output)
    independent_triage: dict[str, Any] = {"available": False, "reason": "missing_independent_agent_labels"}
    if (
        agent_a_labels_path
        and agent_b_labels_path
        and Path(agent_a_labels_path).exists()
        and Path(agent_b_labels_path).exists()
    ):
        labels_a = _read_json(Path(agent_a_labels_path))
        labels_b = _read_json(Path(agent_b_labels_path))
        independent_triage = merge_independent_resolution_labels(
            human_escalation_queues["R7a_PO_self_decision"],
            labels_a,
            labels_b,
        )
        independent_triage["available"] = True
        independent_triage["agent_a_labels_path"] = str(agent_a_labels_path)
        independent_triage["agent_b_labels_path"] = str(agent_b_labels_path)
        output = apply_resolution_merge_to_fixture(output, independent_triage)
        human_escalation_queues = build_human_escalation_queues(output)
    summary = summarize_no_human_fixture(output)
    comparison = _compare_prior_report(prior_report_path, output)
    result = {
        "fixture_path": str(output_fixture_path),
        "report_path": str(output_dir / "no_human_v1_5_report.md"),
        "summary_path": str(output_dir / "no_human_v1_5_summary.json"),
        "po_queue_path": str(output_dir / "R7a_PO_self_decision_queue.json"),
        "external_expert_queue_path": str(output_dir / "R7b_external_expert_last_resort_queue.json"),
        "summary": summary,
        "previous_summary": previous_summary,
        "unanchored_root_cause_counts": all_root_counts,
        "independent_triage": {
            key: value
            for key, value in independent_triage.items()
            if key != "rows"
        },
        "human_escalation_queue_counts": {
            "R7a_PO_self_decision": len(human_escalation_queues["R7a_PO_self_decision"]),
            "R7b_external_expert_last_resort": len(human_escalation_queues["R7b_external_expert_last_resort"]),
        },
        "v0_vs_v1_5_comparison": comparison,
    }
    _write_json(output_fixture_path, output)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "no_human_v1_5_summary.json", result)
    _write_json(output_dir / "R7a_PO_self_decision_queue.json", human_escalation_queues["R7a_PO_self_decision"])
    _write_json(output_dir / "R7b_external_expert_last_resort_queue.json", human_escalation_queues["R7b_external_expert_last_resort"])
    if independent_triage.get("available"):
        _write_json(output_dir / "independent_triage_merge.json", independent_triage)
    (output_dir / "no_human_v1_5_report.md").write_text(_render_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Luban textbook-anchored auditable no-human v1.5 golden.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--output-fixture", default=str(DEFAULT_OUTPUT_FIXTURE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prior-report", default=str(DEFAULT_PRIOR_REPORT))
    parser.add_argument("--agent-a-labels", default="")
    parser.add_argument("--agent-b-labels", default="")
    args = parser.parse_args()
    result = build_no_human_v1_5_bundle(
        fixture_path=Path(args.fixture),
        source_root=Path(args.source_root),
        output_fixture_path=Path(args.output_fixture),
        output_dir=Path(args.output_dir),
        prior_report_path=Path(args.prior_report) if args.prior_report else None,
        agent_a_labels_path=Path(args.agent_a_labels) if args.agent_a_labels else None,
        agent_b_labels_path=Path(args.agent_b_labels) if args.agent_b_labels else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
