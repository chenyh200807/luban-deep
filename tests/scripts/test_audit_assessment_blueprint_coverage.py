from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from deeptutor.services.assessment.blueprint import get_assessment_blueprint


def test_audit_script_writes_json_report_from_fixture(tmp_path: Path) -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    fixture = tmp_path / "coverage_rows.json"
    output = tmp_path / "report.json"
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
    ]
    fixture.write_text(json.dumps({"rows": rows}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_assessment_blueprint_coverage.py",
            "--fixture",
            str(fixture),
            "--output",
            str(output),
        ],
        check=False,
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["blueprint_version"] == "diagnostic_v1"
    assert report["status"] == "pass"
    assert report["requested_count"] == 20
    assert len(report["sections"]) == len(blueprint.sections)
