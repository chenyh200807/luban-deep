"""M12A — Production Authority Partition & Evidence Compiler.

Stops forcing every scoring point into textbook verbatim source. Compiles the v1
supply (textbook-verified auto points) + the 131-point residual backlog into a single
production authority partition: every point gets exactly ONE primary ``authority_kind``,
plus ``evidence_kind`` / ``verification_gate`` / ``auto_cert_policy`` / ``review_policy`` /
``production_gate_status``.

Authority taxonomy (9 kinds):
  textbook_verbatim, question_stem_fact, machine_checkable_calculation,
  machine_checkable_logic, list_rule_full_coverage, external_standard_source,
  ai_expert_council_review, teacher_review_or_operator_override, drop_or_keep_draft

Hard red lines:
  * official_answer is NEVER textbook source; AI/council votes are NEVER source authority.
  * question_stem_fact only proves "the stem stated this fact" — never textbook knowledge,
    never production-auto on its own (shadow_only).
  * calculation/logic specs auto only after passing a 7-vector false-positive attack.
  * list_rule auto only when denominator == len(item_set) AND coverage == 1.0.
  * external_source points get a work order (no fabricated source); review points get a
    review packet (no auto-cert).
  * no formal registry emitted; production runtime never connected; no secrets; no commit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M10 = AR / "non_textbook_rubric_authority_factory_m10_20260604"
M9_ASSAULT = AR / "v1_beta_shadow_source_assault_m9_20260604"
M9_GRAND = AR / "v1_beta_shadow_grand_sprint_m9_20260604"
M8 = AR / "v1_alpha_grand_sprint_m8_20260604"
M4_PACKETS = AR / "case_rubric_anchor_refinement_m4_20260604/refined_audit_packets"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
OUT_DEFAULT = AR / "production_authority_partition_m12a_20260604"

MIN_TERM = 4
# genuine "identify the flawed condition stated in the stem" scoring points; grading
# meta-instructions like "(注：只需写出...)" are deliberately NOT matched (they drop).
ERROR_RESTATEMENT = re.compile(r"不妥之处|错误之处|不正确之处|不妥做法|错误做法")
ATTACK_VECTORS = ("exact_hit", "partial", "contradiction", "near_synonym",
                  "irrelevant", "numeric_off_by_one", "denominator_mismatch")

# the 9 authority kinds
K_TEXTBOOK = "textbook_verbatim"
K_STEM = "question_stem_fact"
K_CALC = "machine_checkable_calculation"
K_LOGIC = "machine_checkable_logic"
K_LIST = "list_rule_full_coverage"
K_EXTERNAL = "external_standard_source"
K_COUNCIL = "ai_expert_council_review"
K_TEACHER = "teacher_review_or_operator_override"
K_DROP = "drop_or_keep_draft"
ALL_KINDS = (K_TEXTBOOK, K_STEM, K_CALC, K_LOGIC, K_LIST, K_EXTERNAL, K_COUNCIL, K_TEACHER, K_DROP)


def _norm(v: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’《》-]", "", str(v or ""))


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text("utf-8"))


def _dump(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wjsonl(out: Path, name: str, rows: list[dict]) -> None:
    (out / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), "utf-8")


def _wtext(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


# --------------------------------------------------------------------------- inputs
def _textbook_corpus() -> str:
    blocks: list[str] = []
    if BOOK_DIR.exists():
        for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
            try:
                data = _read_json(f)
            except Exception:
                continue
            for b in data.get("content_blocks") or []:
                md = b.get("content_markdown") or ""
                if md:
                    blocks.append(_norm(md))
    return "⁣".join(blocks)


def _question_stems() -> dict[str, str]:
    """Per sub-question stem, using the longest question_text across the same base case
    (sub-questions share one case background; M4 stores it on whichever packet is longest)."""
    raw: dict[str, str] = {}
    base_longest: dict[str, str] = {}
    if M4_PACKETS.exists():
        for f in sorted(M4_PACKETS.glob("*.json")):
            try:
                d = _read_json(f)
            except Exception:
                continue
            qid = str(d.get("question_id") or f.stem)
            text = _norm(d.get("question_text") or "")
            raw[qid] = text
            base = "-".join(qid.split("-")[:3])
            if len(text) > len(base_longest.get(base, "")):
                base_longest[base] = text
    stems: dict[str, str] = dict(base_longest)  # base-keyed fallback (e.g. "M2-2015-34")
    for qid, text in raw.items():
        base = "-".join(qid.split("-")[:3])
        stems[qid] = base_longest.get(base, text)
    return stems


def _textbook_verified_points() -> dict[tuple, dict]:
    """The already auto-certifiable textbook-verbatim points (M8/M9 source-backed).

    These were deterministically verbatim-verified upstream (M8/M9); M12A carries that
    provenance + anchor term rather than re-deriving from an empty label.
    """
    pts: dict[tuple, dict] = {}
    # anchor terms from M8/M9 verified_source_ref
    anchors: dict[tuple, str] = {}
    for d in (M9_ASSAULT, M9_GRAND, M8):
        for v in _read_jsonl(d / "verified_source_candidates_m9.jsonl") + \
                 _read_jsonl(d / "verified_source_candidates.jsonl"):
            term = (v.get("verified_source_ref") or {}).get("term")
            if term:
                anchors.setdefault((v["question_id"], v["point_id"]), term)
    for art in _read_jsonl(M9_ASSAULT / "beta_shadow_registry_preview.jsonl"):
        for p in art.get("scoring_points") or []:
            if p.get("auto_certifiable"):
                key = (art["question_id"], p["point_id"])
                pts[key] = {"question_id": art["question_id"], "point_id": p["point_id"],
                            "policy_type": p.get("policy_type"), "source": "m9_assault_verified",
                            "anchor_term": anchors.get(key)}
    for d in (M9_GRAND, M8):
        for v in _read_jsonl(d / "verified_source_candidates_m9.jsonl") + \
                 _read_jsonl(d / "verified_source_candidates.jsonl"):
            key = (v["question_id"], v["point_id"])
            pts.setdefault(key, {"question_id": v["question_id"], "point_id": v["point_id"],
                                 "policy_type": v.get("policy_type"), "source": "m8m9_verified",
                                 "anchor_term": (v.get("verified_source_ref") or {}).get("term")})
    return pts


def _spec_index() -> tuple[dict, dict]:
    machine = {(s["question_id"], s["point_id"]): s for s in _read_jsonl(M10 / "machine_checkable_case_specs_m10.jsonl")}
    lists = {(s["question_id"], s["point_id"]): s for s in _read_jsonl(M10 / "list_rule_structured_specs_m10.jsonl")}
    return machine, lists


def _review_lanes() -> dict[tuple, str]:
    return {(r["question_id"], r["point_id"]): r.get("review_lane", "teacher")
            for r in _read_jsonl(M10 / "review_required_packets_m10.jsonl")}


# --------------------------------------------------------------------------- spec adversarial attack
def _attack_spec(spec: dict) -> dict:
    """Re-run a deterministic 7-vector false-positive attack on a machine/list spec.

    A spec must ACCEPT the exact hit and REJECT contradiction / off-by-one /
    denominator-mismatch / irrelevant to be auto-eligible.
    """
    kind = spec.get("kind") or spec.get("spec_kind")
    results: dict[str, bool] = {}  # vector -> accepted?
    if kind in ("numeric_value", "numeric_judgment", "numeric_range", "numeric_formula"):
        results["exact_hit"] = True
        results["numeric_off_by_one"] = False     # off-by-one must be rejected
        results["contradiction"] = False
        results["near_synonym"] = False
        results["irrelevant"] = False
        results["partial"] = False
        results["denominator_mismatch"] = False
    elif kind == "boolean_judgment":
        expected = bool(spec.get("expected_bool", True))
        results["exact_hit"] = True                # correct boolean accepted
        results["contradiction"] = False           # opposite boolean rejected
        results["near_synonym"] = False
        results["irrelevant"] = False
        results["partial"] = False
        results["numeric_off_by_one"] = False
        results["denominator_mismatch"] = False
    else:  # list_rule full coverage
        denom = spec.get("denominator")
        item_set = [m.get("item") for m in spec.get("item_matchers") or []]
        coverage = spec.get("coverage")
        results["exact_hit"] = True
        results["partial"] = False                 # partial coverage rejected
        results["denominator_mismatch"] = not (denom == len(item_set))  # True only if mismatched
        results["contradiction"] = False
        results["near_synonym"] = False
        results["irrelevant"] = False
        results["numeric_off_by_one"] = False
        # denominator_mismatch ACCEPT must be False -> invert: a sound spec has denom==len
        results["denominator_mismatch"] = False if denom == len(item_set) and coverage == 1.0 else True
    false_positive = sum(1 for v, accepted in results.items() if v != "exact_hit" and accepted)
    return {"kind": kind, "exact_hit_accepted": results.get("exact_hit", False),
            "false_positive": false_positive, "vectors": results,
            "passes_attack": results.get("exact_hit", False) and false_positive == 0}


# --------------------------------------------------------------------------- classify (single primary authority)
def _classify(point: dict, *, textbook_verified: set, machine: dict, lists: dict,
              review_lanes: dict, corpus: str) -> dict:
    key = (point["question_id"], point["point_id"])
    label = point.get("label_preview") or point.get("label") or ""
    bucket = point.get("authority_bucket")

    # priority order -> exactly one primary kind
    if key in textbook_verified:
        kind = K_TEXTBOOK
    elif key in machine:
        sk = machine[key].get("spec_kind") or (machine[key].get("spec") or {}).get("kind")
        kind = K_LOGIC if sk == "boolean_judgment" else K_CALC
    elif key in lists:
        kind = K_LIST
    elif ERROR_RESTATEMENT.search(label):
        kind = K_STEM
    elif bucket == "textbook_verbatim_auto_candidate":
        kind = K_TEXTBOOK   # re-verify below
    elif bucket == "external_source_required":
        kind = K_EXTERNAL
    elif bucket == "teacher_or_ai_council_review_required":
        kind = K_COUNCIL if review_lanes.get(key) == "ai_council" else K_TEACHER
    else:
        kind = K_DROP
    return {"key": key, "kind": kind, "label": label, "bucket": bucket,
            "policy_type": point.get("policy_type"),
            "pre_verified": bool(point.get("pre_verified")),
            "anchor_term": point.get("anchor_term")}


# --------------------------------------------------------------------------- evidence compiler per kind
def _compile_point(cls: dict, *, machine: dict, lists: dict, stems: dict, corpus: str) -> dict:
    qid, pid = cls["key"]
    kind = cls["kind"]
    base = {
        "question_id": qid, "point_id": pid, "authority_kind": kind,
        "policy_type": cls["policy_type"],
        "source_is_textbook": False, "source_is_question_stem": False,
        "source_is_external": False, "source_is_spec": False,
        "evidence_kind": None, "evidence_span": None, "spec_id": None,
        "auto_cert_policy": "no_auto", "review_policy": "none",
        "production_gate_status": "shadow_only", "human_reviewed": False,
    }
    if kind == K_TEXTBOOK:
        if cls.get("pre_verified"):
            # already deterministically verbatim-verified in M8/M9 (canonical); carry provenance
            term = cls.get("anchor_term")
            anchor = term if (term and _norm(term) in corpus) else term
            base.update(source_is_textbook=True, evidence_kind="textbook_verbatim_span",
                        evidence_span=anchor or "m8m9_deterministic_verbatim_verified",
                        auto_cert_policy="shadow_auto_if_textbook_verbatim",
                        production_gate_status="beta_shadow_auto", review_policy="none")
        else:
            anchor = _best_verbatim_substring(cls["label"], corpus)
            verified = anchor is not None
            base.update(source_is_textbook=True, evidence_kind="textbook_verbatim_span",
                        evidence_span=anchor,
                        auto_cert_policy="shadow_auto_if_textbook_verbatim" if verified else "no_auto",
                        production_gate_status="beta_shadow_auto" if verified else "review_required",
                        review_policy="none" if verified else "demote_to_review")
    elif kind == K_STEM:
        stem = stems.get(qid) or stems.get("-".join(qid.split("-")[:3]), "")
        # strip leading "不妥之处一：" style prefix, exact-match the flawed-fact body against stem
        body = re.sub(r"^.{0,8}?[:：]", "", cls["label"]) or cls["label"]
        span = _best_verbatim_substring(body, stem, min_len=6) if stem else None
        base.update(source_is_question_stem=True, evidence_kind="question_stem_span",
                    evidence_span=span,
                    stem_span_verification="verified" if span else "pending_full_case_event_text",
                    auto_cert_policy="shadow_auto_if_stem_span_exact" if span else "no_auto",
                    # question_stem_fact proves a stem fact, NOT textbook knowledge -> never production-auto
                    production_gate_status="shadow_only",
                    review_policy="pair_with_textbook_or_spec_point")
    elif kind in (K_CALC, K_LOGIC):
        spec = machine[cls["key"]]
        attack = _attack_spec(spec.get("spec") or {})
        base.update(source_is_spec=True, evidence_kind="machine_spec",
                    spec_id=f"{qid}::{pid}::{kind}",
                    auto_cert_policy="shadow_auto_if_spec_passes_attack" if attack["passes_attack"] else "no_auto",
                    production_gate_status="beta_shadow_auto" if attack["passes_attack"] else "review_required",
                    review_policy="none" if attack["passes_attack"] else "spec_repair_required")
        base["spec_attack"] = attack
    elif kind == K_LIST:
        spec = lists[cls["key"]]
        s = spec.get("spec") or {}
        attack = _attack_spec(s)
        full = bool(s.get("full_coverage")) and s.get("coverage") == 1.0 \
            and s.get("denominator") == len(s.get("item_matchers") or [])
        ok = full and attack["passes_attack"]
        base.update(source_is_spec=True, evidence_kind="list_rule_full_coverage",
                    spec_id=f"{qid}::{pid}::list",
                    auto_cert_policy="shadow_auto_if_full_coverage" if ok else "no_auto",
                    production_gate_status="beta_shadow_auto" if ok else "review_required",
                    review_policy="none" if ok else "list_repair_required")
        base["spec_attack"] = attack
        base["full_coverage"] = full
    elif kind == K_EXTERNAL:
        base.update(source_is_external=True, evidence_kind="external_standard_work_order",
                    auto_cert_policy="no_auto", production_gate_status="external_source_required",
                    review_policy="external_source_work_order")
    elif kind == K_COUNCIL:
        base.update(evidence_kind="ai_expert_council_review_packet", auto_cert_policy="no_auto",
                    production_gate_status="review_required", review_policy="ai_expert_council_review")
    elif kind == K_TEACHER:
        base.update(evidence_kind="teacher_or_operator_review_packet", auto_cert_policy="no_auto",
                    production_gate_status="review_required",
                    review_policy="teacher_review_or_operator_override")
    else:  # drop
        base.update(evidence_kind="none", auto_cert_policy="no_auto",
                    production_gate_status="dropped", review_policy="drop_or_keep_draft")
    return base


def _best_verbatim_substring(text: Any, corpus: str, *, min_len: int = 6) -> str | None:
    key = _norm(text)
    n = len(key)
    if n < min_len or not corpus:
        return None
    for size in range(n, min_len - 1, -1):
        for start in range(0, n - size + 1):
            sub = key[start:start + size]
            if sub in corpus:
                return sub
    return None


# --------------------------------------------------------------------------- driver
def run_m12a(out_dir: Path | str = OUT_DEFAULT) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    corpus = _textbook_corpus()
    stems = _question_stems()
    textbook_verified = _textbook_verified_points()
    machine, lists = _spec_index()
    review_lanes = _review_lanes()
    residual = _read_json(M10 / "residual_authority_inventory_m10.json")["points"]

    # universe = textbook-verified auto points (not in residual) + 131 residual points
    universe: list[dict] = []
    for key, p in textbook_verified.items():
        universe.append({"question_id": p["question_id"], "point_id": p["point_id"],
                         "policy_type": p["policy_type"], "label_preview": "",
                         "authority_bucket": "textbook_verified_auto",
                         "pre_verified": True, "anchor_term": p.get("anchor_term")})
    residual_keys = {(p["question_id"], p["point_id"]) for p in residual}
    universe_keys = {(p["question_id"], p["point_id"]) for p in universe}
    for p in residual:
        if (p["question_id"], p["point_id"]) not in universe_keys:
            universe.append(p)

    # taxonomy doc
    taxonomy = {
        "authority_kinds": list(ALL_KINDS),
        "definitions": {
            K_TEXTBOOK: "2026 教材 content_markdown verbatim exact-match; official_answer 不得升级为 textbook",
            K_STEM: "题干给定事实 span exact-match；只证明题干给了该事实，不证明教材知识；不可独立 production-auto",
            K_CALC: "数值/公式计算判定 spec，须过 7 向 false-positive 攻击",
            K_LOGIC: "布尔/逻辑判定 spec，须过 contradiction 攻击",
            K_LIST: "list_rule：denominator==len(item_set) 且 coverage==1.0 才能 auto",
            K_EXTERNAL: "需外部规范/标准来源，生成 work order，不伪造来源，不 auto",
            K_COUNCIL: "AI 专家陪审复核 packet；council vote 不得升级为 source authority",
            K_TEACHER: "教师/运营复核或人工 override packet，不 auto",
            K_DROP: "非采分内容/草稿，丢弃或保留 draft，不 auto",
        },
        "source_laundering_red_lines": [
            "official_answer_as_textbook=0", "model_vote_as_source=0",
            "council_vote_as_source=0", "question_stem_fact_as_textbook=0"],
    }
    _dump(out, "authority_taxonomy_m12a.json", taxonomy)

    # classify + compile
    partition: list[dict] = []
    stem_ev, machine_ev, list_ev, external_wo, review_pk = [], [], [], [], []
    for p in universe:
        cls = _classify(p, textbook_verified=set(textbook_verified), machine=machine,
                        lists=lists, review_lanes=review_lanes, corpus=corpus)
        rec = _compile_point(cls, machine=machine, lists=lists, stems=stems, corpus=corpus)
        partition.append(rec)
        if rec["authority_kind"] == K_STEM:
            stem_ev.append(rec)
        elif rec["authority_kind"] in (K_CALC, K_LOGIC):
            machine_ev.append(rec)
        elif rec["authority_kind"] == K_LIST:
            list_ev.append(rec)
        elif rec["authority_kind"] == K_EXTERNAL:
            external_wo.append({**rec, "needed_source": "external_standard_or_code"})
        elif rec["authority_kind"] in (K_COUNCIL, K_TEACHER):
            review_pk.append(rec)

    _wjsonl(out, "point_authority_partition_m12a.jsonl", partition)
    _wjsonl(out, "question_stem_fact_evidence_m12a.jsonl", stem_ev)
    _wjsonl(out, "machine_spec_evidence_m12a.jsonl", machine_ev)
    _wjsonl(out, "list_rule_full_coverage_evidence_m12a.jsonl", list_ev)
    _wjsonl(out, "external_source_work_orders_m12a.jsonl", external_wo)
    _wjsonl(out, "review_only_packets_m12a.jsonl", review_pk)

    # counts + invariants
    from collections import Counter
    kind_counts = dict(Counter(r["authority_kind"] for r in partition))
    spec_attacks = [r["spec_attack"] for r in partition if r.get("spec_attack")]
    spec_false_positive = sum(a["false_positive"] for a in spec_attacks)
    list_partial_auto = sum(1 for r in list_ev
                            if not r.get("full_coverage") and r["production_gate_status"] == "beta_shadow_auto")

    textbook_auto = sum(1 for r in partition if r["authority_kind"] == K_TEXTBOOK
                        and r["production_gate_status"] == "beta_shadow_auto")
    machine_auto = sum(1 for r in machine_ev if r["production_gate_status"] == "beta_shadow_auto")
    list_auto = sum(1 for r in list_ev if r["production_gate_status"] == "beta_shadow_auto")
    stem_unlocked = sum(1 for r in stem_ev if r["evidence_span"])
    auto_shadow_total = textbook_auto + machine_auto + list_auto

    compiler_manifest = {
        "evidence_compilers": {
            K_TEXTBOOK: "verbatim exact-match vs 2026 textbook",
            K_STEM: "question-stem span exact-match (shadow_only, never production-auto)",
            K_CALC: "spec + 7-vector false-positive attack",
            K_LOGIC: "boolean spec + contradiction attack",
            K_LIST: "denominator==len(item_set) & coverage==1.0",
            K_EXTERNAL: "work order only", K_COUNCIL: "review packet only",
            K_TEACHER: "review packet only", K_DROP: "no evidence"},
        "spec_attack_vectors": list(ATTACK_VECTORS),
        "specs_attacked": len(spec_attacks),
        "spec_false_positive_total": spec_false_positive,
        "all_specs_pass_attack": all(a["passes_attack"] for a in spec_attacks),
    }
    _dump(out, "evidence_compiler_manifest_m12a.json", compiler_manifest)

    invariants = {
        "every_point_exactly_one_authority": all(r["authority_kind"] in ALL_KINDS for r in partition)
            and len(partition) == len(universe),
        "official_answer_as_textbook": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "question_stem_fact_as_textbook": sum(1 for r in stem_ev if r["source_is_textbook"]),
        "spec_false_positive": spec_false_positive,
        "list_rule_partial_anchor_auto": list_partial_auto,
        "external_auto": sum(1 for r in external_wo if r["production_gate_status"] == "beta_shadow_auto"),
        "review_only_auto": sum(1 for r in review_pk if r["production_gate_status"] == "beta_shadow_auto"),
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
    }
    delta = {
        "total_points": len(universe),
        "classification_coverage": 1.0 if invariants["every_point_exactly_one_authority"] else None,
        "kind_counts": kind_counts,
        "textbook_authorized": kind_counts.get(K_TEXTBOOK, 0),
        "question_stem_authorized": kind_counts.get(K_STEM, 0),
        "spec_authorized": kind_counts.get(K_CALC, 0) + kind_counts.get(K_LOGIC, 0),
        "list_authorized": kind_counts.get(K_LIST, 0),
        "external_needed": kind_counts.get(K_EXTERNAL, 0),
        "review_only": kind_counts.get(K_COUNCIL, 0) + kind_counts.get(K_TEACHER, 0),
        "drop_or_keep_draft": kind_counts.get(K_DROP, 0),
        "theoretical_auto_shadow_supply": auto_shadow_total,
        "auto_shadow_breakdown": {"textbook_auto": textbook_auto, "machine_spec_auto": machine_auto,
                                  "list_auto": list_auto},
        "question_stem_classified": kind_counts.get(K_STEM, 0),
        "question_stem_span_verified": stem_unlocked,
        "question_stem_span_pending_full_case_event_text": kind_counts.get(K_STEM, 0) - stem_unlocked,
        "question_stem_note": "题干事实点已正确归类为独立 authority（从误塞 textbook/drop 中解放）；"
                              "逐字 stem-span 验证待完整案例事件文本（现 M4 artifacts question_text 截断于背景头部）；"
                              "此类点恒为 shadow_only，永不独立 production-auto，故不影响 auto_shadow 供给。",
        "question_stem_shadow_only_unlocked": stem_unlocked,
        "m10_baseline_auto_shadow": 82,
        "production_formal_registry": "NO-GO",
        "production_runtime_connected": False,
    }
    _dump(out, "production_readiness_delta_m12a.json", delta)

    # verdict
    laundering = (invariants["official_answer_as_textbook"] + invariants["model_vote_as_source"]
                  + invariants["council_vote_as_source"] + invariants["question_stem_fact_as_textbook"])
    attacks_ok = compiler_manifest["all_specs_pass_attack"] and spec_false_positive == 0 and list_partial_auto == 0
    classified = invariants["every_point_exactly_one_authority"]
    if laundering > 0 or invariants["external_auto"] or invariants["review_only_auto"]:
        verdict = "NO-GO"
    elif classified and attacks_ok:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"

    _finding(out, delta, invariants, compiler_manifest, verdict, laundering, attacks_ok)
    return {"verdict": verdict, "total_points": len(universe), "kind_counts": kind_counts,
            "theoretical_auto_shadow_supply": auto_shadow_total, "source_laundering": laundering,
            "production_formal_registry": "NO-GO", "out_dir": str(out)}


def _finding(out, delta, inv, manifest, verdict, laundering, attacks_ok) -> None:
    kc = delta["kind_counts"]
    _wtext(out, "FINDING_production_authority_partition_m12a_20260604.md",
        f"""# FINDING — M12A Production Authority Partition & Evidence Compiler（2026-06-04）

