"""Phase 3 — does the multi-AI team's *grading* skill transfer to *rule authoring*?

Phase 1/2 validated GRADING (given a rule + answer → verdict, vs 131 human labels).
This phase validates a DIFFERENT task with a DIFFERENT failure mode: RULE AUTHORING
(given stem + official answer + point labels → propose the list_rule). A team that
grades well can still hallucinate a list_rule the official key does not support, so
this transfer must be proven before spending on the full 152-case factory run.

Non-circular by construction: the 20 human-authored list_rules (and which 42 points
have NO list_rule) are the held-out gold; the proposers never see them. The decision
metric is whether the cross-family consensus over-mints rules on the 42 non-list
points (precision) and catches the 20 real list points (recall).

Falsifiability (eval-design #6) — what would prove the authoring task does NOT transfer:
  * list-type detection precision < 0.80  → team over-mints list_rules the key can't support
  * list-type detection recall    < 0.80  → team misses real enumeration points
If either holds, the full-152 authoring run is NOT justified without a human-author
gate or an added adversarial (Codex/Opus) refute layer on every proposed rule.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location(
    "deep_runner", REPO / "scripts/run_luban_rich_leaf_llm_deep_compile_runner.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)

ART = REPO / "artifacts/luban_human_validation_v1/po_slice_20260601"
OUT = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
PACKET = ART / "po_review_packet.json"

PROPOSERS = [("deepseek", "规则提议员A"), ("dashscope", "规则提议员B")]

AUTHOR_SYS = (
    "你是一级建造师建筑实务案例题评分规则编译员。给你一道题的题干、官方参考答案、官方解析,"
    "以及该题已切好的若干采分点(label/满分)。你的任务:为每个采分点判断它是不是【列举/枚举型】采分点——"
    "即官方答案是一串并列要点(如'列出N个设施名称'、'列出N条理由'、'列出N项措施'),判分按命中项数给分/封顶。"
    "判断必须严格锚定官方答案的实际形态,不得凭空臆造:只有官方答案在该点确实是并列枚举时才标 is_list_rule=true。"
    "对单一论断/单一判断/单一计算结果等非并列点,必须 is_list_rule=false。"
    "列举型须给出 total_items(官方该点并列的总项数)。踩字铁律:规范术语须命中原文,近义/错位不算→exact_term_required。"
    "此外判断题干是否含【元规则罚则】(如'本问题X项,多答不得分'),含则在 penalty_rule 给出。"
    "只输出 JSON,不要多余文字: "
    "{\"points\":[{\"point_id\":\"<原样回填>\",\"is_list_rule\":true|false,"
    "\"total_items\":<整数或null>,\"exact_term_required\":true|false,"
    "\"rule_text\":\"<列举型给一句判分规则,非列举型空字符串>\"}],"
    "\"penalty_rule\":{\"exists\":true|false,\"scope\":\"<涉及哪些point或子问>\",\"text\":\"<罚则原文复述,无则空>\"}}"
)


def _author(call, case: dict) -> dict:
    points = [{"point_id": p["point_id"], "label": p.get("label"), "max_score": p.get("max_score")}
              for p in case.get("gold_scoring_points") or []]
    payload = {
        "题干": (case.get("stem") or "")[:1200],
        "官方参考答案": case.get("official_answer") or "",
        "官方解析": (case.get("official_analysis") or "")[:800],
        "采分点": points,  # NOTE: human list_rule/penalty_rule deliberately withheld
    }
    messages = [
        {"role": "system", "content": AUTHOR_SYS},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        result = call("author", messages)
        obj = json.loads(result["content"])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160], "points": [], "penalty_rule": {}}
    by_id = {}
    for p in obj.get("points") or []:
        pid = str(p.get("point_id") or "")
        by_id[pid] = {
            "is_list_rule": bool(p.get("is_list_rule")),
            "total_items": p.get("total_items"),
            "exact_term_required": bool(p.get("exact_term_required")),
            "rule_text": str(p.get("rule_text") or ""),
        }
    return {"points": by_id, "penalty_rule": obj.get("penalty_rule") or {}}


_NUM_RE = re.compile(r"(\d+)\s*(?:个|条|项|点)")


def _gold_total_items(list_rule_text: str) -> int | None:
    """Extract the canonical enumeration count from the human gold list_rule text.

    Gold phrases the total count as e.g. '5个机具', '8条理由', '官方列6项', '10个编号定位点'.
    We take the FIRST 数量+量词 as the total — least-ambiguous anchor (the '满分需命中M项'
    threshold varies and is not the count we compare)."""
    if not list_rule_text:
        return None
    m = _NUM_RE.search(list_rule_text)
    return int(m.group(1)) if m else None


def main() -> int:
    packet = json.loads(PACKET.read_text("utf-8"))
    cases = packet["cases"]

    calls = {}
    for prov, _ in PROPOSERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=120, max_tokens=1500)
        if c is None:
            raise SystemExit(f"{prov} API key missing")
        calls[prov] = c

    def work(case):
        out = {prov: _author(calls[prov], case) for prov, _ in PROPOSERS}
        return case["case_id"], out

    authored = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for cid, out in ex.map(work, cases):
            authored[cid] = out

    # ---- score authoring vs held-out human gold ----
    rows = []
    for case in cases:
        cid = case["case_id"]
        a = authored[cid]
        for p in case.get("gold_scoring_points") or []:
            pid = str(p["point_id"])
            gold_lr = p.get("list_rule")
            gold_is_list = bool(gold_lr)
            gold_total = _gold_total_items(gold_lr or "")
            ds = a["deepseek"]["points"].get(pid, {})
            qw = a["dashscope"]["points"].get(pid, {})
            ds_list = bool(ds.get("is_list_rule"))
            qw_list = bool(qw.get("is_list_rule"))
            consensus_list = ds_list and qw_list  # both agree it IS a list point
            rows.append({
                "case_id": cid, "point_id": pid, "label": (p.get("label") or "")[:50],
                "gold_is_list": gold_is_list, "gold_total_items": gold_total,
                "ds_is_list": ds_list, "ds_total": ds.get("total_items"),
                "qw_is_list": qw_list, "qw_total": qw.get("total_items"),
                "consensus_is_list": consensus_list,
            })

    n = len(rows)
    # primary metric: consensus list-type detection vs gold (the over-minting test)
    tp = sum(1 for r in rows if r["gold_is_list"] and r["consensus_is_list"])
    fp = sum(1 for r in rows if not r["gold_is_list"] and r["consensus_is_list"])
    fn = sum(1 for r in rows if r["gold_is_list"] and not r["consensus_is_list"])
    tn = sum(1 for r in rows if not r["gold_is_list"] and not r["consensus_is_list"])
    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None
    # secondary: cap-N (total_items) exact match on consensus true-positives (DS used as the
    # production-lane proposer); honest caveat — gold count is regex-extracted, noisy.
    capn = [(r["ds_total"], r["gold_total_items"]) for r in rows
            if r["gold_is_list"] and r["consensus_is_list"] and r["gold_total_items"] is not None]
    capn_match = sum(1 for a, b in capn if a == b)

    # per-proposer raw agreement (before consensus) for transparency
    def raw(prov_key):
        agree = sum(1 for r in rows if r[prov_key] == r["gold_is_list"])
        return round(agree / n, 4)

    # penalty_rule: single-case spot check only (Q4 is the lone gold) — NOT a metric
    penalty_spot = []
    for case in cases:
        if case.get("penalty_rule"):
            a = authored[case["case_id"]]
            penalty_spot.append({
                "case_id": case["case_id"],
                "gold": case["penalty_rule"][:200],
                "deepseek": a["deepseek"].get("penalty_rule"),
                "dashscope": a["dashscope"].get("penalty_rule"),
            })

    falsified = (precision is not None and precision < 0.80) or (recall is not None and recall < 0.80)
    metrics = {
        "n_points": n, "gold_list_points": tp + fn, "gold_non_list_points": fp + tn,
        "consensus_list_detection": {
            "precision": precision, "recall": recall,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "interpretation": "precision=不在非列举点上凭空mint规则; recall=不漏真列举点",
        },
        "raw_agreement_vs_gold": {"deepseek": raw("ds_is_list"), "dashscope": raw("qw_is_list")},
        "capn_exact_match_on_consensus_tp": {
            "matched": capn_match, "of": len(capn),
            "caveat": "gold count regex-extracted from NL list_rule, noisy; secondary signal only",
        },
        "penalty_spot_check_anecdotal": penalty_spot,
        "falsifiability": {
            "rule": "precision<0.80 或 recall<0.80 → 授权任务不可直接放全量",
            "authoring_transfer_FALSIFIED": falsified,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase3_rule_authoring_results.json").write_text(json.dumps({
        "schema": "luban_multi_ai_rule_authoring_validation.v1", "generated_at_date": "2026-06-14",
        "classification": {"candidate_only": True, "gold_is_human_not_ai": True,
                           "task": "rule_authoring (distinct from grading)",
                           "held_out": "human list_rule/penalty_rule withheld from proposers"},
        "roles": {"deepseek": "规则提议员A(生产lane)", "dashscope": "规则提议员B(跨家族)"},
        "metrics": metrics, "rows": rows,
    }, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
