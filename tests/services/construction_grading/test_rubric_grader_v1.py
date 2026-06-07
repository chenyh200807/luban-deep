"""Rubric grader v1 — LLM-adjudicated scoring-point grading -> GradingEvent -> learning evidence.

Hermetic: judge_fn is a deterministic stub (no LLM). Proves deterministic sum, exact_required binary,
partial credit, high-risk flag, and learning-evidence projection.
"""
from __future__ import annotations

import asyncio

from deeptutor.services.construction_grading import rubric_grader_v1 as G


def _rubric():
    return [
        {"point_id": "P1", "text": "数控钢筋调直切断机", "score": 1.0, "policy": "exact_required",
         "required_terms": ["数控钢筋调直切断机"]},
        {"point_id": "P2", "text": "列举6项检验", "score": 3.0, "policy": "list", "required_terms": []},
        {"point_id": "P3", "text": "判断不妥并改正", "score": 2.0, "policy": "boolean_judgment", "required_terms": []},
    ]


def _judge(verdicts):
    def fn(point, answer):
        return verdicts.get(point["point_id"], {"status": G.MISS})
    return fn


def test_deterministic_sum_and_exact_required_binary():
    # P1 near-synonym (普通钢筋调直机) -> exact_required MISS (binary, no partial)
    # P2 list 4/6 -> partial 0.66 * 3 = 2.0; P3 hit -> 2.0
    judge = _judge({
        "P1": {"status": G.PARTIAL, "partial_ratio": 0.8, "evidence_span": "普通钢筋调直机"},  # exact->treated binary->miss
        "P2": {"status": G.PARTIAL, "partial_ratio": 0.66},
        "P3": {"status": G.HIT, "evidence_span": "总监理工程师组织"},
    })
    ev = G.grade_with_rubric(qid="Q1", student_answer="...", rubric_points=_rubric(), judge_fn=judge)
    pts = {p["point_id"]: p for p in ev["scoring_points"]}
    assert pts["P1"]["hit"] == G.MISS and pts["P1"]["score"] == 0.0       # exact_required binary
    assert pts["P1"]["mistake_type"] == G.MISTAKE_NEAR_SYNONYM
    assert abs(pts["P2"]["score"] - 1.98) < 0.01                          # 3 * 0.66
    assert pts["P3"]["score"] == 2.0
    assert ev["awarded_score"] == round(0 + 1.98 + 2.0, 2)
    assert ev["max_score"] == 6.0
    assert ev["official_score_allowed"] is False


def test_high_risk_on_low_confidence():
    judge = _judge({"P1": {"status": G.HIT, "low_confidence": True}, "P2": {"status": G.MISS}, "P3": {"status": G.MISS}})
    ev = G.grade_with_rubric(qid="Q1", student_answer="x", rubric_points=_rubric(), judge_fn=judge)
    assert ev["high_risk_review"] is True


def test_learning_evidence_projection_lists_missed_points():
    judge = _judge({"P1": {"status": G.MISS}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}})
    ev = G.grade_with_rubric(qid="Q1", student_answer="x", rubric_points=_rubric(), judge_fn=judge, student_id="u1")
    le = G.to_learning_evidence(ev, node_code="1A413040")
    assert le["event_type"] == "learning_evidence"
    weak_ids = {w["concept_label"] for w in le["weak_points"]}
    assert "数控钢筋调直切断机" in weak_ids and "判断不妥并改正" in weak_ids  # the 2 missed
    # concept_id is canonical-taxonomy authority — a question-level node_code is NOT a per-point
    # concept, so it is NEVER stamped as concept_id (fail-safe against profile pollution).
    assert all(w["concept_id"] is None for w in le["weak_points"])
    assert all(w["concept_provenance"] == "question_level_node_code" for w in le["weak_points"])
    assert le["writeback_performed"] is False


def test_normalize_points_to_nominal_scales_to_max_score():
    # 3 open-world points raw_total=6.0, nominal (V0 max_score)=2.0 -> sum scaled to 2.0
    pts = [{"point_id": "P1", "text": "a", "score": 3.0, "policy": "list", "required_terms": []},
           {"point_id": "P2", "text": "b", "score": 2.0, "policy": "list", "required_terms": []},
           {"point_id": "P3", "text": "c", "score": 1.0, "policy": "list", "required_terms": []}]
    scaled = G.normalize_points_to_nominal(pts, nominal_total=2.0)
    assert round(sum(p["score"] for p in scaled), 2) == 2.0
    # relative weights preserved (P1 largest)
    assert scaled[0]["score"] > scaled[1]["score"] > scaled[2]["score"]
    # original not mutated (immutability)
    assert pts[0]["score"] == 3.0


def test_normalize_points_fallback_base_when_no_nominal():
    pts = [{"point_id": "P1", "text": "a", "score": 1.0, "policy": "list", "required_terms": []},
           {"point_id": "P2", "text": "b", "score": 1.0, "policy": "list", "required_terms": []}]
    scaled = G.normalize_points_to_nominal(pts, nominal_total=0)  # no nominal -> base 10
    assert round(sum(p["score"] for p in scaled), 2) == 10.0


