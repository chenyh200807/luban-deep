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


# ---------------------------------------------------------------------------
# Control-plane / reveal-terminal hard-corpus scenario sets (plan §14.A Task 1).
# These drive the *canonical* turn-fact authorities deterministically (no live
# LLM) so the hard corpus is a real executable gate, not a telemetry stand-in.
# They run on a separate code path from the scene/grounding/exact golden above
# and never touch GOLDEN_PATH.
# ---------------------------------------------------------------------------

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SCENARIO_SETS = ("control_plane_hard_cases", "reveal_terminal_hard_cases")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


async def _run_control_plane_scenarios(rows: list[dict[str, Any]]) -> list[str]:
    """Drive the canonical scene authority; assert expected/must_not per row.

    The scene authority is the single canonical writer for
    ``question_lifecycle_scene``; a fat kernel must NOT be able to override it
    (the ``fat_kernel_reads_scene_then_reroutes`` row carries a bogus
    ``fat_kernel_attempted_route_override`` that the authority must ignore).
    """
    failures: list[str] = []
    for row in rows:
        name = row.get("name", "<unnamed>")
        ctx = _FakeContext(
            user_message=row.get("user_message", ""),
            metadata=copy.deepcopy(row.get("metadata", {})),
        )
        decision = await resolve_question_lifecycle_scene_decision(ctx, enable_llm=False)
        actual = decision.scene
        expected = row.get("expected", {})
        must_not = row.get("must_not", {})
        if "scene" in expected and actual != expected["scene"]:
            failures.append(f"{name}: scene={actual!r} expected={expected['scene']!r}")
        if "scene" in must_not and actual == must_not["scene"]:
            failures.append(f"{name}: scene={actual!r} hit must_not={must_not['scene']!r}")
    return failures


def _remaining_hidden_keys(obj: Any, hidden: tuple[str, ...], path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in hidden:
                found.append(f"{path}.{key}")
            found += _remaining_hidden_keys(value, hidden, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            found += _remaining_hidden_keys(value, hidden, f"{path}[{idx}]")
    return found


def _run_reveal_terminal_scenarios(rows: list[dict[str, Any]]) -> list[str]:
    """Drive the public-redaction authority; assert no hidden fact survives.

    ACK / first_useful_content frames do not exist in the runtime yet, so the
    matching ``must_not_leak_in`` entries are dormant (no such frame is ever
    produced — trivially leak-free). The real teeth are on the metadata frame:
    after redaction, no ``_HIDDEN_PAYLOAD_KEYS`` key may survive at any depth.
    """
    from deeptutor.api.routers.unified_ws import _redact_metadata_for_public
    from deeptutor.services.question_followup import PUBLIC_HIDDEN_PAYLOAD_KEYS

    failures: list[str] = []
    for row in rows:
        name = row.get("name", "<unnamed>")
        redacted = _redact_metadata_for_public(copy.deepcopy(row.get("metadata", {})))
        leftover = _remaining_hidden_keys(redacted, PUBLIC_HIDDEN_PAYLOAD_KEYS)
        if leftover:
            failures.append(f"{name}: hidden keys survived redaction: {leftover}")
    # 出题轮"自带答案" emit 出口（安全 SEV-1，2026-06-29）：上面的 redaction 只覆盖
    # metadata 出口（回指揭示）。must_not_leak_in 里的 "body"（学生可见正文）此前是
    # dormant（无 driver）。下面驱动真实 _build_visible_response(hide=True) 可见文本
    # 出口，钉死 organic 出题轮答案不进 body。
    failures += _run_generation_visible_scenarios(rows)
    return failures


def _run_generation_visible_scenarios(rows: list[dict[str, Any]]) -> list[str]:
    """Drive the REAL question-generation visible-text exit (no live LLM).

    For rows carrying a ``generated_text`` (an organic LLM emission), render the
    student-visible body via the production ``_build_visible_response`` under a
    suppress (hide=True) practice-generation context, and assert the answer never
    survives into the body — and (Y) the question surface does survive when present.
    Pure/deterministic: ``_build_visible_response`` does no IO/LLM given its inputs.
    """
    from deeptutor.capabilities.tutorbot import TutorBotCapability
    from deeptutor.core.context import UnifiedContext
    from deeptutor.services.question_followup import (
        extract_choice_result_summary_from_text,
    )

    cap = TutorBotCapability()
    failures: list[str] = []
    for row in rows:
        generated = row.get("generated_text")
        if not generated:
            continue
        name = row.get("name", "<unnamed>")
        ctx = UnifiedContext(
            session_id="harness-generation",
            user_message=row.get("user_message", "出3道单选题"),
            metadata={
                "interaction_hints": {"suppress_answer_reveal_on_generate": True}
            },
        )
        body = cap._build_visible_response(
            context=ctx,
            final_response=generated,
            parsed_result_summary=extract_choice_result_summary_from_text(generated),
            reveal_answers=False,
            reveal_explanations=False,
        )
        for forbidden in row.get("body_must_not_contain", []):
            if forbidden in body:
                failures.append(f"{name}: answer leaked into visible body: {forbidden!r}")
        for required in row.get("body_must_contain", []):
            if required not in body:
                failures.append(
                    f"{name}: question surface missing from visible body: {required!r}"
                )
    return failures


async def _run_scenario_set(scenario_set: str, *, check: bool) -> int:
    fixture = FIXTURES_DIR / f"{scenario_set}.jsonl"
    if not fixture.exists():
        print(f"ERROR: scenario fixture missing: {fixture}", file=sys.stderr)
        return 2
    try:
        rows = _load_jsonl(fixture)
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - infra
        print(f"ERROR: failed to load {fixture}: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"ERROR: scenario fixture empty: {fixture}", file=sys.stderr)
        return 2

    try:
        if scenario_set == "control_plane_hard_cases":
            failures = await _run_control_plane_scenarios(rows)
        else:
            failures = _run_reveal_terminal_scenarios(rows)
    except Exception as exc:  # noqa: BLE001 - authority import/exec is the gate
        print(f"ERROR: authority execution failed for {scenario_set}: {exc}", file=sys.stderr)
        return 2

    if failures:
        print(f"ERROR: {scenario_set} drift ({len(failures)}/{len(rows)} rows):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"{scenario_set} OK ({len(rows)} rows, no authority drift)")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--update", action="store_true", help="(re)freeze the golden baseline")
    group.add_argument("--check", action="store_true", help="diff current decisions vs golden (gate mode)")
    parser.add_argument(
        "--scenario-set",
        choices=SCENARIO_SETS,
        default=None,
        help="run a hard-corpus scenario set against the canonical authorities (use with --check)",
    )
    args = parser.parse_args()

    if args.scenario_set is not None:
        return await _run_scenario_set(args.scenario_set, check=args.check)

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
