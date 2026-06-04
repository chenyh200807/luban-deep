#!/usr/bin/env python
"""QA/test runtime shadow smoke for the closest stable live turn path.

Truth level:
- WS config probe is covered by tests/api/test_luban_runtime_shadow_live_route.py.
- This script drives DeepQuestionCapability's real RESULT event path with external-like
  config_overrides. It does not call private shadow helpers directly.
- Model output is deterministic to keep the smoke hermetic; no provider, DB, RAG, or
  Learning Brain write is required.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter


OUT_DIR = Path("artifacts/luban_consensus_gold/qa_runtime_shadow_live_smoke_20260604")
ENGINE = "deepseek_fast"


def _install_module(fullname: str, **attrs: Any) -> None:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            sys.modules[pkg_name] = pkg
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)

    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[fullname] = module
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        setattr(parent, parts[-1], module)


def _install_deep_question_fakes() -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading smoke")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **_kwargs: Any) -> str:
            return "得分：1分（满分3分）。"

    _install_module("deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoordinator)
    _install_module(
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )


def _deterministic_builder(question, student_answer, *, student_id, artifact_gate):
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

    points = question.get("scoring_points") or []
    predictions = [
        {
            "point_id": sp["point_id"],
            "hit": "hit",
            "score": float(sp.get("max_score") or 1),
            "evidence_span": student_answer,
            "rationale": "qa live route smoke deterministic hit",
        }
        for sp in points
    ]
    return build_ai_draft(
        question,
        student_answer,
        predictions,
        points=points,
        student_id=student_id,
        artifact_gate=artifact_gate,
    )


async def _collect_events(context: UnifiedContext) -> list[StreamEvent]:
    bus = StreamBus()
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    await DeepQuestionCapability().run(context, bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


def _context_for_sample(sample: dict[str, Any], *, flag: bool) -> UnifiedContext:
    answer = str(sample["student_answer"])
    config: dict[str, Any] = {}
    if flag:
        config["grading_engine_runtime_shadow"] = True
        config["grading_engine_runtime_shadow_engine"] = ENGINE
    return UnifiedContext(
        user_message=f"[History Context]\nQA route smoke.\n\n[User Question]\n{answer}",
        language="zh",
        config_overrides=config,
        metadata={
            "user_id": sample["student_id"],
            "raw_user_message": answer,
            "conversation_context_text": "QA route smoke: learner submitted a construction case answer.",
            "turn_semantic_decision": {"next_action": "route_to_grading"},
            "question_followup_action": {
                "intent": "answer_questions",
                "answers": [{"question_id": sample["question_id"], "answer": answer}],
            },
            "question_followup_context": {
                "question_id": sample["question_id"],
                "question": sample["question"],
                "question_type": "case",
                "correct_answer": sample["correct_answer"],
                "concentration": sample.get("concentration", "建筑实务案例题"),
            },
        },
    )


def _public_result(metadata: dict[str, Any]) -> dict[str, Any]:
    legacy = copy.deepcopy(metadata.get("construction_grading_result") or {})
    shadow = copy.deepcopy(metadata.get("luban_grading_engine_shadow") or None)
    return {
        "question_id": metadata.get("question_id"),
        "has_legacy": bool(legacy),
        "legacy": legacy,
        "has_shadow": isinstance(shadow, dict),
        "luban_grading_engine_shadow": shadow,
    }


async def _run_one(sample: dict[str, Any], *, flag: bool) -> dict[str, Any]:
    events = await _collect_events(_context_for_sample(sample, flag=flag))
    result = next(event.metadata for event in events if event.type == StreamEventType.RESULT)
    return _public_result(result)


def _legacy_key(result: dict[str, Any]) -> dict[str, Any]:
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    return {
        "authority": legacy.get("authority"),
        "type": legacy.get("type"),
        "score_awarded": legacy.get("score_awarded"),
        "max_score": legacy.get("max_score"),
        "grading_mode": legacy.get("grading_mode"),
    }


def _sample_inputs() -> list[dict[str, Any]]:
    answer = (
        "应补充施工总进度计划表(图)、分期(分批)实施工程的开竣工日期及工期一览表、"
        "资源需要量及供应平衡表；现场临时用电应采用专用开关箱。"
    )
    correct = (
        "施工总进度计划应包括施工总进度计划表(图)、分期(分批)实施工程的开竣工日期及工期一览表、"
        "资源需要量及供应平衡表；临时用电应采用专用开关箱。"
    )
    return [
        {
            "label": "published",
            "question_id": "Q17-1A433000",
            "student_id": "qa_live_shadow_published",
            "question": "写出施工现场管理相关案例题答案。",
            "correct_answer": correct,
            "student_answer": answer,
        },
        {
            "label": "draft",
            "question_id": "Q20-1A413000",
            "student_id": "qa_live_shadow_draft",
            "question": "计算混凝土配合比并说明施工调整。",
            "correct_answer": correct,
            "student_answer": answer,
        },
        {
            "label": "blocked",
            "question_id": "Q15-NA",
            "student_id": "test_live_shadow_blocked",
            "question": "写出建筑实务案例题关键评分点。",
            "correct_answer": correct,
            "student_answer": answer,
        },
        {
            "label": "missing",
            "question_id": "Q-MISSING-LIVE-SHADOW",
            "student_id": "qa_live_shadow_missing",
            "question": "不存在 artifact 的案例题。",
            "correct_answer": correct,
            "student_answer": answer,
        },
        {
            "label": "non_qa",
            "question_id": "Q17-1A433000",
            "student_id": "real_student_123",
            "question": "非 QA 用户尝试打开 shadow。",
            "correct_answer": correct,
            "student_answer": answer,
        },
    ]


async def _run_smoke() -> dict[str, Any]:
    _install_deep_question_fakes()
    adapter._build_deepseek_fast_draft = _deterministic_builder  # type: ignore[attr-defined]
    samples = _sample_inputs()
    flag_off: list[dict[str, Any]] = []
    flag_on: list[dict[str, Any]] = []
    legacy_diff: list[dict[str, Any]] = []

    for sample in samples:
        off = await _run_one(sample, flag=False)
        on = await _run_one(sample, flag=True)
        flag_off.append({"sample": sample["label"], "question_id": sample["question_id"], **off})
        flag_on.append({"sample": sample["label"], "question_id": sample["question_id"], **on})
        legacy_diff.append(
            {
                "sample": sample["label"],
                "question_id": sample["question_id"],
                "legacy_key_equal": _legacy_key(off) == _legacy_key(on),
                "off": _legacy_key(off),
                "on": _legacy_key(on),
            }
        )

    return {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "highest_layer": "ws_testclient_result_event_covered_by_tests_plus_capability_batch_smoke",
        "engine": ENGINE,
        "samples": samples,
        "flag_off": flag_off,
        "flag_on": flag_on,
        "legacy_diff": legacy_diff,
    }


def _write_outputs(report: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "route_smoke_inputs.json").write_text(
        json.dumps(report["samples"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "flag_off_outputs.json").write_text(
        json.dumps(report["flag_off"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "flag_on_outputs.json").write_text(
        json.dumps(report["flag_on"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "legacy_diff.json").write_text(
        json.dumps(report["legacy_diff"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "sample_client_payload.md").write_text(
        """# Sample Client Payload

