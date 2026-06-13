#!/usr/bin/env python3
"""Pure-API multi-model adversarial arbitration gold panel — focused validation.

Measurement instrument for trustworthy per-point grading gold labels, free of
"self-grade / single-judge noise". Reuses the M35 pure-API judge building blocks
(``scripts/m35_gold_judges.py``: ``build_judge_prompt`` / ``parse_judge_output`` /
``_chat_completions_call`` / ``JudgeStats``) so the panel is wholly metered HTTP
providers — no ``claude`` / ``codex`` CLI, hence no subscription quota wall
(see memory: m35-gold-labeling-needs-quota-proof-panel).

Per (golden scoring point x student answer) it:
  1. asks a blind panel of >=3 independent-backend models for hit/partial/miss
     + evidence span (no cross-visibility);
  2. deterministically reconciles: unanimous -> consensus; strict panel
     majority -> arbiter confirms; split -> arbiter (a model that never sat on
     the panel) adjudicates; arbiter abstains on a split -> unadjudicated
     (never a fabricated verdict);
  3. compares the panel consensus against the golden fixture's
     ``ground_truth_ledger`` reference label and reports:
       - inter-model agreement (panel unanimity rate, pairwise rate),
       - panel-consensus vs reference-ledger agreement,
       - the split frontier (the points worth a thin human/official screw).

Scope: candidate_only / review_only. production_write_count == 0. This script
performs NO production DB / canonical-truth / published-registry / remote write.
It is an OFFLINE gold/measurement builder, not a runtime path.

Tiers:
  - ``shape``  : injected fake judges, no network (default; CI-safe).
  - ``live``   : real HTTP providers; requires --live AND
                 LUBAN_ARBITRATION_PANEL_LIVE=1 (double opt-in).

Usage:
  python scripts/run_luban_arbitration_gold_panel.py --cases Q3-1A433000,Q5-1A432000
  LUBAN_ARBITRATION_PANEL_LIVE=1 python scripts/run_luban_arbitration_gold_panel.py \
      --cases Q3-1A433000 --tier live --live
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.m35_gold_judges import (  # noqa: E402
    JUDGE_TIMEOUT_SECONDS,
    JudgeStats,
    _http_post_json,
    _wrap_judge,
    load_dotenv_file,
)

JudgeFn = Callable[[dict[str, Any], str, dict[str, Any]], dict[str, Any]]

SCHEMA_VERSION = "luban_arbitration_gold_panel.v1"
GOLDEN_FIXTURE = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DOTENV_PATH = REPO / ".env"
LIVE_ENV_FLAG = "LUBAN_ARBITRATION_PANEL_LIVE"
CREDIT_RANK = {"miss": 0, "partial": 1, "hit": 2}
ABSTAIN = "abstain"
UNADJUDICATED = "unadjudicated"

# Pure-API panel. Each backend is an INDEPENDENT provider (different vendor /
# weights), so their votes are not collinear. deepseek-chat is intentionally
# NOT a panel member: on api.deepseek.com it is server-side aliased to the same
# deepseek-v4-flash backend (verified: model_in_resp=deepseek-v4-flash), so it
# would double-count one backend rather than add an independent vote.
PANEL_SPECS = {
    "deepseek-v4-flash": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "qwen-max": {"provider": "dashscope", "model": "qwen-max"},
    "glm-4-plus": {"provider": "bigmodel", "model": "glm-4-plus"},
}
ARBITER_SPEC = {"id": "deepseek-reasoner", "provider": "deepseek", "model": "deepseek-reasoner"}

DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com/v1"
DASHSCOPE_DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BIGMODEL_DEFAULT_BASE = "https://open.bigmodel.cn/api/paas/v4"

# Reasoning models (v4-flash, glm, reasoner) spend output tokens on hidden
# reasoning before the answer JSON; a 400-token ceiling can truncate to empty
# content (finish_reason=length). Give them headroom.
JUDGE_MAX_TOKENS = 1200


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------- judge factory


def _chat_call(
    url: str, api_key: str, model: str, prompt: str, max_tokens: int = JUDGE_MAX_TOKENS,
) -> tuple[str | None, dict[str, int] | None]:
    """OpenAI-compatible chat-completions call with a configurable token ceiling.

    Local to this script (not the shared M35 ``_chat_completions_call``, which
    pins max_tokens=400): the pure-API panel uses reasoning models that spend
    output tokens on hidden chain-of-thought before the verdict JSON, so a low
    ceiling truncates them to empty content. Reuses the shared ``_http_post_json``
    transport (timeout + JudgeTransportError handling)."""
    body = _http_post_json(
        url,
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "stream": False,
        },
        JUDGE_TIMEOUT_SECONDS,
    )
    choices = body.get("choices") or []
    content = None
    if choices and isinstance(choices[0], dict):
        content = (choices[0].get("message") or {}).get("content")
    raw_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    usage = {
        "prompt_tokens": int(raw_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(raw_usage.get("completion_tokens") or 0),
        "total_tokens": int(raw_usage.get("total_tokens") or 0),
    }
    return content, usage


def _provider_url(provider: str, env: Mapping[str, str]) -> tuple[str, str]:
    """Return (chat_completions_url, api_key) for a provider from env."""
    if provider == "deepseek":
        base = str(env.get("DEEPSEEK_BASE_URL") or DEEPSEEK_DEFAULT_BASE).rstrip("/")
        key = str(env.get("DEEPSEEK_API_KEY") or "").strip()
    elif provider == "dashscope":
        base = str(env.get("DASHSCOPE_BASE_URL") or DASHSCOPE_DEFAULT_BASE).rstrip("/")
        key = str(env.get("DASHSCOPE_API_KEY") or env.get("QWEN_API_KEY") or "").strip()
    elif provider == "bigmodel":
        base = str(env.get("BIGMODEL_BASE_URL") or BIGMODEL_DEFAULT_BASE).rstrip("/")
        key = str(env.get("BIGMODEL_API_KEY") or "").strip()
    else:  # pragma: no cover - guarded by PANEL_SPECS
        raise ValueError(f"unknown provider: {provider!r}")
    return f"{base}/chat/completions", key


def build_live_judges(
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, JudgeFn], JudgeStats, dict[str, Any]]:
    """Build the pure-API panel + arbiter, degrading honestly on missing keys.

    Returns ``(judge_fns, stats, roster)``. ``roster`` records which models
    are live and which degraded (missing key), so the report never claims a
    judge that did not run.
    """
    if env is None:
        merged: dict[str, str] = {**load_dotenv_file(DOTENV_PATH), **dict(os.environ)}
    else:
        merged = dict(env)

    stats = JudgeStats()
    judge_fns: dict[str, JudgeFn] = {}
    panel_live: list[str] = []
    panel_degraded: list[dict[str, str]] = []

    for model_id, spec in PANEL_SPECS.items():
        url, key = _provider_url(spec["provider"], merged)
        if not key:
            panel_degraded.append({"model_id": model_id, "reason": f"missing key for {spec['provider']}"})
            continue
        model_name = spec["model"]
        judge_fns[model_id] = _wrap_judge(
            model_id,
            stats,
            (lambda u, k, m: lambda prompt: _chat_call(u, k, m, prompt))(url, key, model_name),
        )
        panel_live.append(model_id)

    arb_url, arb_key = _provider_url(ARBITER_SPEC["provider"], merged)
    arbiter_live = bool(arb_key)
    if arbiter_live:
        judge_fns[ARBITER_SPEC["id"]] = _wrap_judge(
            ARBITER_SPEC["id"],
            stats,
            (lambda u, k, m: lambda prompt: _chat_call(u, k, m, prompt))(
                arb_url, arb_key, ARBITER_SPEC["model"]
            ),
        )

    roster = {
        "blind_panel_live": panel_live,
        "blind_panel_degraded": panel_degraded,
        "arbiter": ARBITER_SPEC["id"] if arbiter_live else None,
        "arbiter_degraded": None if arbiter_live else {"reason": f"missing key for {ARBITER_SPEC['provider']}"},
    }
    return judge_fns, stats, roster


# --------------------------------------------------------------- reconciliation


def _judge(fn: JudgeFn, point: dict[str, Any], answer: str, anchor: dict[str, Any]) -> dict[str, Any]:
    raw = fn(point, answer, anchor)
    verdict = str(raw.get("verdict") or "")
    if verdict == ABSTAIN:
        return {"verdict": ABSTAIN, "evidence_span": "", "confidence": 0.0,
                "abstain_reason": str(raw.get("abstain_reason") or "")}
    if verdict not in CREDIT_RANK:
        return {"verdict": ABSTAIN, "evidence_span": "", "confidence": 0.0,
                "abstain_reason": f"invalid_verdict:{verdict}"}
    return {"verdict": verdict, "evidence_span": str(raw.get("evidence_span") or ""),
            "confidence": float(raw.get("confidence") or 0.0)}


def _judge_panel(
    judge_fns: Mapping[str, JudgeFn], panel_ids: list[str],
    point: dict[str, Any], answer: str, anchor: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=max(1, len(panel_ids))) as pool:
        futures = {mid: pool.submit(_judge, judge_fns[mid], point, answer, anchor) for mid in panel_ids}
        return {mid: fut.result() for mid, fut in futures.items()}


def reconcile_point(
    point: dict[str, Any], answer: str, anchor: dict[str, Any],
    judge_fns: Mapping[str, JudgeFn], panel_ids: list[str], arbiter_id: str | None,
) -> dict[str, Any]:
    """Same reconciliation contract as the M35 governed-gold pipeline."""
    votes = _judge_panel(judge_fns, panel_ids, point, answer, anchor)
    counts = Counter(v["verdict"] for v in votes.values() if v["verdict"] != ABSTAIN)
    voted = sum(counts.values())
    top_verdict, top_count = counts.most_common(1)[0] if counts else (None, 0)
    size = len(panel_ids)

    arbiter_vote: dict[str, Any] | None = None
    if voted == size and top_count == size:
        route, consolidated = "unanimous", top_verdict
    else:
        if arbiter_id is not None:
            arbiter_vote = _judge(judge_fns[arbiter_id], point, answer, anchor)
        arb_abstained = arbiter_vote is None or arbiter_vote["verdict"] == ABSTAIN
        if top_count * 2 > size:
            consolidated = top_verdict
            if arbiter_vote is None:
                route = "majority_no_arbiter"
            else:
                route = "majority_review_confirmed" if arbiter_vote["verdict"] == top_verdict else "majority_review_unconfirmed"
        elif not arb_abstained:
            route, consolidated = "arbitration", arbiter_vote["verdict"]
        else:
            route, consolidated = "arbitration_unresolved", UNADJUDICATED

    supporting = [mid for mid in panel_ids if votes[mid]["verdict"] == consolidated]
    if arbiter_vote is not None and arbiter_vote["verdict"] == consolidated:
        supporting.append(arbiter_id)
    return {
        "blind_votes": {mid: v["verdict"] for mid, v in votes.items()},
        "blind_evidence": {mid: v["evidence_span"] for mid, v in votes.items()},
        "arbiter_vote": arbiter_vote["verdict"] if arbiter_vote else None,
        "route": route,
        "consensus_verdict": consolidated,
        "supporting_model_ids": supporting,
        "panel_unanimous": voted == size and top_count == size,
    }


# --------------------------------------------------------------- agreement


def _pairwise_agreement(verdicts: list[str]) -> float | None:
    """Fraction of model pairs that agree (abstain excluded)."""
    voted = [v for v in verdicts if v != ABSTAIN]
    if len(voted) < 2:
        return None
    agree = total = 0
    for i in range(len(voted)):
        for j in range(i + 1, len(voted)):
            total += 1
            if voted[i] == voted[j]:
                agree += 1
    return round(agree / total, 4) if total else None


# Inter-rater reliability gate. Below this, the panel consensus is treated as a
# directional signal, NOT a trustworthy gold label (quality_claim_allowed=false).
FLEISS_KAPPA_TRUST_THRESHOLD = 0.6


def _fleiss_kappa(items: list[Counter]) -> float | None:
    """Fleiss' kappa over items that share a constant rater count.

    Same estimator as ``run_luban_m35_ai_governed_gold_labeling._fleiss_kappa``:
    each item is a Counter of category->rater_count for the SAME number of
    raters. Items with fewer raters (panel abstentions) must be excluded by the
    caller, since Fleiss' kappa is undefined for a varying rater count.
    """
    if not items:
        return None
    rater_count = sum(items[0].values())
    if rater_count < 2:
        return None
    item_count = len(items)
    categories = sorted({category for item in items for category in item})
    category_share = {
        category: sum(item.get(category, 0) for item in items) / (item_count * rater_count)
        for category in categories
    }
    mean_agreement = sum(
        (sum(count**2 for count in item.values()) - rater_count)
        / (rater_count * (rater_count - 1))
        for item in items
    ) / item_count
    expected_agreement = sum(share**2 for share in category_share.values())
    if 1 - expected_agreement == 0:
        return 1.0
    return round((mean_agreement - expected_agreement) / (1 - expected_agreement), 6)


def _slice_fleiss_kappa(rows: list[dict[str, Any]], panel_ids: list[str]) -> dict[str, Any]:
    """Fleiss' kappa over the blind panel votes across the whole slice.

    Only rows where every panel model returned a non-abstain verdict are scored
    (constant rater count == len(panel_ids)); rows with any abstention are
    excluded and counted honestly. ``quality_claim_allowed`` is the trust gate:
    below ``FLEISS_KAPPA_TRUST_THRESHOLD`` the gold is ai_council_directional.
    """
    full = len(panel_ids)
    counters: list[Counter] = []
    excluded = 0
    for row in rows:
        votes = [row["blind_votes"].get(mid, ABSTAIN) for mid in panel_ids]
        if any(v == ABSTAIN for v in votes) or len(votes) != full:
            excluded += 1
            continue
        counters.append(Counter(votes))
    kappa = _fleiss_kappa(counters)
    allowed = kappa is not None and kappa >= FLEISS_KAPPA_TRUST_THRESHOLD
    return {
        "fleiss_kappa": kappa,
        "scored_item_count": len(counters),
        "excluded_for_abstention": excluded,
        "rater_count": full,
        "threshold": FLEISS_KAPPA_TRUST_THRESHOLD,
        "quality_claim_allowed": allowed,
        "label_authority": (
            "ai_arbitration_panel_candidate" if allowed else "ai_council_directional"
        ),
    }


def _reference_label(ledger: dict[str, Any], point_id: str) -> str | None:
    for ph in ledger.get("point_hits") or []:
        if str(ph.get("point_id")) == point_id:
            return str(ph.get("hit") or "")
    return None


# --------------------------------------------------------------- shape judges


def _shape_judges() -> tuple[dict[str, JudgeFn], JudgeStats, dict[str, Any]]:
    """Deterministic fake panel: votes are derived from point/answer hashing so
    the reconciliation + agreement math is exercised offline (no network)."""
    stats = JudgeStats()

    def make(model_id: str, bias: int) -> JudgeFn:
        def judge(point: dict[str, Any], answer: str, anchor: dict[str, Any]) -> dict[str, Any]:
            stats.record(model_id, abstained=False, usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
            h = (abs(hash((point.get("point_id"), len(answer)))) + bias) % 10
            verdict = "hit" if h < 6 else ("partial" if h < 8 else "miss")
            return {"verdict": verdict, "evidence_span": answer[:8], "confidence": 0.5}
        return judge

    judge_fns = {mid: make(mid, i) for i, mid in enumerate(PANEL_SPECS)}
    judge_fns[ARBITER_SPEC["id"]] = make(ARBITER_SPEC["id"], 7)
    roster = {
        "blind_panel_live": list(PANEL_SPECS),
        "blind_panel_degraded": [],
        "arbiter": ARBITER_SPEC["id"],
        "arbiter_degraded": None,
        "tier_note": "shape: injected fake judges, no network",
    }
    return judge_fns, stats, roster


# --------------------------------------------------------------- run


def _point_to_criterion(golden_point: dict[str, Any]) -> dict[str, Any]:
    """Map a golden_v1 scoring point to the build_judge_prompt 'criterion' shape."""
    criterion = golden_point.get("label") or ""
    basis = golden_point.get("official_basis") or ""
    if basis and basis not in criterion:
        criterion = f"{criterion}\n【官方依据】{basis}"
    return {
        "point_id": str(golden_point.get("point_id") or ""),
        "max_score": golden_point.get("max_score"),
        "criterion": criterion,
    }


def run_panel(
    cases: list[dict[str, Any]],
    judge_fns: Mapping[str, JudgeFn],
    panel_ids: list[str],
    arbiter_id: str | None,
) -> dict[str, Any]:
    per_point_rows: list[dict[str, Any]] = []
    for case in cases:
        anchor = {
            "question_id": case.get("case_id"),
            "stem": case.get("stem"),
            "total_score": case.get("max_score"),
        }
        gold_points = case.get("gold_scoring_points") or []
        for sample in case.get("eval_samples") or []:
            answer = str(sample.get("answer_text") or "")
            ledger = sample.get("ground_truth_ledger") or {}
            for gp in gold_points:
                point = _point_to_criterion(gp)
                rec = reconcile_point(point, answer, anchor, judge_fns, panel_ids, arbiter_id)
                ref = _reference_label(ledger, point["point_id"])
                panel_verdicts = list(rec["blind_votes"].values())
                per_point_rows.append({
                    "case_id": case.get("case_id"),
                    "student_id": sample.get("student_id"),
                    "archetype": sample.get("archetype"),
                    "point_id": point["point_id"],
                    "blind_votes": rec["blind_votes"],
                    "arbiter_vote": rec["arbiter_vote"],
                    "route": rec["route"],
                    "consensus_verdict": rec["consensus_verdict"],
                    "panel_unanimous": rec["panel_unanimous"],
                    "pairwise_agreement": _pairwise_agreement(panel_verdicts),
                    "reference_ledger_label": ref,
                    "consensus_matches_reference": (
                        None if ref is None or rec["consensus_verdict"] in (UNADJUDICATED,)
                        else rec["consensus_verdict"] == ref
                    ),
                })
    return _aggregate(per_point_rows, panel_ids)


def _aggregate(rows: list[dict[str, Any]], panel_ids: list[str]) -> dict[str, Any]:
    n = len(rows)
    unanimous = sum(1 for r in rows if r["panel_unanimous"])
    routes = Counter(r["route"] for r in rows)
    pair_vals = [r["pairwise_agreement"] for r in rows if r["pairwise_agreement"] is not None]
    ref_checkable = [r for r in rows if r["consensus_matches_reference"] is not None]
    ref_match = sum(1 for r in ref_checkable if r["consensus_matches_reference"])
    split_frontier = [
        {"case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
         "blind_votes": r["blind_votes"], "arbiter_vote": r["arbiter_vote"],
         "consensus_verdict": r["consensus_verdict"], "reference_ledger_label": r["reference_ledger_label"]}
        for r in rows if not r["panel_unanimous"]
    ]
    disagree_with_reference = [
        {"case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
         "consensus_verdict": r["consensus_verdict"], "reference_ledger_label": r["reference_ledger_label"],
         "blind_votes": r["blind_votes"], "route": r["route"]}
        for r in ref_checkable if not r["consensus_matches_reference"]
    ]
    return {
        "per_point_count": n,
        "panel_unanimity_rate": round(unanimous / n, 4) if n else None,
        "mean_pairwise_agreement": round(sum(pair_vals) / len(pair_vals), 4) if pair_vals else None,
        "panel_fleiss_kappa": _slice_fleiss_kappa(rows, panel_ids),
        "route_counts": dict(routes),
        "reference_checkable_count": len(ref_checkable),
        "consensus_vs_reference_agreement": round(ref_match / len(ref_checkable), 4) if ref_checkable else None,
        "split_frontier_count": len(split_frontier),
        "split_frontier": split_frontier,
        "consensus_disagrees_with_reference": disagree_with_reference,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="Q3-1A433000,Q5-1A432000",
                        help="comma-separated case_ids from luban_case_grading_golden_v1.json")
    parser.add_argument("--tier", choices=["shape", "live"], default="shape")
    parser.add_argument("--live", action="store_true", help="opt-in to real provider calls (with env flag)")
    parser.add_argument("--output", default="artifacts/luban_grading_artifacts/luban_arbitration_gold_panel_20260613/panel_validation.json")
    parser.add_argument("--max-students", type=int, default=0, help="cap eval_samples per case (0=all)")
    args = parser.parse_args(argv)

    golden = _read_json(GOLDEN_FIXTURE)
    wanted = [c.strip() for c in args.cases.split(",") if c.strip()]
    by_id = {c["case_id"]: c for c in golden["cases"]}
    missing_cases = [cid for cid in wanted if cid not in by_id]
    if missing_cases:
        print(f"ERROR: unknown case_ids: {missing_cases}", file=sys.stderr)
        return 2
    cases = [by_id[cid] for cid in wanted]
    if args.max_students > 0:
        cases = [{**c, "eval_samples": (c.get("eval_samples") or [])[: args.max_students]} for c in cases]

    live_ok = args.tier == "live" and args.live and os.environ.get(LIVE_ENV_FLAG) == "1"
    if args.tier == "live" and not live_ok:
        print(f"ERROR: live tier requires --live AND {LIVE_ENV_FLAG}=1", file=sys.stderr)
        return 2

    if live_ok:
        judge_fns, stats, roster = build_live_judges()
    else:
        judge_fns, stats, roster = _shape_judges()

    panel_ids = roster["blind_panel_live"]
    if len(panel_ids) < 3:
        print(f"ERROR: arbitration panel needs >=3 live independent models; got {panel_ids} "
              f"(degraded: {roster['blind_panel_degraded']})", file=sys.stderr)
        return 3
    arbiter_id = roster.get("arbiter")

    result = run_panel(cases, judge_fns, panel_ids, arbiter_id)
    kappa_block = result["panel_fleiss_kappa"]
    report = {
        "schema_version": SCHEMA_VERSION,
        "classification": "candidate_only",
        "review_status": "review_only",
        "production_write_count": 0,
        # Trust gate promoted to top level: when Fleiss' kappa < threshold the gold
        # is directional only and must not be cited as a quality claim.
        "quality_claim_allowed": kappa_block["quality_claim_allowed"],
        "gold_label_authority": kappa_block["label_authority"],
        "safety": {
            "production_db_write": False,
            "canonical_truth_write": False,
            "published_registry_write": False,
            "remote_write": False,
        },
        "tier": args.tier,
        "live": live_ok,
        "golden_fixture": str(GOLDEN_FIXTURE.relative_to(REPO)),
        "cases": wanted,
        "panel_roster": roster,
        "label_authority": kappa_block["label_authority"],
        "label_scope": "offline_measurement_not_runtime",
        "model_stats": stats.snapshot(),
        "aggregate": {k: v for k, v in result.items() if k != "rows"},
    }
    out_path = REPO / args.output if not Path(args.output).is_absolute() else Path(args.output)
    _write_json(out_path, report)
    _write_json(out_path.with_name("panel_validation_rows.json"), {"rows": result["rows"]})

    agg = report["aggregate"]
    print(f"tier={args.tier} live={live_ok} points={agg['per_point_count']} "
          f"unanimity={agg['panel_unanimity_rate']} pairwise={agg['mean_pairwise_agreement']} "
          f"fleiss_kappa={agg['panel_fleiss_kappa']['fleiss_kappa']} "
          f"quality_claim_allowed={agg['panel_fleiss_kappa']['quality_claim_allowed']} "
          f"consensus_vs_reference={agg['consensus_vs_reference_agreement']} "
          f"split_frontier={agg['split_frontier_count']}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
