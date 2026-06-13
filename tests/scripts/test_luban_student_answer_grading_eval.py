from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "run_luban_student_answer_grading_eval",
    REPO / "scripts" / "run_luban_student_answer_grading_eval.py",
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


def test_parse_student_answer_md_extracts_student_answer(tmp_path):
    path = tmp_path / "samples.md"
    path.write_text(
        """# x
### Q2023-03｜项目质量计划

#### 样本元数据

- 样本ID：`Q2023-03__S06`
- 学生ID：`S06`
- ability_label：`low`
- answer_quality_label：`weak`
- 中文标签：基础薄弱
- 预估得分区间：30%-42%

#### 题目

- 年份：2023
- 来源 chunk：`EXAM_1A434000_P0015_01`

【背景资料】背景

【问题】
1. 问题一？

#### 回答

作答：
问题1：学生答案。

#### 本题水平判断

- 学生归类：基础薄弱
""",
        encoding="utf-8",
    )
    samples = mod.parse_student_answer_md(path)
    assert len(samples) == 1
    sample = samples[0]
    assert sample["sample_id"] == "Q2023-03__S06"
    assert sample["student_id"] == "S06"
    assert sample["score_range"] == [30, 42]
    assert sample["source_chunks"] == ["EXAM_1A434000_P0015_01"]
    assert sample["student_answer"].startswith("问题1：学生答案。")


def test_score_range_hit():
    assert mod._score_range_hit(35, [30, 42]) is True
    assert mod._score_range_hit(55, [30, 42]) is False
    assert mod._score_range_hit(None, [30, 42]) is None


def test_normalize_grading_payload_accepts_common_live_model_keys():
    normalized = mod.normalize_grading_payload(
        {
            "score_percentage": 80,
            "points": [{"sub_no": "1", "status": "hit"}],
            "deductions": ["漏答第2问"],
            "error_tags": ["漏列采分点"],
            "learning_evidence": {"weaknesses": ["桩基检测"]},
            "next_action": {"focus": "检测方法"},
            "evidence_refs": ["ref1"],
        }
    )
    assert normalized["score_pct"] == 80
    assert normalized["point_results"] == [{"sub_no": "1", "status": "hit"}]
    assert normalized["deduction_reasons"] == ["漏答第2问"]
    assert normalized["misconception_tags"] == ["漏列采分点"]
    assert normalized["learning_evidence_event"] == {"weaknesses": ["桩基检测"]}
    assert normalized["next_review_action"] == {"focus": "检测方法"}
    assert normalized["citations"] == ["ref1"]


def test_compact_scoring_artifact_is_point_shaped():
    artifact = mod.build_compact_scoring_artifact(
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 2.0,
                    "question": "指出不妥。",
                    "gold_answer": "项目质量计划应在项目策划过程中编制。应动态管理。",
                }
            ],
        }
    )
    assert artifact["artifact_schema"] == "compact_scoring_artifact.v1"
    assert artifact["source_chunks"] == ["EXAM_X"]
    assert artifact["points"][0]["sub_no"] == "1"
    assert artifact["points"][0]["expected_points"]
    assert artifact["points"][0]["deduction_shape"]["must_emit_next_action"] is True


def test_typed_case_grading_artifact_splits_numbered_subquestions_and_points():
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    artifact = mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 5.0,
                    "question": "1. 三检是什么？\n5. 除墙体节能工程外，建筑节能围护结构节能子部分的分项工程还有哪些？",
                    "gold_answer": "1. 自检、互检、专检。\n5. 除墙体节能工程外，建筑节能围护结构节能子部分的分项工程还有：幕墙节能工程、门窗节能工程、屋面节能工程、地面节能工程。",
                }
            ],
        },
    )
    assert artifact["artifact_schema"] == "case_grading_artifact.v1"
    sub5 = [item for item in artifact["subquestions"] if item["sub_no"] == "5"][0]
    answers = [point["canonical_answer"] for point in sub5["scoring_points"]]
    assert any("幕墙节能工程" in answer for answer in answers)
    assert any("门窗节能工程" in answer for answer in answers)
    assert any("屋面节能工程" in answer for answer in answers)
    assert any("地面节能工程" in answer for answer in answers)
    assert all(point["point_id"].startswith("Q2024-03-5-P") for point in sub5["scoring_points"])


