#!/usr/bin/env python3
"""Stage 5.1 PGO mnemonic quality + stable learner-truth gate.

The gate does three things:
1. checks live Stage 5 traffic exposes the mnemonic action after non-full PGO grading;
2. checks controlled mnemonic content against a deterministic quality rubric;
3. writes repeated PGO learning evidence through LearnerStateService and verifies
   persisted compiled truth readback.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.services.construction_grading.writeback import (  # noqa: E402
    write_case_grading_event_learning_evidence,
)
from deeptutor.services.learner_state.service import LearnerStateService  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts" / "luban_grading_artifacts"
DEFAULT_LIVE_WS_EVENTS = (
    ARTIFACT_ROOT
    / "pgo_stage5_live_traffic_canary_20260614_ee94d_expanded"
    / "live_ws_events.json"
)
DEFAULT_OUT = ARTIFACT_ROOT / "pgo_stage51_learning_truth_gate_20260614"
SCHEMA = "luban_pgo_stage51_learning_truth_gate.v1"
USER_ID = "qa_stage51_pgo_truth"
BOT_ID = "construction-exam"

DEFAULT_MNEMONIC_SAMPLES = [
    {
        "sample_id": "deployment_plan_four_items",
        "text": "总进度、分期开竣工、资源平衡、施工准备，部署计划四项别漏。",
        "required_terms": ["总进度", "分期", "资源", "施工准备"],
    }
]

_FORBIDDEN_MNEMONIC_TERMS = ("官方满分", "保证得分", "肯定给分", "随便", "TODO", "待补", "编造")


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root

    def get_tutor_state_root(self) -> Path:
        return self._root / "tutor_state"

    def get_learner_state_root(self) -> Path:
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self) -> Path:
        return self._root / "runtime" / "learner_state_outbox.db"

    def get_guide_dir(self) -> Path:
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MemberServiceStub:
    def get_profile(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "display_name": "Stage 5.1 QA 学员"}


class _LocalOnlyCoreStoreStub:
    is_configured = False


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_turns(live_ws_events: dict[str, Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for role, role_turns in sorted((live_ws_events or {}).items()):
        for turn in list(role_turns or []):
            if isinstance(turn, dict):
                turns.append({"role": role, **turn})
    return turns


def _metadata(turn: dict[str, Any]) -> dict[str, Any]:
    result = turn.get("result_event") if isinstance(turn.get("result_event"), dict) else {}
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return dict(metadata or {})


def _grading_event(metadata: dict[str, Any]) -> dict[str, Any]:
    payload = metadata.get("luban_case_rubric_v1") if isinstance(metadata.get("luban_case_rubric_v1"), dict) else {}
    event = payload.get("grading_event") if isinstance(payload.get("grading_event"), dict) else {}
    return dict(event or {})


def _action_slugs(metadata: dict[str, Any]) -> set[str]:
    progressive = (
        metadata.get("progressive_disclosure")
        if isinstance(metadata.get("progressive_disclosure"), dict)
        else {}
    )
    actions = [progressive.get("primary_next_action")]
    actions.extend(list(progressive.get("secondary_actions") or []))
    return {
        str(action.get("slug") or "").strip()
        for action in actions
        if isinstance(action, dict) and str(action.get("slug") or "").strip()
    }


def _evaluate_live_mnemonic_actions(live_ws_events: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for turn in _flatten_turns(live_ws_events):
        metadata = _metadata(turn)
        event = _grading_event(metadata)
        if event.get("rubric_bank_slot") != "pgo":
            continue
        try:
            awarded = float(event.get("awarded_score") or 0)
            maximum = float(event.get("max_score") or 0)
        except (TypeError, ValueError):
            continue
        if maximum <= 0 or awarded >= maximum:
            continue
        slugs = _action_slugs(metadata)
        records.append({
            "role": turn.get("role"),
            "sample_id": turn.get("sample_id"),
            "show_mnemonic": "show_mnemonic" in slugs,
            "action_slugs": sorted(slugs),
        })
    missing = [record for record in records if not record["show_mnemonic"]]
    return {
        "status": "PASS" if records and not missing else "FAIL",
        "non_full_pgo_count": len(records),
        "action_present_count": len(records) - len(missing),
        "missing_records": missing,
    }


def _evaluate_mnemonic_content(samples: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for sample in samples:
        text = str(sample.get("text") or "").strip()
        required_terms = [str(item or "").strip() for item in list(sample.get("required_terms") or []) if str(item or "").strip()]
        reasons: list[str] = []
        if len(text) < 12 or len(text) > 80:
            reasons.append("length_out_of_range")
        if any(term in text for term in _FORBIDDEN_MNEMONIC_TERMS):
            reasons.append("forbidden_claim")
        required_min = min(3, len(required_terms))
        matched_terms = [term for term in required_terms if term in text]
        if len(matched_terms) < required_min:
            reasons.append("required_terms_missing")
        if "。" not in text and "，" not in text and "、" not in text:
            reasons.append("not_memorable_phrase")
        if reasons:
            failures.append({
                "sample_id": str(sample.get("sample_id") or ""),
                "reasons": reasons,
                "matched_terms": matched_terms,
            })
    return {
        "content_status": "PASS" if samples and not failures else "FAIL",
        "sample_count": len(samples),
        "pass_count": len(samples) - len(failures),
        "failures": failures,
    }


def _pgo_grading_event(question_id: str) -> dict[str, Any]:
    return {
        "event_type": "case_grading_completed",
        "student_id": USER_ID,
        "question_id": question_id,
        "awarded_score": 0.0,
        "max_score": 5.0,
        "coverage": 0.0,
        "high_risk_review": False,
        "degraded": False,
        "grading_source": "rubric_scored_pgo",
        "rubric_bank_slot": "pgo",
        "score_authority": "official_total_x_verdict_coverage",
        "answer_key_authority": "exam_reference_answer",
        "official_score_allowed": False,
        "scoring_points": [
            {
                "point_id": "P1",
                "knowledge_point": "屋面与防水工程施工",
                "policy_type": "exact_required",
                "hit": "miss",
                "score": 0.0,
                "max_score": 5.0,
                "mistake_type": "omitted",
                "evidence_span": "卷材搭接宽度不足",
                "required_terms": ["卷材搭接宽度"],
            }
        ],
    }


def _stable_truth_promotion(
    out_dir: Path,
    *,
    use_core_store: bool = False,
    learner_state_service_factory: Any | None = None,
) -> dict[str, Any]:
    runtime_root = out_dir / "learner_runtime"
    if callable(learner_state_service_factory):
        service = learner_state_service_factory(runtime_root)
    elif use_core_store:
        service = LearnerStateService(
            path_service=_PathServiceStub(runtime_root),
            member_service=_MemberServiceStub(),
        )
    else:
        service = LearnerStateService(
            path_service=_PathServiceStub(runtime_root),
            member_service=_MemberServiceStub(),
            core_store=_LocalOnlyCoreStoreStub(),
        )
    writebacks: list[dict[str, Any]] = []
    for attempt in (1, 2):
        writebacks.append(
            write_case_grading_event_learning_evidence(
                learner_state_service=service,
                user_id=USER_ID,
                grading_event=_pgo_grading_event(f"STAGE51-PGO-{attempt}"),
                source_id=f"stage51-turn-{attempt}:STAGE51-PGO-{attempt}",
                source_bot_id=BOT_ID,
                user_answer="卷材搭接宽度不足。",
                question_stem="题库内案例：某屋面工程卷材防水施工，指出施工做法的不妥之处。",
                node_code="1A413050",
                session_id="stage51-session",
            )
        )
    synthesis = service.synthesize_learning_truth(USER_ID, dry_run=False, event_limit=None)
    projection = dict(synthesis.get("projection") or {})
    readback = service.read_compiled_learning_truth(USER_ID)
    weak_points = list(readback.get("weak_points") or [])
    weak = weak_points[0] if weak_points else {}
    return {
        "persisted_readback_status": "PASS" if weak.get("evidence_level") == "L1_repeated" else "FAIL",
        "writeback_count": sum(int(item.get("writeback_count") or 0) for item in writebacks),
        "claim_promotion_allowed_all": all(
            bool(dict(item.get("learning_evidence_payload") or {}).get("claim_promotion_allowed"))
            for item in writebacks
        ),
        "preview_only_any": any(
            bool(dict(item.get("learning_evidence_payload") or {}).get("preview_only"))
            for item in writebacks
        ),
        "weak_point_count": len(weak_points),
        "weak_point_concept_id": str(weak.get("concept_id") or ""),
        "weak_point_error_code": str(weak.get("error_code") or ""),
        "weak_point_evidence_level": str(weak.get("evidence_level") or ""),
        "compiled_truth_path": str(runtime_root / "learner_state" / USER_ID / "COMPILED_TRUTH.json"),
        "output_projection_hash": str(dict(readback.get("synthesis_run") or {}).get("output_projection_hash") or ""),
        "dry_run_projection_hash": str(dict(projection.get("synthesis_run") or {}).get("output_projection_hash") or ""),
    }


def run_stage51_gate(
    *,
    live_ws_events: dict[str, Any] | None = None,
    live_ws_events_path: str | Path | None = None,
    mnemonic_samples: list[dict[str, Any]] | None = None,
    out_dir: str | Path = DEFAULT_OUT,
    use_core_store: bool = False,
    learner_state_service_factory: Any | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events_path = Path(live_ws_events_path) if live_ws_events_path else DEFAULT_LIVE_WS_EVENTS
    if live_ws_events is None:
        live_ws_events = _load_json(events_path) if events_path.exists() else {}
    samples = list(mnemonic_samples if mnemonic_samples is not None else DEFAULT_MNEMONIC_SAMPLES)
    action_report = _evaluate_live_mnemonic_actions(live_ws_events)
    content_report = _evaluate_mnemonic_content(samples)
    promotion_report = _stable_truth_promotion(
        out,
        use_core_store=use_core_store,
        learner_state_service_factory=learner_state_service_factory,
    )

    blockers: list[str] = []
    if action_report["status"] != "PASS":
        blockers.append("mnemonic_action_missing_for_non_full_pgo")
    if content_report["content_status"] != "PASS":
        blockers.append("mnemonic_content_quality_failed")
    if promotion_report["persisted_readback_status"] != "PASS":
        blockers.append("stable_truth_promotion_readback_failed")
    if not promotion_report["claim_promotion_allowed_all"] or promotion_report["preview_only_any"]:
        blockers.append("pgo_evidence_not_promotable")
    blockers = sorted(set(blockers))
    status = "STAGE51_GO" if not blockers else "STAGE51_BLOCKED"
    report = {
        "schema": SCHEMA,
        "status": status,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_live_ws_events": str(events_path),
        "mnemonic_quality": {
            "live_action_status": action_report["status"],
            **action_report,
            **content_report,
        },
        "stable_truth_promotion": promotion_report,
        "go_no_go": {
            "status": status,
            "blockers": blockers,
            "mnemonic_live_action_status": action_report["status"],
            "mnemonic_content_status": content_report["content_status"],
            "stable_truth_readback_status": promotion_report["persisted_readback_status"],
        },
    }
    _write_json(out / "stage51_learning_truth_gate.json", report)
    _write_json(out / "go_no_go.json", report["go_no_go"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-ws-events", type=Path, default=DEFAULT_LIVE_WS_EVENTS)
    parser.add_argument("--mnemonic-samples", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--use-core-store",
        action="store_true",
        help="Use the configured LearnerState core store for persisted readback instead of local-only files.",
    )
    args = parser.parse_args()
    samples = _load_json(args.mnemonic_samples) if args.mnemonic_samples else None
    result = run_stage51_gate(
        live_ws_events_path=args.live_ws_events,
        mnemonic_samples=samples,
        out_dir=args.out_dir,
        use_core_store=args.use_core_store,
    )
    print(json.dumps(result["go_no_go"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["go_no_go"]["status"] == "STAGE51_GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