def test_normalize_then_grade_max_matches_nominal():
    pts = [{"point_id": "P1", "text": "a", "score": 5.0, "policy": "list", "required_terms": []},
           {"point_id": "P2", "text": "b", "score": 5.0, "policy": "list", "required_terms": []}]
    scaled = G.normalize_points_to_nominal(pts, nominal_total=4.0)
    ev = G.grade_with_rubric(qid="Q1", student_answer="x", rubric_points=scaled,
                             judge_fn=lambda p, a: {"status": G.HIT})
    assert ev["max_score"] == 4.0 and ev["awarded_score"] == 4.0   # comparable to in-bank scale


def test_derive_outcome_from_event():
    # partial -> not correct, percentage, PARTIAL
    o = G.derive_outcome_from_event({"awarded_score": 1.0, "max_score": 2.0})
    assert o["is_correct"] is False and o["score"] == 50 and o["diagnosis"] == "PARTIAL"
    # full -> correct
    o2 = G.derive_outcome_from_event({"awarded_score": 2.0, "max_score": 2.0})
    assert o2["is_correct"] is True and o2["score"] == 100 and o2["diagnosis"] == "CORRECT"
    # zero -> miss vocabulary
    o3 = G.derive_outcome_from_event({"awarded_score": 0.0, "max_score": 2.0})
    assert o3["is_correct"] is False and o3["score"] == 0 and o3["diagnosis"] == "采分点遗漏"
    # max 0 -> safe
    o4 = G.derive_outcome_from_event({"awarded_score": 0.0, "max_score": 0.0})
    assert o4["is_correct"] is False and o4["score"] == 0


def test_render_case_rubric_feedback_same_source_and_reasons():
    # partial / wrong-content / hit each render with the matching tag + reason, derived purely from
    # the event (same-source: rendered words can never disagree with the score).
    judge = _judge({
        "P1": {"status": G.HIT, "evidence_span": "数控钢筋调直切断机"},          # exact_required hit
        "P2": {"status": G.PARTIAL, "partial_ratio": 0.5, "evidence_span": "检验A"},  # list partial
        "P3": {"status": G.MISS, "mistake_type": G.MISTAKE_WRONG, "evidence_span": "塔吊"},  # wrong content
    })
    ev = G.grade_with_rubric(qid="Q1", student_answer="x", rubric_points=_rubric(), judge_fn=judge)
    text = G.render_case_rubric_feedback(ev, question_stem="某案例题")
    assert "某案例题" in text
    assert f"【得分】{ev['awarded_score']} / {ev['max_score']} 分" in text  # same source as the score
    assert "✅" in text                                    # P1 hit
    assert "⚠️" in text and "部分命中" in text          # P2 partial (list)
    assert "答错：你写的「塔吊」" in text                   # P3 wrong-content, NOT "漏写"
    assert "薄弱点" in text and "列举6项检验" in text       # P2 (partial) is a weak point


def test_rubric_v1_shadow_qa_gate_and_grading():
    from deeptutor.services.construction_grading import runtime_shadow_adapter as A
    pts = [{"point_id": "P1", "text": "数控钢筋调直切断机", "score": 1.0, "policy": "exact_required",
            "required_terms": ["数控钢筋调直切断机"]},
           {"point_id": "P2", "text": "列举项", "score": 1.0, "policy": "list", "required_terms": []}]
    judge = lambda p, a: {"status": G.HIT} if p["point_id"] == "P2" else {"status": G.MISS}  # noqa: E731
    # non-QA student -> fail closed
    r = A.build_rubric_v1_shadow_result(question_id="Q1", student_answer="x", student_id="real_1",
                                        rubric_points=pts, judge_fn=judge)
    assert r["status"] == "fail_closed"
    # QA student -> grades, never official
    r2 = A.build_rubric_v1_shadow_result(question_id="Q1", student_answer="x", student_id="qa_1",
                                         node_code="1A413040", rubric_points=pts, judge_fn=judge)
    assert r2["status"] == "ok" and r2["official_score_allowed"] is False
    assert r2["grading_event"]["awarded_score"] == 1.0  # P2 hit, P1 exact miss
    assert len(r2["learning_evidence"]["weak_points"]) == 1
    # no rubric + open-world -> signals caller
    r3 = A.build_rubric_v1_shadow_result(question_id="ZZZ", student_answer="x", student_id="qa_1", judge_fn=judge)
    assert r3["status"] == "no_rubric_open_world"


def test_grade_with_batch_judge_marks_degraded_on_empty_verdicts() -> None:
    # FAIL-SAFE root-cause fix: no trustworthy verdict for ANY point (LLM down / malformed -> empty
    # verdicts) -> degraded=True. The deterministic sum is still 0, but the flag tells the caller to fall
    # back to legacy rather than surface "0/满分" as an authoritative grade.
    async def _boom(**_kw):
        raise RuntimeError("llm down")

    ev = asyncio.run(G.grade_with_batch_judge_async(
        qid="q", student_answer="ans", rubric_points=_rubric(), complete_fn=_boom, api_key="k"))
    assert ev["degraded"] is True
    assert ev["awarded_score"] == 0.0


