from __future__ import annotations

import json
import subprocess
import sys


def test_run_learning_fact_retrieval_maintenance_reads_stdin() -> None:
    payload = {
        "cases": [
            {
                "id": "case-script",
                "query": "单选题：屋面防水等级",
                "expected_source_types": ["standard"],
                "evidence_bundle": {
                    "retrieval_plan": {"plan_id": "p1"},
                    "ranking_trace": {"provenance_features": []},
                    "sources": [{"chunk_id": "std-1", "source_type": "standard"}],
                },
            }
        ],
        "compiled_learning_truth": {"weak_points": [], "typed_graph": {"edges": []}},
    }
    result = subprocess.run(
        [sys.executable, "scripts/run_learning_fact_retrieval_maintenance.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["case_count"] == 1
    assert report["sections"]["eval_cases"][0]["case_id"] == "case-script"
