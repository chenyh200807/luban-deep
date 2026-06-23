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


# --- #23 第二层(task#26):召回侧隔离 _drop_cross_type_case_exam_evidence ---


def _case_exam_item() -> dict:
    """题库一道案例题召回项,其解析含别题背景数值"中标价1.7亿"。"""
    return {
        "chunk_id": "q_case_42",
        "_source_table": "questions_bank",
        "question_type": "案例分析题",
        "source_type": "exam",
        "rag_content": "【题目】某招标项目……【解析】背景中标价1.7亿，2%为340万，500万超标。",
    }


def _standard_item() -> dict:
    """规则/标准 evidence(judge 判分需要,不得误删)。"""
    return {
        "chunk_id": "std_zbtbf",
        "_source_table": "kb_chunks",
        "question_type": "",
        "source_type": "standard",
        "rag_content": "投标保证金不得超过招标项目估算价的2%，且不超过80万元。",
    }


def test_drops_case_exam_evidence_for_mcq_query():
    """#23 第二层:学生粘 MCQ(query_shape=mcq_like)时,从 evidence 剔除题库案例题
    (其解析含别题"中标价1.7亿",judge 会锚定误用),但保留规则/标准 evidence。"""
    out = SupabasePipeline._drop_cross_type_case_exam_evidence(
        [_case_exam_item(), _standard_item()], query_shape="mcq_like"
    )
    ids = [i["chunk_id"] for i in out]
    assert "q_case_42" not in ids  # 别题案例剔除
    assert "std_zbtbf" in ids  # 规则 evidence 保留


def test_keeps_case_exam_evidence_for_case_like_query():
    """学生确实粘案例题(case_like)→ 案例 evidence 合法,不剔。"""
    out = SupabasePipeline._drop_cross_type_case_exam_evidence(
        [_case_exam_item(), _standard_item()], query_shape="case_like"
    )
    assert len(out) == 2


def test_keeps_non_case_questions_bank_mcq_evidence():
    """题库里的非案例题(单选/判断)不受影响——判据是 case 题型,不是 questions_bank。"""
    mcq = {
        "chunk_id": "q_mcq_1",
        "_source_table": "questions_bank",
        "question_type": "单项选择题",
        "source_type": "exam",
    }
    out = SupabasePipeline._drop_cross_type_case_exam_evidence([mcq], query_shape="mcq_like")
    assert len(out) == 1


def test_drops_to_empty_never_returns_polluted_source_when_all_case():
    """fail-safe(DeepSeek 异源审修正):召回全是案例题时,剔空返回**空安全集**,
    绝不退回原(退回原=别题"1.7亿"重新进入 evidence=过滤失效)。judge 退化纯题面判。"""
    out = SupabasePipeline._drop_cross_type_case_exam_evidence(
        [_case_exam_item()], query_shape="mcq_like"
    )
    assert out == []  # 不是 [_case_exam_item()](污染源)


def test_no_drop_returns_original_when_nothing_matched():
    """没有任何 case exam 命中(全是规则 evidence)→ 原样返回。"""
    items = [_standard_item()]
    out = SupabasePipeline._drop_cross_type_case_exam_evidence(items, query_shape="mcq_like")
    assert out == items