def test_typed_validator_rejects_high_score_with_missed_point():
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    artifact = mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 1.0,
                    "question": "5. 除墙体节能工程外，建筑节能围护结构节能子部分的分项工程还有哪些？",
                    "gold_answer": "5. 幕墙节能工程、门窗节能工程、屋面节能工程、地面节能工程。",
                }
            ],
        },
    )
    points = artifact["subquestions"][0]["scoring_points"]
    payload = {
        "score_pct": 100,
        "point_results": [
            {
                "point_id": points[0]["point_id"],
                "sub_no": "5",
                "status": "miss",
                "awarded_points": 0,
                "max_points": points[0]["weight"],
                "deduction_reason": "漏答幕墙节能工程",
                "basis_ref": points[0]["point_id"],
            }
        ],
        "deduction_reasons": ["漏答第5小问"],
        "misconception_tags": ["漏列采分点"],
    }
    validation = mod.validate_grading_output({"typed_case_grading_artifact": artifact}, payload)
    # Hardened: typed-artifact contract violations surface as contract_invalid
    # and request one regrade (was the generic "failed" before hardening).
    assert validation["status"] == "contract_invalid"
    assert validation["should_regrade"] is True
    assert "high_score_conflicts_with_miss_or_deduction" in validation["errors"]
    assert any(error.startswith("missing_point_results:") for error in validation["errors"])


def test_parse_arm_list_rejects_unknown_arm():
    assert mod.parse_arm_list("runtime_slim_grader,typed_case_grading_artifact_grader") == [
        "runtime_slim_grader",
        "typed_case_grading_artifact_grader",
    ]
    try:
        mod.parse_arm_list("missing_arm")
    except ValueError as exc:
        assert "missing_arm" in str(exc)
    else:
        raise AssertionError("unknown arm should fail")


def test_build_gold_reference_for_real_source_chunk():
    sample = {
        "year": 2023,
        "source_chunks": ["EXAM_1A434000_P0015_01"],
    }
    reference = mod.build_gold_reference(sample)
    assert len(reference["gold_points"]) >= 4
    assert any("项目质量计划" in point["gold_answer"] for point in reference["gold_points"])


# ---------------------------------------------------------------------------
# Hardening 1: atomic scoring-point provenance (gold_ref + textbook source_ref)
# ---------------------------------------------------------------------------


def _provenance_index_with_node_terms():
    """A minimal textbook provenance index keyed by required-term overlap.

    Models the v3.2 rich-leaf pack: each scoring point carries a textbook
    chunk_id, an optional quote, and required_terms that we index by term.
    """
    return mod.build_textbook_provenance_index(
        {
            "runtime_token_pack_units": [
                {
                    "leaf_id": "L_jienng",
                    "compiled_context": {
                        "scoring_points": [
                            {
                                "statement": "幕墙节能工程是建筑节能围护结构的分项工程之一。",
                                "required_terms": ["幕墙节能工程", "幕墙"],
                                "provenance": {
                                    "chunk_id": "1A412010_063_0124",
                                    "quote": "幕墙节能工程",
                                    "source_authority": "textbook",
                                },
                            },
                            {
                                "statement": "门窗节能工程属于围护结构节能分项工程。",
                                "required_terms": ["门窗节能工程", "门窗"],
                                "provenance": {
                                    "chunk_id": "1A422000_043_0069",
                                    "source_authority": "textbook",
                                },
                            },
                        ]
                    },
                }
            ]
        }
    )


def test_textbook_provenance_index_maps_terms_to_chunk_refs():
    index = _provenance_index_with_node_terms()
    幕墙_refs = mod.lookup_textbook_source_refs("幕墙节能工程", index)
    assert any(ref.get("source_ref") == "1A412010_063_0124" for ref in 幕墙_refs)
    assert all(ref.get("source_authority") == "textbook" for ref in 幕墙_refs)
    assert mod.lookup_textbook_source_refs("无此采分点术语XYZ", index) == []


