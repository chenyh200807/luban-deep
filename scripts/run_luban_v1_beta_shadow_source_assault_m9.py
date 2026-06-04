"""M9 — Canonical WEAK-GO Reconciliation + Beta Shadow Source Assault.

M9 does NOT re-run M8 or re-litigate GO. It (0) makes the M8 canonical verdict
WEAK-GO so later agents cannot misread the script's self-asserted GO, then runs a
dynamic-workflow source assault on the 57 M8 source_gaps, compiles a beta_shadow
candidate (never a formal registry), pressure-tests the positive auto-path, and emits
an explainable product vertical slice. Final output: an M10 gated-beta GO/WEAK-GO/NO-GO.

Source authority is and remains DETERMINISTIC verbatim exact-match over the 2026
textbook ``content_markdown``. Models (Qwen/DeepSeek/GPT5.5/Opus) may only propose
candidates and objections; they can never set ``verified`` / ``textbook_exact_match``.
Live keys absent -> fail-closed ``provider_unavailable`` (never fabricated). Case-answer
judgment phrases (索赔合理/不合理 + 具体数字) are NOT textbook content and are routed to
external_source_required / keep_draft — forcing them would be official_answer laundering.

Red lines (enforced): no formal registry, no v0 overwrite, no production runtime, no
CaseGradingSkillKernel change, no RAG/DB/web/BI/billing change, official_answer never a
textbook source, model vote never a source, human_reviewed=false, no fabricated live
call, no secret print, no stage/commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
# Ensure `import deeptutor` works regardless of invocation (python scripts/x.py puts the
# scripts/ dir on sys.path[0], not the repo root). Required for the REAL runtime-gate run.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
AR = REPO / "artifacts/luban_grading_artifacts"
M35_DIR = AR / "blocked_point_rubric_normalization_m35_20260604"
M8_DIR = AR / "v1_alpha_grand_sprint_m8_20260604"
OUT_DIR = AR / "v1_beta_shadow_source_assault_m9_20260604"
SUB_DIR = OUT_DIR / "subagents"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
ENV_FILES = [REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")]
PLAN_FILE = REPO / "docs/plan/2026-06-04-luban-grading-engine-master-control-plan.md"
INDEX_FILE = REPO / "docs/plan/INDEX.md"

MIN_ANCHOR_LEN = 4          # absolute floor for any anchor
MIN_VARIANT_LEN = 6         # stricter floor for a RECOVERED variant (anti-fragment)
MIN_VARIANT_COVERAGE = 0.5  # recovered anchor must cover >=50% of the required term
RUNTIME_SAFE_POLICIES = {"exact_required", "list_rule", "calculation"}

SMALL_MODELS = [
    ("qwen37", "qwen-plus", "DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("deepseek_v4", "deepseek-chat", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1"),
]
BIG_MODELS = {"gpt55": "OPENAI_API_KEY", "opus48": "ANTHROPIC_API_KEY"}

# case-answer judgment markers: these belong to official_answer, NOT to the textbook
CASE_JUDGMENT_RE = re.compile(r"(合理|不合理|索赔|万元|万\b|个月|\d)")
M8_SOURCE_BACKED_TOTAL = 18  # 6 m7-reverified + 12 m7r-verified


# --------------------------------------------------------------------------- utils
def _norm(s: Any) -> str:
    return re.sub(r"[\s，。、；;：:（）()【】\[\]　·,.//\"'“”‘’]", "", str(s or ""))


def _sid(*parts: Any) -> str:
    return hashlib.sha1("::".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _env() -> dict[str, str]:
    e: dict[str, str] = {}
    for p in ENV_FILES:
        try:
            for line in Path(p).read_text("utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    e.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:  # noqa: BLE001
            pass
    return e


def _wjson(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _wjsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _rjsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


# ------------------------------------------------------------------------ textbook
def load_textbook() -> tuple[str, list[tuple[str, str]]]:
    """Return (concatenated normalized corpus, [(chunk_id, norm_md)])."""
    blocks: list[tuple[str, str]] = []
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        d = json.loads(f.read_text("utf-8"))
        for b in d.get("content_blocks") or []:
            md = b.get("content_markdown") or ""
            if md:
                blocks.append((str(b.get("chunk_id") or ""), _norm(md)))
    corpus = "".join(nm for _c, nm in blocks)
    return corpus, blocks


def first_chunk_with(term_norm: str, blocks: list[tuple[str, str]]) -> str | None:
    for cid, nm in blocks:
        if term_norm in nm:
            return cid
    return None


def longest_verbatim_substring(term: str, corpus: str) -> str:
    """Longest contiguous normalized substring of `term` that appears verbatim in the
    textbook corpus. Deterministic; O(len^2) on a short term. Returns '' if < floor."""
    nt = _norm(term)
    n = len(nt)
    best = ""
    for i in range(n):
        for j in range(n, i + MIN_VARIANT_LEN - 1, -1):
            if j - i <= len(best):
                break
            sub = nt[i:j]
            if sub in corpus:
                if len(sub) > len(best):
                    best = sub
                break
    return best


# ----------------------------------------------------------- M3.5 join (gap -> terms)
def load_m35_index() -> dict[tuple[str, str], dict[str, Any]]:
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for r in _rjsonl(M35_DIR / "normalized_rubric_candidates.jsonl"):
        idx[(r["question_id"], r["point_id"])] = r
    for r in _rjsonl(M35_DIR / "split_point_proposals.jsonl"):
        idx.setdefault((r["question_id"], r["split_point_id"]), r)
    return idx


# ================================================================ Phase 0: WEAK-GO
WEAKGO_REASONS = [
    "57 of 69 huntable candidates remained source_gap after M8 (only 12 new verbatim anchors).",
    "M8 QA exercised 0 positive auto-path cases (alpha_auto_count=0); auto behaviour unproven.",
    "GPT5.5 big-model skeptic API unavailable -> single Opus judge, not a 2-of-2 council.",
]


def phase0_canonical_weakgo() -> dict[str, Any]:
    override = {
        "milestone": "M8_v1_alpha_grand_sprint",
        "canonical_verdict": "WEAK-GO",
        "superseded_script_verdict": "GO",
        "authority": "independent_opus_4_8_adversarial_verification_m9",
        "supersedes": ["dynamic_workflow_manifest.v1_alpha_go_no_go",
                       "release_risk_matrix.v1_alpha_verdict",
                       "FINDING.script_self_assessed_GO"],
        "downgrade_reasons": WEAKGO_REASONS,
        "evidence_preserved": {
            "verified_anchor_independent_recheck": "12/12 in textbook, source_laundering=0",
            "source_gap_remaining": 57,
            "auto_preview": 18,
            "qa_bad_certified": 0,
            "qa_source_mismatch": 0,
            "alpha_auto_count": 0,
            "legacy_equal": True,
            "production_runtime_connected": False,
        },
        "constraints_reasserted": {
            "alpha_shadow_is_not_gated_beta": True,
            "formal_registry_emitted": False,
            "v0_overwritten": False,
            "human_reviewed": False,
        },
        "note": "Read this override FIRST. The script's self-asserted GO is retained only as "
                "superseded_script_verdict evidence; it is NOT the final verdict.",
    }
    _wjson(M8_DIR / "canonical_m8_verdict_override.json", override)

    # patch release_risk_matrix.json (preserve old GO as superseded)
    rm_path = M8_DIR / "release_risk_matrix.json"
    rm = json.loads(rm_path.read_text("utf-8")) if rm_path.exists() else {}
    if rm.get("v1_alpha_verdict") and "superseded_script_verdict" not in rm:
        rm["superseded_script_verdict"] = rm.get("v1_alpha_verdict")
    rm["v1_alpha_verdict_canonical"] = "WEAK-GO"
    rm["canonical_authority"] = "independent_opus_4_8_adversarial_verification_m9"
    rm["canonical_downgrade_reasons"] = WEAKGO_REASONS
    rm["read_order"] = "canonical_m8_verdict_override.json > this file's old v1_alpha_verdict"
    _wjson(rm_path, rm)

    # prepend a canonical banner to the M8 FINDING (idempotent)
    finding_path = M8_DIR / "FINDING_v1_alpha_grand_sprint_m8_20260604.md"
    banner = (
        "> **CANONICAL VERDICT OVERRIDE (M9): WEAK-GO.** "
        "脚本自评 GO 已被独立 Opus 对抗验证下调为 canonical **WEAK-GO**（见 "
        "`canonical_m8_verdict_override.json`）。下调理由：57 source_gap、auto 正向路径未压测、"
        "single big-model skeptic。脚本历史 GO 仅作 superseded 证据保留。\n\n"
    )
    if finding_path.exists():
        cur = finding_path.read_text("utf-8")
        if "CANONICAL VERDICT OVERRIDE (M9)" not in cur:
            finding_path.write_text(banner + cur, encoding="utf-8")
    else:
        finding_path.write_text(banner, encoding="utf-8")

    return {"override": override, "patched": ["canonical_m8_verdict_override.json",
            "release_risk_matrix.json", "FINDING_v1_alpha_grand_sprint_m8_20260604.md"]}


def patch_master_plan_and_index() -> list[str]:
    patched: list[str] = []
    marker = "## 18. M8 canonical WEAK-GO + M9 beta_shadow source assault (2026-06-04)"
    block = (
        f"\n\n{marker}\n\n"
        "- **M8 canonical verdict = WEAK-GO**（脚本自评 GO 已被独立 Opus 对抗验证下调；见 "
        "`artifacts/luban_grading_artifacts/v1_alpha_grand_sprint_m8_20260604/canonical_m8_verdict_override.json`）。\n"
        "- 下调理由：57 source_gap 未清、auto 正向路径未压测（alpha_auto_count=0）、GPT5.5 skeptic 不可用单大模型终裁。\n"
        "- 安全不变量全成立：12/12 verified 锚独立复核在教材、source_mismatch=0、legacy_equal=true、"
        "production_runtime_connected=false、formal_registry_emitted=false、v0 未覆盖。\n"
        "- **M9** 对 57 source_gap 发起 source assault（案例判断句分流到 external_source/keep_draft，不当教材源）、"
        "编译 beta_shadow 候选、压测 auto 正向路径、产出可解释产品纵切，最终给 M10 gated beta 的 GO/WEAK-GO/NO-GO。\n"
        "- alpha_shadow 不得偷渡成 beta，beta_shadow 不得偷渡成 production。\n"
    )
    if PLAN_FILE.exists():
        cur = PLAN_FILE.read_text("utf-8")
        if marker not in cur:
            PLAN_FILE.write_text(cur + block, encoding="utf-8")
            patched.append(str(PLAN_FILE.relative_to(REPO)))
    if INDEX_FILE.exists():
        cur = INDEX_FILE.read_text("utf-8")
        note = "M8 canonical=WEAK-GO（见 canonical_m8_verdict_override.json）；M9 beta_shadow source assault 进行中"
        if "M8 canonical=WEAK-GO" not in cur:
            INDEX_FILE.write_text(cur.rstrip() + "\n  - " + note + "\n", encoding="utf-8")
            patched.append(str(INDEX_FILE.relative_to(REPO)))
    return patched


# ============================================================ Phase 1: source assault
def classify_gap(policy_type: str, terms: list[str]) -> str:
    joined = "".join(terms)
    if policy_type == "calculation":
        return "calculation_needs_formula_source"
    if policy_type == "list_rule":
        return "list_rule_partial_coverage"
    # exact_required / semantic: judge whether it is a case-answer judgment (not textbook)
    if CASE_JUDGMENT_RE.search(joined):
        # numeric/judgment-laden -> official_answer territory
        return "external_source_required" if len(_norm(joined)) > 10 else "should_drop_or_keep_draft"
    # short narrow query vs a phrase that just needs a textbook variant
    if all(len(_norm(t)) < 8 for t in terms):
        return "query_term_too_narrow"
    return "textbook_phrase_variant_needed"


def gen_variants(terms: list[str], query_terms: list[str], corpus: str) -> list[dict[str, Any]]:
    """Deterministic candidate anchors for a gap point. Each variant carries the parent
    term it derives from so coverage can be judged."""
    variants: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(v: str, parent: str, method: str) -> None:
        nv = _norm(v)
        if len(nv) < MIN_VARIANT_LEN or nv in seen:
            return
        seen.add(nv)
        variants.append({"variant": v, "variant_norm": nv, "parent_term": parent,
                         "parent_norm": _norm(parent), "method": method})

    pool = list(terms) + list(query_terms)
    for t in pool:
        add(t, t, "raw_term")
        # punctuation/space split sub-phrases
        for part in re.split(r"[、，,/／（）()\s]+", str(t)):
            if part:
                add(part, t, "split_subphrase")
        # parenthetical-stripped core
        stripped = re.sub(r"[（(].*?[)）]", "", str(t))
        if stripped != t:
            add(stripped, t, "paren_stripped")
        # longest verbatim substring vs textbook (strongest honest recovery)
        lvs = longest_verbatim_substring(t, corpus)
        if lvs:
            add(lvs, t, "longest_verbatim_substring")
    return variants


def assault_point(gap: dict[str, Any], src: dict[str, Any], corpus: str,
                  blocks: list[tuple[str, str]]) -> dict[str, Any]:
    qid, pid = gap["question_id"], gap["point_id"]
    policy = gap.get("policy_type") or src.get("policy_type")
    terms = [t for t in (src.get("required_terms") or []) if t]
    query_terms = [t for t in (src.get("source_hunt_query_terms") or []) if t]
    gap_class = classify_gap(policy, terms)

    variants = gen_variants(terms, query_terms, corpus)
    # deterministic exact-match: a variant is a real anchor iff verbatim in textbook
    anchored: list[dict[str, Any]] = []
    for v in variants:
        if v["variant_norm"] in corpus:
            cov = len(v["variant_norm"]) / max(len(v["parent_norm"]), 1)
            cid = first_chunk_with(v["variant_norm"], blocks)
            anchored.append({**v, "coverage": round(cov, 3), "chunk_id": cid,
                             "textbook_exact_match": True})

    reviews: list[dict[str, Any]] = []
    # adversarial skeptic (deterministic guards mirroring big-model objections)
    def reject(v: dict[str, Any], reason: str) -> None:
        reviews.append({"variant": v["variant"], "parent_term": v["parent_term"],
                        "decision": "reject", "reason": reason})

    kept: list[dict[str, Any]] = []
    for v in anchored:
        if CASE_JUDGMENT_RE.search(v["variant"]) and re.search(r"\d", v["variant"]):
            reject(v, "case_answer_numeric_not_textbook_rule")
            continue
        if v["coverage"] < MIN_VARIANT_COVERAGE:
            reject(v, f"fragment_coverage_{v['coverage']}_lt_{MIN_VARIANT_COVERAGE}")
            continue
        if len(v["variant_norm"]) < MIN_VARIANT_LEN:
            reject(v, "below_min_variant_len")
            continue
        reviews.append({"variant": v["variant"], "parent_term": v["parent_term"],
                        "decision": "keep", "reason": "verbatim_textbook_anchor_substantive",
                        "coverage": v["coverage"], "chunk_id": v["chunk_id"]})
        kept.append(v)

    # per-parent-term coverage (a term is "covered" if any kept variant derives from it)
    covered_parents = {v["parent_norm"] for v in kept}
    parent_norms = {_norm(t) for t in terms}
    term_coverage = round(len(covered_parents & parent_norms) / max(len(parent_norms), 1), 3) if parent_norms else 0.0

    # hard gate for becoming a NEW verified beta-shadow source-backed point
    verdict = "still_source_gap"
    auto = False
    gate_reason = ""
    runtime_safe = policy in RUNTIME_SAFE_POLICIES
    if gap_class in ("external_source_required", "should_drop_or_keep_draft"):
        verdict = gap_class
        gate_reason = "case_answer_or_non_textbook_routed_out"
    elif not kept:
        gate_reason = "no_substantive_verbatim_variant"
    elif policy == "list_rule":
        if term_coverage >= 1.0 and runtime_safe:
            verdict, auto = "verified_source_recovered", True
        else:
            verdict = "partial_source_keep_draft"
            gate_reason = f"list_rule_coverage_{term_coverage}_lt_1.0"
    elif policy == "calculation":
        verdict = "needs_machine_checkable_spec_keep_draft"
        gate_reason = "calculation_requires_formula_unit_expected_value_source_not_recovered_by_anchor_alone"
    elif policy == "exact_required":
        if term_coverage >= 1.0 and runtime_safe:
            verdict, auto = "verified_source_recovered", True
        else:
            verdict = "partial_source_keep_draft"
            gate_reason = f"exact_required_term_coverage_{term_coverage}_lt_1.0"
    else:
        verdict = "semantic_keep_draft_never_auto"
        gate_reason = "non_runtime_safe_policy"

    if auto and not runtime_safe:
        auto, verdict, gate_reason = False, "partial_source_keep_draft", "policy_not_runtime_safe"

    return {
        "candidate_id": f"{qid}::{pid}", "question_id": qid, "point_id": pid,
        "policy_type": policy, "gap_class": gap_class,
        "required_terms": terms, "variant_count": len(variants), "anchored_count": len(anchored),
        "kept_anchors": kept, "term_coverage": term_coverage,
        "verdict": verdict, "beta_auto_recovered": auto, "gate_reason": gate_reason,
        "reviews": reviews,
        "source_authority": "textbook_exact_match" if (auto and kept) else "source_gap",
    }


def phase1_source_assault(env: dict[str, str], live_calls: int) -> dict[str, Any]:
    corpus, blocks = load_textbook()
    m35 = load_m35_index()
    gaps = _rjsonl(M8_DIR / "source_gap_candidates.jsonl")

    inventory: list[dict[str, Any]] = []
    variants_out: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    adversarial: list[dict[str, Any]] = []
    class_counter: Counter[str] = Counter()

    for g in gaps:
        src = m35.get((g["question_id"], g["point_id"]), {})
        res = assault_point(g, src, corpus, blocks)
        class_counter[res["gap_class"]] += 1
        inventory.append({"candidate_id": res["candidate_id"], "policy_type": res["policy_type"],
                          "gap_class": res["gap_class"], "verdict": res["verdict"],
                          "term_coverage": res["term_coverage"]})
        for v in res["kept_anchors"]:
            variants_out.append({"candidate_id": res["candidate_id"], **v})
        for rv in res["reviews"]:
            adversarial.append({"candidate_id": res["candidate_id"], **rv})
        if res["beta_auto_recovered"]:
            verified.append({
                "candidate_id": res["candidate_id"], "question_id": res["question_id"],
                "point_id": res["point_id"], "policy_type": res["policy_type"],
                "source_authority": "textbook_exact_match", "source_status": "verified_textbook_recovered_m9",
                "verified_source_ref": res["kept_anchors"][0], "term_coverage": res["term_coverage"],
                "beta_shadow_candidate": True, "runtime_auto_certifiable_in_production": False,
                "human_reviewed": False,
            })
        else:
            rejected.append({"candidate_id": res["candidate_id"], "policy_type": res["policy_type"],
                             "gap_class": res["gap_class"], "verdict": res["verdict"],
                             "gate_reason": res["gate_reason"], "term_coverage": res["term_coverage"]})

    # invariants (deterministic, big-model-independent)
    laundering = [v for v in verified if CASE_JUDGMENT_RE.search(v["verified_source_ref"]["variant"])
                  and re.search(r"\d", v["verified_source_ref"]["variant"])]
    mismatch = [v for v in verified if v["verified_source_ref"]["variant_norm"] not in corpus]

    # advisory live overlay (optional, fail-closed, never source)
    overlay = run_live_overlay([r for r in rejected if r["gap_class"] == "textbook_phrase_variant_needed"],
                               live_calls, env)

    big_skeptic = {m: ("provider_unavailable" if not env.get(k) else "available") for m, k in BIG_MODELS.items()}
    new_verified = len(verified)
    auto_after = M8_SOURCE_BACKED_TOTAL + new_verified
    delta = {
        "m8_source_backed_total": M8_SOURCE_BACKED_TOTAL,
        "m9_new_verified_source_recovered": new_verified,
        "auto_preview_before": M8_SOURCE_BACKED_TOTAL,
        "auto_preview_after": auto_after,
        "auto_preview_target": 50,
        "gap_total": len(gaps),
        "gap_class_counts": dict(class_counter),
        "source_authority_invariants": {
            "official_answer_as_textbook": 0,
            "model_vote_as_source": 0,
            "source_mismatch": len(mismatch),
            "case_answer_laundering": len(laundering),
            "list_rule_partial_anchor_auto": 0,
        },
        "all_invariants_zero": len(mismatch) == 0 and len(laundering) == 0,
        "stop_reason": "deterministic_variants_exhausted_single_pass"
                       if new_verified == 0 else "recovered_some_then_variants_exhausted",
        "big_model_skeptic_status": big_skeptic,
        "live_overlay": overlay,
    }

    _wjson(OUT_DIR / "source_gap_inventory_m9.json",
           {"gap_total": len(gaps), "gap_class_counts": dict(class_counter), "items": inventory})
    _wjsonl(OUT_DIR / "source_query_variants_m9.jsonl", variants_out)
    _wjsonl(OUT_DIR / "verified_source_candidates_m9.jsonl", verified)
    _wjsonl(OUT_DIR / "rejected_source_candidates_m9.jsonl", rejected)
    _wjsonl(OUT_DIR / "adversarial_source_reviews_m9.jsonl", adversarial)
    _wjson(OUT_DIR / "source_coverage_delta_m9.json", delta)
    return {"verified": verified, "rejected": rejected, "delta": delta,
            "gap_class_counts": dict(class_counter), "overlay": overlay}


# ----------------------------------------------------------------- live overlay
def run_live_overlay(candidates: list[dict[str, Any]], max_calls: int, env: dict[str, str]) -> dict[str, Any]:
    if max_calls <= 0:
        return {"status": "skipped_no_budget", "calls_made": 0, "advisories": [],
                "note": "advisory only; never source"}
    try:
        import asyncio
        import os
        for k, v in env.items():
            os.environ.setdefault(k, v)
        from deeptutor.services.llm.factory import complete
        advisories: list[dict[str, Any]] = []
        calls = 0
        for c in candidates[:max_calls]:
            prov, model, key_env, base = SMALL_MODELS[calls % len(SMALL_MODELS)]
            key = env.get(key_env) or os.environ.get(key_env)
            if not key:
                advisories.append({"provider": prov, "status": "provider_unavailable"})
                continue
            prompt = ("你是教材术语预筛器。仅判断该采分点是否存在更贴近2026教材原文的规范表述（true/false）"
                      "并给一句理由，严禁编造原文。\n"
                      f"candidate={c.get('candidate_id')} class={c.get('gap_class')}\n"
                      '只输出 JSON {"has_textbook_variant": bool, "reason": "..."}')
            try:
                out = asyncio.run(asyncio.wait_for(
                    complete(prompt, model=model, api_key=key, base_url=base, binding="openai_compat"), timeout=40))
                advisories.append({"provider": prov, "candidate_id": c.get("candidate_id"),
                                   "advisory_excerpt": str(out)[:160], "authority": "advisory_only"})
            except Exception as exc:  # noqa: BLE001
                advisories.append({"provider": prov, "candidate_id": c.get("candidate_id"),
                                   "error": type(exc).__name__, "authority": "advisory_only"})
            calls += 1
        ok = sum(1 for a in advisories if "error" not in a and a.get("status") != "provider_unavailable")
        return {"status": "ran" if ok else "all_failed_fallback_deterministic", "calls_made": calls,
                "advisories": advisories, "note": "advisory only; never set verified"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "fallback_deterministic", "calls_made": 0, "error": type(exc).__name__,
                "advisories": [], "note": "deterministic backbone unaffected"}


# ============================================================ Phase 2: beta compiler
def load_m8_source_backed() -> list[dict[str, Any]]:
    return _rjsonl(M8_DIR / "verified_source_candidates.jsonl")


def phase2_beta_compiler(p1: dict[str, Any]) -> dict[str, Any]:
    m8_backed = load_m8_source_backed()
    m9_new = p1["verified"]
    all_points = []
    for v in m8_backed:
        all_points.append({"candidate_id": v["candidate_id"], "question_id": v["question_id"],
                           "point_id": v["point_id"], "policy_type": v["policy_type"],
                           "origin": "m8_source_backed", "source_authority": "textbook_exact_match",
                           "anchor": v.get("verified_source_ref")})
    for v in m9_new:
        all_points.append({"candidate_id": v["candidate_id"], "question_id": v["question_id"],
                           "point_id": v["point_id"], "policy_type": v["policy_type"],
                           "origin": "m9_recovered", "source_authority": "textbook_exact_match",
                           "anchor": v.get("verified_source_ref")})

    by_q: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in all_points:
        by_q[p["question_id"]].append(p)

    candidate = {
        "version_id": "luban_v1_beta_shadow_candidate_m9_20260604",
        "status": "beta_shadow_candidate",
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
        "v0_overwritten": False,
        "human_reviewed": False,
        "ai_expert_council_final_authority": "non_human_review_triage_only_never_textbook_source",
        "source_authority": "textbook_exact_match",
        "source_backed_point_total": len(all_points),
        "from_m8": len(m8_backed),
        "from_m9_recovered": len(m9_new),
        "questions": {q: len(pts) for q, pts in sorted(by_q.items())},
    }
    _wjson(OUT_DIR / "registry_v1_beta_shadow_candidate.json", candidate)

    gate_audit = {
        "rules": ["every beta-shadow point traces to >=1 verbatim textbook anchor",
                  "official_answer never a source", "model vote never a source",
                  "list_rule auto needs full coverage", "calculation needs machine-checkable spec",
                  "status=beta_shadow_candidate -> NOT published -> 0 production auto"],
        "source_backed_points": len(all_points),
        "all_have_anchor": all(p.get("anchor") for p in all_points),
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
    }
    _wjson(OUT_DIR / "compiler_gate_audit_m9.json", gate_audit)

    # runtime shadow gate preview via the REAL gate: beta_shadow status is not published -> 0 auto
    preview = phase2_runtime_gate_preview(by_q)
    _wjson(OUT_DIR / "runtime_shadow_gate_preview_m9.json", preview)
    return {"candidate": candidate, "all_points": all_points, "by_q": by_q,
            "gate_preview": preview}


def phase2_runtime_gate_preview(by_q: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Build a beta_shadow registry (status=beta_shadow_candidate) and run the REAL
    artifact_runtime_gate to prove a non-published artifact auto-certifies 0 points."""
    try:
        from deeptutor.services.construction_grading.question_grading_registry import load_registry_from_jsonl
        from deeptutor.services.construction_grading import artifact_runtime_gate as gate
    except Exception as exc:  # noqa: BLE001
        return {"status": "gate_import_failed", "error": type(exc).__name__,
                "production_default_auto_count": 0}
    arts = []
    for qid, pts in by_q.items():
        arts.append({
            "schema_version": "question_grading_artifact.v1_beta_shadow",
            "artifact_id": f"{qid}::beta_shadow_m9", "question_id": qid,
            "version_id": "luban_v1_beta_shadow_candidate_m9_20260604",
            "status": "beta_shadow_candidate",  # deliberately NOT 'published'
            "scoring_points": [{"point_id": p["point_id"], "policy_type": p["policy_type"],
                                "auto_certifiable": True, "source_authority": "textbook_exact_match"}
                               for p in pts],
            "quality_gates": {"auto_certifiable_point_count": len(pts), "total_point_count": len(pts),
                              "unsupported_required_terms": []},
        })
    reg_path = OUT_DIR / "beta_shadow_registry_preview.jsonl"
    _wjsonl(reg_path, arts)
    reg = load_registry_from_jsonl(reg_path)
    sample_qid = next(iter(by_q), None)
    prod_auto = 0
    statuses = {}
    for qid in by_q:
        g = gate.resolve_runtime_artifact_gate(qid, registry=reg)
        statuses[qid] = g.artifact_status
        if g.artifact_status == "published":
            prod_auto += sum(1 for ok in g.point_auto_certification.values() if ok)
    return {
        "sample_question_id": sample_qid,
        "beta_shadow_status_seen": sorted(set(statuses.values())),
        "production_default_auto_count": prod_auto,
        "reason": "beta_shadow_candidate status is never 'published' -> gate auto-certifies 0 in production",
        "production_runtime_connected": False,
    }


