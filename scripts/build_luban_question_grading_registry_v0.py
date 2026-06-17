"""Compile the 20 golden questions into a QuestionGradingArtifact Registry v0.

Thin wrapper: all schema / publish-gate logic lives in
``question_grading_artifacts`` + ``question_grading_registry``. This script only
projects the readable golden cases, serializes the registry, and emits a quality
report + FINDING.

It does NOT recompile knowledge, run models, touch the DB, or fabricate sources.
Missing/weak sources stay weak (auto_certifiable=False); we never invent a
textbook anchor to raise the published count.

Canonical output dir: artifacts/luban_grading_artifacts/registry_v0_20260604/
  (the earlier luban_consensus_gold/question_grading_registry_v0_20260604/ is SUPERSEDED)
  - registry_report.json               (spec-shaped: questions[] + summary)
  - question_grading_artifacts.jsonl   (one artifact per line)
  - question_grading_registry.json     (status index by question_id)
  - publish_report.json                (aggregate quality report)
  - FINDING_question_grading_registry_v0_20260604.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.question_grading_artifacts import (
    VERSION_ID,
    build_question_grading_artifact,
    list_case_ids,
)
from deeptutor.services.construction_grading.question_grading_registry import (
    QuestionGradingRegistry,
    build_registry,
)

REPO = Path(__file__).resolve().parents[1]
# Canonical registry artifact dir (single publish authority). The earlier
# luban_consensus_gold/question_grading_registry_v0_20260604/ dir is SUPERSEDED
# and must not be written or read as authority anymore.
DEFAULT_OUT = (
    REPO
    / "artifacts"
    / "luban_grading_artifacts"
    / "registry_v0_20260604"
)
SUPERSEDED_OUT = (
    REPO
    / "artifacts"
    / "luban_consensus_gold"
    / "question_grading_registry_v0_20260604"
)


def build_artifacts() -> list[dict[str, Any]]:
    return [build_question_grading_artifact(cid) for cid in list_case_ids()]


def build_publish_report(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    policy_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    blocked_reasons: Counter[str] = Counter()

    total_points = 0
    auto_pts = 0
    weak_pts = 0
    missing_policy = 0
    missing_source = 0
    top_risks: list[dict[str, Any]] = []

    for art in artifacts:
        status_counts[art["status"]] += 1
        for r in art["quality_gates"]["blocked_reasons"]:
            blocked_reasons[r] += 1
        unsupported = art["quality_gates"]["unsupported_required_terms"]
        if unsupported:
            top_risks.append(
                {
                    "question_id": art["question_id"],
                    "status": art["status"],
                    "unsupported_required_terms": unsupported,
                }
            )
        for sp in art["scoring_points"]:
            total_points += 1
            policy_counts[sp.get("policy_type") or "unknown"] += 1
            if sp.get("auto_certifiable"):
                auto_pts += 1
            if sp.get("source_status") != "ok":
                weak_pts += 1
                missing_source += 1
            if not sp.get("policy_type"):
                missing_policy += 1
            for ref in sp.get("source_refs") or []:
                source_counts[ref.get("source_type") or "unknown"] += 1

    return {
        "version_id": VERSION_ID,
        "total_questions": len(artifacts),
        "published_count": status_counts.get("published", 0),
        "draft_count": status_counts.get("draft", 0),
        "blocked_count": status_counts.get("blocked", 0),
        "total_scoring_points": total_points,
        "policy_type_counts": dict(policy_counts),
        "source_type_counts": dict(source_counts),
        "auto_certifiable_point_count": auto_pts,
        "weak_source_point_count": weak_pts,
        "missing_policy_count": missing_policy,
        "missing_source_count": missing_source,
        "blocked_reasons": dict(blocked_reasons),
        "top_risks": top_risks,
    }


def build_registry_index(registry: QuestionGradingRegistry) -> dict[str, Any]:
    index: dict[str, Any] = {"version_id": VERSION_ID, "questions": {}}
    for qid in registry.question_ids():
        art = registry.get_artifact(qid)
        assert art is not None
        index["questions"][qid] = {
            "artifact_id": art["artifact_id"],
            "status": art["status"],
            "status_reason": art["status_reason"],
            "auto_certifiable_point_count": art["quality_gates"][
                "auto_certifiable_point_count"
            ],
            "total_scoring_points": len(art["scoring_points"]),
            "content_hash": art["provenance"]["content_hash"],
        }
    index["summary"] = registry.publish_summary()
    return index


def render_finding(report: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    draft_ids = [a["question_id"] for a in artifacts if a["status"] == "draft"]
    blocked_ids = [a["question_id"] for a in artifacts if a["status"] == "blocked"]
    typed_policy_pts = sum(
        1
        for a in artifacts
        for sp in a["scoring_points"]
        if sp.get("policy_type")
        in {"exact_required", "list_rule", "calculation", "penalty_rule", "figure_label"}
    )
    lines = [
        "# QuestionGradingArtifact Registry v0 (2026-06-04)",
        "",
        "## Canonical artifact dir (single publish authority)",
        "",
        "- canonical: `artifacts/luban_grading_artifacts/registry_v0_20260604/`",
        "- superseded: `artifacts/luban_consensus_gold/question_grading_registry_v0_20260604/` "
        "(kept only as a stale snapshot; never read/written as authority).",
        "",
        "## Scope",
        "",
        "- File-based publish gate. No DB, no production runtime, no kernel change, no RAG authority.",
        f"- Compiled from golden fixture + cached typed-policy packets; version `{VERSION_ID}`.",
        "",
        "## Publish counts",
        "",
        f"- published: **{report['published_count']}**",
        f"- draft: **{report['draft_count']}**  ({', '.join(draft_ids) or 'none'})",
        f"- blocked: **{report['blocked_count']}**  ({', '.join(blocked_ids) or 'none'})",
        f"- total scoring points: {report['total_scoring_points']}",
        "",
        "## Source quality",
        "",
        f"- weak-source points (auto_certifiable=False): **{report['weak_source_point_count']}**",
        f"- auto-certifiable points: **{report['auto_certifiable_point_count']}**",
        f"- non-auto-certifiable points: **{report['total_scoring_points'] - report['auto_certifiable_point_count']}**",
        f"- missing-policy points: {report['missing_policy_count']}",
        f"- typed_policy coverage (typed policy_type points): {typed_policy_pts}/{report['total_scoring_points']}",
        "",
        "## Was any textbook source fabricated?",
        "",
        "- **NO.** A `textbook` source_ref (verified=True) is emitted only from a real "
        "`evidence_policy.textbook_quote` + chunk_id. Points without a real textbook "
        "anchor are marked `source_status=missing_or_weak` and `auto_certifiable=False`. "
        "No anchor is invented to raise the published count.",
        "",
        "## How the registry serves runtime",
        "",
        "- `get_question_grading_artifact(question_id)` returns "
        "`ArtifactLookupResult(found, status, artifact, auto_certification_allowed)`.",
        "- published -> `auto_certification_allowed=True` (may enter auto_certified flow).",
        "- draft / blocked -> `auto_certification_allowed=False` (AI-Draft / high_risk only).",
        "- unknown -> `found=False, status=artifact_missing` (no auto-grading).",
        "",
        "## Next step (20 -> full bank)",
        "",
        "- Two choices only: (1) extend the same projection to the full question bank, "
        "or (2) wire this registry gate into the AI-Draft runtime test chain. "
        "No new DB table either way.",
        "",
        "## Top risks",
        "",
    ]
    if report["top_risks"]:
        for risk in report["top_risks"]:
            lines.append(
                f"- {risk['question_id']} ({risk['status']}): unsupported required_terms "
                f"on {risk['unsupported_required_terms']}"
            )
    else:
        lines.append("- none flagged")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    registry = QuestionGradingRegistry(build_artifacts())
    # Use the *runtime-refined* artifacts (registry may have demoted published/draft
    # to blocked) so every report below is consistent with what the gate returns.
    artifacts = [registry.get_artifact(qid) for qid in registry.question_ids()]
    report = build_publish_report(artifacts)
    index = build_registry_index(registry)
    registry_report = build_registry(registry=registry)

    (out_dir / "registry_report.json").write_text(
        json.dumps(registry_report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "question_grading_artifacts.jsonl").write_text(
        "\n".join(json.dumps(a, ensure_ascii=False, sort_keys=True) for a in artifacts)
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "question_grading_registry.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "publish_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "FINDING_question_grading_registry_v0_20260604.md").write_text(
        render_finding(report, artifacts), encoding="utf-8"
    )

    # Mark the earlier dir as superseded (do NOT delete — it may hold a parallel
    # snapshot). Only drop a pointer so nothing treats it as authority.
    if SUPERSEDED_OUT.exists() and SUPERSEDED_OUT.resolve() != out_dir.resolve():
        (SUPERSEDED_OUT / "SUPERSEDED.md").write_text(
            "# SUPERSEDED\n\n"
            "This QuestionGradingArtifact Registry v0 snapshot is **superseded**.\n\n"
            "Canonical (single publish authority): "
            "`artifacts/luban_grading_artifacts/registry_v0_20260604/`\n\n"
            "Do not read or write this dir as authority.\n",
            encoding="utf-8",
        )

    print(
        f"registry v0 -> {out_dir}\n"
        f"  published={report['published_count']} "
        f"draft={report['draft_count']} blocked={report['blocked_count']} "
        f"points={report['total_scoring_points']} "
        f"auto_certifiable={report['auto_certifiable_point_count']} "
        f"weak={report['weak_source_point_count']}"
    )


if __name__ == "__main__":
    main()
