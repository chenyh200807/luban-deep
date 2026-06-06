"""Textbook knowledge runtime consumer (increment ① · runtime).

Proves the signed textbook pack resolves into verbatim teaching/source context, that release
authority is the server kwarg only (F1), and that tamper / missing supply fall through. Hermetic:
builds a small signed bundle in a temp supply dir (never touches the tracked supply).
"""
from __future__ import annotations

import json

import pytest

from deeptutor.services.construction_grading import compiler_pipeline as P
from deeptutor.services.construction_grading import feedback_ingest_bridge as B
from deeptutor.services.construction_grading import textbook_knowledge_runtime as RT
from deeptutor.services.construction_grading import textbook_knowledge_worker as W

_CORPUS = "建筑高度大于27m且不大于100m的住宅建筑为高层民用建筑。低层或多层住宅建筑高度不大于27m。"
_BLOCK = {
    "chunk_id": "1A411011_001_0001", "content_markdown": _CORPUS,
    "taxonomy": {"node_code": "1A411011", "taxonomy_path": "建筑工程技术 > 建筑设计"},
    "knowledge_cards": [
        {"card_title": "高层分类", "card_type": "强制条文(数值)",
         "card_content": "低层或多层住宅建筑高度不大于27m。", "key_numbers": ["27m"]},
    ],
}


@pytest.fixture
def supply(tmp_path, monkeypatch):
    ev = B.ingest_sources(textbook_blocks=[_BLOCK], run_id="rt-1")
    res = P.run_pipeline(ev, run_id="rt-1", llm_worker=W.default_textbook_block_worker,
                         lane="textbook", max_iter=1)
    bundle = res["signed_bundle"]
    d = tmp_path / "supply"
    d.mkdir()
    (d / "textbook_knowledge_release_candidate.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    (d / "canonical_pointer.json").write_text(json.dumps(
        {"namespace": "textbook_knowledge_full", "status": "release_candidate", "published": False,
         "expected_content_hash": bundle["manifest"]["content_hash"]}), "utf-8")
    monkeypatch.setattr(RT, "_SUPPLY_DIR", d)
    RT._load_supply.cache_clear()
    yield
    RT._load_supply.cache_clear()


def test_available_nodes(supply):
    assert "1A411011" in RT.available_nodes()


def test_resolve_grant_controls_official(supply):
    on = RT.resolve_textbook_knowledge("1A411011", grant_release=True)
    assert on is not None
    assert on["mode"] == "textbook_knowledge_node"
    assert on["card_count"] == 1
    assert on["provenance"] == "verbatim_2026_textbook_content_markdown"
    assert on["official_score_allowed"] is True
    assert on["controlled_official"] is True
    assert on["llm_may_decide_correctness"] is False
    # same signed pack, no server grant -> teaching/source context, not official
    off = RT.resolve_textbook_knowledge("1A411011", grant_release=False)
    assert off["official_score_allowed"] is False
    assert off["not_production_grade"] is True


def test_unknown_node_and_tamper_fall_through(supply, tmp_path, monkeypatch):
    assert RT.resolve_textbook_knowledge("1A999999") is None
    # tamper the on-disk bundle -> verify fails -> resolve falls through
    bundle_path = RT._SUPPLY_DIR / "textbook_knowledge_release_candidate.json"
    b = json.loads(bundle_path.read_text("utf-8"))
    b["records"][0]["textbook_quote"] = "篡改"
    bundle_path.write_text(json.dumps(b, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    RT._load_supply.cache_clear()
    assert RT.resolve_textbook_knowledge("1A411011") is None


def test_node_code_for_question_exact_and_section_and_miss(supply):
    # exact: the question's own node IS a textbook node
    assert RT.node_code_for_question("QTZ_1A411011_SMR_x") == ("1A411011", "exact")
    # section: shares the longest unique >=6-char prefix with the one textbook node 1A411011
    assert RT.node_code_for_question("q_1A411019_y") == ("1A411011", "section")
    # too-shallow prefix (only "1A" shared) -> fall open
    assert RT.node_code_for_question("q_1A511011_z") is None
    # no node code embedded -> None
    assert RT.node_code_for_question("just a free text question") is None


def test_missing_supply_falls_through(tmp_path, monkeypatch):
    monkeypatch.setattr(RT, "_SUPPLY_DIR", tmp_path / "nope")
    RT._load_supply.cache_clear()
    assert RT.available_nodes() == []
    assert RT.resolve_textbook_knowledge("1A411011") is None
    RT._load_supply.cache_clear()