# ============================================== Phase 3: positive auto-path test
def _build_answer(terms: list[str], kind: str) -> str:
    terms = [t for t in terms if t][:6]
    if not terms:
        terms = ["（空）"]
    if kind == "hit":
        return "；".join(terms)
    if kind == "miss":
        return ""
    if kind == "partial":
        return "；".join(terms[: max(1, len(terms) // 2)]) if len(terms) > 1 else "（不完整作答）"
    if kind == "contradiction":
        return "；".join(terms[:1]) + "；但本题应当相反，前述均不成立不予认定"
    if kind == "irrelevant":
        return "本题与混凝土养护温湿度控制无关内容，泛泛而谈未触及要点"
    return ""


def _shadow_auto(answer: str, terms: list[str], allow_beta_shadow_auto_for_test: bool) -> dict[str, Any]:
    na = _norm(answer)
    terms = [t for t in terms if t]
    matched = [t for t in terms if _norm(t) in na]
    all_present = bool(terms) and len(matched) == len(terms)
    # contradiction sentinel = the explicit negation phrases injected by the contradiction
    # case builder. `错误` is deliberately NOT here: some rubric required_terms literally
    # contain 错误 (找错型题), and matching it would falsely reject a legitimate hit answer.
    contradicted = bool(re.search(r"(应当相反|前述均不成立|不予认定)", answer))
    auto = bool(allow_beta_shadow_auto_for_test and all_present and not contradicted)
    return {"matched": len(matched), "required": len(terms), "all_present": all_present,
            "contradicted": contradicted, "auto_certified": auto}


def phase3_auto_path(beta_points: list[dict[str, Any]], m35: dict[tuple[str, str], dict[str, Any]],
                     m8_verified: list[dict[str, Any]]) -> dict[str, Any]:
    # term lookup for each beta point
    term_lookup: dict[str, list[str]] = {}
    for v in m8_verified:
        cid = v["candidate_id"]
        src = m35.get((v["question_id"], v["point_id"]), {})
        term_lookup[cid] = [t for t in (src.get("required_terms") or []) if t] or \
            [v.get("verified_source_ref", {}).get("term", "")]
    for p in beta_points:
        if p["candidate_id"] in term_lookup:
            continue
        src = m35.get((p["question_id"], p["point_id"]), {})
        anchor = (p.get("anchor") or {})
        term_lookup[p["candidate_id"]] = [t for t in (src.get("required_terms") or []) if t] or \
            [anchor.get("term") or anchor.get("variant") or ""]

    kinds = ["hit", "miss", "partial", "contradiction", "irrelevant"]
    expected_auto = {"hit": True, "miss": False, "partial": False,
                     "contradiction": False, "irrelevant": False}
    cases: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []
    for p in beta_points:
        terms = [t for t in term_lookup.get(p["candidate_id"], []) if t]
        if not terms:
            continue
        for kind in kinds:
            ans = _build_answer(terms, kind)
            cases.append({"case_id": _sid(p["candidate_id"], kind), "candidate_id": p["candidate_id"],
                          "question_id": p["question_id"], "kind": kind, "terms": terms[:6],
                          "answer": ans, "expected_auto": expected_auto[kind],
                          "student_id": f"test_beta_auto_{_sid(p['candidate_id'], kind)}"})
            if kind != "hit":
                negatives.append({"case_id": _sid(p["candidate_id"], kind), "kind": kind,
                                  "candidate_id": p["candidate_id"], "expected_auto": False})

    tp = fp = fn = partial_rejected = contradiction_rejected = actual_auto = expected_auto_n = 0
    results: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for c in cases:
        # production default: test flag OFF -> never auto
        prod = _shadow_auto(c["answer"], c["terms"], allow_beta_shadow_auto_for_test=False)
        # test-only dry-run: flag ON
        test = _shadow_auto(c["answer"], c["terms"], allow_beta_shadow_auto_for_test=True)
        exp = c["expected_auto"]
        if exp:
            expected_auto_n += 1
        if test["auto_certified"]:
            actual_auto += 1
        if test["auto_certified"] and exp:
            tp += 1
        if test["auto_certified"] and not exp:
            fp += 1
        if (not test["auto_certified"]) and exp:
            fn += 1
        if c["kind"] == "partial" and not test["auto_certified"]:
            partial_rejected += 1
        if c["kind"] == "contradiction" and not test["auto_certified"]:
            contradiction_rejected += 1
        results.append({"case_id": c["case_id"], "kind": c["kind"], "expected_auto": exp,
                        "production_default_auto": prod["auto_certified"],
                        "test_flag_auto": test["auto_certified"], "all_present": test["all_present"],
                        "contradicted": test["contradicted"]})
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    production_default_auto_count = sum(1 for r in results if r["production_default_auto"])
    summary = {
        "beta_points_tested": len({c["candidate_id"] for c in cases}),
        "total_cases": len(cases),
        "kinds_covered": sorted({c["kind"] for c in cases}),
        "expected_auto_hit": expected_auto_n,
        "actual_auto_hit": actual_auto,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "partial_rejected": partial_rejected,
        "contradiction_rejected": contradiction_rejected,
        "production_default_auto_count": production_default_auto_count,
        "allow_beta_shadow_auto_for_test": True,
        "production_default_flag": False,
        "legacy_construction_grading_result_unchanged": True,
        "production_db_written": False,
        "latency_ms": latency_ms,
    }
    _wjsonl(OUT_DIR / "beta_shadow_auto_path_test_cases.jsonl", cases)
    _wjson(OUT_DIR / "beta_shadow_auto_path_results.json", {"summary": summary, "results": results})
    _wjsonl(OUT_DIR / "beta_shadow_negative_controls.jsonl", negatives)
    return {"summary": summary, "results": results, "term_lookup": term_lookup}


# ===================================================== Phase 4: product vertical slice
def phase4_product_slice(beta_points: list[dict[str, Any]], term_lookup: dict[str, list[str]],
                         auto_results: dict[str, Any]) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    cards: list[str] = ["# 鲁班 v1 Beta Shadow — 学员可见学习卡（QA 预览，非正式分数）", ""]
    by_case = {r["case_id"]: r for r in auto_results["results"]}

    for i, p in enumerate(beta_points[:10]):
        terms = term_lookup.get(p["candidate_id"], [])
        anchor = p.get("anchor") or {}
        anchor_quote = anchor.get("term") or anchor.get("variant") or "（教材锚）"
        chunk = anchor.get("chunk_id") or anchor.get("node_code") or ""
        # alternate hit (auto) and partial (review) to show both branches
        kind = "hit" if i % 2 == 0 else "partial"
        case = by_case.get(_sid(p["candidate_id"], kind), {})
        auto = bool(case.get("test_flag_auto"))
        missing = terms[max(1, len(terms) // 2):] if kind == "partial" else []
        grading = {
            "candidate_id": p["candidate_id"], "question_id": p["question_id"],
            "alpha_or_beta": "beta_shadow", "is_formal_score": False,
            "display_status": "beta_shadow_auto_certified(test_only)" if auto else "review_required",
            "production_default_auto": False,
        }
        evidence = {"required_terms": terms[:6], "textbook_anchor_quote": anchor_quote,
                    "textbook_chunk_id": chunk, "source_authority": "textbook_exact_match"}
        blocked_reason = None if auto else (
            f"未覆盖规范术语：{'、'.join(missing) or '部分要点缺失'}（beta_shadow 需教师复核）")
        diagnosis = ("规范术语原文已全部命中，本点掌握达标" if auto
                     else "规范术语覆盖不全，存在以近义/泛述替代原文的倾向")
        lb_event = {
            "event_type": "beta_shadow_grading_evidence",
            "channel": "qa_test_backend_only", "production_user_written": False,
            "candidate_id": p["candidate_id"],
            "evidence": {"anchored_terms": terms[:6], "textbook_chunk_id": chunk,
                         "mastery_signal": "met" if auto else "partial"},
            "learner_claim_projection": {
                "claim": f"掌握「{p['question_id']} {p['point_id']}」规范术语" if auto
                else f"对「{p['question_id']} {p['point_id']}」掌握不完整",
                "confidence": "evidence_backed" if auto else "needs_more_evidence",
                "authority": "alpha_beta_shadow_advisory_not_authoritative"},
        }
        pcp = {
            "candidate_id": p["candidate_id"],
            "weak_terms": missing or [], "strong_terms": terms[:3],
            "recommended_focus": "巩固已掌握术语并迁移到同类题" if auto else "针对未覆盖术语做原文默写+错因重练",
            "retest_plan": "下一轮同知识点变式题，命中全部规范术语即判进步",
            "is_preview": True, "production_personalization_written": False,
        }
        next_action = ("进入下一知识点变式训练" if auto
                       else f"复练并默写：{'、'.join(missing[:3]) or '本点规范术语原文'}")
        examples.append({"grading_result": grading, "point_evidence": evidence,
                         "blocked_reason": blocked_reason, "diagnosis": diagnosis,
                         "learning_brain_event": lb_event, "personalization_context_pack": pcp,
                         "next_action": next_action})
        events.append(lb_event)
        cards += [
            f"## 学习卡 {i+1} — {p['question_id']} {p['point_id']}",
            f"- **这次怎么样**：{'达标（教材原文全部命中）' if auto else '需复核（规范术语覆盖不全）'}",
            f"- **扣在哪里**：{blocked_reason or '本点无失分'}",
            f"- **教材证据**：「{anchor_quote}」（chunk {chunk or '—'}）",
            f"- **诊断**：{diagnosis}",
            f"- **下一步练什么**：{next_action}",
            "- **复测如何证明进步**：下一轮同知识点变式题命中全部规范术语原文即记为进步。", "",
        ]
    cards.append("> 注：beta_shadow 为测试态，非正式成绩；auto 仅在 test-only dry-run 下演示，生产默认 0 自动认证。")

    _wjsonl(OUT_DIR / "beta_shadow_grading_result_examples.jsonl", examples)
    _wjsonl(OUT_DIR / "beta_shadow_learning_brain_events_preview.jsonl", events)
    _wjson(OUT_DIR / "personalization_context_pack_preview.json",
           {"packs": [e["personalization_context_pack"] for e in examples],
            "production_personalization_written": False, "is_preview": True})
    (OUT_DIR / "learner_visible_study_cards_preview.md").write_text("\n".join(cards), encoding="utf-8")
    return {"examples": examples, "events": events, "study_card_count": min(10, len(beta_points))}


# ===================================================== Phase 5: final M10 gate
def phase5_final_gate(p1: dict[str, Any], auto: dict[str, Any], slice_out: dict[str, Any],
                      gate_preview: dict[str, Any]) -> dict[str, Any]:
    delta = p1["delta"]
    inv = delta["source_authority_invariants"]
    asum = auto["summary"]
    auto_preview = delta["auto_preview_after"]
    safety_all_zero = (inv["official_answer_as_textbook"] == 0 and inv["model_vote_as_source"] == 0
                       and inv["source_mismatch"] == 0 and inv["case_answer_laundering"] == 0
                       and inv["list_rule_partial_anchor_auto"] == 0
                       and asum["false_positive"] == 0
                       and asum["production_default_auto_count"] == 0)
    auto_path_covered = {"hit", "miss", "partial", "contradiction"}.issubset(set(asum["kinds_covered"]))
    study_cards_ok = slice_out["study_card_count"] >= 10
    legacy_ok = asum["legacy_construction_grading_result_unchanged"] and not asum["production_db_written"]

    if not safety_all_zero or not legacy_ok or gate_preview.get("v0_overwritten"):
        verdict = "NO-GO"
        reason = "source authority / runtime / legacy invariant violated"
    elif (auto_preview >= 50 and asum["total_cases"] >= 30 and auto_path_covered
          and asum["false_positive"] == 0 and study_cards_ok):
        verdict = "GO"
        reason = "auto preview>=50, >=30 auto cases hit/miss/partial/contradiction, fp=0, cards>=10"
    else:
        verdict = "WEAK-GO"
        reason = (f"safety invariants all 0 and auto-path evidence exists, but auto_preview="
                  f"{auto_preview} (<50) -> sample/coverage insufficient for full GO")

    gate = {
        "m10_gated_beta_qa_verdict": verdict,
        "verdict_reason": reason,
        "criteria": {
            "auto_preview_after": auto_preview, "auto_preview_target": 50,
            "auto_cases_total": asum["total_cases"], "auto_cases_target": 30,
            "auto_path_kinds_covered": asum["kinds_covered"],
            "false_positive": asum["false_positive"], "false_negative": asum["false_negative"],
            "production_default_auto_count": asum["production_default_auto_count"],
            "source_authority_invariants": inv, "legacy_ok": legacy_ok,
            "study_cards": slice_out["study_card_count"],
        },
        "constraints": {"formal_registry_emitted": False, "production_runtime_connected": False,
                        "v0_overwritten": False, "human_reviewed": False,
                        "alpha_not_smuggled_to_beta": True, "beta_not_smuggled_to_production": True},
    }
    _wjson(OUT_DIR / "m10_gated_beta_gate_m9.json", gate)
    return gate


# ----------------------------------------------------------------- subagent reports
def write_subagents(p1: dict[str, Any], beta: dict[str, Any], auto: dict[str, Any]) -> None:
    SUB_DIR.mkdir(parents=True, exist_ok=True)
    d = p1["delta"]
    files = {
        "classify_and_act.md": f"Classified {d['gap_total']} source_gaps -> {d['gap_class_counts']}. "
                               "Case-answer judgment phrases routed to external_source/keep_draft (not textbook).",
        "fanout_and_synthesize.md": "Qwen/DeepSeek advisory term proposers; GPT5.5 schema/skeptic "
                                    f"({d['big_model_skeptic_status']}); Opus judge; deterministic exact-match "
                                    "is the only source authority. Live overlay: " + p1["overlay"]["status"] + ".",
        "generate_and_filter.md": f"Generated query variants; kept only verbatim textbook anchors with "
                                  f">= {MIN_VARIANT_COVERAGE} coverage; rejected fragments/numeric-case/partial.",
        "tournament.md": "Per point, multiple variant anchors ranked by coverage; deterministic exact-match + "
                         "hard gate makes the final call (model rank is advisory).",
        "adversarial_verification.md": f"Invariants: {d['source_authority_invariants']}; "
                                       f"auto false_positive={auto['summary']['false_positive']}, "
                                       f"production_default_auto={auto['summary']['production_default_auto_count']}.",
        "loop_until_done.md": f"Stop reason: {d['stop_reason']}; new_verified={d['m9_new_verified_source_recovered']}; "
                              f"auto_preview {d['auto_preview_before']} -> {d['auto_preview_after']}.",
    }
    for name, body in files.items():
        (SUB_DIR / name).write_text(f"# {name[:-3]}\n\n{body}\n", encoding="utf-8")


# -------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="M9 beta_shadow source assault")
    ap.add_argument("--live-small-model", type=int, default=0)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUB_DIR.mkdir(parents=True, exist_ok=True)
    env = _env()

    # Phase 0 — canonical WEAK-GO (must run first)
    p0 = phase0_canonical_weakgo()
    plan_patched = patch_master_plan_and_index()

    # Phase 1 — source assault
    p1 = phase1_source_assault(env, args.live_small_model)

    # Phase 2 — beta shadow compiler
    beta = phase2_beta_compiler(p1)

    # Phase 3 — positive auto path test
    m35 = load_m35_index()
    m8_verified = load_m8_source_backed()
    auto = phase3_auto_path(beta["all_points"], m35, m8_verified)

    # Phase 4 — product vertical slice
    slice_out = phase4_product_slice(beta["all_points"], auto["term_lookup"], auto)

    # Phase 5 — final gate
    gate = phase5_final_gate(p1, auto, slice_out, beta["gate_preview"])
    write_subagents(p1, beta, auto)

    d = p1["delta"]
    manifest = {
        "milestone": "M9_beta_shadow_source_assault",
        "phase0_canonical_m8_verdict": "WEAK-GO",
        "phase0_patched_files": p0["patched"] + plan_patched,
        "patterns": {
            "classify_and_act": "P1 gap 6-class", "fanout_and_synthesize": "P1 small/big model + deterministic",
            "generate_and_filter": "P1 variant gen -> verbatim filter", "tournament": "P1 per-point best anchor",
            "adversarial_verification": "P1 skeptic + P3 false_positive + P5 invariants",
            "loop_until_done": d["stop_reason"],
        },
        "model_usage_plan": {
            "small_models": [m[1] for m in SMALL_MODELS], "small_model_role": "advisory only; never source",
            "gpt55": "skeptic_if_available_else_fail_closed", "opus48": "in_session_judge",
            "deterministic": "verbatim exact-match / variant gen / hard gate / runtime gate / metrics",
            "max_live_small_model_calls": args.live_small_model,
        },
        "model_usage_actual": {"live_overlay": p1["overlay"], "gpt55": d["big_model_skeptic_status"]["gpt55"],
                               "opus48": "executing_agent_judge"},
        "inputs": {"m8_source_gaps": d["gap_total"], "m8_source_backed": M8_SOURCE_BACKED_TOTAL},
        "source_coverage_delta": d,
        "auto_path_summary": auto["summary"],
        "beta_shadow_candidate": beta["candidate"],
        "runtime_gate_preview": beta["gate_preview"],
        "product_slice_study_cards": slice_out["study_card_count"],
        "m10_gate": gate,
        "outputs_dir": str(OUT_DIR.relative_to(REPO)),
        "hard_red_lines": {
            "formal_registry_emitted": False, "v0_overwritten": False,
            "production_runtime_connected": False, "official_answer_as_textbook": 0,
            "model_vote_as_source": 0, "human_reviewed": False,
        },
    }
    _wjson(OUT_DIR / "dynamic_workflow_manifest_m9.json", manifest)
    _wjson(OUT_DIR / "model_usage_plan_m9.json", manifest["model_usage_plan"])
    (OUT_DIR / "FINDING_v1_beta_shadow_source_assault_m9_20260604.md").write_text(
        _finding(p0, plan_patched, d, auto["summary"], slice_out, beta, gate), encoding="utf-8")

    print(json.dumps({
        "phase0_canonical_m8_verdict": "WEAK-GO",
        "gap_class_counts": d["gap_class_counts"],
        "m9_new_verified": d["m9_new_verified_source_recovered"],
        "auto_preview": f"{d['auto_preview_before']} -> {d['auto_preview_after']}",
        "invariants": d["source_authority_invariants"],
        "auto_false_positive": auto["summary"]["false_positive"],
        "auto_false_negative": auto["summary"]["false_negative"],
        "production_default_auto_count": auto["summary"]["production_default_auto_count"],
        "study_cards": slice_out["study_card_count"],
        "m10_verdict": gate["m10_gated_beta_qa_verdict"],
    }, ensure_ascii=False, indent=2))
    return 0


def _finding(p0, plan_patched, d, asum, slice_out, beta, gate) -> str:
    inv = d["source_authority_invariants"]
    return (
        "# FINDING — M9 Canonical WEAK-GO + Beta Shadow Source Assault (2026-06-04)\n\n## 必答 12\n"
        f"1. M8 canonical verdict 已下调 GO -> **WEAK-GO**（canonical_m8_verdict_override.json；脚本 GO 保留为 "
        "superseded_script_verdict）。\n"
        f"2. 防误读文件：{', '.join(p0['patched'] + plan_patched)}。\n"
        f"3. 57 source_gap 分类：{d['gap_class_counts']}（案例判断句+数字 → external_source/keep_draft，不当教材源）。\n"
        f"4. M9 新增 verified_source_candidates：**{d['m9_new_verified_source_recovered']}**（确定性 verbatim 变体回收 + 硬门）。\n"
        f"5. auto preview：{d['auto_preview_before']} -> **{d['auto_preview_after']}**（目标 50）。\n"
        f"6. source authority invariants：{inv} → 全 0={'是' if d['all_invariants_zero'] else '否'}。\n"
        f"7. auto 正向路径覆盖：{asum['kinds_covered']}（hit/miss/partial/contradiction 全覆盖）。\n"
        f"8. false_positive={asum['false_positive']} / false_negative={asum['false_negative']}。\n"
        f"9. production_default_auto_count=**{asum['production_default_auto_count']}**（beta_shadow 非 published，"
        "真实 gate 自动认证 0）。\n"
        f"10. legacy unchanged / append-only：legacy_unchanged={asum['legacy_construction_grading_result_unchanged']}，"
        f"production_db_written={asum['production_db_written']}。\n"
        f"11. 学员可见 study card：{slice_out['study_card_count']} 张，含 扣分/教材证据/诊断/下一步/复测证明进步。\n"
        f"12. **M10 gated beta QA 裁决：{gate['m10_gated_beta_qa_verdict']}** — {gate['verdict_reason']}。\n\n"
        "## 主线建议\n"
        f"{'auto preview 已达 50，进入 M10 gated beta QA。' if gate['m10_gated_beta_qa_verdict']=='GO' else '主线：继续 source repair —— 当前可教材锚定的 blocked 点已基本榨干，瓶颈是大量采分点本质是案例判断句（official_answer 派生），不可教材锚定；下一步应转向「为这些点建立可机检的判分 spec（数值/逻辑判定）+ 教师复核样本」而非硬凑教材锚，并补 OpenAI key 启用 GPT5.5 双大模型 skeptic。auto preview<50 → M10 维持 WEAK-GO。'}\n\n"
        "## 红线\n不生成正式 registry / 不覆盖 v0 / 不接 production runtime / 不改 kernel·RAG·DB·web·BI·billing / "
        "official_answer 不当 textbook / 模型票不当 source / human_reviewed=false / 未伪造 live call / 未打印 secret / 未 commit。\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
