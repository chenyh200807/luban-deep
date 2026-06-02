from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.compile_2026_scoring_point_assets import _pdf_page_hint_from_row


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compile_scoring_point_assets_script_writes_verified_assets(tmp_path: Path) -> None:
    source_root = tmp_path / "2026"
    book_dir = source_root / "2026教材" / "第二次加强"
    book_dir.mkdir(parents=True)
    payload = {
        "content_blocks": [
            {
                "chunk_id": "c1",
                "content_markdown": "施工现场应设置连续封闭的围挡，围挡应坚固、稳定、整洁、美观。",
                "content_type": "normative_rule",
                "taxonomy": {"node_code": "1A421000"},
                "source_meta": {"page_num": 1, "source_name": "2026一建《建筑》电子版教材_9-166"},
                "assessment": {"grading_keywords": ["围挡"]},
            },
            {
                "chunk_id": "c2",
                "content_markdown": "钢筋理论重量应按707.2kg计算。",
                "content_type": "rule_numeric",
                "taxonomy": {"node_code": "1A421000"},
                "source_meta": {"page_num": 2, "source_name": "2026一建《建筑》电子版教材_9-166"},
                "assessment": {"grading_keywords": ["707.2kg"]},
            },
        ]
    }
    (book_dir / "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["LUBAN_2026_SOURCE_ROOT"] = str(source_root)
    run_id = "pytest-scoring-point-assets"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/compile_2026_scoring_point_assets.py",
            "--run-id",
            run_id,
            "--force",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "gate=pass" in result.stdout
    run_dir = REPO_ROOT / "artifacts" / "knowledge_compiler" / "2026" / run_id
    rows = [
        json.loads(line)
        for line in (run_dir / "scoring_point_assets.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = json.loads((run_dir / "quality_report.json").read_text(encoding="utf-8"))
    assert rows
    assert report["invalid_textbook_anchor_count"] == 0
    assert report["loose_anchor_violation_count"] == 0
    spotcheck = json.loads((run_dir / "pdf_spotcheck_queue.json").read_text(encoding="utf-8"))
    assert spotcheck["samples"][0]["page_hint"] == 9


def test_pdf_page_hint_uses_row_page_not_batch_first_chunk() -> None:
    assert (
        _pdf_page_hint_from_row(
            {
                "source_path": "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
                "page_num": 18,
            }
        )
        == 184
    )
