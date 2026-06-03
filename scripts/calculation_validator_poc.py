#!/usr/bin/env python3
"""Offline calculation numeric-validator POC for the Luban agentic grading harness.

Scope (narrow, deterministic): ONLY point_type=calculation. Extracts the expected
result number from the point label, extracts the student's number from the answer,
compares with an explicit tolerance. If either value can't be reliably extracted ->
`unverifiable` (never guessed). Does NOT touch text_term points. NOT runtime.

Question answered: does a deterministic numeric check correct LLM/dual errors on
calculation points without introducing new false negatives, and is it worth being
the first typed deterministic guardrail?
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json"
PACKET = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602/agentic_grading_packet.json"
MANIFEST = REPO / "artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json"

# unit -> absolute tolerance on the result value
_UNIT_TOL = {"万元": 0.5, "元": 0.5, "名": 0.0, "个月": 0.0, "天": 0.0, "kg": 0.5, "%": 0.5}
_NUM = r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?"


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _last_number_with_unit(text: str) -> tuple[float, str] | None:
    best = None
    best_pos = -1
    # The final result is stated last; pick the value+unit at the maximum text position.
    for unit in ("万元", "个月", "kg", "名", "天", "元", "%"):
        for m in re.finditer(rf"({_NUM})\s*{re.escape(unit)}", text):
            v = _to_float(m.group(1))
            if v is not None and m.start() > best_pos:
                best, best_pos = (v, unit), m.start()
    return best


def expected_from_label(label: str) -> tuple[float, str] | None:
    """Pull the result value + unit from a calculation label.

    Prefer quoted answer phrases because labels often include distractor numbers
    such as unit prices or durations in explanatory parentheses.
    """
    text = str(label or "")
    quoted_segments = re.findall(r"'([^']+)'|\"([^\"]+)\"|“([^”]+)”", text)
    for groups in quoted_segments:
        segment = next((item for item in groups if item), "")
        result = _last_number_with_unit(segment)
        if result:
            return result
    return _last_number_with_unit(text)


def student_value(answer: str, unit: str, expected: float) -> tuple[float | None, str]:
    """Find the student's number for this quantity. Prefer the number adjacent to the unit;
    fall back to the numerically-closest number in the answer."""
    cands = []
    for m in re.finditer(rf"({_NUM})\s*{re.escape(unit)}", answer):
        v = _to_float(m.group(1))
        if v is not None:
            cands.append(v)
    if cands:
        return min(cands, key=lambda v: abs(v - expected)), "unit_adjacent"
    nums = [_to_float(x) for x in re.findall(_NUM, answer)]
    nums = [v for v in nums if v is not None]
    if not nums:
        return None, "no_number"
    return min(nums, key=lambda v: abs(v - expected)), "closest_number"


def validate() -> dict:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    calc_points = {}
    for c in golden["cases"]:
        for p in c.get("gold_scoring_points") or []:
            if str(p.get("point_type")) == "calculation":
                calc_points[(c["case_id"], p["point_id"])] = p
    tasks = {t["task_id"]: t for t in json.loads(PACKET.read_text(encoding="utf-8"))["tasks"]}

    rows = []
    for t in tasks.values():
        cid, sid = t["case_id"], t["student_id"]
        for sp in t["scoring_points"]:
            key = (cid, sp["point_id"])
            if key not in calc_points:
                continue
            exp = expected_from_label(sp.get("label", ""))
            if not exp:
                rows.append({"case_id": cid, "student_id": sid, "point_id": sp["point_id"], "verdict": "unverifiable", "reason": "no_expected_value"})
                continue
            ev, unit = exp
            sv, how = student_value(t["student_answer"], unit, ev)
            if sv is None:
                rows.append({"case_id": cid, "student_id": sid, "point_id": sp["point_id"], "verdict": "unverifiable", "reason": how, "expected": ev, "unit": unit})
                continue
            tol = _UNIT_TOL.get(unit, 0.5)
            ok = abs(sv - ev) <= tol
            rows.append({
                "case_id": cid, "student_id": sid, "point_id": sp["point_id"],
                "verdict": "numeric_correct" if ok else "numeric_wrong",
                "expected": ev, "student_value": sv, "unit": unit, "tolerance": tol, "extraction": how,
            })
    return {"validator": "calculation_numeric_v1", "tolerance_policy": _UNIT_TOL, "rows": rows}


def main() -> int:
    out = validate()
    (REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_shadow_20260603/calculation_validator_metrics.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    from collections import Counter

    print("verdicts:", dict(Counter(r["verdict"] for r in out["rows"])))
    print("rows:", len(out["rows"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
