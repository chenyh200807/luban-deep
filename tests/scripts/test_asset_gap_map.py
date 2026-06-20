from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_asset_gap_map.py"
EXTRACTIONS_ROOT = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions"
DATA_ASSET_BRIEF = EXTRACTIONS_ROOT / "data_asset_brief_v1" / "manifest.json"
ASSET_BUCKETS = EXTRACTIONS_ROOT / "data_asset_brief_v1" / "asset_buckets.json"
JSON_LEDGER = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "manifest.json"
JSON_SOURCES = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "sources.jsonl"
PDF_LEDGER = EXTRACTIONS_ROOT / "pdf_source_ledger_v1" / "manifest.json"
PDF_SOURCES = EXTRACTIONS_ROOT / "pdf_source_ledger_v1" / "pdf_sources.jsonl"
OKF_SCOPE = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "manifest.json"
OKF_ALIGNMENT = EXTRACTIONS_ROOT / "okf_source_alignment_v0" / "report.json"
OKF_CASE_ALIGNMENT = EXTRACTIONS_ROOT / "okf_source_alignment_v0" / "case_alignment.jsonl"
COMPILED_AUTHORITY = EXTRACTIONS_ROOT / "compiled_asset_authority_map_v1" / "manifest.json"
RUNTIME_POINTERS = EXTRACTIONS_ROOT / "compiled_asset_authority_map_v1" / "runtime_pointers.jsonl"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_asset_gap_map", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _collect_bytes(path: Path):
    return {
        child.relative_to(path).as_posix(): child.read_bytes()
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def _build_kwargs(output_root: Path):
    return {
        "data_asset_brief_path": DATA_ASSET_BRIEF,
        "asset_buckets_path": ASSET_BUCKETS,
        "json_ledger_path": JSON_LEDGER,
        "json_sources_path": JSON_SOURCES,
        "pdf_ledger_path": PDF_LEDGER,
        "pdf_sources_path": PDF_SOURCES,
        "okf_scope_path": OKF_SCOPE,
        "okf_alignment_path": OKF_ALIGNMENT,
        "okf_case_alignment_path": OKF_CASE_ALIGNMENT,
        "compiled_authority_path": COMPILED_AUTHORITY,
        "runtime_pointers_path": RUNTIME_POINTERS,
        "output_root": output_root,
        "generated_at": "2026-06-19T00:00:00+08:00",
    }


def test_asset_gap_map_builds_actionable_gap_queues(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "asset_gap_map_v1"

    result = builder.build_asset_gap_map(**_build_kwargs(output_root))

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_asset_gap_map_manifest.v1"
    assert manifest["authority_status"] == "asset_gap_map_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["counts"]["gap_items"] == 9
    assert manifest["counts"]["open_gap_items"] == 9
    assert manifest["counts"]["by_priority"] == {"P1": 5, "P2": 4}

    queues = _read_json(output_root / "action_queues.json")["queues"]
    assert sum(row["missing_count"] for row in queues["exam_content_gap"]) == 139
    assert len(queues["json_source_claim_review_backlog"]) == 383
    assert len(queues["pdf_p1_compile_or_map"]) == 21
    assert len(queues["pdf_p2_verify_provenance"]) == 39
    assert len(queues["okf_case_level_alignment_backfill"]) == 16
    assert len(queues["runtime_published_pointer_consumer_evidence"]) == 4
    assert len(queues["runtime_policy_conflict_live_reader"]) == 1
    assert len(queues["runtime_blocked_or_candidate_pointer_review"]) == 11
    by_runtime_bundle = {row["runtime_bundle"]: row for row in queues["runtime_published_pointer_consumer_evidence"]}
    assert by_runtime_bundle["v_topic_waterproof"]["gap_kind"] == "published_pointer_payload_manifest_conflict"
    assert by_runtime_bundle["v_topic_waterproof"]["pointer_published"] is True
    assert by_runtime_bundle["v_topic_waterproof"]["payload_manifest_published"] is False
    assert by_runtime_bundle["v_topic_waterproof"]["hash_gate_status"] == "mismatch"
    policy_conflict = queues["runtime_policy_conflict_live_reader"][0]
    assert policy_conflict["runtime_bundle"] == "v_case_rubric_scored"
    assert policy_conflict["runtime_read_allowed"] is False
    assert policy_conflict["policy_conflict_live_reader"] is True
    assert policy_conflict["consumer_evidence_status"] == "policy_conflict_live_reader"

    gap_items = _read_jsonl(output_root / "gap_items.jsonl")
    by_id = {row["gap_id"]: row for row in gap_items}
    assert by_id["exam_content_gap"]["affected_count"] == 139
    assert by_id["exam_content_gap"]["priority"] == "P1"
    assert by_id["json_source_claim_review_gap"]["affected_count"] == 383
    assert by_id["json_source_claim_review_gap"]["evidence"]["by_bucket"]["lecture_cleaned_json"] == 335
    assert by_id["pdf_p1_compile_or_map"]["evidence"]["by_category"]["standard_pdf"] == 13
    assert by_id["okf_case_level_alignment_backfill"]["affected_count"] == 16
    assert by_id["runtime_published_pointer_consumer_evidence"]["affected_count"] == 4
    assert by_id["runtime_policy_conflict_live_reader"]["affected_count"] == 1
    assert by_id["runtime_policy_conflict_live_reader"]["priority"] == "P1"
    assert all(item["runtime_guard"]["runtime_consumable"] is False for item in gap_items)
    assert all(item["runtime_guard"]["official_score_allowed"] is False for item in gap_items)

    next_actions = _read_json(output_root / "next_actions.json")
    assert next_actions["principle"] == (
        "LLMs maintain candidate knowledge organization; deterministic gates sign releases and protect authority."
    )
    assert next_actions["actions"][0]["gap_id"] == "exam_content_gap"
    assert next_actions["actions"][4]["gap_id"] == "runtime_policy_conflict_live_reader"
    assert "do not write runtime_supply" in next_actions["actions"][0]["must_not_do"]

    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "Asset Gap Map v1" in summary
    assert "not runtime supply" in summary
    assert "json_source_claim_review_backlog" in summary


def test_asset_gap_map_rejects_dangerous_output_root_before_reset(monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_asset_gap_map(**_build_kwargs(REPO_ROOT))


def test_asset_gap_map_rejects_invalid_runtime_guard_before_output(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "asset_gap_map_v1"
    bad_json_ledger = tmp_path / "bad_json_ledger.json"
    payload = _read_json(JSON_LEDGER)
    payload["runtime_guard"]["runtime_consumable"] = True
    bad_json_ledger.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kwargs = _build_kwargs(output_root)
    kwargs["json_ledger_path"] = bad_json_ledger

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid input: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid runtime guard runtime_consumable"):
        builder.build_asset_gap_map(**kwargs)


def test_asset_gap_map_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "asset_gap_map_v1"
    output_root.mkdir(parents=True)
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_asset_gap_map(**_build_kwargs(output_root))


def test_asset_gap_map_repeated_generation_is_byte_identical_with_fixed_timestamp(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "asset_gap_map_v1"
    kwargs = _build_kwargs(output_root)

    builder.build_asset_gap_map(**kwargs)
    first = _collect_bytes(output_root)
    builder.build_asset_gap_map(**kwargs)
    second = _collect_bytes(output_root)

    assert second == first
