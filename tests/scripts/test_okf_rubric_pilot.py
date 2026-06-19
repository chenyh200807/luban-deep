from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_okf_rubric_pilot.py"
SOURCE_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "case_rubric_canonical.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_okf_rubric_pilot", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pilot_roots(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "okf_pilot" / "rubric_v0",
        tmp_path / "extractions" / "okf_rubric_pilot_v0",
    )


def _build_tmp_pilot(builder, tmp_path: Path):
    source_root, compiled_root = _pilot_roots(tmp_path)
    result = builder.build_pilot(
        source_path=SOURCE_PATH,
        source_root=source_root,
        compiled_root=compiled_root,
        year="2021",
        case_no="1",
        generated_at="2026-06-19T00:00:00+08:00",
    )
    return source_root, compiled_root, result


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_build_pilot_preserves_non_official_authority(tmp_path):
    builder = _load_builder()
    source_root, compiled_root, result = _build_tmp_pilot(builder, tmp_path)

    manifest = result["manifest"]
    assert manifest["authority"] == "training_org_analysis_yousen"
    assert manifest["not_official"] is True
    assert manifest["official_score_allowed"] is False
    assert manifest["counts"] == {
        "cases": 1,
        "rubrics": 5,
        "scoring_points": 15,
    }

    context_pack = _read_json(compiled_root / "question_context_pack.json")
    assert context_pack["authority_guardrail"]["official_score_allowed"] is False
    assert {point["authority"] for point in context_pack["scoring_points"]} == {"training_org_analysis_yousen"}
    assert all(point["official_score_allowed"] is False for point in context_pack["scoring_points"])

    point_index = _read_json(compiled_root / "scoring_point_index.json")
    assert "sp_2021_1_q01_01" in point_index["points_by_id"]
    assert point_index["points_by_id"]["sp_2021_1_q01_01"]["point_score"] == 1.0


def test_generated_markdown_has_required_okf_like_frontmatter(tmp_path):
    builder = _load_builder()
    source_root, _compiled_root, _result = _build_tmp_pilot(builder, tmp_path)

    case_doc = (source_root / "cases" / "case_2021_1.md").read_text(encoding="utf-8")
    point_doc = (source_root / "scoring_points" / "sp_2021_1_q01_01.md").read_text(encoding="utf-8")
    for text in [case_doc, point_doc]:
        assert text.startswith("---\n")
        assert "\ntype: " in text
        assert "\ncanonical_id: " in text
        assert "\nauthority: " in text
        assert "\nnot_official: true\n" in text
        assert "\nofficial_score_allowed: false\n" in text
        assert "\nsource_ref: " in text


def test_build_pilot_rejects_official_source_flag(tmp_path):
    builder = _load_builder()
    bad_source = tmp_path / "bad_case_rubric.json"
    original = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    original["_meta"]["NOT_official"] = False
    bad_source.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    source_root, compiled_root = _pilot_roots(tmp_path)

    try:
        builder.build_pilot(
            source_path=bad_source,
            source_root=source_root,
            compiled_root=compiled_root,
        )
    except ValueError as exc:
        assert "NOT_official=true" in str(exc)
    else:
        raise AssertionError("expected official source flag to be rejected")


def test_build_pilot_rejects_unexpected_authority(tmp_path):
    builder = _load_builder()
    bad_source = tmp_path / "bad_authority_case_rubric.json"
    original = _read_json(SOURCE_PATH)
    original["_meta"]["authority"] = "other_authority"
    bad_source.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    source_root, compiled_root = _pilot_roots(tmp_path)

    with pytest.raises(ValueError, match="unexpected rubric authority"):
        builder.build_pilot(
            source_path=bad_source,
            source_root=source_root,
            compiled_root=compiled_root,
        )


def test_build_pilot_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            source_root=REPO_ROOT,
            compiled_root=tmp_path / "extractions" / "okf_rubric_pilot_v0",
        )


def test_build_pilot_rejects_source_path_inside_output_tree(tmp_path):
    builder = _load_builder()
    source_root, compiled_root = _pilot_roots(tmp_path)
    nested_source = source_root / "input.json"
    nested_source.parent.mkdir(parents=True)
    nested_source.write_text(SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="source_path must not be inside generated output"):
        builder.build_pilot(
            source_path=nested_source,
            source_root=source_root,
            compiled_root=compiled_root,
        )


