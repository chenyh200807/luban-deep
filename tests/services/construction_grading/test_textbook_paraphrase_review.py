"""Textbook paraphrase review channel (increment ① · backlog).

Proves the channel OPENS the synthesis backlog into review packets, stages them as candidates in a
namespace separate from any release, and that the deterministic signer is hard-gated: it signs ONLY a
governed ``faithful`` verdict with grounded numbers into the SEPARATE weaker class, and never mints
verbatim authority. Hermetic (no LLM, no network, no real supply).
"""
from __future__ import annotations

from deeptutor.services.construction_grading import compiler_feedback as CF
from deeptutor.services.construction_grading import full_knowledge_compiler as FKC
from deeptutor.services.construction_grading import textbook_paraphrase_review as PR

# A real-shape synthesis card: the source says "5年/50年/100年" in prose; the claim restructures it as
# a compact list (faithful paraphrase, NOT a literal substring) -> synthesis backlog.
_SOURCE = (
    "结构设计工作年限：临时性结构为 5 年；普通房屋和构筑物为 50 年；"
    "特别重要的建筑结构为 100 年。设计时应按此年限取值。"
)
_CARD = {
    "chunk_id": "1A411011_024_0045", "node_code": "1A411011",
    "card_title": "房屋建筑结构设计工作年限",
    "card_content": "临时性建筑结构：5年；普通房屋和构筑物：50年；特别重要的建筑结构：100年。",
    "key_numbers": ["5", "50", "100"],
}
_WO = {"point_id": "1A411011_024_0045::C2", "node_code": "1A411011", "provenance_class": "synthesis",
       "reason": "no_verbatim_no_number"}


def _queue():
    return PR.build_review_queue(
        [_WO], {"1A411011_024_0045::C2": _CARD}, {"1A411011_024_0045": _SOURCE})


def test_channel_opens_with_packet_and_triage():
    q = _queue()
    assert q["open_count"] == 1 and not q["unjoinable"]
    p = q["packets"][0]
    assert p["namespace"] == PR.PARAPHRASE_NAMESPACE
    assert p["review_question"] == PR.REVIEW_QUESTION
    assert p["source_markdown"] == _SOURCE
    assert p["claim_content"] == _CARD["card_content"]
    assert p["review_verdict"] is None  # unfilled -> channel open, not decided
    assert p["triage"]["key_numbers_all_grounded"] is True  # 5/50/100 all in source


def test_non_synthesis_backlog_is_ignored():
    wo = {**_WO, "provenance_class": "external_standard"}
    q = PR.build_review_queue([wo], {_WO["point_id"]: _CARD}, {"1A411011_024_0045": _SOURCE})
    assert q["open_count"] == 0


def test_unjoinable_item_is_recorded_not_dropped():
    q = PR.build_review_queue([_WO], {}, {})  # no card / no source
    assert q["open_count"] == 0
    assert q["unjoinable"] == [{"point_id": _WO["point_id"], "reason": "card_or_source_unavailable"}]


def test_candidates_separate_namespace_never_promoted():
    cands = PR.make_paraphrase_candidates(_queue()["packets"])
    led = CF.build_ledger(cands)
    assert led["all_separate_from_release"] is True
    assert led["candidate_used_as_release_truth"] == 0
    assert all(c["namespace"] == CF.NAMESPACE for c in cands)
    assert all(c["kind"] == CF.KIND_SOURCE and c["promote_to_release"] is False for c in cands)


def test_signer_fail_closed_without_verdict():
    res = PR.sign_verified_paraphrase_release_candidate(_queue()["packets"])
    assert res["manifest"]["signed_count"] == 0  # no verdict -> nothing signed
    assert res["work_order"][0]["reason"] == "no_governed_faithful_verdict"


def test_signer_signs_governed_faithful_verdict_into_separate_weaker_class():
    p = _queue()["packets"][0]
    p = {**p, "review_verdict": "faithful", "reviewer_role": "human_reviewer", "reviewer_id": "rev_42"}
    res = PR.sign_verified_paraphrase_release_candidate([p])
    m, recs = res["manifest"], res["records"]
    assert m["signed_count"] == 1
    assert m["namespace"] == PR.PARAPHRASE_NAMESPACE != FKC.TEXTBOOK_KNOWLEDGE_NAMESPACE
    assert m["verbatim_authority_records"] == 0
    assert FKC.verify_lane_bundle(res, PR.PARAPHRASE_NAMESPACE) is True
    r = recs[0]
    assert r["provenance_class"] == "verified_paraphrase"
    assert r["official_answer_capable"] is False
    assert r["answer_key_authority"] == "paraphrase_teaching_context_not_verbatim"
    assert r["grounded_key_numbers"] == ["5", "50", "100"]
    assert r["reviewer_id"] == "rev_42"


def test_signer_rejects_ungoverned_reviewer():
    p = _queue()["packets"][0]
    p = {**p, "review_verdict": "faithful", "reviewer_role": "model_vote", "reviewer_id": "opus"}
    res = PR.sign_verified_paraphrase_release_candidate([p])
    assert res["manifest"]["signed_count"] == 0
    assert res["work_order"][0]["reason"] == "no_governed_faithful_verdict"


def test_signer_rejects_ungrounded_number_even_if_faithful():
    # reviewer marks faithful, but the claim carries a number 999 absent from the source -> laundering
    card = {**_CARD, "key_numbers": ["5", "999"]}
    q = PR.build_review_queue([_WO], {_WO["point_id"]: card}, {"1A411011_024_0045": _SOURCE})
    p = {**q["packets"][0], "review_verdict": "faithful",
         "reviewer_role": "governed_council", "reviewer_id": "council_1"}
    res = PR.sign_verified_paraphrase_release_candidate([p])
    assert res["manifest"]["signed_count"] == 0
    assert res["work_order"][0]["reason"] == "key_number_not_grounded_in_source"