def test_typed_artifact_attaches_gold_ref_and_textbook_source_ref():
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    index = _provenance_index_with_node_terms()
    artifact = mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 4.0,
                    "question": "5. 围护结构节能子部分的分项工程还有哪些？",
                    "gold_answer": "5. 幕墙节能工程、门窗节能工程、屋面节能工程、地面节能工程。",
                }
            ],
        },
        provenance_index=index,
    )
    points = artifact["subquestions"][0]["scoring_points"]
    # every atomic point must carry a provenance block bound to a gold ref
    assert all(isinstance(point.get("provenance"), dict) for point in points)
    assert all(point["provenance"].get("gold_ref") for point in points)
    # the 幕墙 point binds to its textbook source_ref
    幕墙 = [p for p in points if "幕墙节能工程" in p["canonical_answer"]][0]
    assert 幕墙["provenance"]["source_ref"] == "1A412010_063_0124"
    assert 幕墙["provenance"]["source_authority"] == "textbook"
    assert 幕墙["provenance"]["sourced"] is True
    # 屋面 has no entry in this tiny index -> marked unsourced (not fabricated)
    屋面 = [p for p in points if "屋面节能工程" in p["canonical_answer"]][0]
    assert 屋面["provenance"]["sourced"] is False
    assert 屋面["provenance"]["source_authority"] == "unsourced"
    assert 屋面["provenance"]["gold_ref"]  # gold binding always present


def test_validator_warns_on_unsourced_points_without_failing():
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    artifact = mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 2.0,
                    "question": "5. 分项工程还有哪些？",
                    "gold_answer": "5. 幕墙节能工程、门窗节能工程。",
                }
            ],
        },
        provenance_index=mod.build_textbook_provenance_index({"runtime_token_pack_units": []}),
    )
    points = artifact["subquestions"][0]["scoring_points"]
    payload = {
        "score_pct": 100,
        "point_results": [
            _schema_point_result(p, status="hit", awarded=p["weight"]) for p in points
        ],
    }
    validation = mod.validate_grading_output({"typed_case_grading_artifact": artifact}, payload)
    assert any(w.startswith("unsourced_scoring_points:") for w in validation["warnings"])
    # unsourced is a warning, not a contract failure on its own
    assert "contract_invalid_unsourced" not in validation["errors"]


# ---------------------------------------------------------------------------
# Hardening 2: locked output schema -> contract_invalid on missing/typed fields
# ---------------------------------------------------------------------------


def _schema_point_result(point, *, status="hit", awarded=None, **overrides):
    """A fully schema-conformant point_result for ``point``."""
    result = {
        "point_id": point["point_id"],
        "sub_no": point.get("sub_no") or overrides.get("sub_no") or "5",
        "max_points": point["weight"],
        "required_points": [point["canonical_answer"]],
        "accepted_variants": point.get("acceptable_variants") or [point["canonical_answer"]],
        "student_evidence_quote": "学生答案片段",
        "status": status,
        "awarded_points": point["weight"] if awarded is None else awarded,
        "deduction_reason": "" if status == "hit" else "漏列该采分点",
        "misconception_tag": "" if status == "hit" else "漏列采分点",
        "next_review_action": "回看规范条文并列项训练",
        "learning_evidence_event": {"knowledge_points": [], "weaknesses": [], "evidence_refs": []},
        "basis_ref": point["point_id"],
    }
    result.update(overrides)
    return result


def test_enforce_output_schema_passes_complete_point_result():
    point = {"point_id": "Q-1-P1", "weight": 1.0, "canonical_answer": "x", "sub_no": "1"}
    errors = mod.enforce_output_schema([_schema_point_result(point)])
    assert errors == []


def test_enforce_output_schema_flags_missing_required_field():
    point = {"point_id": "Q-1-P1", "weight": 1.0, "canonical_answer": "x", "sub_no": "1"}
    result = _schema_point_result(point)
    del result["next_review_action"]
    del result["misconception_tag"]
    errors = mod.enforce_output_schema([result])
    assert any("missing_field" in err and "next_review_action" in err for err in errors)
    assert any("missing_field" in err and "misconception_tag" in err for err in errors)