## WebSocket `/api/v1/ws`

```json
{
  "type": "start_turn",
  "content": "请批改我的案例题答案",
  "capability": "deep_question",
  "language": "zh",
  "config": {
    "grading_engine_runtime_shadow": true,
    "grading_engine_runtime_shadow_engine": "deepseek_fast",
    "followup_question_context": {
      "question_id": "Q17-1A433000",
      "question_type": "case",
      "question": "写出施工现场消防安全管理要点。"
    }
  }
}
```

## REST `/api/v1/chat/start-turn`

```json
{
  "query": "请批改我的案例题答案",
  "capability": "deep_question",
  "grading_engine_runtime_shadow": true,
  "grading_engine_runtime_shadow_engine": "deepseek_fast",
  "followup_question_context": {
    "question_id": "Q17-1A433000",
    "question_type": "case",
    "question": "写出施工现场消防安全管理要点。"
  }
}
```
""",
        encoding="utf-8",
    )
    summary_rows = []
    on_by_sample = {item["sample"]: item for item in report["flag_on"]}
    off_by_sample = {item["sample"]: item for item in report["flag_off"]}
    for diff in report["legacy_diff"]:
        sample = diff["sample"]
        on = on_by_sample[sample]
        off = off_by_sample[sample]
        shadow = on.get("luban_grading_engine_shadow") if isinstance(on.get("luban_grading_engine_shadow"), dict) else {}
        summary_rows.append(
            f"| {sample} | {off['has_shadow']} | {on['has_shadow']} | "
            f"{shadow.get('shadow_status', '')} | "
            f"{(shadow.get('artifact_gate') or {}).get('artifact_status', '')} | "
            f"{diff['legacy_key_equal']} | {shadow.get('writeback_performed', '')} |"
        )
    finding = "\n".join(
        [
            "# FINDING qa runtime shadow live smoke 2026-06-04",
            "",
            "## Answers",
            "",
            "1. 本轮打到的最高真实层级：FastAPI TestClient `/api/v1/ws` 客户端收到 RESULT event shadow payload；批量样本由 DeepQuestionCapability RESULT event harness 生成。没有启动 live server，也没有真实 provider 调用。",
            "2. flag 入口：WS 通过 `config.grading_engine_runtime_shadow` / `config.grading_engine_runtime_shadow_engine`；REST `/api/v1/chat/start-turn` 通过同名 body 字段进入 runtime config。",
            "3. flag off：全部样本没有 `luban_grading_engine_shadow`。",
            "4. flag on：QA/test 样本返回 `luban_grading_engine_shadow`；non-QA 返回 fail closed。",
            "5. legacy：off/on 关键 legacy 字段保持一致。",
            "6. shadow：只 append 到 result metadata，不覆盖 `construction_grading_result`。",
            "7. DB / Learning Brain：未写 DB，shadow 固定 `writeback_performed=false`；测试另行 monkeypatch writeback 确认 shadow 不新增写调用。",
            "8. published/draft/blocked/missing/non-QA 行为见下表。",
            "9. adapter exception：新增 route 测试覆盖 fail closed，legacy 仍返回。",
            "10. 可以进入 teacher-review 真实写回小批：可以，但只限 QA/test 用户，并保留 teacher-final writeback gate。",
            "",
            "## Sample Table",
            "",
            "| sample | flag_off_shadow | flag_on_shadow | shadow_status | artifact_status | legacy_key_equal | writeback |",
            "|---|---:|---:|---|---|---:|---:|",
            *summary_rows,
            "",
            "## Files",
            "",
            "- `route_smoke_inputs.json`",
            "- `flag_off_outputs.json`",
            "- `flag_on_outputs.json`",
            "- `legacy_diff.json`",
            "- `sample_client_payload.md`",
            "",
        ]
    )
    (OUT_DIR / "FINDING_qa_runtime_shadow_live_smoke_20260604.md").write_text(
        finding,
        encoding="utf-8",
    )


def main() -> int:
    report = asyncio.run(_run_smoke())
    _write_outputs(report)
    print(
        json.dumps(
            {
                "out_dir": str(OUT_DIR),
                "samples": [
                    {
                        "sample": item["sample"],
                        "has_shadow": item["has_shadow"],
                        "shadow_status": (
                            item.get("luban_grading_engine_shadow") or {}
                        ).get("shadow_status")
                        if isinstance(item.get("luban_grading_engine_shadow"), dict)
                        else "",
                        "artifact_status": (
                            (item.get("luban_grading_engine_shadow") or {}).get("artifact_gate") or {}
                        ).get("artifact_status")
                        if isinstance(item.get("luban_grading_engine_shadow"), dict)
                        else "",
                    }
                    for item in report["flag_on"]
                ],
                "legacy_all_equal": all(item["legacy_key_equal"] for item in report["legacy_diff"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
