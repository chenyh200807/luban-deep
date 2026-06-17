"""Living LLM Artifact Compiler — compiled registry resolver (S6 seam).

Proves the signed case-rubric bundle reaches the runtime context pack through the four-gate verify,
that release authority is granted ONLY by the server-side grant (not the bundle/client), and that
tamper / status / pinned-hash / namespace failures fall through (None), never mint authority.
Hermetic.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import compiled_registry_resolver as R
from deeptutor.services.construction_grading import full_knowledge_compiler as FKC

_NS = "case_rubric_full"


def _signed_bundle():
    """Build a signed case-rubric bundle with a manifest question_index (P1,P2 -> Q1)."""
    points = [
        {"point_id": "Q1::P1", "authority_kind": "calc", "text": "工期顺延 25 天",
         "machine_spec": {"kind": "machine_checkable_calc", "expected": 25}, "required_terms": ["顺延"]},
        {"point_id": "Q1::P2", "authority_kind": "logic", "text": "索赔成立", "required_terms": ["索赔"]},
    ]
    bundle = FKC.compile_case_rubric_release_candidate(points)
    bundle["manifest"]["question_index"] = {"Q1": ["Q1::P1", "Q1::P2"]}
    pointer = {"namespace": _NS, "status": "release_candidate", "published": False,
               "expected_content_hash": bundle["manifest"]["content_hash"]}
    return bundle, pointer


def test_verify_bundle_passes_for_signed():
    bundle, pointer = _signed_bundle()
    ok, reason = R.verify_bundle(bundle, pointer, namespace=_NS)
    assert ok is True and reason == "ok"


def test_resolve_question_returns_rubric():
    bundle, pointer = _signed_bundle()
    res = R.resolve_question("Q1", bundle=bundle, pointer=pointer, namespace=_NS)
    assert res is not None
    assert res["status"] == "resolved"
    assert res["question_type"] == "case"
    assert res["rubric"]["point_count"] == 2
    assert set(res["required_terms"]) == {"顺延", "索赔"}


def test_grant_release_controls_official_score():
    bundle, pointer = _signed_bundle()
    # server grants release -> controlled official allowed
    pack_on = R.build_pack_for_question("Q1", bundle=bundle, pointer=pointer, namespace=_NS, grant_release=True)
    pol_on = pack_on.to_dict()["diagnostic_policy"]
    assert pol_on["official_score_allowed"] is True
    assert pol_on["controlled_official"] is True
    # SAME signed bundle, no server grant -> NOT official (authority is the kwarg, never the bundle)
    pack_off = R.build_pack_for_question("Q1", bundle=bundle, pointer=pointer, namespace=_NS, grant_release=False)
    assert pack_off.to_dict()["diagnostic_policy"]["official_score_allowed"] is False


def test_unknown_question_falls_through():
    bundle, pointer = _signed_bundle()
    assert R.resolve_question("NOPE", bundle=bundle, pointer=pointer, namespace=_NS) is None
    assert R.build_pack_for_question("NOPE", bundle=bundle, pointer=pointer, namespace=_NS, grant_release=True) is None


def test_tamper_falls_through():
    bundle, pointer = _signed_bundle()
    bundle["records"][0]["machine_spec"] = {"kind": "tampered"}  # mutate without re-signing
    ok, reason = R.verify_bundle(bundle, pointer, namespace=_NS)
    assert ok is False and reason == "verify_lane_bundle_failed"
    assert R.resolve_question("Q1", bundle=bundle, pointer=pointer, namespace=_NS) is None


def test_pinned_hash_mismatch_falls_through():
    bundle, pointer = _signed_bundle()
    pointer["expected_content_hash"] = "deadbeef"
    ok, reason = R.verify_bundle(bundle, pointer, namespace=_NS)
    assert ok is False and reason == "pinned_hash_mismatch"


def test_published_status_falls_through():
    bundle, pointer = _signed_bundle()
    bundle["manifest"]["published"] = True
    ok, reason = R.verify_bundle(bundle, pointer, namespace=_NS)
    assert ok is False  # published bundle never trusted at runtime


def test_namespace_mismatch_falls_through():
    bundle, pointer = _signed_bundle()
    ok, reason = R.verify_bundle(bundle, pointer, namespace="objective_answer_key_full")
    assert ok is False  # signature is over (hash|namespace|status); wrong namespace fails


def test_relevance_rank_focuses_and_caps():
    cards = [
        {"point_id": "p1", "textbook_quote": "混凝土强度等级C30", "taxonomy_path": "结构 > 材料",
         "required_terms": ["C30"], "key_numbers": ["30"]},
        {"point_id": "p2", "textbook_quote": "填方压实分层厚度250mm", "taxonomy_path": "施工 > 土方",
         "required_terms": ["250mm"], "key_numbers": ["250"]},
        {"point_id": "p3", "textbook_quote": "桩基低应变法检测桩身缺陷", "taxonomy_path": "施工 > 桩基",
         "required_terms": [], "key_numbers": []},
    ]
    top = R._relevance_rank(cards, "关于混凝土强度C30的问题", limit=1)
    assert [c["point_id"] for c in top] == ["p1"]  # only the most relevant card
    # zero-overlap query -> first-by-point_id, still capped (never the whole dump)
    none = R._relevance_rank(cards, "完全无关的外星语", limit=2)
    assert [c["point_id"] for c in none] == ["p1", "p2"]
    # limit<=0 -> all, point_id-sorted
    allc = R._relevance_rank(cards, "C30", limit=0)
    assert [c["point_id"] for c in allc] == ["p1", "p2", "p3"]