def test_enforce_output_schema_flags_type_error():
    point = {"point_id": "Q-1-P1", "weight": 1.0, "canonical_answer": "x", "sub_no": "1"}
    result = _schema_point_result(point)
    result["awarded_points"] = "not-a-number"
    result["status"] = "bogus_status"
    errors = mod.enforce_output_schema([result])
    assert any("type_error" in err and "awarded_points" in err for err in errors)
    assert any("status" in err for err in errors)


def test_validator_marks_contract_invalid_on_schema_violation():
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    artifact = mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 1.0,
                    "question": "5. 分项工程？",
                    "gold_answer": "5. 幕墙节能工程。",
                }
            ],
        },
    )
    points = artifact["subquestions"][0]["scoring_points"]
    bad = _schema_point_result(points[0])
    del bad["student_evidence_quote"]
    validation = mod.validate_grading_output(
        {"typed_case_grading_artifact": artifact},
        {"score_pct": points[0]["weight"] / points[0]["weight"] * 100, "point_results": [bad]},
    )
    assert validation["status"] == "contract_invalid"
    assert validation.get("should_regrade") is True
    assert any("missing_field" in err for err in validation["errors"])


# ---------------------------------------------------------------------------
# Hardening 3: cross-point consistency contract
# ---------------------------------------------------------------------------


def _two_sub_artifact():
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    return mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 5.0,
                    "question": "1. 三检是什么？\n5. 除墙体节能工程外，分项工程还有哪些？",
                    "gold_answer": "1. 自检、互检、专检。\n5. 幕墙节能工程、门窗节能工程、屋面节能工程、地面节能工程。",
                }
            ],
        },
    )


def test_validator_rejects_awarded_sum_exceeding_max():
    artifact = _two_sub_artifact()
    points = [p for sub in artifact["subquestions"] for p in sub["scoring_points"]]
    results = [_schema_point_result(p, status="hit", awarded=p["weight"] * 2) for p in points]
    validation = mod.validate_grading_output(
        {"typed_case_grading_artifact": artifact},
        {"score_pct": 100, "point_results": results},
    )
    assert validation["status"] == "contract_invalid"
    assert any("awarded" in err for err in validation["errors"])


def test_validator_requires_deduction_reason_on_miss():
    artifact = _two_sub_artifact()
    points = [p for sub in artifact["subquestions"] for p in sub["scoring_points"]]
    results = []
    for index, p in enumerate(points):
        result = _schema_point_result(p, status="hit", awarded=p["weight"])
        if index == 0:
            result["status"] = "miss"
            result["awarded_points"] = 0
            result["deduction_reason"] = "   "  # blank -> must fail
        results.append(result)
    validation = mod.validate_grading_output(
        {"typed_case_grading_artifact": artifact},
        {"score_pct": 80, "point_results": results},
    )
    assert validation["status"] == "contract_invalid"
    assert any("missing_deduction_reason" in err for err in validation["errors"])


def test_validator_rejects_subquestion_collapse():
    """Every artifact sub_no must have at least one point_result.

    The 节能 sub-question (sub 5) decomposes into 4 atomic points; collapsing
    all of Q2024-03 into a single sub_1 result must be a contract failure.
    """
    artifact = _two_sub_artifact()
    sub5_points = [
        p for sub in artifact["subquestions"] if sub["sub_no"] == "5" for p in sub["scoring_points"]
    ]
    assert len(sub5_points) == 4  # 幕墙/门窗/屋面/地面
    sub1_points = [
        p for sub in artifact["subquestions"] if sub["sub_no"] == "1" for p in sub["scoring_points"]
    ]
    # only emit sub-1 results, drop every sub-5 result -> collapse
    results = [_schema_point_result(p, status="hit", awarded=p["weight"]) for p in sub1_points]
    validation = mod.validate_grading_output(
        {"typed_case_grading_artifact": artifact},
        {"score_pct": 100, "point_results": results},
    )
    assert validation["status"] == "contract_invalid"
    assert any("subquestion_without_point_results" in err for err in validation["errors"])
    assert any("5" in err for err in validation["errors"] if "subquestion_without_point_results" in err)


