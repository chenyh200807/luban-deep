#!/usr/bin/env python3
"""Learner Memory Lifecycle cohort soak artifact runner.

Default mode is hermetic: no network, no SSH, no remote write. It fixes the
artifact contract for the later test2 run so deployment evidence cannot depend
on ad-hoc shell transcripts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.deep_question_adapter import (  # noqa: E402
    build_deep_question_grading_result,
)
from deeptutor.services.construction_grading.learning_evidence import (  # noqa: E402
    build_learning_evidence_payload,
)
from deeptutor.services.learner_state.canonical_truth_policy import (  # noqa: E402
    canonical_truth_promotion_decision,
)
from deeptutor.services.learner_state.learning_brain_read_model import (  # noqa: E402
    build_learning_brain_read_model,
)
from deeptutor.services.learner_state.personalization_context import (  # noqa: E402
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.service import LearnerStateService  # noqa: E402

ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
G4_FLAG = "LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED"
G4_COHORT = "LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_COHORT"
BROAD_FLAG = "LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_TRUSTED_ADJUDICATION_ENABLED"


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root / "data" / "user"

    def get_tutor_state_root(self) -> Path:
        return self.get_user_root() / "tutor_state"

    def get_learner_state_root(self) -> Path:
        return self.get_user_root() / "learner_state"

    def get_learner_state_outbox_db(self) -> Path:
        return self._root / "data" / "runtime" / "outbox.db"

    def get_guide_dir(self) -> Path:
        path = self.get_user_root() / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MemberServiceStub:
    def get_profile(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "display_name": user_id}

    def get_today_progress(self, _user_id: str) -> dict[str, Any]:
        return {}

    def get_chapter_progress(self, _user_id: str) -> list[dict[str, Any]]:
        return []


class _CoreStoreStub:
    is_configured = True

    def __init__(self) -> None:
        self.compiled: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}

    def read_profile(self, _user_id: str) -> dict[str, Any]:
        return {}

    def write_profile(self, _user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        return dict(profile or {})

    def read_progress(self, _user_id: str) -> dict[str, Any]:
        return {}

    def write_progress(self, _user_id: str, progress: dict[str, Any]) -> dict[str, Any]:
        return dict(progress or {})

    def read_memory_events(self, user_id: str, limit: int | None = 20) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self.events.get(user_id, [])]
        if limit is None or limit < 0:
            return rows
        return rows[-int(limit):]

    def write_compiled_learning_truth(self, user_id: str, projection: dict[str, Any]) -> dict[str, Any]:
        self.compiled[user_id] = {"learning_brain": dict(projection or {})}
        return dict(projection or {})

    def read_compiled_learning_truth(self, user_id: str) -> dict[str, Any]:
        return dict(self.compiled.get(user_id) or {})


@dataclass
class _EnvPatch:
    values: dict[str, str]
    _old: dict[str, str | None] | None = None

    def __enter__(self) -> None:
        self._old = {key: os.environ.get(key) for key in self.values}
        for key, value in self.values.items():
            os.environ[key] = value

    def __exit__(self, *_exc: object) -> None:
        for key, old in (self._old or {}).items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _certified_policy() -> dict[str, Any]:
    return {
        "status": "published",
        "policy_id": "learner-memory-lifecycle-objective-v1",
        "rubric_hash": "sha256:learner-memory-lifecycle-rubric",
        "grader_version": "objective-grader-v1",
        "confidence": 0.94,
        "conflict_status": "resolved",
    }


def _question_context(question_id: str) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "question_type": "single_choice",
        "question": "临时用电应采用几级配电？",
        "options": [{"key": "A", "value": "三级"}, {"key": "B", "value": "两级"}],
        "answer_key": "A",
        "correct_answer": "A",
        "node_code": "1A432000",
        "testing_focus": "施工现场临时用电",
    }


def _append_certified_answer_event(
    service: LearnerStateService,
    *,
    user_id: str,
    loop_id: str,
    question_id: str,
    turn_id: str,
) -> Any:
    grading_result = build_deep_question_grading_result(
        _question_context(question_id),
        user_answer="B",
        governed_registry_status="published",
        certified_grading_policy=_certified_policy(),
    )
    if not grading_result:
        raise RuntimeError("grading_result_missing")
    payload = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=turn_id,
        session_id=loop_id,
        governed_certified_authority=True,
    )
    payload["loop_id"] = loop_id
    return service.append_memory_event(
        user_id,
        source_feature="construction_grading",
        source_id=turn_id,
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key=f"{loop_id}:{turn_id}",
    )


def run_soak(*, out_dir: Path | None = None, mode: str = "local-core-store") -> dict[str, Any]:
    if mode != "local-core-store":
        raise ValueError("only local-core-store is supported by this checked-in runner")
    run_id = f"learner_memory_lifecycle_{int(time.time())}"
    out = out_dir or ARTIFACT_ROOT / run_id
    core_store = _CoreStoreStub()
    service = LearnerStateService(
        path_service=_PathServiceStub(out),
        member_service=_MemberServiceStub(),
        core_store=core_store,
    )
    user_id = "qa_learner_memory_lifecycle_soak"
    blocked_user_id = "real_student_lifecycle_soak"
    loop_id = f"{run_id}:cohort-loop"

    with _EnvPatch({
        "DEEPTUTOR_ENV": "production",
        G4_FLAG: "1",
        G4_COHORT: "qa_,operator_",
        BROAD_FLAG: "0",
    }):
        initial = _append_certified_answer_event(
            service,
            user_id=user_id,
            loop_id=loop_id,
            question_id="LM-LC-001",
            turn_id=f"{loop_id}:initial",
        )
        retest = _append_certified_answer_event(
            service,
            user_id=user_id,
            loop_id=loop_id,
            question_id="LM-LC-001-RETEST",
            turn_id=f"{loop_id}:retest",
        )
        synthesis = service.synthesize_learning_truth(user_id, dry_run=False)
        projection = synthesis["projection"]
        readback = service.read_compiled_learning_truth(user_id)
        output_hash = dict(projection.get("synthesis_run") or {}).get("output_projection_hash")
        readback_hash = dict(readback.get("synthesis_run") or {}).get("output_projection_hash")
        pcp = build_personalization_context_pack(
            user_id=user_id,
            learning_brain=projection,
            active_training_intent=None,
            recent_events=service.list_memory_events(user_id, limit=None),
        )
        nba = (pcp.get("next_best_action_candidates") or [{}])[0]
        brain_readback = build_learning_brain_read_model(user_id=user_id, projection=readback, surface="qa")
        blocked_decision = canonical_truth_promotion_decision(
            user_id=blocked_user_id,
            projection=projection,
        )

    event_rows = [
        {
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "source_id": event.source_id,
            "memory_kind": event.memory_kind,
            "memory_lifecycle_stage": event.payload_json.get("memory_lifecycle_stage"),
            "evidence_level": dict(event.payload_json.get("quality") or {}).get("evidence_level"),
            "trusted_adjudication": dict(event.payload_json.get("quality") or {}).get("trusted_adjudication"),
        }
        for event in service.list_memory_events(user_id, limit=None)
    ]
    manifest = {
        "run_id": run_id,
        "mode": mode,
        "entry": "local core-store artifact contract; remote test2 /api/v1/ws execution pending",
        "evidence_scope": "local_core_store_artifact_contract",
        "remote_write_performed": False,
        "remote_write_root_if_authorized": "/root/deeptutor",
        "cohort_user_id": user_id,
        "blocked_user_id": blocked_user_id,
        "loop_id": loop_id,
        "stage_chain": [
            "grading",
            "learning_evidence",
            "stable_claim",
            "PersonalizationContextPack",
            "NextBestAction",
            "retest",
            "certified_trusted_adjudication",
            "local_canonical_write",
            "local_canonical_readback",
        ],
    }
    go_no_go = {
        "status": "LOCAL_ARTIFACT_GO" if output_hash and output_hash == readback_hash and event_rows else "LOCAL_ARTIFACT_NO_GO",
        "learning_evidence_event_ids": [initial.event_id, retest.event_id],
        "output_projection_hash": output_hash,
        "canonical_readback_hash": readback_hash,
        "same_projection_hash": bool(output_hash and output_hash == readback_hash),
        "canonical_truth_promotion": synthesis.get("canonical_truth_promotion"),
        "blocked_non_cohort_decision": blocked_decision.to_dict(),
        "trusted_source": dict(projection.get("synthesis_run") or {}).get("trusted_adjudication", {}).get("source"),
        "pcp_source": pcp.get("source"),
        "next_best_action_id": nba.get("action_id"),
        "weak_point_count": len(projection.get("weak_points") or []),
        "observed_candidate_count": len(projection.get("observed_candidates") or []),
        "remote_write_performed": False,
    }

    _write_json(out / "manifest.json", manifest)
    _write_jsonl(out / "events.jsonl", event_rows)
    _write_json(out / "projection.json", projection)
    _write_json(out / "canonical_readback.json", readback)
    _write_json(out / "personalization_context_pack.json", pcp)
    _write_json(out / "next_best_action.json", nba)
    _write_json(out / "learning_brain_readback.json", brain_readback)
    _write_json(out / "go_no_go.json", go_no_go)
    return {"out_dir": str(out), "manifest": manifest, "go_no_go": go_no_go}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="local-core-store", choices=["local-core-store"])
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    result = run_soak(out_dir=args.out_dir, mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["go_no_go"]["status"] == "LOCAL_ARTIFACT_GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