def test_build_pilot_rejects_context_source_inside_output_tree(tmp_path):
    builder = _load_builder()
    source_root, compiled_root = _pilot_roots(tmp_path)
    nested_context = source_root / "context.json"
    nested_context.parent.mkdir(parents=True)
    nested_context.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="input sources must not be inside generated output"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            context_path=nested_context,
            source_root=source_root,
            compiled_root=compiled_root,
        )


def test_build_pilot_rejects_rubric_jsonl_source_inside_output_tree(tmp_path):
    builder = _load_builder()
    source_root, compiled_root = _pilot_roots(tmp_path)
    nested_jsonl = compiled_root / "rubric.jsonl"
    nested_jsonl.parent.mkdir(parents=True)
    nested_jsonl.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="input sources must not be inside generated output"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            rubric_jsonl_path=nested_jsonl,
            source_root=source_root,
            compiled_root=compiled_root,
        )


def test_build_pilot_rejects_overlapping_output_roots(tmp_path):
    builder = _load_builder()
    source_root, _compiled_root = _pilot_roots(tmp_path)

    with pytest.raises(ValueError, match="output roots must not overlap"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            source_root=source_root,
            compiled_root=source_root / "extractions" / "okf_rubric_pilot_v0",
        )


def test_build_pilot_rejects_non_sentinel_generated_shaped_tree_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    source_root, compiled_root = _pilot_roots(tmp_path)
    rogue_doc = source_root / "cases" / "user_review_note.md"
    rogue_doc.parent.mkdir(parents=True)
    rogue_doc.write_text("must not be deleted\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned generated-shaped tree: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            source_root=source_root,
            compiled_root=compiled_root,
        )
    assert rogue_doc.read_text(encoding="utf-8") == "must not be deleted\n"


def test_build_pilot_rejects_invalid_generated_sentinel_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    source_root, compiled_root = _pilot_roots(tmp_path)
    source_root.mkdir(parents=True)
    (source_root / ".okf_pilot_generated.json").write_text(
        json.dumps({"generated_by": "someone_else", "kind": "generated_review_projection"}),
        encoding="utf-8",
    )

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid sentinel: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid generated sentinel"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            source_root=source_root,
            compiled_root=compiled_root,
        )


def test_build_pilot_rejects_valid_sentinel_with_unexpected_nested_file_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    source_root, compiled_root = _pilot_roots(tmp_path)
    source_root.mkdir(parents=True)
    builder.write_sentinel(source_root, kind="generated_review_projection", generated_at="2026-06-19T00:00:00+08:00")
    rogue_doc = source_root / "cases" / "user_review_note.md"
    rogue_doc.parent.mkdir()
    rogue_doc.write_text("must not be deleted\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for mixed generated tree: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe generated output tree"):
        builder.build_pilot(
            source_path=SOURCE_PATH,
            source_root=source_root,
            compiled_root=compiled_root,
        )
    assert rogue_doc.read_text(encoding="utf-8") == "must not be deleted\n"


def test_build_pilot_repeated_generation_is_byte_identical_with_fixed_timestamp(tmp_path):
    builder = _load_builder()
    source_root, compiled_root, _result = _build_tmp_pilot(builder, tmp_path)
    first = {
        "source": _collect_bytes(source_root),
        "compiled": _collect_bytes(compiled_root),
    }

    _build_tmp_pilot(builder, tmp_path)
    second = {
        "source": _collect_bytes(source_root),
        "compiled": _collect_bytes(compiled_root),
    }

    assert second == first


def test_compiled_outputs_include_machine_non_runtime_guards(tmp_path):
    builder = _load_builder()
    _source_root, compiled_root, _result = _build_tmp_pilot(builder, tmp_path)

    expected_guard = {
        "runtime_consumable": False,
        "installed_runtime_supply": False,
        "canonical_write_allowed": False,
        "learner_truth_write_allowed": False,
        "gbrain_write_allowed": False,
        "production_registry_write_allowed": False,
        "official_score_allowed": False,
    }
    for name in ["manifest", "question_context_pack", "scoring_point_index"]:
        data = _read_json(compiled_root / f"{name}.json")
        guard = data["runtime_guard"]
        for key, value in expected_guard.items():
            assert guard[key] is value
        assert guard["release_stage"] == "source_pilot"