def test_grade_with_batch_judge_not_degraded_for_genuine_all_miss() -> None:
    # A real all-miss grade (student genuinely earned nothing) is NOT degraded — verdicts exist for EVERY
    # point, the adjudication happened and is trustworthy. degraded must distinguish "no signal" from
    # "low score". The LLM returns short idx (1..n), mapped back to real point_ids internally.
    async def _all_miss(**_kw):
        return '[{"idx":1,"status":"miss"},{"idx":2,"status":"miss"},{"idx":3,"status":"miss"}]'

    ev = asyncio.run(G.grade_with_batch_judge_async(
        qid="q", student_answer="ans", rubric_points=_rubric(), complete_fn=_all_miss, api_key="k"))
    assert ev["degraded"] is False
    assert ev["awarded_score"] == 0.0


def test_batch_prompt_hides_long_pointids_and_uses_idx() -> None:
    # ROOT-CAUSE: long compound point_ids (EXAM_...::E0::Q1-1) sent as LLM-echo keys get truncated/
    # mismatched, silently scoring real hits as 0. The prompt must present SHORT ordinals (idx) only;
    # the real point_id never leaves the process.
    pts = [{"point_id": "EXAM_1A432000_P0016_02::E0::Q1-1", "text": "采分点甲", "score": 1.0,
            "policy": "list", "required_terms": []},
           {"point_id": "EXAM_1A432000_P0016_02::E0::Q1-2", "text": "采分点乙", "score": 1.0,
            "policy": "list", "required_terms": []}]
    prompt = G._batch_prompt(pts, "学生作答")
    assert "EXAM_1A432000_P0016_02" not in prompt          # long id never shown to the LLM
    assert "采分点甲" in prompt and "采分点乙" in prompt    # the text IS shown
    assert '"idx":1' in prompt.replace(" ", "")            # short stable ordinal used


def test_parse_batch_verdicts_maps_idx_to_real_pointid() -> None:
    pts = [{"point_id": "EXAM::Q1-1", "text": "a", "score": 1.0, "policy": "list", "required_terms": []},
           {"point_id": "EXAM::Q1-2", "text": "b", "score": 1.0, "policy": "list", "required_terms": []}]
    raw = '[{"idx":1,"status":"hit"},{"idx":2,"status":"miss"}]'
    verdicts = G._parse_batch_verdicts(raw, pts)
    assert verdicts["EXAM::Q1-1"]["status"] == "hit"      # idx 1 -> real point_id 1
    assert verdicts["EXAM::Q1-2"]["status"] == "miss"
    # out-of-range / missing idx is ignored -> that point gets no verdict -> degraded coverage check
    assert G._parse_batch_verdicts('[{"idx":9,"status":"hit"}]', pts) == {}
    # robustness: DeepSeek sometimes stringifies idx ("1") — accepted (avoids needless degraded fallback)
    sv = G._parse_batch_verdicts('[{"idx":"1","status":"hit"},{"idx":"2","status":"miss"}]', pts)
    assert sv["EXAM::Q1-1"]["status"] == "hit" and sv["EXAM::Q1-2"]["status"] == "miss"
    # bool is NOT a valid idx (json true coerces to 1 in python int check) — must be rejected
    assert G._parse_batch_verdicts('[{"idx":true,"status":"hit"}]', pts) == {}


def test_partial_coverage_is_degraded() -> None:
    # STRICT coverage: a perfect answer where the LLM only returned a verdict for SOME points must NOT be
    # surfaced as an authoritative (low) score — the missing points are silent zeros. Any gap -> degraded.
    pts = [{"point_id": "P1", "text": "a", "score": 1.0, "policy": "list", "required_terms": []},
           {"point_id": "P2", "text": "b", "score": 1.0, "policy": "list", "required_terms": []},
           {"point_id": "P3", "text": "c", "score": 1.0, "policy": "list", "required_terms": []}]
    partial = {"P1": {"status": "hit"}}                    # only 1 of 3 adjudicated
    ev = G._grade_from_verdicts(qid="q", student_answer="完美", rubric_points=pts,
                                verdicts=partial, student_id="s")
    assert ev["degraded"] is True                          # not "0.33 authoritative", it's untrustworthy
    full = {"P1": {"status": "hit"}, "P2": {"status": "hit"}, "P3": {"status": "miss"}}
    ev2 = G._grade_from_verdicts(qid="q", student_answer="x", rubric_points=pts,
                                 verdicts=full, student_id="s")
    assert ev2["degraded"] is False                        # full coverage -> trustworthy


def test_load_rubric_bank_is_cached_process_wide() -> None:
    # C1 regression: the verify-gated bank must load ONCE per process. The old closure-inside-load_rubric
    # rebuilt its lru_cache on every call (never hit). A module-level cache exposes cache_info() proving
    # 1 miss + N-1 hits across N calls.
    G._rubric_bank.cache_clear()
    for _ in range(5):
        G.load_rubric("any-qid")
    info = G._rubric_bank.cache_info()
    assert info.misses == 1 and info.hits == 4
    G._rubric_bank.cache_clear()