def test_validator_rejects_score_pct_inconsistent_with_point_sum():
    artifact = _two_sub_artifact()
    points = [p for sub in artifact["subquestions"] for p in sub["scoring_points"]]
    # award full credit on every point but claim 40% -> self-inconsistent
    results = [_schema_point_result(p, status="hit", awarded=p["weight"]) for p in points]
    validation = mod.validate_grading_output(
        {"typed_case_grading_artifact": artifact},
        {"score_pct": 40, "point_results": results},
    )
    assert validation["status"] == "contract_invalid"
    assert any("score_pct_mismatch" in err for err in validation["errors"])
    assert validation.get("should_regrade") is True


def test_q2024_03_missing_fifth_subquestion_fails_validator_and_never_100():
    """Regression anchor: dropping sub-5 (节能 4 points) must fail and not get 100.

    Q2024-03 has 5 sub-questions; a grader that answers 1-4 and silently omits
    sub-5 must trip the consistency contract, not be awarded a perfect score.
    """
    sample = {"question_id": "Q2024-03", "sample_id": "Q2024-03__S05"}
    artifact = mod.build_typed_case_grading_artifact(
        sample,
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 10.0,
                    "question": (
                        "1. 三检是什么？\n2. 验收程序？\n3. 旁站要求？\n4. 见证取样？\n"
                        "5. 除墙体节能工程外，分项工程还有哪些？"
                    ),
                    "gold_answer": (
                        "1. 自检、互检、专检。\n2. 先自评后报验。\n3. 关键工序旁站。\n"
                        "4. 见证人员现场取样。\n"
                        "5. 幕墙节能工程、门窗节能工程、屋面节能工程、地面节能工程。"
                    ),
                }
            ],
        },
    )
    sub_nos = {sub["sub_no"] for sub in artifact["subquestions"]}
    assert {"1", "2", "3", "4", "5"} <= sub_nos
    # grader answers 1-4 perfectly, never emits any sub-5 result, claims 100
    results = []
    for sub in artifact["subquestions"]:
        if sub["sub_no"] == "5":
            continue
        for p in sub["scoring_points"]:
            results.append(_schema_point_result(p, status="hit", awarded=p["weight"]))
    validation = mod.validate_grading_output(
        {"typed_case_grading_artifact": artifact},
        {"score_pct": 100, "point_results": results},
    )
    assert validation["status"] == "contract_invalid"
    assert validation["recomputed_score_pct"] != 100
    assert any("subquestion_without_point_results" in err for err in validation["errors"])
    assert validation.get("should_regrade") is True


def test_load_provenance_index_degrades_when_pack_missing(tmp_path):
    assert mod._load_provenance_index(tmp_path / "no_such_pack.json") is None
    assert mod._load_provenance_index(None) is None


def test_load_provenance_index_reads_unit_scoring_points(tmp_path):
    pack = tmp_path / "pack.json"
    pack.write_text(
        '{"runtime_token_pack_units": [{"leaf_id": "L1", "compiled_context": '
        '{"scoring_points": [{"required_terms": ["幕墙节能工程"], "provenance": '
        '{"chunk_id": "1A412010_063_0124", "source_authority": "textbook"}}]}}]}',
        encoding="utf-8",
    )
    index = mod._load_provenance_index(pack)
    refs = mod.lookup_textbook_source_refs("幕墙节能工程", index)
    assert refs and refs[0]["source_ref"] == "1A412010_063_0124"


def test_contract_summary_counts_valid_invalid_and_regrades():
    summary = mod._contract_summary(
        [
            {"status": "completed", "validation_status": "passed"},
            {"status": "completed", "validation_status": "contract_invalid", "regrade_attempted": True},
            {"status": "completed", "validation_status": "contract_invalid", "regrade_attempted": True, "unsourced_point_count": 2},
            {"status": "failed"},
        ]
    )
    assert summary["completed_rows"] == 3
    assert summary["contract_valid_count"] == 1
    assert summary["contract_invalid_count"] == 2
    assert summary["regrade_triggered_count"] == 2
    assert summary["unsourced_point_total"] == 2
    assert summary["validator_pass_rate"] == round(1 / 3, 4)
