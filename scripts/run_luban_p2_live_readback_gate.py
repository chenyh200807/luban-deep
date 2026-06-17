#!/usr/bin/env python3
"""P2 local live-readback gate for the grading-to-brain loop.

The gate is intentionally local and readback-first:
  judge trace -> learning_evidence -> LearnerStateService.MEMORY_EVENTS
  -> LearnerStateService.synthesize_learning_truth(dry_run=True) -> PCP/NBA

It writes only under the requested artifact output directory. It never writes
production DB state, canonical learner truth, published registries, or remote
state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.services.construction_grading.rubric_grader_v1 import to_learning_evidence  # noqa: E402
from deeptutor.services.learner_state.learning_brain_read_model import (  # noqa: E402
    build_learning_brain_read_model,
)
from deeptutor.services.learner_state.next_best_action import build_next_best_actions  # noqa: E402
from deeptutor.services.learner_state.outbox import LearnerStateOutbox  # noqa: E402
from deeptutor.services.learner_state.personalization_context import (  # noqa: E402
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.service import LearnerStateService  # noqa: E402
from deeptutor.services.learner_state.training_intent import (  # noqa: E402
    build_learning_training_intent,
)
from scripts.run_luban_judge_grading_to_brain_trace import (  # noqa: E402
    BOT,
    DEFAULT_MANIFEST,
    DEFAULT_PER_ROW,
    USER,
    run_trace,
)

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/p2_live_readback_20260611"
ARTIFACT_VERSION_FALLBACK = "luban_m35_fastapi_case_subquestions_20q_100a.v1"
REQUIRED_READBACK_KEYS = (
    "learner_memory_event_id",
    "weakness_projection_id",
    "next_action_id",
    "retest_condition_id",
)


class _LocalPathService:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root / "user"

    def get_learner_state_root(self) -> Path:
        return self._root / "learner_state"

    def get_runtime_dir(self) -> Path:
        return self._root / "runtime"

    def get_guide_dir(self) -> Path:
        return self._root / "guide"


class _NoRemoteCoreStore:
    is_configured = False


class _LocalMemberService:
    def get_profile(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "display_name": user_id}

    def get_today_progress(self, _user_id: str) -> dict[str, Any]:
        return {}

    def get_chapter_progress(self, _user_id: str) -> list[dict[str, Any]]:
        return []


def _sha(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _local_service(root: Path) -> LearnerStateService:
    path_service = _LocalPathService(root)
    return LearnerStateService(
        path_service=path_service,  # type: ignore[arg-type]
        member_service=_LocalMemberService(),
        outbox_service=LearnerStateOutbox(path_service=path_service),  # type: ignore[arg-type]
        core_store=_NoRemoteCoreStore(),
    )


def _claims(projection: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in [
            *list(projection.get("weak_points") or []),
            *list(projection.get("observed_candidates") or []),
        ]
        if isinstance(item, dict)
    ]


def _first_missing_point(grading_event: dict[str, Any]) -> dict[str, Any]:
    for point in list(grading_event.get("scoring_points") or []):
        if isinstance(point, dict) and str(point.get("hit") or "") != "hit":
            return dict(point)
    return {}


def _weakness_projection_id(projection: dict[str, Any]) -> str:
    claim = next(iter(_claims(projection)), {})
    for key in ("claim_id", "object_id"):
        value = str(claim.get(key) or "").strip()
        if value:
            return value
    concept_id = str(claim.get("concept_id") or "").strip()
    error_code = str(claim.get("error_code") or "").strip()
    if concept_id or error_code:
        return f"weakness:{concept_id}:{error_code}"
    return ""


def _append_evidence_pair(
    service: LearnerStateService,
    *,
    user_id: str,
    evidence: dict[str, Any],
    qid: str,
    artifact_version: str,
) -> list[str]:
    ids: list[str] = []
    for index in (1, 2):
        attempt_id = f"attempt_{qid}_{index}"
        event = service.append_memory_event(
            user_id,
            source_feature="construction_grading",
            source_id=f"p2_live_readback:{attempt_id}",
            source_bot_id=BOT,
            memory_kind="learning_evidence",
            payload_json=evidence,
            dedupe_key=f"p2-live:{user_id}:{attempt_id}:{qid}:{artifact_version}",
        )
        ids.append(event.event_id)
    return ids


def _build_training_intent(
    *,
    user_id: str,
    node_code: str,
    first_missing_point: dict[str, Any],
    event_ids: list[str],
) -> dict[str, Any]:
    error_label = str(first_missing_point.get("mistake_type") or "omitted").strip() or "omitted"
    return build_learning_training_intent(
        user_id=user_id,
        concept_id=node_code or str(first_missing_point.get("point_id") or ""),
        concept_label=str(first_missing_point.get("knowledge_point") or ""),
        error_code="E02",
        error_label=error_label,
        evidence_refs=event_ids,
        training_mode="mixed_review",
        source="p2_live_readback_gate",
    )


def _retest_condition(
    *,
    artifact_version: str,
    first_missing_point: dict[str, Any],
    next_action_id: str,
) -> dict[str, Any]:
    point_id = str(first_missing_point.get("point_id") or "").strip()
    condition = {
        "target_point_id": point_id,
        "must_reference_artifact_version": artifact_version,
        "success_condition": "new attempt has the same target point_id as hit with a verified evidence_span",
        "next_action_id": next_action_id,
        "promotion_note": "local live readback is convergence evidence only; mastery/canonical truth still needs governed retest authority",
    }
    condition["retest_condition_id"] = "retest_" + hashlib.sha256(
        json.dumps(condition, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return condition


def build_p2_live_readback_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    per_row_path: str | Path = DEFAULT_PER_ROW,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    include_required_readbacks: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    source_trace_dir = out / "source_judge_trace"
    trace = run_trace(
        out_dir=str(source_trace_dir),
        per_row_path=Path(per_row_path),
        manifest_path=Path(manifest_path),
    )
    grading_event = json.loads((source_trace_dir / "grading_event.json").read_text(encoding="utf-8"))

    chain = dict(trace.get("chain") or {})
    node_code = str(chain.get("node_code") or "").strip()
    qid = str(chain.get("question_id") or grading_event.get("question_id") or "").strip()
    artifact_version = str(chain.get("artifact_version") or ARTIFACT_VERSION_FALLBACK).strip()
    base_evidence = to_learning_evidence(grading_event, node_code=node_code)

    shadow_service = _local_service(out / "local_runtime" / "shadow")
    shadow_evidence = dict(base_evidence)
    shadow_evidence["quality"] = {
        **dict(base_evidence.get("quality") or {}),
        "writeback_eligible": False,
        "authority": "artifact_first_llm_judge_shadow",
    }
    _append_evidence_pair(
        shadow_service,
        user_id=f"{USER}_p2_shadow",
        evidence=shadow_evidence,
        qid=qid,
        artifact_version=artifact_version,
    )
    shadow_projection = shadow_service.synthesize_learning_truth(
        f"{USER}_p2_shadow",
        dry_run=True,
    )["projection"]
    shadow_claims = _claims(shadow_projection)
    shadow_writeback_blocked = len(shadow_claims) == 0

    live_service = _local_service(out / "local_runtime" / "live")
    live_evidence = dict(base_evidence)
    live_evidence["quality"] = {
        **dict(base_evidence.get("quality") or {}),
        "writeback_eligible": True,
        "authority": "local_live_readback_fixture",
    }
    user_id = f"{USER}_p2_live_readback"
    event_ids = _append_evidence_pair(
        live_service,
        user_id=user_id,
        evidence=live_evidence,
        qid=qid,
        artifact_version=artifact_version,
    )
    readback_events = live_service.list_memory_events(user_id, limit=None)
    readback_event_ids = [
        event.event_id
        for event in readback_events
        if event.memory_kind == "learning_evidence"
    ]
    projection = live_service.synthesize_learning_truth(user_id, dry_run=True)["projection"]
    read_model = build_learning_brain_read_model(user_id=user_id, projection=projection, surface="qa")
    first_missing = _first_missing_point(grading_event)
    intent = _build_training_intent(
        user_id=user_id,
        node_code=node_code,
        first_missing_point=first_missing,
        event_ids=readback_event_ids,
    )
    learning_brain = {"compiled_objects": list(dict(projection.get("compiled_objects") or {}).values())}
    pcp = build_personalization_context_pack(
        user_id=user_id,
        learning_brain=learning_brain,
        active_training_intent=intent,
        recent_events=[{"event_id": event_id} for event_id in readback_event_ids],
    )
    candidates = pcp.get("next_best_action_candidates") or build_next_best_actions(
        user_id=user_id,
        training_intents=[intent],
        graph_chain=read_model.get("graph_chain") if isinstance(read_model, dict) else {},
        max_actions=1,
    )
    next_action = dict(candidates[0]) if candidates else {}
    next_action_id = str(next_action.get("action_id") or "").strip()
    retest = _retest_condition(
        artifact_version=artifact_version,
        first_missing_point=first_missing,
        next_action_id=next_action_id,
    )

    readback_ids = {
        "learner_memory_event_id": readback_event_ids[0] if readback_event_ids else "",
        "weakness_projection_id": _weakness_projection_id(projection),
        "next_action_id": next_action_id,
        "retest_condition_id": str(retest.get("retest_condition_id") or ""),
    }
    if not include_required_readbacks:
        readback_ids["next_action_id"] = ""
    required_readbacks_present = all(str(readback_ids.get(key) or "").strip() for key in REQUIRED_READBACK_KEYS)
    blockers: list[str] = []
    if not required_readbacks_present:
        blockers.append("live_readback_missing_required_ids")
    if not shadow_writeback_blocked:
        blockers.append("shadow_writeback_not_blocked")
    if live_service.read_compiled_learning_truth(user_id):
        blockers.append("canonical_truth_written")

    package = {
        "schema_version": "luban_p2_live_readback_gate.v1",
        "generated_at": "2026-06-11",
        "inputs": {
            "per_row_path": str(Path(per_row_path)),
            "manifest_path": str(Path(manifest_path)),
            "source_trace_dir": _artifact_path(source_trace_dir),
        },
        "p2_live_readback": {
            "verdict": "STRONG-GO" if not blockers else "NO-GO",
            "mode": "local_live_readback",
            "scope": "local_artifact_root_only_not_release_truth",
            "convergence_claim_allowed": not blockers,
            "required_readbacks_present": required_readbacks_present,
            "shadow_writeback_blocked": shadow_writeback_blocked,
            "readback_ids": readback_ids,
            "blockers": blockers,
        },
        "chain": {
            "artifact_version": artifact_version,
            "question_id": qid,
            "node_code": node_code,
            "point_matches": list(chain.get("point_matches") or []),
            "grading_event_hash": _sha(grading_event),
            "learning_evidence_hash": _sha(base_evidence),
            "learner_memory_event_ids": readback_event_ids,
            "weakness_projection_id": readback_ids["weakness_projection_id"],
            "learning_brain_read_model_hash": _sha(read_model),
            "pcp_hash": _sha(pcp),
            "next_action_id": readback_ids["next_action_id"],
            "retest_condition": retest,
        },
        "sources": {
            "memory_events_source": "LearnerStateService.MEMORY_EVENTS",
            "learning_projection_source": "LearnerStateService.synthesize_learning_truth(dry_run=True)",
            "pcp_source": "PersonalizationContextPack",
            "next_action_source": "training_intent",
        },
        "local_artifacts": {
            "runtime_root": _artifact_path(out / "local_runtime"),
            "memory_events_jsonl": _artifact_path(
                out / "local_runtime" / "live" / "learner_state" / user_id / "MEMORY_EVENTS.jsonl"
            ),
            "outbox_sqlite": _artifact_path(out / "local_runtime" / "live" / "runtime" / "outbox.db"),
        },
        "not_exercised": [
            "production_db_write",
            "canonical_learner_truth_write",
            "published_registry_write",
            "remote_or_aliyun_write",
            "official_score_promotion",
            "real_wechat_package_readback",
        ],
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
    }
    (out / "learning_brain_read_model.json").write_text(
        json.dumps(read_model, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "personalization_context_pack.json").write_text(
        json.dumps(pcp, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "next_best_action.json").write_text(
        json.dumps(next_action, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "p2_live_readback_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-row", default=str(DEFAULT_PER_ROW))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    package = build_p2_live_readback_package(
        output_dir=args.output_dir,
        per_row_path=args.per_row,
        manifest_path=args.manifest,
    )
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
