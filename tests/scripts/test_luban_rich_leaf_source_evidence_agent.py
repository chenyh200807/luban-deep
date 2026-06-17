from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _weak_work_orders() -> dict:
    return {
        "schema": "luban_rich_leaf_weak_source_refinement.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "work_orders_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "leaf_work_orders": [
            {
                "leaf_id": "L1",
                "artifact_id": "A1",
                "name_path": "费用控制 > 工程价款支付与结算 > 工程预付款与起扣点",
                "status": "source_authority_gap",
                "lane_work_orders": [
                    {
                        "missing_lane": "textbook",
                        "status": "no_candidate_sources_found",
                        "terms": ["预付款比例", "起扣点计算", "工程预付款与起扣点"],
                        "promotion_allowed": False,
                        "runtime_install_allowed": False,
                    },
                    {
                        "missing_lane": "standard",
                        "status": "no_candidate_sources_found",
                        "terms": ["预付款比例", "起扣点计算", "工程预付款与起扣点"],
                        "promotion_allowed": False,
                        "runtime_install_allowed": False,
                    },
                ],
                "promotion_allowed": False,
                "runtime_install_allowed": False,
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


def test_source_evidence_agent_finds_lane_matched_candidates_without_using_question_as_support(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_evidence_agent import build_source_evidence_agent_report

    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "2026教材" / "第二次加强" / "book.json",
        [{"id": "TB1", "text": "工程预付款比例应按合同约定，起扣点计算应结合主要材料占比。"}],
    )
    _write_json(
        docs_root / "题库" / "2025真题" / "exam.json",
        [{"id": "Q1", "question": "计算工程预付款起扣点。", "answer": "按预付款比例和主要材料占比计算。"}],
    )

    report = build_source_evidence_agent_report(
        weak_work_orders=_weak_work_orders(),
        docs_root=docs_root,
        max_files=20,
        top_k=3,
    )

    assert report["schema"] == "luban_rich_leaf_source_evidence_agent.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "semantic_verdict_recorded": False,
        "runtime_install_allowed": False,
    }
    assert all(value in (False, 0) for value in report["safety"].values())
    assert report["summary"]["work_order_count"] == 2
    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["question_context_candidate_count"] == 1

    textbook_order = next(row for row in report["source_evidence_work_orders"] if row["missing_lane"] == "textbook")
    assert textbook_order["status"] == "source_candidates_found"
    assert textbook_order["candidate_sources"][0]["source_lane"] == "textbook"
    assert textbook_order["candidate_sources"][0]["support_candidate"] is True
    assert textbook_order["candidate_sources"][0]["record_id"] == "TB1"
    assert textbook_order["candidate_sources"][0]["install_allowed"] is False

    standard_order = next(row for row in report["source_evidence_work_orders"] if row["missing_lane"] == "standard")
    assert standard_order["status"] == "no_lane_matched_source_candidate"
    assert standard_order["candidate_sources"] == []
    assert standard_order["question_context_candidates"][0]["source_lane"] == "question"
    assert standard_order["question_context_candidates"][0]["support_candidate"] is False


def test_source_evidence_agent_reuses_source_gap_loader_for_neutral_bundles(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_evidence_agent import build_source_evidence_agent_report

    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "neutral_bundle" / "source_records.json",
        {
            "source_records": [
                {
                    "source_lane": "textbook",
                    "source_path": "2026教材/费用控制/book.json",
                    "record_id": "TB-neutral",
                    "text": "工程预付款比例和起扣点计算应结合主要材料占比进行判断。",
                }
            ]
        },
    )

    report = build_source_evidence_agent_report(
        weak_work_orders=_weak_work_orders(),
        docs_root=docs_root,
        max_files=20,
        top_k=3,
    )

    textbook_order = next(row for row in report["source_evidence_work_orders"] if row["missing_lane"] == "textbook")
    assert textbook_order["status"] == "source_candidates_found"
    assert textbook_order["candidate_sources"][0]["record_id"] == "TB-neutral"
    assert textbook_order["candidate_sources"][0]["source_lane"] == "textbook"
    assert report["source_corpus"]["record_count_by_lane"] == {"textbook": 1}


def test_source_evidence_agent_keeps_practice_rows_as_question_context_only(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_evidence_agent import build_source_evidence_agent_report

    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "neutral_bundle" / "practice_records.json",
        {
            "source_records": [
                {
                    "content_type": "exercise",
                    "record_id": "Q-neutral",
                    "question_data": "计算工程预付款比例和起扣点计算。",
                    "correct_answer": "结合主要材料占比。",
                    "analysis": "工程预付款与起扣点是常见题型。",
                }
            ]
        },
    )

    report = build_source_evidence_agent_report(
        weak_work_orders=_weak_work_orders(),
        docs_root=docs_root,
        max_files=20,
        top_k=3,
    )

    textbook_order = next(row for row in report["source_evidence_work_orders"] if row["missing_lane"] == "textbook")
    assert textbook_order["candidate_sources"] == []
    assert textbook_order["question_context_candidates"][0]["record_id"] == "Q-neutral"
    assert textbook_order["question_context_candidates"][0]["source_lane"] == "question"
    assert textbook_order["question_context_candidates"][0]["support_candidate"] is False
    assert report["source_corpus"]["record_count_by_lane"] == {"question": 1}


def test_source_evidence_agent_does_not_treat_max_files_as_record_slice(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_evidence_agent import build_source_evidence_agent_report

    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "2026教材" / "book.json",
        [{"id": "TB1", "text": "工程预付款比例。"}],
    )
    _write_json(
        docs_root / "题库" / "exam.json",
        [{"id": "Q1", "question": "计算工程预付款比例和起扣点计算。", "analysis": "主要材料占比用于判断工程预付款起扣点。"}],
    )

    report = build_source_evidence_agent_report(
        weak_work_orders=_weak_work_orders(),
        docs_root=docs_root,
        max_files=1,
        top_k=3,
    )

    assert report["source_corpus"]["record_count_by_lane"] == {"question": 1, "textbook": 1}


def test_source_evidence_agent_cli_writes_review_only_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_evidence_agent import main

    docs_root = tmp_path / "docs2026"
    _write_json(docs_root / "讲义" / "费用控制" / "page_1.json", {"text": "预付款比例和起扣点计算是费用控制常见考点。"})
    work_orders_path = tmp_path / "weak_source_refinement_work_orders.json"
    output_dir = tmp_path / "out"
    _write_json(work_orders_path, _weak_work_orders())

    exit_code = main(
        [
            "--weak-work-orders",
            str(work_orders_path),
            "--docs-root",
            str(docs_root),
            "--output-dir",
            str(output_dir),
            "--max-files",
            "20",
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "source_evidence_agent_candidates.json").read_text("utf-8"))
    assert report["summary"]["work_order_count"] == 2
    assert report["classification"]["runtime_install_allowed"] is False


def test_source_evidence_agent_script_path_cli_reuses_repo_imports(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "neutral_bundle" / "source_records.json",
        {
            "source_records": [
                {
                    "source_lane": "textbook",
                    "source_path": "2026教材/book.json",
                    "record_id": "TB-cli",
                    "text": "工程预付款比例和起扣点计算应结合主要材料占比。",
                }
            ]
        },
    )
    work_orders_path = tmp_path / "weak_source_refinement_work_orders.json"
    output_dir = tmp_path / "out"
    _write_json(work_orders_path, _weak_work_orders())

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_luban_rich_leaf_source_evidence_agent.py",
            "--weak-work-orders",
            str(work_orders_path),
            "--docs-root",
            str(docs_root),
            "--output-dir",
            str(output_dir),
            "--max-files",
            "20",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads((output_dir / "source_evidence_agent_candidates.json").read_text("utf-8"))
    textbook_order = next(row for row in report["source_evidence_work_orders"] if row["missing_lane"] == "textbook")
    assert textbook_order["candidate_sources"][0]["record_id"] == "TB-cli"
