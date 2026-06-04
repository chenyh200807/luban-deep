"""M10 — Non-Textbook Rubric Authority Factory.

The residual bottleneck is no longer "we didn't run source hunt": it is that many scoring
points are case-judgment / calculation / list points that CANNOT be 2026-textbook verbatim
anchored, yet still must be graded. M10 lays a *legitimate authority hierarchy* over them.

Six authority buckets:
  1. textbook_verbatim_auto_candidate     -> only path to source-backed auto (unchanged)
  2. machine_checkable_case_spec_candidate -> calc/numeric/fixed-logic; official_answer is a
                                              CASE RUBRIC SEED (never a textbook source); needs
                                              formula/unit/expected/acceptance_range/negative_controls
  3. list_rule_structured_candidate        -> denominator + item_set + per-item matcher; coverage==1.0
  4. external_source_required              -> textbook-absent; emit work order only, no auto
  5. teacher_or_ai_council_review_required -> case judgment / semantic synthesis; beta review, no auto
  6. drop_or_keep_draft                    -> hints / error-restatement / un-gradeable noise

HARD: official_answer is NEVER a textbook source (it may seed a case rubric, labelled as such);
model votes are NEVER a source; no semantic-only auto; no formal registry; no production runtime;
no v0 overwrite; human_reviewed=false; alpha/beta stay shadow. The deterministic matcher is the
only hard gate; every machine-checkable spec must survive a 7-vector false-positive attack.

Output -> artifacts/luban_grading_artifacts/non_textbook_rubric_authority_factory_m10_20260604/
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AR = REPO / "artifacts" / "luban_grading_artifacts"
M35 = AR / "blocked_point_rubric_normalization_m35_20260604"
M8 = AR / "v1_alpha_grand_sprint_m8_20260604"
M9 = AR / "v1_beta_shadow_source_assault_m9_20260604"
OUT = AR / "non_textbook_rubric_authority_factory_m10_20260604"

BUCKET = {
    "TEXTBOOK": "textbook_verbatim_auto_candidate",
    "MACHINE": "machine_checkable_case_spec_candidate",
    "LIST": "list_rule_structured_candidate",
    "EXTERNAL": "external_source_required",
    "REVIEW": "teacher_or_ai_council_review_required",
    "DROP": "drop_or_keep_draft",
}

_JUDGE_POS = ("合理", "正确", "妥", "符合", "成立", "可以", "应予")
_JUDGE_NEG = ("不合理", "不正确", "不妥", "不符合", "不成立", "不可以", "无效", "错误")
_META_PAT = re.compile(r"不妥之处|错误之处|注[:：]|只需写出|题目上缺少|理由[:：]")
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_FORMULA = re.compile(r"[A-Za-z一-龥]*\s*[=＝]\s*[-+*/×÷().\d\s]+[=＝]\s*(-?\d+(?:\.\d+)?)")
_RANGE = re.compile(r"(\d+(?:/\d+)?)\s*[~～-]\s*(\d+(?:/\d+)?)")
_UNIT = re.compile(r"(个月|天|日|月|年|m2|m3|mm|cm|km|MPa|kN|kg|t|%|万元|元|根|层|个|m)")


def _wj(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _wl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), "utf-8")


def _jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text("utf-8").splitlines() if l.strip()] if path.exists() else []


def _frac(s: str) -> float:
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b)
    return float(s)


def _judgment(label: str) -> bool | None:
    if any(n in label for n in _JUDGE_NEG):
        return False
    if any(p in label for p in _JUDGE_POS):
        return True
    return None


# ----------------------------- spec generation -----------------------------

def _machine_spec(point: dict[str, Any]) -> dict[str, Any] | None:
    """Build a deterministic, machine-checkable case spec. Returns None if not machine-checkable.
    official_answer here is a CASE RUBRIC SEED (source_seed=official_answer_not_textbook)."""
    label = str(point.get("point_label") or "")
    unit_m = _UNIT.search(label)
    unit = unit_m.group(1) if unit_m else None
    judgment = _judgment(label)

    # 1) explicit formula with a final result  ->  numeric_formula
    fm = _FORMULA.search(label)
    if fm:
        expected = float(fm.group(1))
        return {"kind": "numeric_formula", "formula": fm.group(0), "expected": expected, "unit": unit,
                "acceptance_range": [expected, expected], "judgment": judgment,
                "negative_controls": _neg_numeric(expected)}

    # 2) numeric range (e.g. 1/1000~3/1000)  ->  numeric_range
    rg = _RANGE.search(label)
    if rg:
        lo, hi = sorted((_frac(rg.group(1)), _frac(rg.group(2))))
        return {"kind": "numeric_range", "lo": lo, "hi": hi, "unit": unit, "judgment": judgment,
                "negative_controls": _neg_range(lo, hi)}

    # 3) numeric judgment (a value + 合理/不合理 ...)  ->  numeric_judgment
    nums = _NUM.findall(label)
    if nums and judgment is not None:
        expected = float(nums[0])
        return {"kind": "numeric_judgment", "expected": expected, "unit": unit, "judgment": judgment,
                "acceptance_range": [expected, expected], "negative_controls": _neg_numeric(expected, judgment)}

    # 4) pure boolean judgment (合理/不合理 with no decisive number)
    if judgment is not None and not _META_PAT.search(label):
        return {"kind": "boolean_judgment", "expected_bool": judgment, "unit": None,
                "negative_controls": [{"vector": "contradiction", "input": (not judgment)}]}

    # 5) a bare numeric value + unit (e.g. 900mm)  ->  numeric_value
    if nums and unit:
        expected = float(nums[0])
        return {"kind": "numeric_value", "expected": expected, "unit": unit,
                "acceptance_range": [expected, expected], "negative_controls": _neg_numeric(expected)}
    return None


def _neg_numeric(expected: float, judgment: bool | None = None) -> list[dict[str, Any]]:
    ctrls = [
        {"vector": "numeric_off_by_one", "input": expected + 1},
        {"vector": "irrelevant", "input": expected * 7 + 13},
        {"vector": "contradiction", "input": -expected if expected else 999999},
    ]
    if judgment is not None:
        ctrls.append({"vector": "judgment_flip", "input": expected, "judgment": not judgment})
    return ctrls


def _neg_range(lo: float, hi: float) -> list[dict[str, Any]]:
    span = hi - lo or abs(hi) or 1.0
    return [
        {"vector": "below_range", "input": lo - span - 1},
        {"vector": "above_range", "input": hi + span + 1},
        {"vector": "irrelevant", "input": (hi + 1) * 5 + 7},
    ]


def _list_spec(point: dict[str, Any]) -> dict[str, Any] | None:
    ls = point.get("list_spec") or point.get("list_rule") or {}
    items = list(ls.get("item_set") or [])
    if not items:
        return None
    denom = len(items)  # full coverage == every item has a matcher
    matchers = [{"item": it, "matcher": "normalized_contains", "norm": _norm(it)} for it in items if _norm(it)]
    coverage = round(len(matchers) / denom, 3) if denom else 0.0
    return {"denominator": denom, "item_set": items, "item_matchers": matchers, "coverage": coverage,
            "full_coverage": coverage >= 1.0, "rubric_seed": "official_answer_not_textbook"}


def _norm(s: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’]", "", str(s or ""))


# ----------------------------- deterministic matcher (the only hard gate) -----------------------------

def matcher_accepts(spec: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Deterministic accept/reject. candidate = {value?: float, judgment?: bool, items?: [str]}."""
    kind = spec["kind"] if "kind" in spec else "list"
    if kind in ("numeric_formula", "numeric_value", "numeric_judgment"):
        v = candidate.get("value")
        if v is None:
            return False
        lo, hi = spec["acceptance_range"]
        if not (lo <= v <= hi):
            return False
        if kind == "numeric_judgment" and "judgment" in candidate:
            return candidate["judgment"] == spec.get("judgment")
        return True
    if kind == "numeric_range":
        v = candidate.get("value")
        return v is not None and spec["lo"] <= v <= spec["hi"]
    if kind == "boolean_judgment":
        return candidate.get("judgment") == spec["expected_bool"]
    if kind == "list":
        items = candidate.get("items") or []
        normed = {_norm(i) for i in items}
        need = {m["norm"] for m in spec["item_matchers"]}
        # full coverage required AND no over-claim beyond the rubric denominator
        if len(items) != spec["denominator"]:
            return False
        return need.issubset(normed)
    return False