def test_compiled_case_preserves_context_and_case_level_authority(tmp_path):
    builder = _load_builder()
    _source_root, compiled_root, _result = _build_tmp_pilot(builder, tmp_path)

    context_pack = _read_json(compiled_root / "question_context_pack.json")
    case = context_pack["case"]
    assert case["authority"] == "training_org_analysis_yousen"
    assert case["not_official"] is True
    assert case["official_score_allowed"] is False
    assert case["source_ref"] == "case_rubric_canonical.json"
    assert case["question_source"]["source_chunk_id"] == "EXAM_1A431000_P0016_02"
    assert case["question_source"]["page"] == 16
    assert case["question_source"]["json_path"] == "$.chunks[34]"
    assert case["question_source"]["taxonomy"]["node_code"] == "1A431000"
    assert case["rubric_source"]["page"] == 17
    assert case["rubric_source"]["jsonl_line_range"] == "2-16"
    assert case["rubric_source"]["canonical_json_path"] == '$.rubric["2021"]["1"]'
    assert "指出项目劳动用工管理工作中不妥之处" in case["sub_questions"][0]["stem"]
    assert case["visual_context"]["present"] is True
    assert case["visual_context"]["student_facing_leakage_risk"] is True
    assert len(case["hashes"]["question_chunk_sha256"]) == 64


def test_compiled_manifest_cross_references_artifacts_and_ids(tmp_path):
    builder = _load_builder()
    _source_root, compiled_root, _result = _build_tmp_pilot(builder, tmp_path)

    manifest = _read_json(compiled_root / "manifest.json")
    context_pack = _read_json(compiled_root / manifest["artifact_refs"]["question_context_pack"])
    point_index = _read_json(compiled_root / manifest["artifact_refs"]["scoring_point_index"])

    assert manifest["artifact_refs"] == {
        "question_context_pack": "question_context_pack.json",
        "scoring_point_index": "scoring_point_index.json",
    }
    rubric_ids = {rubric["rubric_id"] for rubric in context_pack["rubrics"]}
    point_ids = {point["point_id"] for point in context_pack["scoring_points"]}
    assert set(context_pack["case"]["rubrics"]) == rubric_ids
    assert set(point_index["points_by_id"]) == point_ids
    assert all(ref in point_ids for rubric in context_pack["rubrics"] for ref in rubric["scoring_point_refs"])


def test_compound_scoring_points_expose_partial_credit_metadata(tmp_path):
    builder = _load_builder()
    _source_root, compiled_root, _result = _build_tmp_pilot(builder, tmp_path)

    point_index = _read_json(compiled_root / "scoring_point_index.json")
    q3 = point_index["points_by_id"]["sp_2021_1_q03_01"]
    assert q3["max_per_group"] == 3.0
    assert q3["partial_credit_rule"] == "unknown_from_source"
    assert q3["acceptable_items"] == [
        "聚氯乙烯防水卷材",
        "氯化聚乙烯防水卷材",
        "氯化聚乙烯-橡胶共混防水卷材",
        "三元丁橡胶防水卷材",
    ]
    assert q3["judge_rule"] == "min(Σ命中采分点×point_score, sub_q_total_score) 封顶"
    assert q3["sub_q_total_score"] == 3.0
    assert q3["rubric_page"] == 17
    assert len(q3["source_hash_sha256"]) == 64


def test_compound_scoring_point_markdown_warns_partial_credit_unknown(tmp_path):
    builder = _load_builder()
    source_root, _compiled_root, _result = _build_tmp_pilot(builder, tmp_path)

    doc = (source_root / "scoring_points" / "sp_2021_1_q03_01.md").read_text(encoding="utf-8")
    assert "Partial credit rule: `unknown_from_source`" in doc
    assert "Acceptable items:" in doc
