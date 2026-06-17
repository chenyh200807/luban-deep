from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_reconciliation_marks_source_present_runtime_partial_and_no_go(tmp_path: Path) -> None:
    from scripts.run_luban_docs2026_runtime_reconciliation import build_reconciliation

    source_root = tmp_path / "docs" / "2026"
    _write_json(source_root / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json", {"outline_structure": []})
    _write_json(source_root / "2026教材" / "第二次加强" / "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json", {"content_blocks": []})
    _write_json(source_root / "标准文件" / "GB.json", {"nodes": [{"id": "a"}]})
    _write_json(source_root / "讲义" / "lesson" / "lesson.json", {"pages": []})
    _write_json(source_root / "题库" / "2025" / "FINAL_CLEANED_EXAM_V2025.json", {"chunks": []})
    (source_root / "题库" / "近三年案例题_按学生答卷排版.md").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "题库" / "近三年案例题_按学生答卷排版.md").write_text("student answers", encoding="utf-8")

    supply_root = tmp_path / "runtime_supply"
    _write_json(
        supply_root / "v_canonical_unified_knowledge" / "canonical_unified_knowledge.json",
        {
            "manifest": {
                "namespace": "canonical_unified_knowledge",
                "status": "release_candidate",
                "tier": "teaching_context_not_answer_key",
                "official_score_allowed": False,
                "content_hash": "hash-u",
            },
            "nodes": {"N1": {}, "N2": {}},
        },
    )
    _write_json(
        supply_root / "v_textbook_knowledge_full" / "textbook_knowledge_release_candidate.json",
        {"manifest": {"namespace": "textbook_knowledge_full", "status": "release_candidate"}, "records": [1, 2]},
    )
    _write_json(
        supply_root / "v_standard_clauses" / "standard_clauses.json",
        {"manifest": {"namespace": "standard_clauses", "status": "release_candidate"}, "records": [1]},
    )

    artifacts_root = tmp_path / "artifacts"
    _write_json(
        artifacts_root / "canonical_unified_knowledge_20260606" / "coverage_report.json",
        {"coverage": {"canonical_leaves_total": 10, "leaves_populated": 2}},
    )
    _write_json(
        artifacts_root / "general_knowledge_dividend_m34_repair_safe_subset_20260611" / "go_no_go_m34.json",
        {"verdict": "NO-GO", "blockers": ["live_ws_gate_not_executed"]},
    )

    report = build_reconciliation(
        source_root=source_root,
        supply_root=supply_root,
        artifacts_root=artifacts_root,
    )

    assert report["schema"] == "luban_docs2026_runtime_reconciliation.v1"
    assert report["source_lanes"]["textbook"]["source_file_count"] == 1
    assert report["source_lanes"]["textbook"]["runtime_record_count"] == 2
    assert report["source_lanes"]["student_answers"]["status"] == "source_available_not_release_truth"
    assert report["coverage"]["canonical_unified_knowledge"]["populated_leaf_rate"] == 0.2
    assert "canonical_unified_knowledge_partial_leaf_coverage" in report["blockers"]
    assert "m34_live_ws_gate_not_executed" in report["blockers"]
    assert report["overall_status"] == "compiled_assets_present_but_not_system_wide_complete"
