"""Textbook knowledge through the deep_question runtime wrapper (increment ① · runtime).

Proves the thin hook gating (flag / cohort / kill / node_code) and append-only legacy safety over a
hermetic signed textbook supply. Hermetic (no LLM, no network).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from deeptutor.capabilities import deep_question as dq
from deeptutor.services.construction_grading import compiler_pipeline as P
from deeptutor.services.construction_grading import feedback_ingest_bridge as B
from deeptutor.services.construction_grading import textbook_knowledge_runtime as RT
from deeptutor.services.construction_grading import textbook_knowledge_worker as W

KEY = "luban_textbook_knowledge"
_CORPUS = "建筑高度大于27m且不大于100m的住宅建筑为高层民用建筑。低层或多层住宅建筑高度不大于27m。"
_BLOCK = {
    "chunk_id": "1A411011_001_0001", "content_markdown": _CORPUS,
    "taxonomy": {"node_code": "1A411011", "taxonomy_path": "x"},
    "knowledge_cards": [{"card_title": "高层", "card_type": "强制条文(数值)",
                         "card_content": "低层或多层住宅建筑高度不大于27m。", "key_numbers": ["27m"]}],
}


@pytest.fixture
def supply(tmp_path, monkeypatch):
    ev = B.ingest_sources(textbook_blocks=[_BLOCK], run_id="w-1")
    bundle = P.run_pipeline(ev, run_id="w-1", llm_worker=W.default_textbook_block_worker,
                            lane="textbook", max_iter=1)["signed_bundle"]
    d = tmp_path / "supply"
    d.mkdir()
    (d / "textbook_knowledge_release_candidate.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    (d / "canonical_pointer.json").write_text(json.dumps(
        {"namespace": "textbook_knowledge_full", "status": "release_candidate", "published": False,
         "expected_content_hash": bundle["manifest"]["content_hash"]}), "utf-8")
    monkeypatch.setattr(RT, "_SUPPLY_DIR", d)
    # keep the four-source canonical lane hermetic: point it at an empty dir so it falls through
    # (its own behaviour is covered by test_canonical_knowledge_runtime).
    from deeptutor.services.construction_grading import canonical_knowledge_runtime as CK
    monkeypatch.setattr(CK, "_SUPPLY_DIR", tmp_path / "no_canonical")
    CK._load.cache_clear()
    monkeypatch.delenv("LUBAN_TEXTBOOK_KNOWLEDGE_ENABLED", raising=False)
    RT._load_supply.cache_clear()
    yield
    RT._load_supply.cache_clear()
    CK._load.cache_clear()


def _ctx(*, flag, user_id="qa_t"):
    md = {"user_id": user_id}
    if flag:
        md["grading_engine_textbook_knowledge"] = True
    return SimpleNamespace(metadata=md, config_overrides={})


def _legacy():
    return {"construction_grading_result": {"a": 1}}


def test_flag_off_legacy_untouched(supply):
    p = _legacy()
    before = dict(p["construction_grading_result"])
    dq._maybe_attach_textbook_knowledge(context=_ctx(flag=False), graded_context={"node_code": "1A411011"}, result_payload=p)
    assert KEY not in p and p["construction_grading_result"] == before


def test_non_cohort_blocked(supply):
    p = _legacy()
    dq._maybe_attach_textbook_knowledge(context=_ctx(flag=True, user_id="real_1"), graded_context={"node_code": "1A411011"}, result_payload=p)
    assert KEY not in p


def test_cohort_node_attaches_teaching_context(supply):
    p = _legacy()
    legacy_before = dict(p["construction_grading_result"])
    dq._maybe_attach_textbook_knowledge(context=_ctx(flag=True, user_id="qa_alice"), graded_context={"node_code": "1A411011"}, result_payload=p)
    assert p[KEY]["mode"] == "textbook_knowledge_node"
    assert p[KEY]["card_count"] == 1
    assert p[KEY]["official_score_allowed"] is False  # teaching context, not an official score
    assert p["construction_grading_result"] == legacy_before  # append-only


def test_no_node_code_attaches_nothing(supply):
    p = _legacy()
    dq._maybe_attach_textbook_knowledge(context=_ctx(flag=True, user_id="qa_alice"), graded_context={}, result_payload=p)
    assert KEY not in p


def test_auto_maps_question_id_to_node(supply):
    # no explicit node_code; the question_id embeds 1A411011 -> auto-mapped (exact) to textbook context
    p = _legacy()
    dq._maybe_attach_textbook_knowledge(
        context=_ctx(flag=True, user_id="qa_alice"),
        graded_context={"question_id": "QTZ_1A411011_SMR_x", "user_answer": "A"},
        result_payload=p,
    )
    assert p[KEY]["mode"] == "textbook_knowledge_node"
    assert p[KEY]["node_match"] == "exact"
    assert p[KEY]["card_count"] == 1


def test_unmappable_question_id_attaches_nothing(supply):
    p = _legacy()
    dq._maybe_attach_textbook_knowledge(
        context=_ctx(flag=True, user_id="qa_alice"),
        graded_context={"question_id": "QTZ_1A511011_x", "user_answer": "A"},  # node not in pack
        result_payload=p,
    )
    assert KEY not in p


def test_kill_switch_tombstone(supply, monkeypatch):
    monkeypatch.setenv("LUBAN_TEXTBOOK_KNOWLEDGE_ENABLED", "off")
    p = _legacy()
    dq._maybe_attach_textbook_knowledge(context=_ctx(flag=True, user_id="qa_alice"), graded_context={"node_code": "1A411011"}, result_payload=p)
    assert p[KEY]["status"] == "killed_by_switch"
