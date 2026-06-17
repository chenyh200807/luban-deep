"""Compile case-question rubrics from dual-model (Opus+Codex) reference-answer extractions.

Pipeline: read the LLM-extracted rubrics (from reference answers), apply the deterministic spine
(validate score-sum gate → normalize near-miss scores → dedup by qid → sign), and persist a tracked
release_candidate supply. The grading ground truth is the EXAM REFERENCE ANSWER (Nexus-like: rubric is
scored structure for runtime LLM adjudication, not a textbook-verbatim hard gate).

Inputs (JSON arrays of {qid,total_score,scoring_points[]}):
  --opus  Opus extraction (primary, full coverage)
  --codex Codex extraction (optional, dual-model reconcile on overlap)

NO remote / DB. Re-runnable.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT_SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_case_rubric_scored"
OUT_ART = _REPO / "artifacts" / "luban_grading_artifacts" / "rubric_compile_20260607"

from deeptutor.services.construction_grading import rubric_compiler as RC  # noqa: E402

_AGG = ("聚合", "无选项", "元信息", "无具体给分")


def _normalize_scores(r: dict[str, Any]) -> dict[str, Any] | None:
    """Deterministically scale point scores to total when an extraction is a near-miss (float drift /
    imperfect split). Returns a score-sum-correct rubric, or None if unsalvageable (total<=0)."""
    pts = r.get("scoring_points") or []
    total = r.get("total_score")
    ssum = sum(p.get("score", 0) or 0 for p in pts)
    if not pts or not isinstance(total, (int, float)) or total <= 0 or ssum <= 0:
        return None
    if all((p.get("score", 0) or 0) > 0 for p in pts):
        scaled = [dict(p, score=round((p["score"] / ssum) * total, 2)) for p in pts]
        diff = round(total - sum(p["score"] for p in scaled), 2)
        scaled[-1]["score"] = round(scaled[-1]["score"] + diff, 2)
        return dict(r, scoring_points=scaled)
    return None


def _process(rubrics: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    valid: dict[str, dict[str, Any]] = {}
    stats = {"input": len(rubrics), "aggregate_skipped": 0, "valid_direct": 0,
             "rescued_by_normalize": 0, "unsalvageable": 0}
    for r in rubrics:
        pts = r.get("scoring_points") or []
        if len(pts) == 1 and any(w in str(pts[0].get("text", "")) for w in _AGG):
            stats["aggregate_skipped"] += 1
            continue
        v = RC.validate_rubric(r)
        nr = None
        if v["ok"]:
            nr = v["normalized"]
            stats["valid_direct"] += 1
        else:
            fixed = _normalize_scores(r)
            v2 = RC.validate_rubric(fixed) if fixed else {"ok": False}
            if v2["ok"]:
                nr = v2["normalized"]
                stats["rescued_by_normalize"] += 1
            else:
                stats["unsalvageable"] += 1
        if nr:
            q = nr["qid"]
            if q not in valid or len(nr["scoring_points"]) > len(valid[q]["scoring_points"]):
                valid[q] = nr
    return list(valid.values()), stats


def run(opus_path: str, codex_path: str | None) -> dict[str, Any]:
    opus = json.loads(Path(opus_path).read_text("utf-8"))
    if isinstance(opus, dict):
        opus = opus.get("result", {}).get("rubrics") or opus.get("rubrics") or []
    rubrics = list(opus)
    if codex_path and Path(codex_path).exists():
        codex = json.loads(Path(codex_path).read_text("utf-8"))
        if isinstance(codex, dict):
            codex = codex.get("rubrics") or []
        rubrics += list(codex)  # dedup keeps the finer-grained per qid
    valid, stats = _process(rubrics)
    bundle = RC.sign_rubric_release_candidate(valid)

    OUT_SUPPLY.mkdir(parents=True, exist_ok=True)
    (OUT_SUPPLY / "case_rubric_scored.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    (OUT_SUPPLY / "canonical_pointer.json").write_text(json.dumps(
        {"namespace": "case_rubric_scored", "status": "release_candidate", "published": False,
         "expected_content_hash": bundle["manifest"]["content_hash"]}, ensure_ascii=False, indent=2), "utf-8")
    OUT_ART.mkdir(parents=True, exist_ok=True)
    (OUT_ART / "process_stats.json").write_text(json.dumps(
        {"process": stats, "manifest": bundle["manifest"]}, ensure_ascii=False, indent=2), "utf-8")
    return {"process": stats, "signed_questions": bundle["manifest"]["question_count"],
            "signed_points": bundle["manifest"]["scoring_point_count"],
            "by_policy": bundle["manifest"]["by_policy"], "rejected": bundle["manifest"]["rejected_count"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--opus", required=True)
    ap.add_argument("--codex", default=None)
    args = ap.parse_args()
    r = run(args.opus, args.codex)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
