from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.luban_grading_metrics import (
    adjacent_agreement,
    agreement_block,
    exact_agreement,
    qwk_for_pairs,
    quadratic_weighted_kappa,
)

REPO = Path(__file__).resolve().parents[2]
BAKE = REPO / "artifacts/luban_consensus_gold/list_rule_semantic_model_bakeoff_20260603"


# ---- QWK math ----

def test_qwk_perfect_agreement_is_one() -> None:
    a = [0, 1, 2, 1, 0, 2]
    assert quadratic_weighted_kappa(a, a) == 1.0


def test_qwk_penalizes_distant_disagreement_more() -> None:
    # adjacent disagreement (1 vs 0) should score higher QWK than distant (2 vs 0)
    base = [0, 1, 2, 1, 2, 0, 1, 2, 0, 1]
    adj = list(base); adj[0] = 1  # off by 1
    far = list(base); far[0] = 2  # off by 2 on a miss
    assert quadratic_weighted_kappa(base, adj) > quadratic_weighted_kappa(base, far)


def test_qwk_handles_constant_rater() -> None:
    # one rater constant, other varies -> not perfect, must not crash
    v = quadratic_weighted_kappa([0, 0, 0, 0], [0, 1, 0, 1])
    assert isinstance(v, float)


def test_qwk_for_pairs_maps_hit_labels() -> None:
    assert qwk_for_pairs(["hit", "partial", "miss"], ["hit", "partial", "miss"]) == 1.0


def test_exact_and_adjacent_agreement() -> None:
    a = [2, 2, 2, 2]  # hit
    b = [2, 1, 0, 2]  # hit, partial, miss, hit
    assert exact_agreement(a, b) == 0.5      # 2 of 4 exact
    assert adjacent_agreement(a, b) == 0.75  # miss(0) vs hit(2) is the only >1 gap


def test_agreement_block_shape() -> None:
    blk = agreement_block(["hit", "partial"], ["hit", "miss"])
    for k in ("points", "qwk", "exact_agreement", "adjacent_agreement"):
        assert k in blk


# ---- governance: QWK is diagnostic, does NOT replace hard gates ----

@pytest.mark.skipif(not (BAKE / "qwk_metric_diagnostics.json").exists(), reason="qwk diagnostics not generated")
def test_qwk_diagnostics_declares_hard_gates_unchanged() -> None:
    d = json.loads((BAKE / "qwk_metric_diagnostics.json").read_text(encoding="utf-8"))
    # the artifact must explicitly state the zero-tolerance hard gates remain binding
    hg = d["hard_gates_unchanged"]
    assert any("exact_required_major_violation==0" in x for x in hg)
    assert any("unsupported_positive==0" in x for x in hg)
    assert "DIAGNOSTIC" in d["note"] or "candidate" in d["note"].lower()
    # raw_score_delta retained as guardrail alongside QWK
    assert "raw_score_delta" in d["list_rule_semantic_protocol"]
    assert "qwk" in d["list_rule_semantic_protocol"]
