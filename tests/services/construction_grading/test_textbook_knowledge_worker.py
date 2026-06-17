"""Textbook verbatim lane — S2 worker + end-to-end run_pipeline(lane="textbook").

Proves the worker proposes only verbatim spans (paraphrase → None), and the full pipeline signs a
verbatim card, work-orders an external-GB card and a synthesis card, promotes ONLY in S5, and the
bundle verifies. Hermetic (no LLM).
"""
from __future__ import annotations

from deeptutor.services.construction_grading import compiled_registry_resolver as R
from deeptutor.services.construction_grading import compiler_pipeline as P
from deeptutor.services.construction_grading import feedback_ingest_bridge as B
from deeptutor.services.construction_grading import full_knowledge_compiler as FKC
from deeptutor.services.construction_grading import textbook_knowledge_worker as W

_CORPUS = "建筑高度大于27m且不大于100m的住宅建筑为高层民用建筑。低层或多层住宅建筑高度不大于27m。"
_BLOCK = {
    "chunk_id": "1A411011_001_0001",
    "content_markdown": _CORPUS,
    "taxonomy": {"node_code": "1A411011", "taxonomy_path": "建筑工程技术 > 建筑设计"},
    "knowledge_cards": [
        {"card_title": "高层分类", "card_type": "强制条文(数值)",
         "card_content": "低层或多层住宅建筑高度不大于27m。", "key_numbers": ["27m"]},        # verbatim + num
        {"card_title": "放射性限量", "card_type": "强制条文(数值)",
         "card_content": "根据《建筑材料放射性核素限量》GB 6566-2010: A类 ≤1.0", "key_numbers": ["1.0"]},  # external
        {"card_title": "记忆口诀", "card_type": "记忆型",
         "card_content": "这是一段合成讲解口诀没有教材原文逐字依据", "key_numbers": []},        # synthesis
    ],
}


def test_worker_finds_verbatim_span_only():
    card_ok = _BLOCK["knowledge_cards"][0]
    assert W.find_verbatim_span(card_ok, _CORPUS) == "低层或多层住宅建筑高度不大于27m"
    card_paraphrase = {"card_content": "高度超过二十七米的住宅算高层", "card_title": "x"}
    assert W.find_verbatim_span(card_paraphrase, _CORPUS) is None
    card_external = _BLOCK["knowledge_cards"][1]
    assert W.find_verbatim_span(card_external, _CORPUS) is None  # GB clause not in block body


def test_worker_emits_candidate_per_card_through_make_candidate():
    ev = B.make_evidence_item(evidence_kind="textbook_block", payload=_BLOCK)
    cands = W.default_textbook_block_worker(ev)
    assert len(cands) == 3
    assert all(c["namespace"] == "luban_compiler_candidate" for c in cands)
    assert all(c["promote_to_release"] is False for c in cands)  # never promotable at birth
    assert all(c["payload"]["content_markdown"] == _CORPUS for c in cands)  # same-block corpus


def test_textbook_lane_end_to_end_signs_only_verbatim():
    ev = B.ingest_sources(textbook_blocks=[_BLOCK], run_id="tb-1")
    res = P.run_pipeline(ev, run_id="tb-1", llm_worker=W.default_textbook_block_worker,
                         lane="textbook", max_iter=1)
    bundle = res["signed_bundle"]
    assert bundle is not None
    assert FKC.verify_lane_bundle(bundle, "textbook_knowledge_full") is True
    assert bundle["manifest"]["signed_count"] == 1                 # only the verbatim card
    assert bundle["manifest"]["work_order_count"] == 2            # external + synthesis
    rec = bundle["records"][0]
    assert rec["provenance_class"] == "textbook_authority"
    assert rec["node_code"] == "1A411011"
    assert rec["key_numbers"] == ["27m"]
    # node_index present so the resolver can resolve by node_code
    assert bundle["manifest"]["node_index"]["1A411011"] == [rec["point_id"]]


def test_textbook_lane_promote_only_in_s5_and_safety_clean():
    ev = B.ingest_sources(textbook_blocks=[_BLOCK], run_id="tb-2")
    res = P.run_pipeline(ev, run_id="tb-2", llm_worker=W.default_textbook_block_worker,
                         lane="textbook", max_iter=1)
    s = res["safety"]
    assert s["illegit_promote_outside_s5"] == 0
    assert s["candidate_used_as_release_truth"] == 0
    assert s["key_number_not_in_text_signed"] == 0
    assert s["external_or_reviewonly_auto_signed"] == 0
    assert s["published"] is False
    assert s["canonical_truth_written"] is False
    assert s["tamper_fail_closed"] is True
    promoted = [c for c in res["candidates"] if c.get("promote_to_release") is True]
    assert len(promoted) == 1
    assert any(e.get("stage") == "S5" for e in promoted[0]["stage_log"])


def test_resolver_node_handoff_authority_is_server_kwarg_only():
    ev = B.ingest_sources(textbook_blocks=[_BLOCK], run_id="tb-3")
    res = P.run_pipeline(ev, run_id="tb-3", llm_worker=W.default_textbook_block_worker,
                         lane="textbook", max_iter=1)
    bundle = res["signed_bundle"]
    pointer = {"namespace": "textbook_knowledge_full", "status": "release_candidate",
               "published": False, "expected_content_hash": bundle["manifest"]["content_hash"]}
    # resolve a signed node
    resolution = R.resolve_node("1A411011", bundle=bundle, pointer=pointer)
    assert resolution is not None
    assert resolution["rubric"]["card_count"] == 1
    # granted -> controlled official; ungranted -> not official (authority is the server kwarg)
    on = R.build_pack_for_node("1A411011", bundle=bundle, pointer=pointer, grant_release=True)
    off = R.build_pack_for_node("1A411011", bundle=bundle, pointer=pointer, grant_release=False)
    assert on.to_dict()["diagnostic_policy"]["official_score_allowed"] is True
    assert off.to_dict()["diagnostic_policy"]["official_score_allowed"] is False
    # unknown node + tamper fall through
    assert R.resolve_node("1A999999", bundle=bundle, pointer=pointer) is None
    bundle["records"][0]["key_numbers"] = ["999"]
    assert R.resolve_node("1A411011", bundle=bundle, pointer=pointer) is None  # tamper fail-closed
