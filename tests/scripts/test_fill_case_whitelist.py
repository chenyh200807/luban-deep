"""Whitelist filler: only教研-consensus-passed qids enter; fail-closed otherwise."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "fill_case_whitelist_from_review",
    Path(__file__).resolve().parents[2] / "scripts" / "fill_case_whitelist_from_review.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def _write_review(d: Path, qid: str, consensus_status, subs):
    (d / f"{qid.replace('::', '__')}.review.json").write_text(
        json.dumps({
            "qid": qid,
            "consensus": ({"status": consensus_status} if consensus_status else None),
            "reviewers": [{"name": "教研甲"}, {"name": "教研乙"}],
            "points": [{"point_id": f"{qid}::p{i}", "proposed_sub_no": n} for i, n in enumerate(subs)],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_only_passed_consensus_enters(tmp_path):
    _write_review(tmp_path, "Q_PASS::E0", "passed", [1, 1, 2])
    _write_review(tmp_path, "Q_PENDING::E0", None, [1, 2])
    _write_review(tmp_path, "Q_REJECTED::E0", "rejected", [1])

    entries = _MOD._passed_entries(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e["qid"] == "Q_PASS::E0"
    assert e["status"] == "allowed"
    assert e["sub_qids"] == ["Q_PASS::E0::sub1", "Q_PASS::E0::sub2"]
    assert e["approved_by"] == ["教研甲", "教研乙"]


def test_no_passed_reviews_yields_empty_failclosed(tmp_path):
    _write_review(tmp_path, "Q::E0", None, [1])
    assert _MOD._passed_entries(tmp_path) == []
