"""M13B — Case Event Text Backfill for Question-Stem Authority (supply line, not runtime).

M12A surfaced 9 ``question_stem_fact`` points whose ``span_verified=0`` because the M4
question_text was truncated / missing. This supply-line job hunts the COMPLETE case-event
text for each point and runs a DETERMINISTIC exact span verification: the fact (the
official "不妥之处" claim, stripped to its substantive clause) must appear VERBATIM in the
full question/case-event stem text.

Hard distinctions (enforced):
  * A ``question_stem_fact`` only proves the STEM stated the fact. It is NEVER a textbook
    source and is never upgraded to ``textbook`` authority (question_stem_as_textbook=0).
  * The official_answer is NOT a stem source. A fact is only ``verified`` if it matches a
    genuine question_text/stem field — never the official_answer
    (official_answer_as_question_stem_source=0 unless the answer text is proven to come
    from the stem, which we do not assume).
  * Source authority is deterministic exact-match. Small models (DeepSeek/Qwen) may only
    advise text location; here the full text is absent, so no live call is made.

Outputs verified / pending / impossible. Missing full text -> work order, never fabricated.
No runtime change, no beta loader change, no registry emission, production_auto_count=0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AR = REPO / "artifacts/luban_grading_artifacts"
M12A_DIR = AR / "production_authority_partition_m12a_20260604"
M5_FILE = AR / "case_rubric_authority_adjudication_m5_20260604/authority_adjudication.json"
M6_FILE = AR / "registry_v1_candidate_dry_run_m6_20260604/question_grading_artifacts_v1_candidate.jsonl"
OUT_DIR = AR / "case_event_text_backfill_m13b_20260604"

STEM_MISSING_MARKER = "题干缺失"
STEM_MIN_LEN = 30        # below this the stem is effectively missing
STEM_TRUNCATION_HINT = 300  # M4/M6 hard-truncate case stems at 300 normalized chars
FACT_PREFIX_RE = re.compile(r"^.*?不妥之处[一二三四五六七八九十]?[：:]")


def _norm(s: Any) -> str:
    return re.sub(r"[\s，。、；;：:（）()【】\[\]　·,.//\"'“”‘’%]", "", str(s or ""))


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


# ------------------------------------------------------------------ loaders
def load_stem_facts() -> list[dict[str, Any]]:
    return _rjsonl(M12A_DIR / "question_stem_fact_evidence_m12a.jsonl")


def load_m5_points() -> dict[tuple[str, str], dict[str, Any]]:
    if not M5_FILE.exists():
        return {}
    data = json.loads(M5_FILE.read_text("utf-8"))
    return {(p.get("question_id"), p.get("point_id")): p for p in (data.get("points") or [])}


def load_stem_sources() -> dict[str, list[dict[str, Any]]]:
    """Per question_id, the candidate STEM texts (question_text / stem fields only).
    The official_answer field is deliberately excluded — it is never a stem source."""
    sources: dict[str, list[dict[str, Any]]] = {}

    def add(qid: str, text: str, origin: str) -> None:
        if not qid or not isinstance(text, str):
            return
        sources.setdefault(qid, []).append({"origin": origin, "text": text, "len": len(text)})

    # M5 question_text (stem side)
    for (qid, _pid), p in load_m5_points().items():
        add(qid, p.get("question_text") or "", "m5_question_text")
    # M6 registry stem
    for art in _rjsonl(M6_FILE):
        add(art.get("question_id"), art.get("stem") or "", "m6_registry_stem")
    return sources


# ------------------------------------------------------------------ core
def extract_fact(label: str) -> str:
    """The substantive clause of the official '不妥之处X：...' claim."""
    label = str(label or "").strip()
    m = FACT_PREFIX_RE.match(label)
    fact = label[m.end():] if m else label
    return fact.strip()


def best_stem(sources: list[dict[str, Any]]) -> dict[str, Any]:
    real = [s for s in sources if STEM_MISSING_MARKER not in s["text"] and len(s["text"]) >= STEM_MIN_LEN]
    if not real:
        # fall back to whatever exists (to report the missing marker honestly)
        chosen = max(sources, key=lambda s: s["len"], default={"origin": "none", "text": "", "len": 0})
        return {**chosen, "status": "missing"}
    chosen = max(real, key=lambda s: s["len"])
    status = "truncated" if chosen["len"] <= STEM_TRUNCATION_HINT else "full"
    return {**chosen, "status": status}


def verify_point(fact_row: dict[str, Any], m5: dict[tuple[str, str], dict[str, Any]],
                 stem_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    qid, pid = fact_row["question_id"], fact_row["point_id"]
    p = m5.get((qid, pid), {})
    label = p.get("label") or p.get("point_label") or ""
    fact = extract_fact(label)

    stem = best_stem(stem_sources.get(qid, []))
    stem_text, stem_status = stem["text"], stem["status"]

    span_hit = bool(fact) and _norm(fact) in _norm(stem_text)
    # classification
    if span_hit:
        classification = "verified"
        reason = "fact_verbatim_in_question_stem"
    elif stem_status in ("missing", "truncated"):
        classification = "pending"
        reason = f"full_case_event_text_{stem_status}_fact_beyond_available_text"
    else:  # full stem present but fact not found -> genuinely not a stem quote
        classification = "impossible"
        reason = "fact_absent_from_complete_stem_not_a_question_stem_fact"

    return {
        "question_id": qid, "point_id": pid,
        "authority_kind": "question_stem_fact",
        "policy_type": fact_row.get("policy_type"),
        "fact": fact,
        "fact_source": "official_answer_label_paraphrase",  # provenance of the CLAIM, not the stem
        "stem_origin": stem["origin"], "stem_len": stem["len"], "stem_status": stem_status,
        "span_exact_match": span_hit,
        "matched_against": "question_stem_text_only",
        "official_answer_used_as_source": False,   # we never match against official_answer
        "is_textbook_source": False,               # a stem fact is never textbook authority
        "classification": classification,
        "reason": reason,
        "auto_cert_policy": "no_auto",
        "production_gate_status": "shadow_only",
        "human_reviewed": False,
    }


def build_work_order(v: dict[str, Any]) -> dict[str, Any]:
    qid = v["question_id"]
    hint = {
        "M2-2015-34-01": "2015 年案例 5 第 2 问（施工总平面/材料加工场地/出入口/环形载重道路）",
        "M2-2015-34-02": "2015 年案例 5 第 3 问（现场施工用电组织设计编制/审批链）",
        "M2-2015-32-02": "2015 年案例 3（安全技术交底/三违巡查事件）",
        "M2-2015-33-01": "2015 年案例 4（项目管理规划大纲与实施规划编制）",
        "M2-2016-31-03": "2016 年案例 2（小砌块龄期/搭接长度/竖向灰缝砂浆饱满度）",
    }.get(qid, qid)
    return {
        "work_order_id": f"WO_M13B_{qid}_{v['point_id']}",
        "question_id": qid, "point_id": v["point_id"],
        "needed_artifact": "full_case_event_text (untruncated question stem)",
        "blocker": v["reason"], "current_stem_status": v["stem_status"], "current_stem_len": v["stem_len"],
        "fact_to_verify": v["fact"],
        "source_hint": hint,
        "acceptance": "fact must appear VERBATIM in the supplied full case-event text (deterministic exact-match)",
        "must_not": ["fabricate stem text", "use official_answer as the stem source",
                     "upgrade question_stem_fact to textbook authority"],
        "assignee_line": "A-line / content-supply (exam paper / 题库 full case text)",
    }


# ------------------------------------------------------------------ main
def main() -> int:
    argparse.ArgumentParser(description="M13B case event text backfill").parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    facts = load_stem_facts()
    m5 = load_m5_points()
    stem_sources = load_stem_sources()

    verifications = [verify_point(f, m5, stem_sources) for f in facts]
    by_class: dict[str, list[dict[str, Any]]] = {"verified": [], "pending": [], "impossible": []}
    for v in verifications:
        by_class[v["classification"]].append(v)

    work_orders = [build_work_order(v) for v in verifications if v["classification"] in ("pending", "impossible")]

    # inventory: per question, what stem text exists
    inventory = {}
    qids = sorted({f["question_id"] for f in facts})
    for qid in qids:
        srcs = stem_sources.get(qid, [])
        chosen = best_stem(srcs)
        inventory[qid] = {
            "candidate_stem_sources": [{"origin": s["origin"], "len": s["len"],
                                        "is_missing_marker": STEM_MISSING_MARKER in s["text"]} for s in srcs],
            "best_stem_origin": chosen["origin"], "best_stem_len": chosen["len"],
            "best_stem_status": chosen["status"],
            "full_case_event_text_available": chosen["status"] == "full",
        }
    inventory_doc = {
        "questions": inventory,
        "questions_with_full_text": sum(1 for q in inventory.values() if q["full_case_event_text_available"]),
        "questions_missing_or_truncated": sum(1 for q in inventory.values()
                                              if not q["full_case_event_text_available"]),
        "stem_sources_scanned": ["m5_question_text", "m6_registry_stem"],
        "official_answer_excluded_from_stem_sources": True,
    }

    # source audit: laundering invariants
    audit = {
        "question_stem_as_textbook": sum(1 for v in verifications if v["is_textbook_source"]),
        "official_answer_as_question_stem_source": sum(1 for v in verifications
                                                       if v["official_answer_used_as_source"]),
        "verified_points_have_exact_span": all(v["span_exact_match"] for v in by_class["verified"]),
        "verified_count": len(by_class["verified"]),
        "pending_count": len(by_class["pending"]),
        "impossible_count": len(by_class["impossible"]),
        "total_points": len(verifications),
        "all_nine_covered": len(verifications) == 9,
        "production_auto_count": 0,
        "runtime_changed": False,
        "beta_loader_changed": False,
        "registry_emitted": False,
        "fabricated_text": False,
        "consumable_by_m13_m14": len(by_class["verified"]) > 0,
        "advisory_models_used": "none (full case-event text absent -> text-location advisory moot; fail-closed)",
    }

    _wjson(OUT_DIR / "case_event_text_inventory_m13b.json", inventory_doc)
    _wjsonl(OUT_DIR / "question_stem_span_verification_m13b.jsonl", verifications)
    _wjson(OUT_DIR / "case_event_text_source_audit_m13b.json", audit)
    _wjsonl(OUT_DIR / "pending_case_text_work_orders_m13b.jsonl", work_orders)
    (OUT_DIR / "FINDING_case_event_text_backfill_m13b_20260604.md").write_text(
        _finding(verifications, by_class, inventory_doc, audit, work_orders), encoding="utf-8")

    print(json.dumps({
        "total_points": len(verifications),
        "verified": len(by_class["verified"]),
        "pending": len(by_class["pending"]),
        "impossible": len(by_class["impossible"]),
        "question_stem_as_textbook": audit["question_stem_as_textbook"],
        "official_answer_as_question_stem_source": audit["official_answer_as_question_stem_source"],
        "production_auto_count": audit["production_auto_count"],
        "runtime_changed": audit["runtime_changed"],
        "work_orders": len(work_orders),
        "consumable_by_m13_m14": audit["consumable_by_m13_m14"],
    }, ensure_ascii=False, indent=2))
    return 0


def _finding(verifications, by_class, inventory_doc, audit, work_orders) -> str:
    lines = ["# FINDING — M13B Case Event Text Backfill (2026-06-04)\n",
             "## 9 个 question_stem_fact 点逐一状态\n"]
    for v in verifications:
        lines.append(f"- **{v['question_id']} {v['point_id']}** ({v['policy_type']}): "
                     f"`{v['classification']}` — stem={v['stem_origin']}/{v['stem_len']}字/{v['stem_status']}; "
                     f"fact={v['fact'][:36]!r}; reason={v['reason']}")
    lines += [
        "\n## 必答\n",
        f"1. 9 点状态：verified={len(by_class['verified'])}、pending={len(by_class['pending'])}、"
        f"impossible={len(by_class['impossible'])}。",
        f"2. verified 数 = **{audit['verified_count']}**。",
        f"3. pending 数 = **{audit['pending_count']}**（完整案例事件文本缺失/截断，事实落在 300 字切口之后）。",
        f"4. impossible 数 = **{audit['impossible_count']}**。",
        f"5. source laundering 是否 0：question_stem_as_textbook={audit['question_stem_as_textbook']}、"
        f"official_answer_as_question_stem_source={audit['official_answer_as_question_stem_source']} → "
        f"{'是，全 0' if audit['question_stem_as_textbook']==0 and audit['official_answer_as_question_stem_source']==0 else '否'}。",
        f"6. 能否供 M13/M14 消费：{'能' if audit['consumable_by_m13_m14'] else '否——本轮 verified=0，需先补全完整案例事件文本（见工单）'}。",
        "\n## 关键判断（不伪造）\n",
        "- 这些“不妥之处”事实派生自 official_answer 的转述；真实题干在可用数据里 **缺失 / 截断 300 字**"
        "（M2-2015-34-01、34-02 的 stem 直接是 `[题干缺失]`；32-02/33-01/31-03 截断在 300 字，事实在切口之后）。",
        "- 全仓 + docs/2026 穷尽搜索：`材料加工场地 / 环形载重 / 砂浆饱满度 / 现场施工用电组织设计` 等 late-stem 特征短语"
        "**只出现在答案侧**，无任何题库/真题完整案例文本。",
        "- 因此把 official_answer 当题干源 = 红线 laundering，**已拒绝**；9 点全部判 pending，"
        f"生成 {len(work_orders)} 张补源工单交 A 线/内容补给。",
        "\n## 红线\n不改 runtime / 不改 beta loader / 不生成 registry / question_stem_fact 不升 textbook / "
        "official_answer 不当题干源 / production_auto_count=0 / 未伪造文本 / 未打印 secret / 未 commit。\n",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
