"""
Battle2 S2-T3 — 判分反馈差分质量门不变量（零 LLM，hermetic）。

两层裁决不变式（设计 §T3②）+ 门自证（可证伪性，指挥官专项审判要求）：
  * authority 路径：is_correct/score/correct_answer 在进 SubmissionGraderAgent 前
    已由服务端算定，process 全程不得写回 graded_context（停手红线 R1）。
  * 门 harness 自证红测：喂"答案字母改错的合成输出"断言门必红；套话注入必红；
    缺必备段必红；compact 臂更长必红；authority 突变必红。
  * 抽答案用确定性 regex（非 LLM judge，防循环度量）。
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HARNESS_PATH = _REPO_ROOT / "scripts" / "run_mcq_feedback_output_ab.py"
_FIXTURES_PATH = _REPO_ROOT / "eval" / "fixtures" / "mcq_feedback_ab" / "cases.jsonl"


def _load_harness():
    spec = importlib.util.spec_from_file_location("mcq_feedback_output_ab", _HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("mcq_feedback_output_ab", module)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()


# ─────────────────────────────────────────────────────────────────────────────
# R1 authority 路径结构性不变量
# ─────────────────────────────────────────────────────────────────────────────

def _make_graded_context() -> dict[str, Any]:
    return {
        "question_id": "q_inv_1",
        "question_type": "choice",
        "question": "双扇防火门的关闭方式，正确的是？",
        "options": {"A": "同时关闭", "B": "按顺序关闭", "C": "自动关闭", "D": "手动关闭"},
        "user_answer": "C",
        "correct_answer": "B",
        "is_correct": False,
        "score": 0.0,
        "items": [
            {
                "question_id": "q_inv_1",
                "question_type": "choice",
                "user_answer": "C",
                "correct_answer": "B",
                "is_correct": False,
                "score": 0.0,
            }
        ],
    }


def _run_process(question_context: dict[str, Any], llm_text: str) -> None:
    from deeptutor.agents.question.agents.submission_grader_agent import SubmissionGraderAgent

    agent = SubmissionGraderAgent.__new__(SubmissionGraderAgent)
    agent.language = "zh"  # type: ignore[attr-defined]
    agent.get_prompt = lambda key, default="": ""  # type: ignore[attr-defined]
    agent.get_max_tokens = lambda: 4096  # type: ignore[attr-defined]

    async def fake_stream_llm(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        yield llm_text

    agent.stream_llm = fake_stream_llm  # type: ignore[attr-defined]
    asyncio.run(
        agent.process(
            user_message="我选 C",
            question_context=question_context,
            trace_collector={},
        )
    )


def test_process_never_writes_back_adjudication_fields() -> None:
    """判分裁决字段（is_correct/score/correct_answer，含 items）进 agent 前已算定，
    process 全程只读——LLM 输出无论宣称什么都不得回写（停手红线）。"""
    context = _make_graded_context()
    before = copy.deepcopy(context)
    # LLM 输出故意宣称相反裁决，process 也不得回写结构化字段
    _run_process(
        context,
        "### 阅卷结论\n其实你答对了，正确答案是 C。\n\n### 正确答案\nC。\n\n### 为什么错\n无。\n\n### 下一步\n无。",
    )
    assert harness.check_authority_immutable(before, context) == []
    assert context["is_correct"] is False
    assert context["correct_answer"] == "B"
    assert context["score"] == 0.0
    assert context["items"][0]["correct_answer"] == "B"


def test_authority_checker_flags_mutations() -> None:
    before = _make_graded_context()
    mutated = copy.deepcopy(before)
    mutated["is_correct"] = True
    mutated["items"][0]["score"] = 1.0
    violations = harness.check_authority_immutable(before, mutated)
    assert any("is_correct" in v for v in violations)
    assert any("items[0].score" in v for v in violations)


# ─────────────────────────────────────────────────────────────────────────────
# 门自证（可证伪性）：红测必红 + 合法样例必绿
# ─────────────────────────────────────────────────────────────────────────────

def _load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in _FIXTURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_gate_self_red_test_passes() -> None:
    """指挥官专项审判：喂'答案字母改错的合成输出'断言门必红（B1），
    以及 B2/B3/B4/R1 各自可红——run_self_red_test 返回 0 = 全部自证通过。"""
    assert harness.run_self_red_test() == 0


def test_wrong_letter_synthetic_output_turns_gate_red() -> None:
    cases = [c for c in _load_cases() if c["scenario"] == "single_wrong"]
    case = cases[0]
    valid = harness._synthesize_valid_output(case)
    assert harness.check_case_blocking(valid, case) == []
    gold = case["gold"]["correct_letters"][0]
    wrong = next(l for l in "ABCDE" if l != gold and l in case["arm_input"]["question_context"]["options"])
    corrupted = valid.replace(f"正确答案是 {gold}", f"正确答案是 {wrong}")
    failures = harness.check_case_blocking(corrupted, case)
    assert any(f.startswith("B1_") for f in failures), failures


def test_boilerplate_blacklist_catches_all_six_legacy_sentences() -> None:
    cases = [c for c in _load_cases() if c["scenario"] == "single_wrong"]
    case = cases[0]
    valid = harness._synthesize_valid_output(case)
    legacy_six = [s for s in harness.BOILERPLATE_BLACKLIST if len(s) > 10]
    assert len(legacy_six) >= 6
    for sentence in legacy_six:
        failures = harness.check_case_blocking(valid + f"\n### 易错点\n- {sentence}。\n", case)
        assert any(f.startswith("B2_") for f in failures), sentence


def test_letter_extraction_is_deterministic_regex_not_llm() -> None:
    text = "### 阅卷结论\n本题答错，你答了 C、正确答案是 B。\n\n### 正确答案\n正确答案是 B（按顺序关闭）。"
    assert harness.extract_adjudicated_letters(text) == ["B"]
    multi = "### 正确答案\n正确答案是 A、C、E（见教材）。"
    assert harness.extract_adjudicated_letters(multi) == ["A", "C", "E"]
    assert harness.extract_adjudicated_letters("无 heading 无答案宣告") == []


def test_gate_green_on_legit_compact_outputs_for_all_bank_cases() -> None:
    """合法 compact 形状对全部 bank 用例过 blocking 门（open_world 走 corpus 层多数票）。"""
    for case in _load_cases():
        if case["scenario"] in {"open_world", "batch_4", "single_right"}:
            continue
        valid = harness._synthesize_valid_output(case)
        assert harness.check_case_blocking(valid, case) == [], case["case_id"]


# ─────────────────────────────────────────────────────────────────────────────
# 冻结语料契约（eval-design 臂公平前提）
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture_corpus_shape_and_freeze() -> None:
    cases = _load_cases()
    assert len(cases) >= 24
    scenarios = {c["scenario"] for c in cases}
    assert {
        "single_wrong",
        "single_right",
        "multi_missed",
        "multi_extra",
        "judge",
        "batch_4",
        "open_world",
        "combo_option",
        "ocr_noise",
    } <= scenarios
    for case in cases:
        arm_input = case["arm_input"]
        # 检索结果冻结进 fixture（消检索方差）；open_world 外全部带服务端已算定裁决
        assert "grounding_context" in arm_input
        context = arm_input["question_context"]
        if case["scenario"] == "open_world":
            assert context.get("is_correct") is None
            assert not context.get("correct_answer")
            assert "【教材要点" in arm_input["grounding_context"]
        elif case["scenario"] == "batch_4":
            assert len(context["items"]) == 4
            for item in context["items"]:
                assert isinstance(item.get("is_correct"), bool)
                assert item.get("correct_answer")
        else:
            assert isinstance(context.get("is_correct"), bool)
            assert context.get("correct_answer")
        # gold 字母必须来自学员题面 Options（题面字母对齐硬约束）
        options = context.get("options") or (context["items"][0].get("options") if context.get("items") else {})
        for letter in case["gold"]["correct_letters"]:
            assert letter in "ABCDE"
            if case["scenario"] != "batch_4":
                assert letter in options, f"{case['case_id']}: gold letter {letter} not on learner surface"
