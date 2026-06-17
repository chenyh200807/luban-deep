from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _semantic_packets() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_audit_packets.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "semantic_audit_packets": [
            {
                "packet_id": "semantic_audit:P1",
                "patch_id": "P1",
                "artifact_id": "A1",
                "leaf_id": "L1",
                "name_path": "建筑设计程序 > 初步设计",
                "missing_lane": "textbook",
                "source_ref_candidate": {
                    "source_lane": "textbook",
                    "path": "canonical_unified_knowledge:nodes.L0.sources.textbook[0]",
                    "record_id": "TB1",
                    "span": "初步设计文件包括设计说明书、设计图纸、主要设备或材料表和工程概算书。",
                    "span_hash": "hash1",
                    "matched_terms": ["初步设计", "工程概算书"],
                },
                "machine_precheck": {"audit_decision": "machine_precheck_pass", "reason_codes": []},
                "query_context": {"question_source_only_not_support": True, "question_source_record_ids": ["Q1"]},
                "allowed_decisions": ["accept_source_ref_candidate", "reject_wrong_leaf_source"],
                "review_status": "semantic_review_pending",
                "semantic_verdict_recorded": False,
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "candidate_only": True,
            }
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _source_evidence() -> dict:
    return {
        "schema": "luban_rich_leaf_source_evidence_agent.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "source_evidence_work_orders": [
            {
                "leaf_id": "L2",
                "artifact_id": "A2",
                "name_path": "工程价款支付 > 工程预付款与起扣点",
                "missing_lane": "textbook",
                "status": "source_candidates_found",
                "candidate_sources": [
                    {
                        "source_lane": "textbook",
                        "source_path": "/docs/2026/2026教材/book.json",
                        "record_id": "TB2",
                        "span": "工程预付款起扣点应结合预付款比例和主要材料占比计算。",
                        "span_hash": "hash2",
                        "matched_terms": ["预付款比例", "起扣点计算"],
                        "score": 2.5,
                        "support_candidate": True,
                        "candidate_only": True,
                        "install_allowed": False,
                        "runtime_install_allowed": False,
                    }
                ],
                "question_context_candidates": [],
                "review_status": "source_evidence_review_pending",
                "candidate_only": True,
                "review_only": True,
                "promotion_allowed": False,
                "runtime_install_allowed": False,
            },
            {
                "leaf_id": "L3",
                "artifact_id": "A3",
                "name_path": "工程进度款支付",
                "missing_lane": "standard",
                "status": "no_lane_matched_source_candidate",
                "candidate_sources": [],
                "question_context_candidates": [
                    {
                        "source_lane": "question",
                        "source_path": "/docs/2026/题库/exam.json",
                        "record_id": "Q3",
                        "span": "某案例题考查工程进度款支付比例。",
                        "span_hash": "hash3",
                        "support_candidate": False,
                        "candidate_only": True,
                        "install_allowed": False,
                        "runtime_install_allowed": False,
                    }
                ],
                "review_status": "source_evidence_review_pending",
                "candidate_only": True,
                "review_only": True,
                "promotion_allowed": False,
                "runtime_install_allowed": False,
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_semantic_audit_queue_merges_packets_candidates_and_unresolved_work_orders() -> None:
    from scripts.run_luban_rich_leaf_semantic_audit_queue import build_semantic_audit_queue_report

    report = build_semantic_audit_queue_report(semantic_packets=_semantic_packets(), source_evidence=_source_evidence())

    assert report["schema"] == "luban_rich_leaf_semantic_audit_queue.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "semantic_verdict_recorded": False,
        "runtime_install_allowed": False,
    }
    assert report["summary"] == {
        "patch_semantic_packet_count": 1,
        "source_evidence_candidate_count": 1,
        "source_evidence_unresolved_count": 1,
        "audit_item_count": 3,
    }
    assert all(value in (False, 0) for value in report["safety"].values())

    items = report["semantic_audit_queue"]
    assert [item["audit_source_type"] for item in items] == [
        "patch_semantic_packet",
        "source_evidence_candidate",
        "source_evidence_unresolved",
    ]
    assert all(item["review_status"] == "semantic_review_pending" for item in items)
    assert all(item["semantic_verdict_recorded"] is False for item in items)
    assert all(item["runtime_install_allowed"] is False for item in items)
    assert all(item["candidate_only"] is True for item in items)
    assert items[2]["source_candidate"] is None
    assert items[2]["question_context_candidates"][0]["support_candidate"] is False


def test_semantic_audit_queue_cli_writes_review_only_queue(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_audit_queue import main

    semantic_path = tmp_path / "semantic_audit_packets.json"
    source_evidence_path = tmp_path / "source_evidence_agent_candidates.json"
    output_dir = tmp_path / "out"
    _write_json(semantic_path, _semantic_packets())
    _write_json(source_evidence_path, _source_evidence())

    exit_code = main(
        [
            "--semantic-packets",
            str(semantic_path),
            "--source-evidence",
            str(source_evidence_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "semantic_audit_queue.json").read_text("utf-8"))
    assert report["summary"]["audit_item_count"] == 3
    assert report["classification"]["runtime_install_allowed"] is False
