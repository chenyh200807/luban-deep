from __future__ import annotations

from deeptutor.services.rag.pipelines.supabase import SupabasePipeline


def _case_study_exact_question() -> dict:
    """题库一道招投标案例题的 exact_question payload(含背景数字"中标价1.7亿")。"""
    return {
        "id": "bank_case_42",
        "answer_kind": "case_study",
        "covered_subquestions": [
            {
                "display_index": "1",
                "prompt": "指出招投标过程中的不妥之处",
                "authoritative_answer": "投标保证金不得超过估算价2%；背景中中标价1.7亿，2%为340万，500万超标。",
                "analysis": "依据《招标投标法实施条例》……",
            }
        ],
        "case_bundle": {
            "coverage_state": "single_subquestion_only",
            "covered_subquestions": [{"display_index": "1"}],
        },
        "coverage_state": "single_subquestion_only",
    }


def test_case_study_exact_hit_revoked_when_query_is_mcq_not_case_like():
    """#23(2026-06-23,DeepSeek-V4-Pro 异源核坐实):学生粘一道 MCQ/判断题
    (query_shape=mcq_like),经 exact_probe 文本相似度**误命中**题库一道招投标
    案例题(case_study)。题型不匹配=不是同一道题,必须**撤销命中(返回 None)**,
    否则 exact_authority 会把那道案例题的整段标准作答(含别题背景数字"中标价1.7亿")
    确定性拼给学生。这是 fail-closed,不是旧的 fail-open 原样放行。"""
    eq = _case_study_exact_question()
    out = SupabasePipeline._augment_case_exact_question_with_query(
        eq,
        query="某招标项目下列哪项不符合招标投标法？A.投标保证金500万 B.要求本省一级资质 我选A，判对错",
        query_shape="mcq_like",
    )
    assert out is None


def test_case_study_exact_hit_revoked_for_any_non_case_like_shape():
    """题型门对所有非 case_like 形状一致 fail-closed(standard_like/concept_like 同样
    不该命中一道案例题的整段标准作答)。"""
    for shape in ("standard_like", "concept_like", "calc_like"):
        eq = _case_study_exact_question()
        out = SupabasePipeline._augment_case_exact_question_with_query(
            eq, query="投标保证金上限是多少", query_shape=shape
        )
        assert out is None, shape


def test_mcq_exact_hit_not_affected_by_type_gate():
    """MCQ exact 命中(无 covered_subquestions、answer_kind=mcq)是正常命中,
    题型门不得误伤——原样返回。"""
    eq = {"id": "bank_mcq_1", "answer_kind": "mcq", "correct_answer": "C", "options": "[]"}
    out = SupabasePipeline._augment_case_exact_question_with_query(
        eq, query="这题选C对吗", query_shape="mcq_like"
    )
    assert out is eq


def test_case_study_exact_hit_kept_and_augmented_when_query_case_like():
    """回归:学生确实粘了案例题(query_shape=case_like)且含子问 → 正常增强,
    不得撤销;query_subquestions 被填入。"""
    eq = _case_study_exact_question()
    out = SupabasePipeline._augment_case_exact_question_with_query(
        eq,
        query="背景：某工程项目招标。\n1．指出招投标过程中的不妥之处。\n2．应如何整改？",
        query_shape="case_like",
    )
    assert out is not None
    assert out.get("query_subquestions")


def test_none_exact_question_passthrough():
    """无 exact 命中(None)原样穿透(题型门不改变这条已支持的合法态)。"""
    out = SupabasePipeline._augment_case_exact_question_with_query(
        None, query="x", query_shape="mcq_like"
    )
    assert out is None
