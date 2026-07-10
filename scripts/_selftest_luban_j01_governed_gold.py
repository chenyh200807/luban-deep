#!/usr/bin/env python3
"""Dry-run + selftest for the J01 governed-gold harness.

Proves the scaffold actually runs end-to-end WITHOUT any human, on synthetic
annotator data, and that the κ math is correct against hand-computed examples.
This is the "dry-run validation" deliverable — it never signs gold (synthetic
labels are explicitly not gold); it only demonstrates the machinery.

Arms:
  1. κ unit checks — Cohen κ against the classic 0.4 example; Fleiss κ against a
     hand-computed -0.2 example (also demonstrates a NEGATIVE κ organically).
  2. Real slice build on the golden fixture (~150 cells).
  3. Two competent annotators (seeded from the internal ledger, ~18% injected
     disagreement) → high κ, gold frozen, arbitration queue populated.
  4. Random annotators → κ ≈ 0 / negative (reproduces the `fleiss_kappa=-0.05`
     red line: near-random agreement cannot be gold).
  5. Single annotator → engine REFUSES to freeze (directional, not gold).

Run: python scripts/_selftest_luban_j01_governed_gold.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import random
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_luban_j01_governed_gold_slice import build_slice  # noqa: E402
from scripts.score_luban_j01_governed_gold import (  # noqa: E402
    ALLOWED_HITS,
    cohen_kappa,
    fleiss_kappa,
    run,
)

FIELDNAMES = [
    "cell_id", "case_id", "student_id", "point_id", "max_score",
    "human_hit", "human_score", "evidence_span", "human_error_codes", "human_note",
]


def _check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise AssertionError(f"selftest arm failed: {name} {detail}")


def kappa_unit_checks() -> None:
    print("Arm 1: κ math unit checks")
    # Classic Cohen κ example: po=0.7, pe=0.5, κ=0.4.
    a = ["hit"] * 20 + ["hit"] * 5 + ["miss"] * 10 + ["miss"] * 15
    b = ["hit"] * 20 + ["miss"] * 5 + ["hit"] * 10 + ["miss"] * 15
    k = cohen_kappa(a, b, ("hit", "miss"))
    _check("cohen_kappa == 0.4 on classic example", k == 0.4, f"got {k}")
    # Fleiss κ hand example: 2 items, 3 raters, {hit,miss} → κ = -0.2.
    item_ratings = [["hit", "hit", "hit"], ["hit", "hit", "miss"]]
    fk = fleiss_kappa(item_ratings, ("hit", "miss"))
    _check("fleiss_kappa == -0.2 on hand example (negative κ works)", fk == -0.2, f"got {fk}")
    # Perfect agreement → κ = 1.0
    _check("cohen_kappa perfect agreement == 1.0",
           cohen_kappa(["hit", "miss", "partial"], ["hit", "miss", "partial"], ALLOWED_HITS) == 1.0)


def _span_for(hit: str, student_answer: str) -> str:
    if hit == "miss" or not student_answer:
        return ""
    return student_answer.strip()[:8]  # guaranteed verbatim substring


def _write_labels(path: Path, manifest_cells: list[dict], verdicts: dict[str, str]) -> None:
    rows = []
    for cell in manifest_cells:
        cid = cell["cell_id"]
        hit = verdicts[cid]
        max_score = float(cell.get("max_score") or 0)
        score = max_score if hit == "hit" else round(max_score / 2, 2) if hit == "partial" else 0.0
        rows.append({
            "cell_id": cid, "case_id": cell["case_id"], "student_id": cell["student_id"],
            "point_id": cell["point_id"], "max_score": max_score,
            "human_hit": hit, "human_score": score,
            "evidence_span": _span_for(hit, str(cell.get("student_answer_text") or "")),
            "human_error_codes": "", "human_note": "",
        })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _ledger_verdict(cell: dict) -> str:
    ref = str(cell.get("_ledger_reference_hit") or "").strip()
    return ref if ref in ALLOWED_HITS else "miss"


def _perturb(verdict: str, rng: random.Random, prob: float) -> str:
    if rng.random() >= prob:
        return verdict
    alternatives = [c for c in ALLOWED_HITS if c != verdict]
    return rng.choice(alternatives)


def pipeline_dry_run(workdir: Path) -> None:
    print("Arm 2: build real J01 slice on golden fixture")
    result = build_slice(
        fixture_path=PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json",
        bank_path=PROJECT_ROOT / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json",
        output_root=workdir,
        seed="20260705",
        target=150,
        max_per_case=None,
        annotators=["annotatorA", "annotatorB"],
        case_ids=None,
    )
    manifest_path = Path(result["slice_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cells = manifest["cells"]
    _check("selected ~150 cells", result["selected_count"] == 150, f"got {result['selected_count']}")

    def _keys_recursive(obj) -> set[str]:
        found: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                found.add(str(k))
                found |= _keys_recursive(v)
        elif isinstance(obj, list):
            for v in obj:
                found |= _keys_recursive(v)
        return found

    packets = json.loads(Path(result["blind_packets"]).read_text(encoding="utf-8"))
    leak_keys = {"ground_truth_ledger", "_ledger_reference_hit", "ledger_reference_hit",
                 "blind_grade", "point_hits", "prediction", "pred_score"}
    _check("blind_packets carry no ledger/prediction data keys",
           all(not (_keys_recursive(p) & leak_keys) for p in packets),
           "packet keys must exclude ledger/prediction fields")

    rng = random.Random(20260705)
    base = {c["cell_id"]: _ledger_verdict(c) for c in cells}
    verdicts_a = dict(base)
    verdicts_b = {cid: _perturb(v, rng, 0.18) for cid, v in base.items()}

    print("Arm 3: two competent annotators (~18% injected disagreement)")
    label_a = workdir / "annotatorA_filled.csv"
    label_b = workdir / "annotatorB_filled.csv"
    _write_labels(label_a, cells, verdicts_a)
    _write_labels(label_b, cells, verdicts_b)
    res = run(manifest_path=manifest_path, label_specs={"annotatorA": label_a, "annotatorB": label_b}, arbiter_path=None)
    (workdir / "governed_gold_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    overall_irr={res['overall_irr']}  counts={res['counts']}")
    _check("overall Cohen κ computed", res["overall_irr"]["method"] == "cohen_kappa")
    _check("overall κ high for competent pair (>0.5)", (res["overall_irr"]["kappa"] or 0) > 0.5,
           f"κ={res['overall_irr']['kappa']}")
    _check("arbitration queue populated by disagreements", res["counts"]["arbitration_queue"] > 0,
           f"queue={res['counts']['arbitration_queue']}")
    _check("some cells frozen as gold-eligible", res["counts"]["frozen_gold"] > 0,
           f"gold={res['counts']['frozen_gold']}")
    _check("validations complete (no missing/invalid)",
           all(v["is_complete"] for v in res["validations"]))
    _check("gold_version has content_hash", bool(res["gold_version"]["content_hash"]))
    _check("production_write_count == 0", res["production_write_count"] == 0)

    print("Arm 3b: arbiter resolves splits → more gold")
    arbiter = {c["cell_id"]: base[c["cell_id"]] for c in cells}
    arb_path = workdir / "arbiter_filled.csv"
    _write_labels(arb_path, cells, arbiter)
    res_arb = run(manifest_path=manifest_path,
                  label_specs={"annotatorA": label_a, "annotatorB": label_b}, arbiter_path=arb_path)
    _check("arbiter increases frozen gold vs no-arbiter",
           res_arb["counts"]["frozen_gold"] >= res["counts"]["frozen_gold"],
           f"{res['counts']['frozen_gold']} -> {res_arb['counts']['frozen_gold']}")

    print("Arm 4: random annotators → κ near 0 / negative (fleiss=-0.05 red line)")
    rng2 = random.Random(999)
    rand_a = {c["cell_id"]: rng2.choice(ALLOWED_HITS) for c in cells}
    rand_b = {c["cell_id"]: rng2.choice(ALLOWED_HITS) for c in cells}
    ra, rb = workdir / "rand_a.csv", workdir / "rand_b.csv"
    _write_labels(ra, cells, rand_a)
    _write_labels(rb, cells, rand_b)
    res_rand = run(manifest_path=manifest_path, label_specs={"rand_a": ra, "rand_b": rb}, arbiter_path=None)
    print(f"    random κ={res_rand['overall_irr']['kappa']}  frozen_gold={res_rand['counts']['frozen_gold']}")
    _check("random-pair κ near zero (<0.2)", abs(res_rand["overall_irr"]["kappa"] or 0) < 0.2,
           f"κ={res_rand['overall_irr']['kappa']}")

    print("Arm 5: single annotator → refuses to freeze (directional, not gold)")
    res_single = run(manifest_path=manifest_path, label_specs={"annotatorA": label_a}, arbiter_path=None)
    _check("single annotator flagged directional", res_single["single_annotator_directional_only"] is True)
    _check("single annotator freezes ZERO gold", res_single["counts"]["frozen_gold"] == 0,
           f"gold={res_single['counts']['frozen_gold']}")

    print(f"\nArtifacts written under: {workdir}")


def main() -> int:
    print("=== J01 governed-gold harness dry-run / selftest ===\n")
    kappa_unit_checks()
    keep = "--keep" in sys.argv
    if keep:
        workdir = PROJECT_ROOT / "artifacts/luban_governed_gold/_dryrun"
        workdir.mkdir(parents=True, exist_ok=True)
        pipeline_dry_run(workdir)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline_dry_run(Path(tmp))
    print("\n=== ALL ARMS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
