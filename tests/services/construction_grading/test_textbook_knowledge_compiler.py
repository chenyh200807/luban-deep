"""Textbook verbatim lane — the deterministic signer + provenance classifier (the authority core).

Adversarially proves the 5 must-fix provenance guards: corpus-internal verbatim check, per-number
provenance, per-field signing, same-block corpus, narrow symmetric normalization. Nothing signs
unless its claim is verbatim in its OWN block's content_markdown. Hermetic.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import full_knowledge_compiler as FKC

_NS = "textbook_knowledge_full"
_CORPUS = "建筑高度大于27m且不大于100m的住宅建筑为高层民用建筑。低层或多层住宅建筑高度不大于27m。"
_NODE = "1A411011"


def _card(**kw):
    base = {"chunk_id": "1A411011_001_0001", "node_code": _NODE, "content_markdown": _CORPUS,
            "card_type": "强制条文(数值)", "card_content": "", "key_numbers": [], "exact_quote": None,
            "taxonomy_path": "建筑工程技术 > 建筑设计", "point_id": "1A411011_001_0001::C0"}
    base.update(kw)
    return base


def test_verbatim_authority_signs():
    c = _card(exact_quote="建筑高度大于27m且不大于100m的住宅建筑为高层民用建筑", key_numbers=["27m", "100m"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 1
    rec = out["records"][0]
    assert rec["provenance_class"] == "textbook_authority"
    assert rec["key_numbers"] == ["27m", "100m"]  # both verbatim in corpus
    assert FKC.verify_lane_bundle(out, _NS) is True
    assert out["manifest"]["published"] is False


def test_machine_spec_signs_only_confirmed_numbers():
    # one number in corpus (27m), one NOT (500mm from an external citation) -> sign only 27m
    c = _card(key_numbers=["27m", "500mm"], card_content="根据《民用建筑设计统一标准》GB 50352—2019: 27m ... 500mm")
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 1
    rec = out["records"][0]
    assert rec["provenance_class"] == "machine_spec"
    assert rec["key_numbers"] == ["27m"]          # 500mm stripped (not in block body)
    assert "500mm" not in rec["required_terms"]


def test_external_standard_not_signed():
    # GB-cited numbers NOT in the block body -> external work_order, never textbook
    c = _card(content_markdown="放射性核素的限量应符合相关规定。",
              card_content="根据《建筑材料放射性核素限量》GB 6566-2010: A类 ≤1.0, B类 ≤1.3",
              key_numbers=["1.0", "1.3"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0
    assert out["manifest"]["work_order_count"] == 1
    assert out["work_order"][0]["provenance_class"] == "external_standard"


def test_synthesis_not_signed():
    c = _card(exact_quote=None, key_numbers=[], card_content="这是一段没有原文逐字依据的合成讲解口诀。")
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0
    assert out["work_order"][0]["provenance_class"] == "synthesis"


def test_card_title_mnemonics_logic_chain_never_in_authority_surface():
    c = _card(exact_quote="低层或多层住宅建筑高度不大于27m", key_numbers=["27m"],
              card_title="建筑高度分类(27m/100m)", mnemonics="27分界线", logic_chain="IF h<=27 THEN low")
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    rec = out["records"][0]
    assert "card_title" not in rec
    assert "mnemonics" not in rec
    assert "logic_chain" not in rec
    # the signed quote is the verbatim span, NOT the synthesized title
    assert rec["textbook_quote"] == "低层或多层住宅建筑高度不大于27m"


def test_cross_block_contamination_blocked():
    # quote belongs to a DIFFERENT block; this block's own content_markdown does NOT contain it
    c = _card(content_markdown="本条讲的是地基基础，与高度分类无关。",
              exact_quote="建筑高度大于27m的住宅建筑为高层民用建筑", key_numbers=[])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0  # corpus is THIS block only -> not verbatim here


def test_min_span_rejects_short_quote():
    c = _card(exact_quote="高层", key_numbers=[])  # too short
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0


def test_high_frequency_boilerplate_rejected():
    c = _card(exact_quote="应符合相关规定", key_numbers=[], content_markdown="放射性应符合相关规定的要求。",
              _freq_blocklist=[FKC._norm_textbook("应符合相关规定")])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0  # boilerplate present in many blocks -> not an anchor


def test_full_width_digit_normalizes():
    # quote uses full-width ２７ but corpus has half-width 27 -> must still pass (no dishonest tanking)
    c = _card(exact_quote="建筑高度大于２７ｍ且不大于100m的住宅建筑为高层民用建筑", key_numbers=["27m"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 1


def test_paraphrase_rejected():
    c = _card(exact_quote="高度超过二十七米的住宅是高层", key_numbers=[])  # paraphrase, not verbatim
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0


def test_missing_node_code_dropped():
    c = _card(node_code="not-a-node", exact_quote="低层或多层住宅建筑高度不大于27m")
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert out["manifest"]["signed_count"] == 0
    assert out["manifest"]["dropped_count"] == 1


def test_tamper_fails_closed():
    c = _card(exact_quote="低层或多层住宅建筑高度不大于27m", key_numbers=["27m"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    assert FKC.verify_lane_bundle(out, _NS) is True
    out["records"][0]["key_numbers"] = ["999"]  # mutate without re-signing
    assert FKC.verify_lane_bundle(out, _NS) is False


def test_calc_card_splits_printed_vs_derived_numbers():
    # 连环替代法 worked example: 520/720 printed in text; 14560 only ever as an "=" result (derived)
    corpus = ("产量计划值 500，实际值 520。单价实际值 720 元。\n"
              "- 第一次替换与目标的差额 = 378560 - 364000 = 14560 元，说明成本增加 14560 元。")
    c = _card(content_markdown=corpus, exact_quote="第一次替换与目标的差额",
              key_numbers=["520", "720", "14560"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    rec = out["records"][0]
    assert rec["has_derived_numbers"] is True
    assert "14560" in rec["derived_key_numbers"]      # only appears as an "=" result -> derived
    assert "14560" not in rec["key_numbers"]          # never an authoritative textbook number
    assert "14560" not in rec["required_terms"]
    assert "520" in rec["key_numbers"] and "720" in rec["key_numbers"]  # printed values kept
    assert out["manifest"]["records_with_derived_numbers"] == 1


def test_non_calc_card_has_no_derived_numbers():
    c = _card(exact_quote="低层或多层住宅建筑高度不大于27m", key_numbers=["27m"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    rec = out["records"][0]
    assert rec["has_derived_numbers"] is False
    assert rec["derived_key_numbers"] == []
    assert rec["key_numbers"] == ["27m"]              # unchanged for non-calc cards


def test_namespace_isolation():
    c = _card(exact_quote="低层或多层住宅建筑高度不大于27m", key_numbers=["27m"])
    out = FKC.compile_textbook_knowledge_release_candidate([c])
    # signed for textbook namespace; verifying under a different lane fails
    assert FKC.verify_lane_bundle(out, "case_rubric_full") is False