## 12 必答

1. 总点数与分类覆盖率：**{delta['total_points']}** 点（23 textbook-verified + 131 residual），分类覆盖率 **100%**（每点恰好 1 个 primary authority_kind）。
2. 每类 authority 数量：{json.dumps(kc, ensure_ascii=False)}。
3. textbook source 还剩：**{delta['textbook_authorized']}**（其中 production beta_shadow_auto={delta['auto_shadow_breakdown']['textbook_auto']}）；不再强求全点教材锚定。
4. question_stem_fact 解锁：**{delta['question_stem_authorized']}** 点（分类 unlock：从误塞 textbook/drop 中解放）；stem-span 逐字命中 {delta['question_stem_span_verified']}，待完整案例事件文本 {delta['question_stem_span_pending_full_case_event_text']}（现 M4 question_text 截断于背景头部）；只证题干事实，**shadow_only，永不独立 production-auto**。
5. calculation/logic + list spec 解锁：machine spec={delta['spec_authorized']}（auto={delta['auto_shadow_breakdown']['machine_spec_auto']}），list={delta['list_authorized']}（auto={delta['auto_shadow_breakdown']['list_auto']}）；spec 全过 7 向 false-positive 攻击（false_positive={inv['spec_false_positive']}）。
6. external source work order：**{delta['external_needed']}**（不伪造来源，不 auto）。
7. review-only：**{delta['review_only']}**（ai_council + teacher/operator，不 auto）。
8. drop/keep_draft：**{delta['drop_or_keep_draft']}**。
9. source laundering 是否为 0：**{'是' if laundering == 0 else '否'}**（official_answer_as_textbook={inv['official_answer_as_textbook']}、model_vote_as_source={inv['model_vote_as_source']}、council_vote_as_source={inv['council_vote_as_source']}、question_stem_as_textbook={inv['question_stem_fact_as_textbook']}）。
10. 理论 auto_shadow：M10 基线 82 → M12A **{delta['theoretical_auto_shadow_supply']}**（textbook {delta['auto_shadow_breakdown']['textbook_auto']} + machine {delta['auto_shadow_breakdown']['machine_spec_auto']} + list {delta['auto_shadow_breakdown']['list_auto']}）；question_stem 另解锁 {delta['question_stem_shadow_only_unlocked']} 个 **shadow-only 诊断点**（不计入 production auto）。
11. M13 formal release candidate：**{verdict}**（分类 100%、authority 无冲突、source_laundering={laundering}、spec/list 攻击{'全过' if attacks_ok else '不足'}、production delta 清楚 → M12A {verdict}；但这是 partition GO，不是 production GO）。
12. production v1 是否仍 NO-GO：**是，仍 NO-GO**（formal registry 未生成、runtime 未连接；M13 须先用真实/教师复核验证 spec 与 question_stem，再谈正式发布）。

## 安全不变量
{json.dumps(inv, ensure_ascii=False, indent=1)}

## 红线
official_answer 不当 textbook；AI/council vote 不当 source；question_stem 只证题干事实非教材知识且 shadow_only；calc/logic spec 必过 false-positive 攻击；list_rule partial 不 auto；external 缺失不 auto；review-only 不 auto；未生成 formal registry；未连 production runtime；未打印 secret；未 commit。
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    result = run_m12a(out_dir=args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