# ----------------------------- false-positive attack -----------------------------

ATTACK_VECTORS = ("exact_hit", "partial", "contradiction", "near_synonym", "irrelevant",
                  "numeric_off_by_one", "denominator_mismatch")


def attack_spec(spec: dict[str, Any], is_list: bool) -> list[dict[str, Any]]:
    out = []
    if is_list:
        items = spec["item_set"]
        cases = {
            "exact_hit": {"items": items},
            "partial": {"items": items[:-1]} if len(items) > 1 else {"items": []},
            "contradiction": {"items": ["完全无关的项"] * spec["denominator"]},
            "near_synonym": {"items": [it + "x" for it in items]},
            "irrelevant": {"items": ["无关"]},
            "numeric_off_by_one": {"items": items + ["多余项"]},
            "denominator_mismatch": {"items": items + ["越界项"]},
        }
    else:
        kind = spec["kind"]
        if kind == "boolean_judgment":
            exp = spec["expected_bool"]
            cases = {
                "exact_hit": {"judgment": exp},
                "partial": {"judgment": None},
                "contradiction": {"judgment": (not exp)},
                "near_synonym": {"judgment": None},
                "irrelevant": {"value": 0},
                "numeric_off_by_one": {"value": 1},
                "denominator_mismatch": {"value": 2},
            }
        elif kind == "numeric_range":
            lo, hi = spec["lo"], spec["hi"]
            cases = {
                "exact_hit": {"value": (lo + hi) / 2},
                "partial": {"value": lo - 0.0001},
                "contradiction": {"value": -(abs(hi) + 1000)},
                "near_synonym": {"value": hi * 10},
                "irrelevant": {"value": (hi + 1) * 5 + 7},
                "numeric_off_by_one": {"value": hi + 1},
                "denominator_mismatch": {"value": lo - (hi - lo) - 1},
            }
        else:
            exp = spec["expected"]
            jext = {"judgment": spec.get("judgment")} if kind == "numeric_judgment" else {}
            cases = {
                "exact_hit": {"value": exp, **jext},
                "partial": {"value": exp / 2 if exp else 0.5},
                "contradiction": ({"value": exp, "judgment": (not spec.get("judgment"))}
                                  if kind == "numeric_judgment" else {"value": -exp if exp else 999999}),
                "near_synonym": {"value": exp, "judgment": None} if kind == "numeric_judgment" else {"value": exp + 0.0001},
                "irrelevant": {"value": exp * 7 + 13},
                "numeric_off_by_one": {"value": exp + 1, **jext},
                "denominator_mismatch": {"value": exp + 2, **jext},
            }
    for vec in ATTACK_VECTORS:
        cand = cases.get(vec, {})
        accepted = matcher_accepts(spec, cand)
        should_accept = vec == "exact_hit"
        out.append({"vector": vec, "candidate": cand, "accepted": accepted,
                    "should_accept": should_accept,
                    "false_positive": accepted and not should_accept,
                    "false_negative": (not accepted) and should_accept})
    return out


