"""§6.5 等值配对表单构建闸(难度锚修正:变体 anchor 判据,不读难度列)。"""

from __future__ import annotations

import inspect

import pytest

from deeptutor.services.assessment import form_equivalence_gate as gate


def test_parse_kc_anchor_with_brace_exam_refs() -> None:
    parsed = gate.parse_equivalence_anchor(
        "kc:1A413030_123_0234:0 + {2016,第27题} + {2019,第1题第3问}"
    )
    assert parsed["kc_leaves"] == ("1A413030_123_0234",)
    assert parsed["kc_refs"] == ("1A413030_123_0234:0",)
    assert parsed["exam_refs"] == (("2016", "第27题"), ("2019", "第1题第3问"))


def test_parse_exam_colon_and_bare_forms() -> None:
    assert gate.parse_equivalence_anchor("exam:2021:第8题")["exam_refs"] == (
        ("2021", "第8题"),
    )
    assert gate.parse_equivalence_anchor("kc:1A435000_044_0059:0 + 2022第(四)题")[
        "exam_refs"
    ] == (("2022", "第(四)题"),)
    # 多 kc 锚(合并叶)与无真题引用的裸 kc 锚。
    multi = gate.parse_equivalence_anchor(
        "kc:1A433000_052_0077:0 + kc:1A433000_053_0078:0"
    )
    assert multi["kc_leaves"] == ("1A433000_052_0077", "1A433000_053_0078")
    assert multi["exam_refs"] == ()


def _original() -> dict:
    # 编译轻练 MCQ 透传面形态(compiled provider source_meta)。
    return {
        "fact_id": "c01-fact-joint-location-by-member",
        "rule_group": "施工缝·位置",
        "anchor": "kc:1A413030_103_0196:0 + {2021,第8题}",
    }


def _retest() -> dict:
    # 变体池条目形态(同 leaf 同采分点同真题锚,表面换面)。
    return {
        "fact_id": "c01-fact-joint-location-by-member",
        "rule_group": "施工缝·位置",
        "anchor": "kc:1A413030_103_0196:1 + {2021,第8题}",
    }


def test_equivalent_pair_same_leaf_scoring_point_and_exam_anchor() -> None:
    verdict = gate.retest_pair_verdict(_original(), _retest())
    assert verdict["equivalent"] is True
    assert verdict["reasons"] == ()
    assert verdict["original"]["leaf"] == "1A413030_103_0196"


def test_leaf_mismatch_fails() -> None:
    retest = dict(_retest(), anchor="kc:1A434000_074_0116:0 + {2021,第8题}")
    verdict = gate.retest_pair_verdict(_original(), retest)
    assert verdict["equivalent"] is False
    assert any(r.startswith("leaf_mismatch") for r in verdict["reasons"])


def test_scoring_point_mismatch_fails() -> None:
    retest = dict(_retest(), fact_id="c01-fact-other")
    verdict = gate.retest_pair_verdict(_original(), retest)
    assert verdict["equivalent"] is False
    # fact 变了 → leaf 相同(kc 锚仍在)但采分点失配。
    assert any(r.startswith("scoring_point_mismatch") for r in verdict["reasons"])


def test_missing_real_exam_anchor_fails_either_side() -> None:
    verdict = gate.retest_pair_verdict(
        dict(_original(), anchor="kc:1A413030_103_0196:0"), _retest()
    )
    assert "real_exam_anchor_missing:original" in verdict["reasons"]
    verdict = gate.retest_pair_verdict(
        _original(), dict(_retest(), anchor="kc:1A413030_103_0196:1")
    )
    assert "real_exam_anchor_missing:retest" in verdict["reasons"]


def test_different_exam_anchor_band_fails() -> None:
    retest = dict(_retest(), anchor="kc:1A413030_103_0196:1 + {2015,第26题}")
    verdict = gate.retest_pair_verdict(_original(), retest)
    assert "real_exam_anchor_mismatch" in verdict["reasons"]


def test_fact_id_is_leaf_surrogate_when_kc_absent() -> None:
    original = {
        "fact_id": "c01-fact-joint-location-by-member",
        "source_anchor": "exam:2021:第8题",
    }
    retest = {
        "fact_id": "c01-fact-joint-location-by-member",
        "anchor": "2021第8题",
    }
    verdict = gate.retest_pair_verdict(original, retest)
    assert verdict["equivalent"] is True
    assert verdict["original"]["leaf"] == "fact:c01-fact-joint-location-by-member"


def test_gate_passes_all_equivalent_pairs_and_fails_the_form_otherwise() -> None:
    ok = gate.validate_form_retest_pairs(
        [{"pair_id": "p1", "original": _original(), "retest": _retest()}]
    )
    assert ok == {"pairs": 1, "passed": 1, "failures": []}

    with pytest.raises(gate.FormEquivalenceGateError) as excinfo:
        gate.validate_form_retest_pairs(
            [
                {"pair_id": "p1", "original": _original(), "retest": _retest()},
                {
                    "pair_id": "p2",
                    "original": _original(),
                    "retest": dict(_retest(), anchor="kc:1A413030_103_0196:1"),
                },
            ]
        )
    assert "p2" in str(excinfo.value)
    assert "real_exam_anchor_missing:retest" in str(excinfo.value)


def test_empty_pair_list_is_rejected_not_silently_passed() -> None:
    with pytest.raises(gate.FormEquivalenceGateError, match="no_retest_pairs_declared"):
        gate.validate_form_retest_pairs([])


def test_gate_never_reads_questions_bank_difficulty_column() -> None:
    # 难度锚修正的机械防复发闸:判据模块源码零 difficulty 触点——
    # 等值真值只来自 leaf/采分点/真题锚,questions_bank 的难度列(量纲混乱,
    # 盘点 2026-08-06 实证)在本模块没有任何读取入口。
    source = inspect.getsource(gate)
    assert "difficulty" not in source
