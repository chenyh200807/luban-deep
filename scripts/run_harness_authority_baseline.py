#!/usr/bin/env python3
"""Decision-layer golden baseline for the harness single-authority gate.

Freezes the *decision outputs* of the three turn-execution authorities —
question-lifecycle scene, grounding, and exact-answer — over a representative
case set, so a single offline gate can catch semantic regressions in
scene / grounding / exact routing without needing live LLM access.

This is the offline substitute for a full live trace golden (which needs
two-shell pipeline runs against real LLMs and is deferred to a keyed
environment per the harness execution plan). The golden lives in a tracked
fixture (``deeptutor/services/benchmark/fixtures/``) so the eval gate works
on a fresh checkout — ``artifacts/`` is git-ignored. Each authority is called
deterministically here:

- scene    : ``resolve_question_lifecycle_scene_decision(ctx, enable_llm=False)``
             plus the deterministic ``derive_question_lifecycle_scene`` and the
             canonical ``attach_question_lifecycle_scene_to_context`` writer that
             both execution shells must read.
- grounding: ``build_grounding_decision`` / ``build_grounding_decision_from_metadata``.
- exact    : ``extract_exact_question_authority_from_metadata`` +
             ``should_force_exact_authority`` + ``build_exact_authority_response``.

Usage::

    python scripts/run_harness_authority_baseline.py --update   # (re)freeze golden
    python scripts/run_harness_authority_baseline.py --check    # gate: diff vs golden

``--check`` exits non-zero on any decision drift and prints the offending keys,
so the eval gate goes red the moment a shell re-introduces an independent
scene / grounding / exact judgement.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import dataclasses
import difflib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.query_intent import (  # noqa: E402
    build_grounding_decision,
    build_grounding_decision_from_metadata,
)
from deeptutor.services.question_lifecycle_skills import (  # noqa: E402
    attach_question_lifecycle_scene_to_context,
    derive_question_lifecycle_scene,
    resolve_question_lifecycle_scene_decision,
)
from deeptutor.services.rag.exact_authority import (  # noqa: E402
    build_exact_authority_response,
    extract_exact_question_authority_from_metadata,
    should_force_exact_authority,
)

GOLDEN_PATH = (
    PROJECT_ROOT
    / "deeptutor"
    / "services"
    / "benchmark"
    / "fixtures"
    / "harness_authority_decision_golden.json"
)

_ABOUT = (
    "Decision-layer golden for scene/grounding/exact single authority. "
    "Offline & deterministic; full live-trace golden is deferred to a keyed env."
)


@dataclass
class _FakeContext:
    """Mirror of the lightweight ctx the lifecycle authority reads.

    The scene authority only consumes ``user_message`` and ``metadata``; using a
    minimal stand-in keeps the baseline free of runtime/session wiring.
    """

    user_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Representative case set (covers the 7 plan-required surfaces)
#   grounding hit / MCQ exact / case_study exact / free_text /
#   construction scene / follow-up / low-information exam query
# ---------------------------------------------------------------------------

_MCQ_FOLLOWUP_CONTEXT = {
    "question_id": "q1",
    "question_type": "mcq",
    "question": "下列哪个选项正确？",
    "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
}

_CASE_FOLLOWUP_CONTEXT = {
    "question_id": "q1",
    "question_type": "case",
    "question": "案例题：分析该施工方案的不妥之处...",
}

SCENE_CASES: list[dict[str, Any]] = [
    {"name": "scene_practice_generation", "user_message": "再出 3 题"},
    {"name": "scene_question_review_real_exam", "user_message": "分析一道验槽方法真题"},
    {
        "name": "scene_mcq_grading_active_submission",
        "user_message": "B",
        "metadata": {"question_followup_context": _MCQ_FOLLOWUP_CONTEXT},
    },
    {
        "name": "scene_question_review_active_no_submission",
        "user_message": "这道题怎么做",
        "metadata": {"question_followup_context": _MCQ_FOLLOWUP_CONTEXT},
    },
    {
        "name": "scene_case_grading_active_submission",
        "user_message": "施工单位应组织专家论证危大工程方案",
        "metadata": {"question_followup_context": _CASE_FOLLOWUP_CONTEXT},
    },
    {"name": "scene_study_assistant", "user_message": "今天学什么"},
    {"name": "scene_learning_support", "user_message": "我学不动了"},
    {"name": "scene_learning_evidence_story", "user_message": "我最近哪里错"},
    {"name": "scene_low_information_exam_query", "user_message": "2025真题"},
    {"name": "scene_unanchored_mcq_answer", "user_message": "我选B"},
    {"name": "scene_unrelated_chat_fallback", "user_message": "你好"},
    {
        "name": "scene_exam_catalog_followup",
        "user_message": "查看这一类真题目录或考点范围",
    },
]

GROUNDING_CASES: list[dict[str, Any]] = [
    {
        "name": "grounding_grounded_followup_forces_retrieval_first",
        "fn": "decision",
        "kwargs": {
            "query": "这道题我为什么错了，结合教材再解释一下",
            "default_kb": "construction-exam",
            "knowledge_bases": ["construction-exam"],
            "rag_enabled": True,
            "tutorbot_context": True,
            "followup_question": True,
            "answer_type": "knowledge_explainer",
        },
    },
    {
        "name": "grounding_exact_candidate_prefetches_rag",
        "fn": "decision",
        "kwargs": {
            "query": "背景资料：某旧城改造工程。问题：4. 计算项目成本。",
            "default_kb": "construction-exam",
            "knowledge_bases": ["construction-exam"],
            "rag_enabled": True,
            "tutorbot_context": True,
            "exact_question_candidate": True,
        },
    },
    {
        "name": "grounding_exam_schedule_is_current_info",
        "fn": "decision",
        "kwargs": {
            "query": "2026一建考试时间",
            "rag_enabled": True,
            "tutorbot_context": True,
        },
    },
    {
        "name": "grounding_personal_learning_status_stays_internal",
        "fn": "decision",
        "kwargs": {
            "query": "我最近学的怎么样",
            "rag_enabled": True,
            "tutorbot_context": True,
        },
    },
    {
        "name": "grounding_explicit_web_search_command_current_info",
        "fn": "decision",
        "kwargs": {
            "query": "你不是能联网的吗，联网查询",
            "rag_enabled": True,
            "tutorbot_context": True,
        },
    },
    {
        "name": "grounding_textbook_delta_query_prefetches_from_metadata",
        "fn": "from_metadata",
        "kwargs": {
            "query": "2026年教材变化有哪些更新",
            "runtime_metadata": {
                "default_kb": "construction-exam",
                "knowledge_bases": ["construction-exam"],
                "current_info_required": True,
            },
            "rag_enabled": True,
            "tutorbot_context": True,
            "exact_question_candidate": False,
            "practice_generation_request": False,
        },
    },
]

EXACT_CASES: list[dict[str, Any]] = [
    {
        "name": "exact_mcq_force",
        "exact_question": {
            "answer_kind": "mcq",
            "correct_answer": "B",
            "stem": "施工现场临时用电组织设计应由谁编制？",
            "analysis": "本题以题库标准答案为准。B 选项符合规范要求。",
            "options": {
                "A": "项目负责人",
                "B": "电气工程技术人员",
                "C": "专职安全员",
                "D": "监理工程师",
            },
        },
    },
    {
        "name": "exact_free_text_force",
        "exact_question": {
            "answer_kind": "free_text",
            "correct_answer": "应先进行验槽，确认地基承载力满足设计要求后方可施工。",
            "analysis": "验槽是隐蔽工程验收的关键环节。",
        },
    },
    {
        "name": "exact_case_study_full_bundle",
        "exact_question": {
            "answer_kind": "case_study",
            "case_bundle": {
                "covered_subquestions": [
                    {
                        "display_index": "1",
                        "prompt": "Q1",
                        "authoritative_answer": "项目经理应先核查关键线路。",
                        "analysis": "关键线路决定总工期。",
                    },
                    {
                        "display_index": "2",
                        "prompt": "Q2",
                        "authoritative_answer": "随后调整资源投入。",
                        "analysis": "资源投入会影响后续衔接。",
                    },
                ],
                "missing_subquestions": [],
                "coverage_ratio": 1.0,
                "coverage_state": "multi_subquestion_exact",
            },
        },
    },
    {
        "name": "exact_case_study_partial_bundle",
        "exact_question": {
            "answer_kind": "case_study",
            "case_bundle": {
                "covered_subquestions": [
                    {
                        "display_index": "1",
                        "prompt": "Q1",
                        "authoritative_answer": "先判断总工期风险。",
                    }
                ],
                "missing_subquestions": [{"display_index": "2", "prompt": "Q2"}],
                "coverage_ratio": 0.5,
                "coverage_state": "single_subquestion_only",
            },
        },
    },
]


def _normalize(value: Any) -> Any:
    """Make authority decisions JSON-stable: sets→sorted lists, tuples→lists."""
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in value}
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


async def _scene_record(case: dict[str, Any]) -> dict[str, Any]:
    message = case["user_message"]
    base_metadata = copy.deepcopy(case.get("metadata", {}))

    derive_ctx = _FakeContext(user_message=message, metadata=copy.deepcopy(base_metadata))
    derived = derive_question_lifecycle_scene(derive_ctx)

    resolve_ctx = _FakeContext(user_message=message, metadata=copy.deepcopy(base_metadata))
    decision = await resolve_question_lifecycle_scene_decision(resolve_ctx, enable_llm=False)

    attach_ctx = _FakeContext(user_message=message, metadata=copy.deepcopy(base_metadata))
    attached_scene = attach_question_lifecycle_scene_to_context(attach_ctx)

    return _normalize(
        {
            "derive_scene": derived,
            "resolve": {
                "scene": decision.scene,
                "source": decision.source,
                "confidence": decision.confidence,
                "required_anchor_status": decision.required_anchor_status,
                "exact_question_blocked_reason": decision.exact_question_blocked_reason,
                "needs_clarification": bool(decision.needs_clarification),
                "business_gate_result": decision.business_gate_result,
                "selected_skill_names": list(decision.selected_skill_names or ()),
            },
            "attach": {
                "scene": attached_scene,
                "skill_names": list(attach_ctx.metadata.get("question_lifecycle_skill_names") or []),
            },
        }
    )


def _grounding_record(case: dict[str, Any]) -> dict[str, Any]:
    fn = case["fn"]
    kwargs = case["kwargs"]
    if fn == "decision":
        decision = build_grounding_decision(**kwargs)
    elif fn == "from_metadata":
        decision = build_grounding_decision_from_metadata(**kwargs)
    else:  # pragma: no cover - guarded by the static case set
        raise ValueError(f"unknown grounding fn: {fn!r}")
    return _normalize(dataclasses.asdict(decision))


def _exact_record(case: dict[str, Any]) -> dict[str, Any]:
    normalized = extract_exact_question_authority_from_metadata(
        {"exact_question": case["exact_question"]}
    )
    if normalized is None:
        return {"authority_kind": None, "should_force_exact": False, "response": None}
    return _normalize(
        {
            "authority_kind": normalized.get("authority_kind"),
            "should_force_exact": should_force_exact_authority(normalized),
            "response": build_exact_authority_response(normalized),
        }
    )


async def compute_baseline() -> dict[str, Any]:
    scene = {case["name"]: await _scene_record(case) for case in SCENE_CASES}
    grounding = {case["name"]: _grounding_record(case) for case in GROUNDING_CASES}
    exact = {case["name"]: _exact_record(case) for case in EXACT_CASES}
    return {
        "_about": _ABOUT,
        "scene": scene,
        "grounding": grounding,
        "exact": exact,
    }


def _serialize(baseline: dict[str, Any]) -> str:
    return json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _diff(golden: dict[str, Any], current: dict[str, Any]) -> str:
    golden_text = _serialize(golden).splitlines()
    current_text = _serialize(current).splitlines()
    return "\n".join(
        difflib.unified_diff(
            golden_text,
            current_text,
            fromfile="golden",
            tofile="current",
            lineterm="",
        )
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--update", action="store_true", help="(re)freeze the golden baseline")
    group.add_argument("--check", action="store_true", help="diff current decisions vs golden (gate mode)")
    args = parser.parse_args()

    baseline = await compute_baseline()

    if args.update:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(_serialize(baseline), encoding="utf-8")
        print(f"wrote golden baseline -> {GOLDEN_PATH.relative_to(PROJECT_ROOT)}")
        return 0

    if args.check:
        if not GOLDEN_PATH.exists():
            print(f"ERROR: golden baseline missing: {GOLDEN_PATH}", file=sys.stderr)
            return 2
        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        if golden == baseline:
            print("harness authority baseline OK (no decision drift)")
            return 0
        print("ERROR: harness authority decision drift detected:", file=sys.stderr)
        print(_diff(golden, baseline), file=sys.stderr)
        return 1

    # No mode flag: print current baseline for inspection.
    print(_serialize(baseline), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
