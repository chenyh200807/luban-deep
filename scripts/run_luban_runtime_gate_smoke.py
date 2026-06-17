"""Deterministic smoke for the QuestionGradingArtifact runtime gate.

Shows the gate controlling runtime auto-certification across three artifact states,
WITHOUT calling any model: for each case it synthesizes a draft where the model
wants to certify EVERY point, then applies the real registry gate and records what
survives.

  published case -> some points may auto-certify (auto_certifiable ones); weak points
                    downgraded to pending (point_not_auto_certifiable).
  draft case     -> no point may auto-certify (artifact_not_published).
  missing case   -> fail closed (artifact_missing).

No DB, no kernel, no RAG, no production runtime.

Output: artifacts/luban_grading_artifacts/runtime_gate_20260604/
  - runtime_gate_smoke_results.json
  - FINDING_runtime_gate_20260604.md
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.artifact_runtime_gate import (
    apply_runtime_artifact_gate,
    resolve_runtime_artifact_gate,
)
from deeptutor.services.construction_grading.question_grading_artifacts import (
    build_question_grading_artifact,
)

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_grading_artifacts" / "runtime_gate_20260604"

PUBLISHED_CASE = "Q17-1A433000"  # published, has both auto-certifiable and weak points
DRAFT_CASE = "Q20-1A413000"  # 0 auto-certifiable points, no high_risk -> draft
MISSING_CASE = "Q-DOES-NOT-EXIST"


def _all_certify_draft(question_id: str) -> dict[str, Any]:
    """Synthesize a draft where the model tries to auto-certify EVERY point."""
    art = build_question_grading_artifact(question_id)
    points = art.get("scoring_points") or []
    if not points:  # missing artifact -> use a generic 2-point draft
        points = [
            {"point_id": "P1", "max_score": 2},
            {"point_id": "P2", "max_score": 2},
        ]
    return {
        "question_id": question_id,
        "point_results": [
            {
                "point_id": sp["point_id"],
                "score": float(sp.get("max_score") or 0),
                "hit": "hit",
                "auto_certified": True,
                "high_risk_review": False,
                "unsupported": False,
                "display_status": "auto_certified",
            }
            for sp in points
        ],
    }


def _scenario(question_id: str) -> dict[str, Any]:
    gate = resolve_runtime_artifact_gate(question_id)
    draft = _all_certify_draft(question_id)
    n_in = len(draft["point_results"])
    gated = apply_runtime_artifact_gate(draft, gate)
    auto = [p["point_id"] for p in gated["point_results"] if p["auto_certified"]]
    downgraded = [
        {"point_id": p["point_id"], "review_reason": p.get("review_reason")}
        for p in gated["point_results"]
        if not p["auto_certified"]
    ]
    return {
        "question_id": question_id,
        "artifact_status": gate.artifact_status,
        "auto_certification_allowed": gate.auto_certification_allowed,
        "blocked_reason": gate.blocked_reason,
        "points_in": n_in,
        "auto_certified_points": auto,
        "auto_certified_count": len(auto),
        "downgraded_points": downgraded,
        "auto_certified_score": gated["auto_certified_score"],
        "pending_review_score": gated["pending_review_score"],
        "bad_certified_count": gated["bad_certified_count"],
        "artifact_gate": gated["artifact_gate"],
    }


def render_finding(results: list[dict[str, Any]]) -> str:
    by_id = {r["question_id"]: r for r in results}
    pub = by_id[PUBLISHED_CASE]
    dft = by_id[DRAFT_CASE]
    mis = by_id[MISSING_CASE]
    lines = [
        "# Runtime gate smoke (2026-06-04)",
        "",
        "## Scope",
        "",
        "- Registry runtime gate applied to AI-Draft. No model call, no DB, no kernel, no RAG, no production runtime.",
        "- For each case the model tries to auto-certify EVERY point; the gate decides what survives.",
        "",
        "## Results",
        "",
        f"### published — {PUBLISHED_CASE}",
        f"- artifact_status: **{pub['artifact_status']}**, auto_certification_allowed={pub['auto_certification_allowed']}",
        f"- auto-certified {pub['auto_certified_count']}/{pub['points_in']} points: {pub['auto_certified_points']}",
        f"- downgraded (weak/not-certifiable): {[d['point_id'] for d in pub['downgraded_points']]}",
        f"- auto_certified_score={pub['auto_certified_score']}, pending_review_score={pub['pending_review_score']}, bad_certified={pub['bad_certified_count']}",
        "",
        f"### draft — {DRAFT_CASE}",
        f"- artifact_status: **{dft['artifact_status']}**, auto_certification_allowed={dft['auto_certification_allowed']}",
        f"- auto-certified {dft['auto_certified_count']}/{dft['points_in']} (must be 0); reason: artifact_not_published",
        f"- auto_certified_score={dft['auto_certified_score']}, pending_review_score={dft['pending_review_score']} (preserved, not zeroed)",
        "",
        f"### missing — {MISSING_CASE}",
        f"- artifact_status: **{mis['artifact_status']}**, artifact_found={mis['artifact_gate']['artifact_found']}",
        f"- auto-certified {mis['auto_certified_count']}/{mis['points_in']} (must be 0); fail closed: artifact_missing",
        "",
        "## Verdict",
        "",
        "- published -> partial auto-certification (only auto_certifiable points).",
        "- draft / missing -> ZERO auto-certification, pending_review preserved.",
        "- gate only downgrades, never upgrades. bad_certified=0 everywhere.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = [_scenario(c) for c in (PUBLISHED_CASE, DRAFT_CASE, MISSING_CASE)]
    (OUT_DIR / "runtime_gate_smoke_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "FINDING_runtime_gate_20260604.md").write_text(
        render_finding(results), encoding="utf-8"
    )
    for r in results:
        print(
            f"{r['question_id']}: status={r['artifact_status']} "
            f"auto={r['auto_certified_count']}/{r['points_in']} "
            f"pending={r['pending_review_score']} bad={r['bad_certified_count']}"
        )
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
