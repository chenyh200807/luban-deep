"""R1: official answer-key compiler tests (answer_key_authority=exam_reference_answer).

Deterministic parsing only — no LLM, no network. Real-corpus assertions are skipped
when the official exam JSON corpus is not present on the machine.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts import build_luban_m35_official_answer_keys as bak

EXAM_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库")
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_15Q = REPO_ROOT / "tests/fixtures/luban_m35_fastapi_case_scoring_2026/manifest.json"
FIXTURE_27SUBQ = (
    REPO_ROOT / "tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a/manifest.json"
)

requires_corpus = pytest.mark.skipif(
    not EXAM_ROOT.exists(), reason="official exam corpus not available on this machine"
)

SAMPLE_ANSWER_MARKDOWN = """### 安全管理案例题解答

1. （本小题3.0分）

（1）挖土机械作业安全。

（2）降水设施与临时用电安全。

（3）桩基施工的安全防范。

【评分标准：写出3项，即得3分】

2. （本小题6.0分）

（1）试样规格；代表批量；施工部位；计划检测试验时间。

（2）养护箱或养护池。
"""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_split_answer_blocks_by_subquestion_and_score() -> None:
    blocks = bak.split_answer_blocks(SAMPLE_ANSWER_MARKDOWN)

    assert [(b["sub_index"], b["score"]) for b in blocks] == [(1, 3.0), (2, 6.0)]
    # fragments are verbatim substrings of the source markdown (quote_hash 可复核).
    for block in blocks:
        assert block["fragment"] in SAMPLE_ANSWER_MARKDOWN
    assert "本小题3.0分" in blocks[0]["fragment"]
    assert "【评分标准" in blocks[0]["fragment"]
    assert "养护箱或养护池" in blocks[1]["fragment"]


def test_split_scoring_segments_and_policy_note() -> None:
    blocks = bak.split_answer_blocks(SAMPLE_ANSWER_MARKDOWN)
    segments, policy_note = bak.split_scoring_segments(blocks[0]["body"])

    assert len(segments) == 3
    assert segments[0].startswith("（1）")
    assert "桩基施工的安全防范" in segments[2]
    # the 评分标准 line is policy metadata, never a scoring point criterion.
    assert all("评分标准" not in seg for seg in segments)
    assert policy_note is not None and "写出3项" in policy_note
    assert bak.classify_policy(segments[0], policy_note) == "list"


def test_segments_fall_back_to_circled_and_butuo_markers() -> None:
    circled = "① 不妥之处：甲。\n② 不妥之处：乙。"
    segments, _ = bak.split_scoring_segments(circled)
    assert len(segments) == 2

    butuo = "不妥之一：“甲”；正确做法：A。\n不妥之二：“乙”；正确做法：B。\n不妥之三：“丙”；正确做法：C。"
    segments, _ = bak.split_scoring_segments(butuo)
    assert len(segments) == 3

    plain = "关键线路：①→②→③。总工期21个月。"
    segments, _ = bak.split_scoring_segments(plain)
    assert segments == [plain]


def test_allocate_scores_half_point_rule_never_fudges() -> None:
    assert bak.allocate_scores(6.0, 2) == ([3.0, 3.0], "equal_half_point_split")
    assert bak.allocate_scores(7.0, 5) == (
        [1.5, 1.5, 1.5, 1.5, 1.0],
        "front_loaded_half_point_remainder",
    )
    assert bak.allocate_scores(5.5, 1) == ([5.5], "single_point_full_score")
    # infeasible splits are refused (route to work order), never padded to fit.
    assert bak.allocate_scores(1.0, 3) is None
    assert bak.allocate_scores(5.25, 2) is None


def test_builder_imports_no_network_or_llm_clients() -> None:
    source = (REPO_ROOT / "scripts/build_luban_m35_official_answer_keys.py").read_text(
        encoding="utf-8"
    )
    banned = ("requests", "httpx", "urllib", "aiohttp", "socket", "openai", "anthropic")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if re.match(r"^\s*(import|from)\s", line)
    ]
    for line in import_lines:
        for module in banned:
            assert not re.search(rf"\b{module}\b", line), line


@requires_corpus
def test_quote_hash_recomputable_from_real_2024_answer_chunk() -> None:
    exam = json.loads(
        (
            EXAM_ROOT
            / "2024年一级建造师《建筑实务》考试真题及答案解析/FINAL_CLEANED_EXAM_V2024.json"
        ).read_text(encoding="utf-8")
    )
    chunk = next(c for c in exam["chunks"] if c["chunk_id"] == "EXAM_1A436000_P0018_02")
    blocks = bak.split_answer_blocks(chunk["content_markdown"])
    segments, _ = bak.split_scoring_segments(blocks[0]["body"])
    expected_hash = hashlib.sha256(segments[0].encode("utf-8")).hexdigest()
    # the quote itself must be locatable in the official source text.
    assert segments[0] in chunk["content_markdown"]

    compiled, _ = bak.compile_manifest(_load(FIXTURE_15Q), exam_root=EXAM_ROOT)
    question = next(q for q in compiled["questions"] if q["question_id"] == "Q2024-05")
    first_point = question["scoring_points"][0]
    ref = first_point["source_refs"][0]
    assert ref["source_type"] == "exam_reference_answer"
    assert ref["source_id"] == "EXAM_1A436000_P0018_02"
    assert ref["quote_hash"] == expected_hash
    assert ref["verified"] is True


@requires_corpus
def test_compiled_questions_keep_score_sum_identity() -> None:
    for path in (FIXTURE_15Q, FIXTURE_27SUBQ):
        compiled, work_orders = bak.compile_manifest(_load(path), exam_root=EXAM_ROOT)
        assert compiled["answer_key_authority"] == "exam_reference_answer"
        assert (
            compiled["answer_key_build_script"]
            == "scripts/build_luban_m35_official_answer_keys.py"
        )
        resolved = [q for q in compiled["questions"] if q.get("scoring_points")]
        assert resolved, path
        for question in resolved:
            total = question["total_score"]
            points = question["scoring_points"]
            assert abs(sum(p["max_score"] for p in points) - total) <= 0.01
            for point in points:
                assert point["policy_type"] in bak.POLICIES
                assert point["criterion"].strip()
                assert point["max_score"] > 0
                for ref in point["source_refs"]:
                    assert ref["source_type"] == "exam_reference_answer"
                    assert ref["verified"] is True
                    assert re.fullmatch(r"[0-9a-f]{64}", ref["quote_hash"])
            assert (
                question["answer_key_provenance"]["validated_by"]
                == "rubric_compiler.validate_rubric"
            )
        # every non-resolved question is accounted for by an explicit work order.
        unresolved = {
            q["question_id"] for q in compiled["questions"] if not q.get("scoring_points")
        }
        assert unresolved == {wo["question_id"] for wo in work_orders}


@requires_corpus
def test_known_official_totals_are_reproduced() -> None:
    compiled15, _ = bak.compile_manifest(_load(FIXTURE_15Q), exam_root=EXAM_ROOT)
    by_id = {q["question_id"]: q for q in compiled15["questions"]}
    assert by_id["Q2023-01"]["total_score"] == 20.0  # 7+3+5+5
    assert by_id["Q2023-05"]["total_score"] == 30.0  # 7+4+7+6+6
    assert by_id["Q2024-05"]["total_score"] == 30.0  # 3+6+7+7+7 (markdown answer chunk)
    assert by_id["Q2025-04"]["total_score"] == 30.0  # 4+8+5+7+6

    compiled27, _ = bak.compile_manifest(_load(FIXTURE_27SUBQ), exam_root=EXAM_ROOT)
    by_id27 = {q["question_id"]: q for q in compiled27["questions"]}
    assert by_id27["Q2023-01__P01"]["total_score"] == 7.0
    assert by_id27["Q2025-05__P01"]["total_score"] == 5.5


@requires_corpus
def test_ambiguous_subquestions_route_to_work_orders_not_guesses() -> None:
    compiled27, work_orders27 = bak.compile_manifest(_load(FIXTURE_27SUBQ), exam_root=EXAM_ROOT)
    by_reason = {wo["question_id"]: wo for wo in work_orders27}
    # official score for 2023 case-2 subquestion 4 is null in the corpus -> never guessed.
    assert "Q2023-02__P04" in by_reason
    assert by_reason["Q2023-02__P04"]["reason"] == "missing_official_subquestion_score"
    q = next(q for q in compiled27["questions"] if q["question_id"] == "Q2023-02__P04")
    assert not q.get("scoring_points")

    compiled15, work_orders15 = bak.compile_manifest(_load(FIXTURE_15Q), exam_root=EXAM_ROOT)
    by_reason15 = {wo["question_id"]: wo for wo in work_orders15}
    assert by_reason15["Q2023-04"]["reason"] == "no_source_chunk_ref"
    assert (
        by_reason15["Q2024-01"]["reason"]
        == "combined_exercise_without_per_subquestion_scores"
    )
    # work orders are persisted on the manifest itself.
    assert compiled15["work_orders"] == work_orders15
