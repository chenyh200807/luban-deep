"""M25-H: signed release_candidate supply — loader, prefer-over-real, tamper/missing fail-closed."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from deeptutor.services.construction_grading import v2_objective_supply_loader as L


def test_release_candidate_loads_and_verifies():
    r = L.load_release_candidate()
    assert r["verified"] is True
    assert r["status"] == "release_candidate"
    assert len(r["index"]) > 0
    # governed authority + not published
    assert r["manifest"]["published"] is False
    assert r["manifest"]["production_default_connected"] is False
    assert r["manifest"]["source_table"] == "questions_bank"


def test_best_available_prefers_release_candidate():
    best = L.load_best_available()
    assert best["verified"] is True
    assert best["tier"] == "release_candidate"


def test_release_candidate_records_are_governed_real_exam():
    r = L.load_release_candidate()
    for rec in list(r["index"].values())[:50]:
        assert rec["source_ref"]["table"] == "questions_bank"
        assert rec["source_type"] == "REAL_EXAM"
        assert rec["answer_key"]
        assert rec["answer_key_hash"]


def test_release_candidate_tamper_fail_closed(tmp_path):
    shutil.copy(L._RC_DIR / "objective_answer_key_seed_release.jsonl",
                tmp_path / "objective_answer_key_seed_real.jsonl")
    shutil.copy(L._RC_DIR / "runtime_supply_v2_manifest.json", tmp_path)
    seed = tmp_path / "objective_answer_key_seed_real.jsonl"
    lines = seed.read_text().splitlines()
    o = json.loads(lines[0]); o["answer_key"] = "ZZZ"; lines[0] = json.dumps(o, ensure_ascii=False)
    seed.write_text("\n".join(lines) + "\n")
    assert L.load_and_verify(tmp_path)["verified"] is False  # tamper -> fail-closed


def test_release_candidate_published_status_rejected(tmp_path):
    shutil.copy(L._RC_DIR / "objective_answer_key_seed_release.jsonl",
                tmp_path / "objective_answer_key_seed_real.jsonl")
    man = json.loads((L._RC_DIR / "runtime_supply_v2_manifest.json").read_text())
    man["published"] = True
    (tmp_path / "runtime_supply_v2_manifest.json").write_text(json.dumps(man, ensure_ascii=False))
    assert L.load_and_verify(tmp_path)["verified"] is False  # published -> rejected by loader


def test_no_llm_or_vote_in_records():
    r = L.load_release_candidate()
    blob = json.dumps(list(r["index"].values())[:100])
    for banned in ("model_vote", "council_vote", "rag_chunk", "llm_inferred"):
        assert banned not in blob
