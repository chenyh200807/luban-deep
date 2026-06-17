"""QuestionGradingArtifact Registry v1 compiler — DATA-BLOCKED skeleton (2026-06-04).

v1 means "full question bank". Today the only gradeable subjective case-question source
is the 20 golden (already v0). 62 exam-bank questions are MCQ (out of scope); the 6134
node assets are node-level knowledge (not questions); mvp-rubric-20q is prototype.

So this compiler is a FUTURE-READY skeleton, NOT a fake-coverage generator:
  - It discovers *new* gradeable case-question sources (beyond the v0 golden 20).
  - If none exist, it returns ``status="data_blocked"`` and writes a status file. It
    deliberately does NOT emit a same-coverage registry pretending to be a v1 bank.
  - When real new case questions with rubric arrive, ``compile_registry_v1`` projects
    them through the existing question_grading_artifacts schema + ArtifactRuntimeGate
    (no second lookup, no second gate, no fabricated source_refs).

See data-blocker: artifacts/luban_grading_artifacts/registry_v1_20260604/.
Red lines: no fabricated source_ref, no MCQ in case registry, no node-asset-as-rubric,
no new table, no production runtime, no kernel/RAG change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_grading_artifacts" / "registry_v1_20260604"
DATA_BLOCKED = "data_blocked"
COMPILED = "compiled"

# Case-type question types eligible for scoring-point grading (MCQ excluded by design).
_CASE_TYPES = {"written", "case", "case_study", "short_answer", "open_ended", "essay"}


def _golden_question_ids() -> set[str]:
    """The v0 golden 20 already covered by registry v0 — NOT 'new' for v1."""
    from deeptutor.services.construction_grading.question_grading_artifacts import (
        list_case_ids,
    )

    return set(list_case_ids())


def _is_new_gradeable_case_source(path: Path, *, known_ids: set[str]) -> dict[str, Any]:
    """Inspect one source file; return how many NEW gradeable case questions it adds.

    A question counts only if it is case-type AND carries gold_scoring_points AND has a
    question_id not already in the golden 20. MCQ / node-asset / prototype sources add 0.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"path": str(path), "ok": False, "reason": f"unreadable:{exc}", "new_questions": 0}
    cases = data.get("cases") or data.get("items") or data.get("questions") or []
    if not isinstance(cases, list):
        return {"path": str(path), "ok": False, "reason": "no_case_list", "new_questions": 0}
    new = 0
    for c in cases:
        if not isinstance(c, dict):
            continue
        qid = str(c.get("case_id") or c.get("question_id") or "").strip()
        qtype = str(c.get("question_type") or c.get("type") or "case").strip().lower()
        has_points = bool(c.get("gold_scoring_points") or c.get("scoring_points"))
        if qid and qid not in known_ids and qtype in _CASE_TYPES and has_points:
            new += 1
    return {"path": str(path), "ok": True, "new_questions": new}


def discover_new_case_question_sources(extra_sources: list[str | Path] | None = None) -> list[dict[str, Any]]:
    """Sources that add NEW gradeable case questions beyond the golden 20.

    Today this returns only what the caller explicitly passes AND that actually parses
    as new case questions. With no extra sources, it is empty -> data_blocked.
    """
    known = _golden_question_ids()
    found: list[dict[str, Any]] = []
    for src in extra_sources or []:
        p = Path(src)
        if not p.exists():
            found.append({"path": str(p), "ok": False, "reason": "missing", "new_questions": 0})
            continue
        info = _is_new_gradeable_case_source(p, known_ids=known)
        if info.get("new_questions", 0) > 0:
            found.append(info)
    return found


def compile_registry_v1(extra_sources: list[str | Path] | None = None) -> dict[str, Any]:
    """Compile v1 ONLY if new gradeable case-question sources exist; else data_blocked."""
    sources = discover_new_case_question_sources(extra_sources)
    total_new = sum(s.get("new_questions", 0) for s in sources)
    if total_new == 0:
        return {
            "status": DATA_BLOCKED,
            "reason": "no new gradeable case-question source beyond golden 20",
            "new_question_count": 0,
            "fabricated": False,
            "v0_coverage_unchanged": True,
            "see": "artifacts/luban_grading_artifacts/registry_v1_20260604/data_blocker_report.md",
        }
    # FUTURE: project the new gradeable questions through question_grading_artifacts +
    # ArtifactRuntimeGate, applying the same quality gate. Intentionally not implemented
    # until real data exists, so we never emit a fabricated/same-coverage registry.
    return {
        "status": COMPILED,
        "new_question_count": total_new,
        "sources": sources,
        "note": "real-data compile path is a future milestone (M5); not exercised this round",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[],
                        help="path to a new gradeable case-question source (repeatable)")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    result = compile_registry_v1(args.source)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "registry_v1_status.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if result["status"] == DATA_BLOCKED:
        print("registry v1: DATA_BLOCKED — no new gradeable case-question source beyond golden 20.")
        print("No registry emitted (refusing same-coverage v1). See data_blocker_report.md.")
    else:
        print(f"registry v1: would compile {result['new_question_count']} new questions "
              f"(real-data path is milestone M5, not run this round).")


if __name__ == "__main__":
    main()
