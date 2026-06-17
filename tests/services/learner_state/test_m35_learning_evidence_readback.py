from __future__ import annotations

import json

from deeptutor.services.construction_grading.learning_evidence import build_learning_evidence_payload
from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)
from deeptutor.services.learner_state.service import LearnerStateService


class _PathServiceStub:
    def __init__(self, root):
        self._root = root

    @property
    def project_root(self):
        return self._root

    def get_user_root(self):
        return self._root

    def get_tutor_state_root(self):
        return self._root / "tutor_state"

    def get_learner_state_root(self):
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self):
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MemberServiceStub:
    def get_profile(self, user_id: str):
        return {"user_id": user_id}


def test_m35_point_evidence_reads_back_as_weakness_projection(tmp_path) -> None:
    service = LearnerStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_MemberServiceStub(),
    )
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "Q1-NA",
            "score_awarded": 6,
            "max_score": 10,
            "error_events": [
                {
                    "error_code": "E02",
                    "concept_tag": "1A432000",
                    "rubric_item_id": "Q1-NA::P2",
                    "mistake_type": "omitted",
                    "diagnosis": "omitted",
                }
            ],
            "next_training_signal": {"concept": "1A432000", "focus": "专项方案审批"},
            "rubric": {
                "artifact_version": "m35_case_scoring_20260609",
                "rubric_mode": "curated_rubric",
                "scoring_points": [
                    {
                        "point_id": "Q1-NA::P2",
                        "label": "专项方案审批",
                        "max_score": 2,
                        "knowledge_node_id": "1A432000",
                    }
                ],
                "scoring_point_hits": [
                    {
                        "point_id": "Q1-NA::P2",
                        "hit": False,
                        "awarded_score": 0,
                        "error_code": "E02",
                        "mistake_type": "omitted",
                        "evidence_span": "",
                        "source_ref_ids": ["2026_case_set_x#p2"],
                    }
                ],
            },
        },
        turn_id="turn-m35-q1",
    )

    assert payload["canonical_truth_written"] is False
    service.append_memory_event(
        "qa_m35",
        source_feature="construction_grading",
        source_id="turn-m35-q1",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key="m35-q1-p2",
    )

    events = service.list_memory_events("qa_m35")
    point_map = build_scoring_point_map_read_projection(events=events, user_id="qa_m35")
    synthesis = service.synthesize_learning_truth("qa_m35", dry_run=True)
    projection_json = json.dumps(synthesis["projection"], ensure_ascii=False)

    assert point_map["source_status"]["authority"] == "learner_memory_events.learning_evidence"
    assert point_map["items"][0]["point_id"] == "Q1-NA::P2"
    assert point_map["items"][0]["evidence_refs"]
    assert point_map["items"][0]["miss_reasons"] == ["omitted"]
    assert synthesis["projection"]["observed_candidates"][0]["claim_status"] == "observed"
    assert synthesis["projection"]["observed_candidates"][0]["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert "omitted" in projection_json
    assert not (tmp_path / "learner_state" / "qa_m35" / "COMPILED_TRUTH.json").exists()