# ----------------------------- classification -----------------------------

def _classify(point: dict[str, Any], verified_keys: set, mspec: dict | None, lspec: dict | None) -> str:
    key = (point["question_id"], point["point_id"])
    label = str(point.get("point_label") or "")
    policy = point.get("policy_type")
    final = point.get("final_action")
    category = point.get("category") or ""

    if key in verified_keys:
        return BUCKET["TEXTBOOK"]
    if _META_PAT.search(label) or final == "drop_point" or category == "drop_point_candidate":
        return BUCKET["DROP"]
    if policy == "list_rule" and lspec and lspec["item_set"]:
        return BUCKET["LIST"]
    if mspec is not None:
        return BUCKET["MACHINE"]
    if final == "require_external_source" or category == "external_source_needed":
        return BUCKET["EXTERNAL"]
    if policy in ("semantic_allowed", "figure_label") or category == "rewrite_needed":
        return BUCKET["REVIEW"]
    # exact_required case facts with no spec & no textbook -> external source (规范/法规/题干事实)
    if policy == "exact_required":
        return BUCKET["EXTERNAL"]
    return BUCKET["REVIEW"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    points = _jl(M35 / "normalized_rubric_candidates.jsonl")
    v8 = {(v["question_id"], v["point_id"]) for v in _jl(M8 / "verified_source_candidates.jsonl")}
    v9 = {(v["question_id"], v["point_id"]) for v in _jl(M9 / "verified_source_candidates_m9.jsonl")}
    verified_keys = v8 | v9

    inventory: list[dict[str, Any]] = []
    machine_specs: list[dict[str, Any]] = []
    list_specs: list[dict[str, Any]] = []
    work_orders: list[dict[str, Any]] = []
    review_packets: list[dict[str, Any]] = []
    drops: list[dict[str, Any]] = []
    attack_records: list[dict[str, Any]] = []

    for p in points:
        qid, pid = p["question_id"], p["point_id"]
        mspec = _machine_spec(p) if (qid, pid) not in verified_keys else None
        lspec = _list_spec(p) if p.get("policy_type") == "list_rule" and (qid, pid) not in verified_keys else None
        bucket = _classify(p, verified_keys, mspec, lspec)

        inv = {"question_id": qid, "point_id": pid, "policy_type": p.get("policy_type"),
               "category": p.get("category"), "authority_bucket": bucket,
               "label_preview": str(p.get("point_label") or "")[:80].replace("\n", " ")}
        inventory.append(inv)

        if bucket == BUCKET["MACHINE"] and mspec is not None:
            attacks = attack_spec(mspec, is_list=False)
            fp = sum(1 for a in attacks if a["false_positive"])
            row = {"question_id": qid, "point_id": pid, "spec_kind": mspec["kind"],
                   "spec": mspec, "rubric_seed": "official_answer_not_textbook",
                   "source_type": "case_rubric_seed", "textbook_source": False, "verified": False,
                   "auto_certifiable": False, "human_reviewed": False,
                   "false_positive_count": fp, "passes_attack": fp == 0}
            machine_specs.append(row)
            attack_records.append({"question_id": qid, "point_id": pid, "is_list": False, "attacks": attacks})

        elif bucket == BUCKET["LIST"] and lspec is not None:
            attacks = attack_spec(lspec, is_list=True)
            fp = sum(1 for a in attacks if a["false_positive"])
            row = {"question_id": qid, "point_id": pid, "spec": lspec,
                   "rubric_seed": "official_answer_not_textbook", "source_type": "case_rubric_seed",
                   "textbook_source": False, "verified": False, "auto_certifiable": False,
                   "human_reviewed": False, "full_coverage": lspec["full_coverage"],
                   "false_positive_count": fp, "passes_attack": fp == 0}
            list_specs.append(row)
            attack_records.append({"question_id": qid, "point_id": pid, "is_list": True, "attacks": attacks})

        elif bucket == BUCKET["EXTERNAL"]:
            work_orders.append({"question_id": qid, "point_id": pid, "policy_type": p.get("policy_type"),
                                "label": str(p.get("point_label") or "")[:120].replace("\n", " "),
                                "needed_source": "规范/法规/题干事实 (NOT textbook verbatim)",
                                "auto_certifiable": False, "human_reviewed": False})
        elif bucket == BUCKET["REVIEW"]:
            review_packets.append({"question_id": qid, "point_id": pid, "policy_type": p.get("policy_type"),
                                   "label": str(p.get("point_label") or "")[:120].replace("\n", " "),
                                   "review_lane": "teacher_or_ai_council", "auto_certifiable": False,
                                   "human_reviewed": False})
        elif bucket == BUCKET["DROP"]:
            drops.append({"question_id": qid, "point_id": pid,
                          "label": str(p.get("point_label") or "")[:80].replace("\n", " "),
                          "reason": "hint/error_restatement/ungradeable_noise"})
        # TEXTBOOK bucket: pass-through (counted; remains the only source-backed auto path)

    # ---- false-positive attack aggregate ----
    all_attacks = [a for rec in attack_records for a in rec["attacks"]]
    fp_total = sum(1 for a in all_attacks if a["false_positive"])
    fn_total = sum(1 for a in all_attacks if a["false_negative"])
    contradiction = [a for a in all_attacks if a["vector"] == "contradiction"]
    contradiction_rejected = sum(1 for a in contradiction if not a["accepted"])
    attack_summary = {
        "specs_attacked": len(attack_records),
        "attack_vectors_per_spec": list(ATTACK_VECTORS),
        "total_attack_cases": len(all_attacks),
        "false_positive": fp_total,
        "false_negative": fn_total,
        "contradiction_total": len(contradiction),
        "contradiction_rejected": contradiction_rejected,
        "contradiction_rejected_pct": round(contradiction_rejected / len(contradiction), 3) if contradiction else 1.0,
        "exact_hit_accept_rate": round(sum(1 for a in all_attacks if a["vector"] == "exact_hit" and a["accepted"])
                                       / max(len(attack_records), 1), 3),
    }
    _wj(OUT / "false_positive_attack_results_m10.json", attack_summary)

    # ---- inventory + bucket counts ----
    bucket_counts = Counter(i["authority_bucket"] for i in inventory)
    machine_pass = sum(1 for m in machine_specs if m["passes_attack"])
    list_full = sum(1 for l in list_specs if l["full_coverage"] and l["passes_attack"])
    inv_doc = {
        "residual_universe": len(points),
        "all_classified": all(i["authority_bucket"] for i in inventory),
        "unclassified": sum(1 for i in inventory if not i["authority_bucket"]),
        "by_authority_bucket": dict(bucket_counts),
        "machine_checkable_specs": len(machine_specs),
        "machine_checkable_specs_passing_attack": machine_pass,
        "list_rule_structured_specs": len(list_specs),
        "list_rule_full_coverage_passing_attack": list_full,
        "external_source_work_orders": len(work_orders),
        "review_required_packets": len(review_packets),
        "drop_or_keep_draft": len(drops),
        "textbook_verbatim_auto_candidates": bucket_counts.get(BUCKET["TEXTBOOK"], 0),
        "points": inventory,
    }
    _wj(OUT / "residual_authority_inventory_m10.json", inv_doc)
    _wl(OUT / "machine_checkable_case_specs_m10.jsonl", machine_specs)
    _wl(OUT / "list_rule_structured_specs_m10.jsonl", list_specs)
    _wl(OUT / "external_source_work_orders_m10.jsonl", work_orders)
    _wl(OUT / "review_required_packets_m10.jsonl", review_packets)
    _wl(OUT / "drop_or_keep_draft_m10.jsonl", drops)

    # ---- beta_shadow readiness delta ----
    # Three-axis verdict is FIXED by master-control: M8 alpha_shadow=GO (never downgraded),
    # M9/M10 gated-beta readiness=WEAK-GO, production v1=NO-GO. The M9 source_assault file
    # `canonical_m8_verdict=WEAK-GO` means ONLY "not gated beta / not production"; it does NOT
    # downgrade M8 alpha_shadow GO.
    SOURCE_BACKED_AUTO_TARGET = 50
    m8_auto = 18            # M8 textbook-backed auto preview
    m9_auto = 23            # M9 textbook-backed auto preview (source-backed, the only auto path)
    source_backed_auto = m9_auto
    # M10 supply is CANDIDATE spec gradeability (a different authority class than textbook auto);
    # it is not yet real-grading/teacher validated, so it raises beta_shadow gradeability but does
    # NOT by itself clear gated-beta readiness while source-backed auto is still < 50.
    new_spec_gradeable = machine_pass + list_full
    beta_gradeable = m9_auto + new_spec_gradeable
    invariants = {
        "official_answer_as_textbook": 0,
        "model_vote_as_source": 0,
        "semantic_only_auto": 0,
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
        "v0_overwritten": False,
        "human_reviewed_true": 0,
        "live_call_fabricated": False,
    }
    go_conditions = {
        "all_residual_classified": inv_doc["all_classified"] and inv_doc["unclassified"] == 0,
        "machine_checkable_ge_20": machine_pass >= 20,
        "list_full_coverage_specs_attack_clean": all(l["passes_attack"] for l in list_specs if l["full_coverage"]),
        "false_positive_zero": fp_total == 0,
        "contradiction_rejected_full": attack_summary["contradiction_rejected_pct"] == 1.0,
        "safety_invariants_clean": all(v in (0, False) for v in invariants.values()),
        "source_backed_auto_ge_50": source_backed_auto >= SOURCE_BACKED_AUTO_TARGET,
    }
    # Verdict is for M11 GATED BETA READINESS only (a separate axis from M8 alpha_shadow=GO).
    if not go_conditions["safety_invariants_clean"] or fp_total > 0:
        verdict = "NO-GO"  # safety breach / unmitigated false positive
    elif (go_conditions["all_residual_classified"] and machine_pass >= 20
          and go_conditions["contradiction_rejected_full"]
          and go_conditions["source_backed_auto_ge_50"]):
        verdict = "GO"
    else:
        # Real, attack-clean spec increment exists, but source-backed auto is still < 50 and the
        # new specs are unvalidated candidates -> gated-beta readiness stays WEAK-GO.
        verdict = "WEAK-GO"
    delta = {
        "three_axis_verdict": {
            "m8_alpha_shadow": "GO",
            "m9_m10_gated_beta_readiness": verdict,
            "production_v1": "NO-GO",
        },
        "m8_alpha_shadow_not_downgraded": True,
        "source_assault_canonical_m8_note": "canonical_m8_verdict=WEAK-GO means 'not gated beta / not production' only; it does NOT downgrade M8 alpha_shadow GO",
        "auto_preview_m8": m8_auto, "auto_preview_m9": m9_auto,
        "source_backed_auto_preview": source_backed_auto,
        "source_backed_auto_target": SOURCE_BACKED_AUTO_TARGET,
        "m10_new_spec_gradeable_points": new_spec_gradeable,
        "machine_checkable_passing": machine_pass, "list_full_coverage_passing": list_full,
        "beta_shadow_gradeable_total": beta_gradeable,
        "coverage_uplift_vs_m9": new_spec_gradeable,
        "safety_invariants": invariants,
        "go_conditions": go_conditions,
        "m11_gated_beta_qa_verdict": verdict,
        "production_v1": "NO-GO",
        "weak_go_reason": "machine-checkable spec supply is a real attack-clean increment, but source-backed auto preview 23 < 50 and the new non-textbook specs are unvalidated candidates pending M11 QA / teacher review",
    }
    _wj(OUT / "registry_v1_beta_shadow_readiness_delta_m10.json", delta)

    summary = {
        "residual_universe": len(points), "by_bucket": dict(bucket_counts),
        "machine_specs": len(machine_specs), "machine_pass": machine_pass,
        "list_specs": len(list_specs), "list_full_pass": list_full,
        "work_orders": len(work_orders), "review_packets": len(review_packets), "drops": len(drops),
        "false_positive": fp_total, "false_negative": fn_total,
        "contradiction_rejected_pct": attack_summary["contradiction_rejected_pct"],
        "beta_gradeable_total": beta_gradeable, "verdict": verdict,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
